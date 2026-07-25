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
- [x] Gebe im Fussbereich Auskunft, was die KI gerade macht, um dem Anwender sicherheit zu geben, dass nichts abgestürzt ist. Besonders beim prüfen des Kapitels ist da warten ohne Rückmeldung unangenehm aufgefallen.
- [x] Zeit-Überbrückung mit Benutzer-Unterhaltung (docs/unnützesWissen.csv in DB anlegen und in einem zentralen Overlay anzeigen, während die KI arbeitet). Beginne nach 20 Sekunden damit, wchsle alle 20 Sekunden die Nachricht und schliesse das Overlay, wenn die KI fertig ist.
- [x] Implementiere im Export-Tab auch einen PDF Export. Entwerfe hierfür auch ein entsprechendes PDF-Template, das etwas verspielt ist, wie ein hochwertiges Buch.
- [x] Füge im Speicherort (der Geschichten) die Möglichkeit ein (Checkbox), dass automatisch Unterordner für die Epoche und/oder [Name der Geschichte] angelegt und benutzt werden.
- [x] Lektorieren: Beide Seiten sollen dasselbe Text-Layout haben. Mit Zeilenwechseln, damit man weniger horizontal scrollen muss, aktuell wird das nur rechts umgesetzt.
  - [x] Füge eine Legende in die Kopfzeile ein mit den Farben für Grammatik, Rechtschreibung und Anachronismen. Und warum ist der scrollbar rechts viel breiter?
- [x] Wenn das Kapitel geschrieben ist, könnte man für die anderen Tabs die Infos gleich laden, sodass die Infos gleich da sind, wenn man das Tab wechselt. Das vermeidet auch, dass man versehentlich das flasche Kapitel nochmal lektoriert.
- [x] Epoche sollte auch auf Genre erweitert werden, da das fast fliessend ineinander übergeht.
- [x] Quen3 LLM aus dem Test Kontext im Script nehmen. Sie steht gleichberechtigt neben Hermes3 als Schreiber.
- [x] Den Hauptbildschirm so einrichten, dass niemals gescrollt wird. Notfalls sollen die Container zu scrollen sein.
- [x] Architektenstrand soll zwischengespeichert werden können. Und dann auch fortgesetzt werden können.
- [x] Unnützes Wissen zufällig aus der DB holen und zur Überbrückung anzeigen.
# Bugs
- [x] eventuell funktioniert das fort schreiben der Tabs nicht richtig, ich hatte 2mal Kapitel 3, kein Kapitel 4. Muss nochmal verifiziert werden. 
- [x] Die Speicherort-Logik und der Ordnername mus nochmal verifiziert werden.

# Deployment
- [ ] Implementiere einen User-Zugang mit Accounts. Benutze hierfür die bestehende DB. Hier im Entwickler-/Test-System kann der Login inaktiv sein, um es bequem zu halten. Aktiv ist es nur solange bis es erfolgreich implementiert und getestet ist.
  - [ ] Schlage Lösungen vor, wie ein User NUR seine Projekte sehen kann, falls Geschichten auf dem KI-Server liegen bleiben.
- [ ] Layout und Sicherheitskonzept für Frontend auf meiner Domain (daniel-ertl.de; hole Infos zum Deploy aus dem myReceipes Projekt) und KIs lokal auf meinem Server. Homepage->Router(Ports...)->lokaler Server(sowas wie ein API-Key?)