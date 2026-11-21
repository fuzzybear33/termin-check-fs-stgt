# Termin-Check Führerscheinstelle Stuttgart – Einrichtung

Prüft alle 30 Minuten in der GitHub-Cloud, ob für **„Umtausch alter Führerschein in
EU-Führerschein“** Termine frei sind, und schickt E-Mails. Dein PC muss dafür nicht laufen.

**Mails:** Die ersten 4 Prüfungen schicken immer eine Mail (Test). Danach gibt es eine Mail
sofort, wenn Termine da sind, sowie 2 Status-Mails pro Tag (ab 8 Uhr und ab 18 Uhr). Bei
technischen Fehlern kommt höchstens alle 6 Stunden eine Fehler-Mail.

## 1. Repository anlegen
1. Auf https://github.com/new ein neues Repository anlegen, z. B. `termin-check`.
   **Public** wählen: Dann ist GitHub Actions unbegrenzt kostenlos. Bei privaten
   Repositories reichen die 2.000 Freiminuten/Monat für 48 Läufe am Tag nicht aus.
   Passwörter liegen als Secrets trotzdem nicht offen.
2. Auf der leeren Repo-Seite **„uploading an existing file“** klicken und **alle Dateien
   und Ordner** aus diesem Ordner hineinziehen, auch den Ordner `.github`.
   Danach „Commit changes“.
   (Tipp: Den Ordner `.github` blendet der Windows-Explorer evtl. nicht ein. Falls er fehlt,
   „Add file → Create new file“ wählen, als Namen `.github/workflows/termin-check.yml`
   eintippen und den Inhalt der Datei einfügen.)

## 2. Zugangsdaten als Secrets hinterlegen
Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Name        | Wert                                                                |
|-------------|---------------------------------------------------------------------|
| `SMTP_HOST` | `server54.webgo24.de` (laut DNS dein Mailserver bei webgo)           |
| `SMTP_PORT` | `465`                                                               |
| `SMTP_USER` | Benutzername des Postfachs (bei webgo oft die volle E-Mail-Adresse oder ein Name wie `web123p1`; siehe webgo-Kundenmenü) |
| `SMTP_PASS` | Passwort des Postfachs                                              |
| `MAIL_TO`   | `volker@team-goebel.de`                                             |
| `MAIL_FROM` | Absenderadresse, z. B. `volker@team-goebel.de`                      |

Tipp: Am besten ein eigenes Postfach (z. B. `termine@team-goebel.de`) für den Versand anlegen,
damit nicht dein Hauptpasswort in GitHub liegt.

## 3. Schreibrechte für den Workflow
Settings → **Actions → General → Workflow permissions** → „Read and write permissions“ → Save.
(Nötig, damit sich der Workflow in `state.json` merkt, wie viele Mails schon raus sind.)

## 4. Testen
Reiter **Actions** → „Termin-Check Führerscheinstelle“ → **Run workflow**.
Nach ca. 1–2 Minuten sollte die erste Mail („Testlauf 1 von 4“) ankommen.
Danach läuft alles automatisch zu den Minuten :07 und :37 jeder Stunde. GitHub startet
geplante Läufe manchmal ein paar Minuten später.

## Hinweise
* Schlägt ein Lauf fehl (z. B. falsches SMTP-Passwort), schickt GitHub dir selbst eine
  Benachrichtigung an die Adresse deines GitHub-Kontos.
* Screenshots jeder Prüfung findest du im jeweiligen Lauf unter „Artifacts“.
* **Stoppen:** Actions → Workflow → „…“ → **Disable workflow**.
* Die 4 Testmails erneut auslösen: in `state.json` `initial_mails_sent` auf `0` setzen.
