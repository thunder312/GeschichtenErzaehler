# Anwendungsfall: Auf dem Server beginnen, lokal über Nacht fertig schreiben

Kurzfassung zum Nachschlagen: [Quickstart-Nachtlauf.md](Quickstart-Nachtlauf.md).

## Worum geht es?

Der Server (Strato, `https://geschichten.daniel-ertl.de`) ist bequem von
überall erreichbar und hat Rechtschreibprüfung (Hunspell) – seine KI läuft
aber über Athene (CPU) oder den Tunnel zum PC. Der **lokale PC** (RTX 5070 Ti)
schreibt das Kapitel deutlich schneller, kann nach dem Lauf **von selbst
herunterfahren** und hat die KI direkt vor Ort (`PC (lokal)`).

Der Ablauf ist deshalb dreigeteilt:

1. **Server:** Projekt anlegen, Gerüst erarbeiten (Architekt-Interview).
2. **PC:** Projekt per „Abgleich mit Server" holen, Automatikmodus über Nacht
   laufen lassen, PC fährt danach herunter.
3. **PC → Server:** Fertiges Projekt wieder hochladen, am Server prüfen und
   abschließen.

> **Wichtig:** Alle Übertragungen starten **am PC**. Der Server kann den PC
> nicht erreichen (NAT) – deshalb gibt es auf dem Server keinen „Zum PC"-Knopf.

## Voraussetzungen (einmalig)

| Was | Wo / wie prüfen |
|---|---|
| Der Server läuft mit dem Abgleich-Feature (`/api/sync/*`) | Tab **Einstellungen → „Abgleich mit Server" → Verbindung testen** (siehe Schritt 0) liefert „Verbindung steht" |
| Lokale App läuft (Backend :8000, Frontend :5173) | `start-dev.ps1` im Projekt-Root, dann `http://localhost:5173` |
| Ollama auf dem PC läuft, Modelle `mistral-small3.2` (bzw. IQ4_XS-Variante) und `gemma4` vorhanden | `docker exec ollama ollama list`; Details in `pc/README.md` |
| Lokales KI-Ziel `PC (lokal)` (Typ `direct`, `http://127.0.0.1:11434`) | Tab **Einstellungen → KI-Ziele**, „Verbindung testen" |
| Die **Epoche** des Projekts gibt es lokal in der Epochen-Bibliothek | Epochen, die nur auf dem Server existieren, fehlen lokal – siehe „Stolperfallen" |
| Bild-KI-Container (Stable Diffusion) auf dem PC sind gestoppt | sie teilen sich die 16 GB VRAM mit Mistral, sonst rechnet Mistral teils auf der CPU |

## Schritt 0 – Einmalig: Gegenstelle am PC eintragen

Nur beim allerersten Mal (oder nach Passwortwechsel):

1. Lokale App öffnen (`http://localhost:5173`), als Admin anmelden.
2. Tab **Einstellungen** → Karte **🔄 Abgleich mit Server** aufklappen.
3. **Adresse der Gegenstelle:** `https://geschichten.daniel-ertl.de`
4. **Benutzername** und **Passwort** des Server-Logins eintragen.
5. **Speichern**, dann **Verbindung testen**.
   Erwartet: „Verbindung steht – N Projekt(e) auf der Gegenstelle."

Am Server selbst bleibt diese Karte leer.

## Schritt 1 – Am Server: Projekt anlegen und Gerüst erarbeiten

1. `https://geschichten.daniel-ertl.de` öffnen und anmelden.
2. Tab **Projekte** → neue Geschichte anlegen (Titel, **Epoche** wählen).
3. Tab **Architekt / Gerüst**: Interview durchführen und das Gerüst speichern
   (inkl. Kapitelplan). Optional im Tab **Personen-Fundus** Figuren pflegen.
4. **Optional, aber empfohlen:** Kapitel 1 am Server schreiben lassen und
   ansehen, ob Ton und Länge stimmen. Bei Abweichungen jetzt das Gerüst
   nachschärfen – nachts lässt sich nichts mehr korrigieren.

Ergebnis: Das Projekt hat ein Gerüst (und evtl. Kapitel 1), noch nichts ist
lokal vorhanden.

## Schritt 2 – Am PC: Projekt vom Server holen

1. Lokale App öffnen → Tab **Projekte**.
2. Karte **🔄 Abgleich mit Server** aufklappen (sie erscheint nur, wenn
   Schritt 0 erledigt ist). Der Vergleich lädt automatisch; sonst
   **🔃 Neu vergleichen**.
3. In der Zeile des Projekts steht Status **„nur auf dem Server"**.
   Klick auf **⬇ Auf den PC**.
4. Meldung „…: <Nachricht>" abwarten. Die Zeile springt auf
   **„✓ identisch"**, das Projekt erscheint in der lokalen Projektliste.

Kontrolle: Projekt in der lokalen Liste öffnen → Tab **Architekt / Gerüst**
zeigt dasselbe Gerüst wie am Server.

## Schritt 3 – Am PC: Nachtlauf vorbereiten

1. **KI-Ziel wählen:** Im Kopfbereich bei geöffnetem Projekt den Knopf
   **`PC (lokal)`** anklicken. Der Punkt davor muss **grün** sein (rot = Ollama
   läuft nicht).
2. **Bild-KIs stoppen**, falls sie laufen (`docker stop sd-server-dev` o. ä.
   oder über den BildKI-Queue-Dienst, siehe `pc/README.md`).
3. Windows-**Energiesparen/Ruhezustand abschalten** (sonst schläft der PC mitten
   im Lauf ein). Dropbox darf weiterlaufen.
4. Tab **Schreiben** → nach unten zum **Automatikmodus**.
5. Optionen wählen:
   - **„Max. Durchläufe je Kapitel"** (z. B. 3).
   - **🔔 Signalton** – optional, wirkt nur, wenn der Browser-Tab offen bleibt.
   - **⏻ Danach PC herunterfahren** – Haken setzen (erscheint nur an der
     lokalen Instanz; gilt nur für den nächsten Start).
6. Alternativ für ein bereits angefangenes Projekt: Block
   **„➕ Weitere Kapitel schreiben"** → **Vorschau laden** prüfen →
   **„Kapitel N schreiben"**.
7. Automatikmodus **starten**. Falls die Frage „Bild-KI-Container
   herunterfahren?" erscheint: **Herunterfahren & schreiben** (oder ohne
   Herunterfahren fortfahren, wenn keine Bild-KI läuft).
8. Im Statusfenster kurz zuschauen: Phase „Kapitel schreiben", der Autortext
   erscheint live. Erst dann den Raum verlassen.

> **Nicht schließen:** Das Backend-Fenster (uvicorn) und Docker/Ollama müssen
> die ganze Nacht laufen. Den Browser-Tab darfst du schließen.

## Schritt 4 – Über Nacht (nichts zu tun)

- Der Lauf schreibt alle fehlenden Kapitel und wendet eindeutige
  Prüfer-Korrekturen an.
- Alle drei Kapitel hält er an, wenn ungelöste Funde auflaufen
  („Zwischenstopp"); bei Verbindungsabbrüchen versucht er 3× nach 5/10/15 min.
  In beiden Fällen bleibt der PC **an** und das Herunterfahren **entfällt** –
  der Lauf ist nicht fertig.
- Nach erfolgreichem Ende: **60 Sekunden Vorlauf**, dann fährt der PC herunter.
  (Abbrechbar mit dem roten Button, solange du am PC bist.)

## Schritt 5 – Am nächsten Morgen: zurück zum Server

1. PC einschalten, `start-dev.ps1` ausführen, Ollama/Docker abwarten.
2. Lokale App → Tab **Schreiben**: Status prüfen (alle Kapitel fertig?).
   Falls „angehalten": Funde in **Prüfen & Anwenden** ansehen, dann
   **Fortsetzen**.
3. Tab **Projekte** → **🔄 Abgleich mit Server** → Status des Projekts muss
   **„⬆ PC ist neuer"** sein → **⬆ Zum Server**.
   - Kommt eine Rückfrage „Neuere Version überschreiben?" (Status
     „⚠ beide geändert"), hast du am Server zwischenzeitlich etwas geändert.
     **Nicht blind bestätigen** – siehe Stolperfallen. Eine Sicherung
     entsteht automatisch in `_sync_sicherung/`.
4. Am **Server** anmelden → Projekt öffnen: alle Kapitel müssen da sein.
5. Am Server: **Prüfen & Anwenden** und **Rechtschreibung** (Hunspell gibt es
   nur dort) durchgehen, dann **Prüfung abschließen**. Im Dialog „Projekt
   bereinigen?" ist ein Haken „Kopie auf dem PC beim nächsten Abgleich
   aufräumen" – setzen, wenn die lokale Kopie weg darf.
6. Tab **Stand & Export**: Stand erzeugen, PDF exportieren, ggf. Titelbild.
7. Am PC im Abgleich **🧹 Lokal entfernen** (geht nur, wenn der Server schon
   alle lokalen Änderungen hat; exportierte PDFs bleiben).

## Testszenario mit Abnahmekriterien

Zum Durchspielen vor dem ersten echten Nachtlauf – am besten mit einem
**kurzen Testprojekt** (Gerüst mit 2 Kapiteln, z. B. Epoche Regency).

| # | Aktion | Erwartetes Ergebnis |
|---|---|---|
| T1 | Schritt 0: Gegenstelle eintragen, „Verbindung testen" | „Verbindung steht – N Projekt(e)…" |
| T2 | Am Server Testprojekt „Nachtlauf-Test" mit 2-Kapitel-Gerüst anlegen | Projekt in der Serverliste, Gerüst gespeichert |
| T3 | Am PC Abgleich öffnen | Zeile „Nachtlauf-Test": **nur auf dem Server**, Kapitel 0 |
| T4 | **⬇ Auf den PC** | Meldung ohne Fehler; Status **✓ identisch**; Projekt in lokaler Projektliste; Gerüst identisch |
| T5 | KI-Ziel `PC (lokal)` wählen | Punkt grün |
| T6 | Automatikmodus starten, **⏻ Danach PC herunterfahren** zum Test **nicht** setzen | Phase wechselt zu „Kapitel schreiben", Live-Text erscheint, Kapitel 1 und 2 werden geschrieben; Lauf endet „abgeschlossen" |
| T7 | Zeit messen: Kapitel 1 mit `PC (lokal)` vs. früher am Server | PC deutlich schneller (Richtwert Mistral IQ4_XS ≈ 29 Tok/s) |
| T8 | Abgleich neu vergleichen | Status **⬆ PC ist neuer**, Lokal 2 Kap., Server 0 Kap. |
| T9 | **⬆ Zum Server** | Meldung ohne Fehler; Status **✓ identisch** |
| T10 | Am Server Projekt öffnen | Beide Kapitel vorhanden, lesbar; Rechtschreibung-Tab funktioniert |
| T11 | Am Server **Prüfung abschließen**, Haken „Kopie auf dem PC aufräumen" | Am PC zeigt der Abgleich „🧹 Prüfung am Server abgeschlossen – lokale Kopie kann weg" |
| T12 | Am PC **🧹 Lokal entfernen** | Lokaler Projektordner weg, PDFs daneben bleiben, Server-Projekt unberührt |
| T13 | **Konflikt-Test:** T2–T4 wiederholen, dann je ein Kapitel am Server **und** am PC ändern, Abgleich | Status **⚠ beide geändert**; „Zum Server"/„Auf den PC" verlangt Bestätigung; Sicherung entsteht |
| T14 | **Herunterfahren (einmalig, bewusst)**: Test mit einem 1-Kapitel-Projekt und gesetztem Haken | Nach Lauf-Ende Hinweis „PC fährt in N s herunter", Abbrechen-Button wirkt. *(Echter Shutdown wurde bisher nicht getestet – nur mit Abbruch üben, solange nichts Ungespeichertes offen ist.)* |

Bestanden, wenn T1–T12 ohne Fehler laufen und nach T9 Server und PC identisch
sind.

## Stolperfallen

- **Nie beidseitig arbeiten:** Sobald das Projekt am PC liegt, am Server nichts
  daran ändern, bis es zurück ist. Sonst „⚠ beide geändert" – ein Merge ist
  **nicht** vorgesehen, Überschreiben verliert eine Seite (Sicherung in
  `_sync_sicherung/` hilft nur zum Nachholen von Hand).
- **Nicht übertragen werden:** `.mp3` (Hörbücher), `cover_log`
  (Titelbild-Verlauf), `.bak`, Dropbox-/Windows-Müll. `fundus.md` und `orte.md`
  (je Benutzer) werden **nicht** abgeglichen; die Personas des Projekts
  gehören dagegen zum Projekt und werden mitkopiert.
- **Epoche fehlt lokal:** Gibt es die Epoche des Serverprojekts nicht in der
  lokalen Epochen-Bibliothek, fehlen Verbotsliste/Einleitungssatz.
  Aktuell sind Harry-Potter-Universum, Star-Trek und Burg Schreckenstein
  übernommen; bei neuen Epochen vorher von Prod holen.
- **„unsicher" im ersten Abgleich:** Ein von Hand kopiertes Projekt hat keine
  gemeinsame Basis, der Vergleich schätzt nur nach Änderungszeit
  („noch nie abgeglichen"). Nach dem ersten Abgleich nicht mehr.
- **Modelle je KI-Ziel:** Die Persona-Zuordnung (Autor/Prüfer-Modell) gilt je
  KI-Ziel. Für `PC (lokal)` muss der Autor auf dem gewünschten Modell stehen
  (derzeit Mistral IQ4_XS). Prompt-Änderungen im Repo erreichen bestehende
  Projekte nicht – Personas sind pro Projekt kopiert.
- **GPU geteilt:** Läuft über Nacht eine Bild-KI mit, wird der Lauf langsam.
- **Ruhezustand/Windows-Update:** Vorher abschalten bzw. Aktive Zeiten setzen.
- **Neustart mitten im Lauf:** Kein Verlust – „Fortsetzen" setzt exakt dort
  fort, nicht bei Kapitel 1.
