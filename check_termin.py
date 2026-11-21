"""Prüft die Online-Terminvergabe der Führerscheinstelle Stuttgart
("Umtausch alter Führerschein in EU-Führerschein") und verschickt E-Mails.

Mail-Logik:
  * Die ersten INITIAL_MAILS Prüfungen: immer eine Mail (Funktionstest).
  * Danach: sofort eine Mail, wenn Termine verfügbar (oder unklar) sind,
    sonst zwei Status-Mails pro Tag (ab 08:00 und ab 18:00 Uhr deutscher Zeit).
  * Bei technischen Fehlern höchstens alle 6 Stunden eine Fehler-Mail.

Konfiguration über Umgebungsvariablen (GitHub-Secrets):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_TO, optional MAIL_FROM.
  DRY_RUN=1 gibt Mails nur aus, statt sie zu senden.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import smtplib
import ssl
import sys
import time
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

URL = "https://stuttgart.konsentas.de/form/3/?signup_new=1"
CATEGORY = "Führerscheinstelle"
SERVICE = "Umtausch alter Führerschein in EU-Führerschein"

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "state.json"
DEBUG_DIR = HERE / "debug"
TZ = ZoneInfo("Europe/Berlin")

INITIAL_MAILS = 4
STATUS_HOURS = (8, 18)          # Status-Mails ab 08:00 und ab 18:00 Uhr
ERROR_MAIL_INTERVAL_H = 6

NONE, AVAILABLE, UNKNOWN, ERROR = "KEINE", "VERFUEGBAR", "UNKLAR", "FEHLER"
NO_SLOTS_TEXT = "Keine verfügbaren Termine"
TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):[0-5]\d\b")


# --------------------------------------------------------------------------- Prüfung
def check_site() -> tuple[str, str]:
    """Gibt (Ergebnis, Detailtext) zurück."""
    DEBUG_DIR.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(locale="de-DE", viewport={"width": 1400, "height": 1000})
        try:
            page.goto(URL, wait_until="networkidle", timeout=60_000)

            # 1. Kategorie "Führerscheinstelle" aufklappen (die App lädt verzögert)
            toggle = page.locator(
                f'li.department-card[data-department-name="{CATEGORY}"] '
                'a[data-bs-toggle="collapse"]').first
            toggle.wait_for(state="visible", timeout=60_000)
            if toggle.get_attribute("aria-expanded") != "true":
                toggle.click()
            page.wait_for_timeout(1500)

            # 2. Checkbox der Leistung anhaken (Label ist das klickbare Element)
            label = page.locator(f'label[data-process-name="{SERVICE}"]').first
            label.wait_for(state="attached", timeout=15_000)
            box_id = label.get_attribute("for")
            box = page.locator(f"#{box_id}")
            if not box.is_checked():
                label.evaluate("el => el.click()")
                page.wait_for_timeout(800)
            if not box.is_checked():
                raise RuntimeError("Checkbox für die Leistung ließ sich nicht anhaken.")

            # 3. Weiter
            page.locator(".btn_formcontroll_next").first.click()

            # 4. Ergebnis abwarten
            result, detail = UNKNOWN, ""
            deadline = time.time() + 40
            while time.time() < deadline:
                page.wait_for_timeout(1500)
                text = page.inner_text("body")
                if NO_SLOTS_TEXT in text:
                    result, detail = NONE, "Meldung „Keine verfügbaren Termine!“ wird angezeigt."
                    break
                times = sorted(set(m.group(0) for m in TIME_RE.finditer(text)))
                if "Terminauswahl" in text and times:
                    result = AVAILABLE
                    detail = "Gefundene Uhrzeiten (Auszug): " + ", ".join(times[:15])
                    break
            else:
                text = page.inner_text("body")
                detail = ("Keine eindeutige Meldung erkannt. Seitentext (Auszug):\n"
                          + text[:1500])

            page.screenshot(path=str(DEBUG_DIR / "ergebnis.png"), full_page=True)
            (DEBUG_DIR / "ergebnis.txt").write_text(page.inner_text("body"), encoding="utf-8")
            return result, detail
        except Exception as exc:  # noqa: BLE001
            try:
                page.screenshot(path=str(DEBUG_DIR / "fehler.png"), full_page=True)
            except Exception:  # noqa: BLE001
                pass
            return ERROR, f"{type(exc).__name__}: {exc}"
        finally:
            browser.close()


# --------------------------------------------------------------------------- Zustand
def load_state() -> dict:
    default = {"checks": 0, "initial_mails_sent": 0, "last_status_slot": "",
               "last_error_mail": "", "last_result": "", "last_check": ""}
    if STATE_FILE.exists():
        default.update(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    return default


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def status_slot(now: dt.datetime) -> str:
    """Kennung des aktuellen Status-Zeitfensters (z. B. 2026-11-21-18)."""
    morning, evening = STATUS_HOURS
    if now.hour >= evening:
        return f"{now.date()}-{evening:02d}"
    if now.hour >= morning:
        return f"{now.date()}-{morning:02d}"
    return f"{now.date() - dt.timedelta(days=1)}-{evening:02d}"


# --------------------------------------------------------------------------- Mail
def build_mail(result: str, detail: str, now: dt.datetime, reason: str) -> tuple[str, str]:
    stamp = now.strftime("%d.%m.%Y %H:%M")
    steps = (f"So kommst du hin:\n  1. {URL} öffnen\n  2. „{CATEGORY}“ anklicken\n"
             f"  3. „{SERVICE}“ anhaken\n  4. „Weiter“\n")
    if result == AVAILABLE:
        subject = "TERMINE VERFÜGBAR – sofort handeln! (Führerscheinstelle Stuttgart)"
        body = (f"Termine verfügbar, sofort handeln!\n\nGeprüft: {stamp}\n{detail}\n\n"
                f"Link: {URL}\n\n{steps}")
    elif result == UNKNOWN:
        subject = "Termine möglicherweise verfügbar – bitte prüfen (Führerscheinstelle)"
        body = (f"Die Seite zeigt keine „Keine Termine“-Meldung, das Ergebnis ist aber nicht "
                f"eindeutig. Bitte sofort selbst prüfen.\n\nGeprüft: {stamp}\n\nLink: {URL}\n\n"
                f"{steps}\n{detail}")
    elif result == NONE:
        subject = f"Keine Termine verfügbar – {reason} (Führerscheinstelle)"
        body = (f"Keine Termine verfügbar.\n\nGeprüft: {stamp}\n{detail}\n\nLink: {URL}\n\n"
                f"Die Prüfung läuft weiter alle 30 Minuten.")
    else:
        subject = "Termin-Prüfung fehlgeschlagen (Führerscheinstelle)"
        body = (f"Die automatische Prüfung ist fehlgeschlagen. Möglicherweise wurde die Seite "
                f"geändert.\n\nZeit: {stamp}\nFehler: {detail}\n\nLink: {URL}\n\n"
                f"Screenshots liegen im GitHub-Actions-Lauf unter „Artifacts“.")
    return subject, body


def send_mail(subject: str, body: str) -> None:
    if os.environ.get("DRY_RUN") == "1":
        print(f"--- DRY RUN: Mail ---\nBetreff: {subject}\n\n{body}\n--------------------")
        return
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT") or 465)
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    to = os.environ["MAIL_TO"]
    sender = os.environ.get("MAIL_FROM") or user

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(body)

    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
            s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls(context=ctx)
            s.login(user, password)
            s.send_message(msg)
    print(f"Mail gesendet: {subject}")


# --------------------------------------------------------------------------- Ablauf
def main() -> int:
    now = dt.datetime.now(TZ)
    state = load_state()
    result, detail = check_site()
    print(f"[{now:%Y-%m-%d %H:%M}] Ergebnis: {result} – {detail}")

    reason = ""
    if state["initial_mails_sent"] < INITIAL_MAILS:
        reason = f"Testlauf {state['initial_mails_sent'] + 1} von {INITIAL_MAILS}"
    elif result in (AVAILABLE, UNKNOWN):
        reason = "Treffer"
    elif result == ERROR:
        last = state.get("last_error_mail")
        if not last or now - dt.datetime.fromisoformat(last) >= dt.timedelta(hours=ERROR_MAIL_INTERVAL_H):
            reason = "Fehler"
    elif status_slot(now) != state["last_status_slot"]:
        reason = "Statusmeldung"

    state["checks"] += 1
    state["last_result"] = result
    state["last_check"] = now.isoformat(timespec="seconds")

    exit_code = 0
    if reason:
        subject, body = build_mail(result, detail, now, reason)
        try:
            send_mail(subject, body)
            if reason.startswith("Testlauf"):
                state["initial_mails_sent"] += 1
            if result == ERROR:
                state["last_error_mail"] = now.isoformat(timespec="seconds")
            state["last_status_slot"] = status_slot(now)
        except Exception as exc:  # noqa: BLE001
            print(f"Mailversand fehlgeschlagen: {type(exc).__name__}: {exc}", file=sys.stderr)
            exit_code = 1
    else:
        print("Keine Mail nötig.")

    save_state(state)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
