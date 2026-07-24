# Installer
- [ ] komplett mit Docker-compose-files die im installer modifiziert werden können.
# Features
- [x] Architekten Interview
  - [x] feste Antworten (a, b, c) sollen per Butten gewählt werden können.
  - [x] das Architekten-Interview für spätere Referenz im Projekt ablegen.
- [x] Epochen-Erstellung (Interview)
- [x] Nicht-Netzwerk KI-Ziele (lokal und/oder Windows)
- [x] Persona bearbeiten
- [x] Verbotsliste bearbeiten
- [x] lokaler Speicherort für Geschichte definierbar
- [x] KI-Ziele mit Favorit-Haken (genau 1 Favorit möglich) erweitern. -> Wenn gesetzt, immer im Dropdown im Kopfbereich vorausgewählt und NICHT mehr "Lokal / Standard-Ollama".
- [ ] integriere eine Readme Datei über einen Button im Kopfbereich. Inhalt vgl. Bedienungsanleitung.md unter /docs . Öffne schön formatiert in einem neuen Browser-Tab
- [ ] Hilfe-System für Anwender (schreibe ein Hilfefile, dass 1. den Ablauf einer neuen Geschichte erklärt und 2. mögliche Fehler z.B.: Asynchronität behandelt den Umgang damit. Binde einen Button in die Kopfzeile ein, mit dem man den Text in einem eigenen Browser-Tab öffnen kann. Natürlich schön formatiert.)
- [ ] KI-Fehler-Logging (Schreibe ein Protokoll, was die KI am Backend macht, auch Fehler. Speichere das Protokoll zu Geschichte dazu. Wenn Teile der Geschichte neu geschrieben werden, ergänze das Protokoll)
- [ ] Gebe im Fussbereich Auskunft, was die KI gerade macht, um dem Anwender sicherheit zu geben, dass nichts abgestürzt ist. Besonders beim prüfen des Kapitels ist da warten ohne Rückmeldung unangenehm aufgefallen.
- [ ] Zeit-Überbrückung mit Benutzer-Unterhaltung (docs/unnützesWissen.csv in DB anlegen und anzeigen, während die KI arbeitet).
- [ ] Implementiere im Export-Tab auch einen PDF Export. Entwerfe hierfür auch ein entsprechendes PDF-Template, das etwas verspielt ist, wie ein hochwertiges Buch.
- [ ] Füge im Speicherort (der Geschichten) die Möglichkeit ein (Checkbox), dass automatisch Unterordner für die Epoche und/oder [Name der Geschichte] angelegt werden.
- [ ] Lektorieren: Beide Seiten sollen dasselbe Text-Layout haben. Mit Zeilenwechseln, damit man weniger scrollen muss, aktuell wird das nur rechts umgesetzt.
  - [ ] Füge eine Legende in die Kopfzeile ein mit den Farben für Grammatik, Rechtschreibung und Anachronismen.
# Bugs

# Deployment
- [ ] Implementiere einen User-Zugang mit Accounts. Benutze hierfür die bestehende DB. Hier im Entwickler-/Test-System kann der Login inaktiv sein, um es bequem zu halten. Aktiv ist es nur solange bis es erfolgreich implementiert und getestet ist.
  - [ ] Schlage Lösungen vor, wie ein User NUR seine Projekte sehen kann, falls Geschichten auf dem KI-Server liegen bleiben.
- [ ] Layout und Sicherheitskonzept für Frontend auf meiner Domain (daniel-ertl.de; hole Infos zum Deploy aus dem myReceipes Projekt) und KIs lokal auf meinem Server. Homepage->Router(Ports...)->lokaler Server(sowas wie ein API-Key?)