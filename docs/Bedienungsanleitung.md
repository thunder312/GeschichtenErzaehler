🇬🇧 [English version](Bedienungsanleitung.en.md)

# Bedienungsanleitung: novelle.py

Automatisierte Fünf-Rollen-Pipeline für KI-geschriebene Kurzgeschichten und
Novellen mit lokalen Ollama-Modellen. Diese Anleitung richtet sich an die
tägliche Bedienung über die Kommandozeile.

---

## Merkzettel: der Ablauf in Kurzform

| Schritt | Befehl |
|---|---|
| Neue Geschichte anlegen | `./novelle.py neu <Titel>` |
| Gerüst erarbeiten (einmal pro Geschichte) | `./novelle.py architekt` |
| **— pro Kapitel —** | |
| Kapitel schreiben, automatisch prüfen lassen | `./novelle.py schreiben <n>` |
| Funde durchlesen | `cat projekt/befunde_<n>.md` |
| Sichere Anachronismus-Korrekturen übernehmen | `./novelle.py anwenden <n>` |
| Rest der Funde, eigener Eindruck | *(von Hand nachsehen)* |
| Grammatik/Rechtschreibung glätten | `./novelle.py lektorieren <n>` |
| Unbekannte Wörter einzeln durchgehen | `./novelle.py rechtschreibung <n>` |
| **Zustand festhalten – immer zuletzt** | `./novelle.py stand <n>` |
| **— am Schluss —** | |
| Endkontrolle über den ganzen Text | `./novelle.py gesamt` |
| Zwischenstand ziehen, ohne fertig zu sein | `./novelle.py zusammenfassen` bzw. `zusammenfassen 1 3` |

> **Alternativer Start:** Statt `neu` (legt einen neuen Ordner an) kann auch
> `./novelle.py init` verwendet werden, um den **aktuellen** Ordner zu
> befüllen – beide fragen dabei nach der gewünschten Epoche.
>
> **Warum `stand` immer zuletzt?** Der Chronist soll die endgültige Fassung
> zusammenfassen, nicht eine mit noch offenen Fehlern. Beim letzten laut
> Gerüst geplanten Kapitel fügt `stand` außerdem automatisch alles zu
> `projekt/gesamt.md` zusammen – `gesamt` danach ist nur noch die optionale
> Feinkontrolle über den kompletten Text.

Details zu jedem einzelnen Befehl: Abschnitt 4. Details zum automatischen
Zusammenfügen: Abschnitt 6.

---

## 1. Was das Skript macht

`novelle.py` steuert mehrere spezialisierte KI-Rollen, die nacheinander an
einer Geschichte arbeiten, statt alles einem einzigen Modell zu überlassen:

| Rolle | Aufgabe |
|---|---|
| **Architekt** | Interviewt dich und erstellt das Story-Gerüst (Figuren, Konflikt, Kapitelplan) |
| **Autor** | Schreibt die eigentlichen Kapitel, ein Kapitel pro Aufruf |
| **Anachronismus-Prüfer** | Findet historische Fehler bzw. (bei erfundenen Welten) Markenrechts-Nähe |
| **Kontinuitäts-Prüfer** | Findet Widersprüche zwischen Kapiteln |
| **Chronist** | Fasst nach jedem Kapitel den aktuellen Stand zusammen (Figuren, offene Fäden) |
| **Lektor** | Korrigiert Grammatik/Rechtschreibung automatisch |
| **Anachronismus-Korrektor** | Arbeitet nur die sichersten Prüfer-Funde automatisch ein |

Jede Rolle läuft mit eigenem Modell und eigenen Parametern (Temperatur,
Kontextlänge etc.), abgestimmt auf ihre jeweilige Aufgabe.

---

## 2. Ordnerstruktur

```
Novellen-Setup/
├── novelle.py              ← das Skript (nur EINE echte Datei)
├── personas/                ← epochenlose Rollen, gelten für jedes Setting
│   ├── chronist.txt
│   ├── pruefer_kontinuitaet.txt
│   ├── lektor.txt
│   └── anachronismen_korrektur.txt
├── epochen/                 ← eine Bibliothek pro Zeitalter/Setting
│   ├── Mittelalter/
│   │   ├── architekt.txt
│   │   ├── autor.txt
│   │   ├── pruefer_anachronismus.txt
│   │   └── verbotsliste.md
│   ├── Regency/    (gleiche vier Dateien)
│   └── Zukunft/    (gleiche vier Dateien)
│
└── Meine-Geschichte/         ← ein Projektordner, mit `neu` angelegt
    ├── novelle.py             ← Verknüpfung (Symlink) auf das zentrale Skript
    ├── personas/               ← Kopie der 7 Personas fürs jeweilige Setting
    └── projekt/
        ├── geruest.md            ← Story-Gerüst
        ├── stand_00.md, stand_01.md, ...
        ├── kapitel_01.md, kapitel_02.md, ...
        ├── befunde_01.md, ...
        └── verbotsliste.md
```

**Wichtig:** Jeder Projektordner ist nach dem Anlegen für sich lauffähig.
Änderungen an `epochen/` oder den geteilten `personas/` wirken sich nur auf
**neu** angelegte Projekte aus, nicht rückwirkend auf bestehende.

---

## 3. Erste Schritte

```bash
cd Novellen-Setup
./novelle.py neu Der Markt von Rothenfeld
```

Der Titel darf Leerzeichen und Umlaute enthalten; daraus wird automatisch ein
dateisystem-tauglicher Ordnername (`Der-Markt-von-Rothenfeld`).

Das Skript fragt dann nach dem Setting:

```
Welche Epoche/welches Setting soll verwendet werden?
    1) Mittelalter
    2) Regency
    3) Zukunft
```

Danach:

```bash
cd Der-Markt-von-Rothenfeld
./novelle.py modelle       # prüfen, ob die benötigten Ollama-Modelle da sind
./novelle.py architekt     # Gerüst erarbeiten
```

---

## 4. Befehlsübersicht

### Projekt anlegen

| Befehl | Wirkung |
|---|---|
| `./novelle.py neu <Titel>` | Neuen, eigenständigen Projektordner anlegen (fragt nach Epoche) |
| `./novelle.py init` | Wie `neu`, aber befüllt den **aktuellen** Ordner statt einen neuen anzulegen |
| `./novelle.py epoche-erstellen` (Alias `neueepoche`) | Reines Frageformular (kein LLM) zum Anlegen eines **neuen Settings** unter `epochen/` |

### Schreiben

| Befehl | Wirkung |
|---|---|
| `./novelle.py architekt` | Interaktives Gespräch, erzeugt `projekt/geruest.md` automatisch. Fragt inzwischen auch nach dem Autor-Modell und ob automatische Fortsetzung erlaubt sein soll (siehe Abschnitte 8 und 9), schlägt am Ende drei Titel-Optionen vor und benennt den Projektordner automatisch nach dem gewählten Titel um |
| `./novelle.py schreiben <n>` | Kapitel n schreiben, danach automatisch beide Prüfer laufen lassen. Prüft vorher automatisch, ob `stand <n-1>` existiert, und holt ihn bei Bedarf selbst nach (siehe Abschnitt 9) |
| `./novelle.py schreiben <n> "..."` | Wie oben, mit einem zusätzlichen freien Hinweis nur für diesen einen Versuch – siehe Abschnitt 11 |
| `./novelle.py testen <n>` | Kapitel n einmal mit Hermes, einmal mit Qwen schreiben lassen – nur zum Vergleich, verändert `kapitel_<n>.md` nicht |
| `./novelle.py stand <n>` | Chronist: Zustand nach dem (korrigierten!) Kapitel n zusammenfassen. Ist n das laut Gerüst **letzte** geplante Kapitel, werden automatisch alle Kapitel zu `projekt/gesamt.md` zusammengefügt – die einzelnen `kapitel_NN.md`-Dateien bleiben dabei unverändert erhalten. |

### Prüfen und korrigieren

| Befehl | Wirkung |
|---|---|
| `./novelle.py pruefen <n>` | Nur die beiden Prüfer erneut laufen lassen |
| `./novelle.py anwenden <n>` | Nur Anachronismus-Funde mit Sicherheit „hoch" **und** konkretem Ersatzvorschlag automatisch einarbeiten |
| `./novelle.py lektorieren <n>` | Grammatik/Rechtschreibung/Sprachregister korrigieren und Kapitel direkt überschreiben |
| `./novelle.py rechtschreibung <n>` | Interaktiv: unbekannte Wörter (hunspell) einzeln mit Satzkontext durchgehen. Enter = behalten, Ersatzwort eintippen = überall im Kapitel ersetzen |

### Abschluss

| Befehl | Wirkung |
|---|---|
| `./novelle.py gesamt` | Endkontrolle: beide Prüfer über den **gesamten** bisherigen Text laufen lassen |
| `./novelle.py export` | Alle Kapitel zu einer Datei `projekt/gesamt.md` zusammenfügen |
| `./novelle.py zusammenfassen` | Wie `export`, aber jederzeit manuell aufrufbar, für Zwischenstände. Mit Bereich (`zusammenfassen 1 3`) nur Kapitel 1–3, in einer eigenen Datei `projekt/zusammen_01-03.md` |
| `./novelle.py modelle` | Zeigt geladene/verfügbare Ollama-Modelle und ob die benötigten vorhanden sind |

---

## 5. Empfohlener Arbeitsablauf pro Kapitel

```
./novelle.py schreiben 3      → schreibt Kapitel 3, prüft automatisch mit
cat projekt/befunde_03.md     → Befunde durchlesen
./novelle.py anwenden 3       → sichere Anachronismus-Korrekturen übernehmen
[von Hand nachbessern, falls nötig]
./novelle.py lektorieren 3    → Grammatik/Rechtschreibung glätten
./novelle.py stand 3          → ERST JETZT den Zustand festhalten
```

**Warum `stand` zuletzt:** Der Chronist soll den *endgültigen* Text
zusammenfassen, nicht eine Zwischenfassung mit noch unkorrigierten Fehlern.

Bei jedem Schritt, der eine Datei überschreibt (`anwenden`, `lektorieren`,
erneutes `schreiben`), wird die alte Fassung automatisch als
`<datei>.<zeitstempel>.bak` gesichert – nichts geht verloren.

---

## 6. Automatisches Zusammenfügen am Ende

Die Zielwortzahlen und die Gesamtzahl der Kapitel werden **nicht** fest
einprogrammiert, sondern bei jedem Aufruf direkt aus dem Kapitelplan in
`geruest.md` ausgelesen (Zeilen wie „Kapitel drei: ... Zielwortzahl: 1.600
Wörter."). Das funktioniert unabhängig davon, ob der Architekt die
Kapitelnummern als Ziffern oder ausgeschrieben formuliert hat.

Sobald du `./novelle.py stand <n>` für das **letzte** laut Gerüst geplante
Kapitel aufrufst, geschieht automatisch Folgendes:

1. Alle vorhandenen `kapitel_NN.md`-Dateien werden zu `projekt/gesamt.md`
   zusammengefügt (in Kapitelreihenfolge, durch Leerzeilen getrennt).
2. Die einzelnen Kapitel-Dateien bleiben **unverändert erhalten** – falls
   später doch noch etwas nachbearbeitet werden muss, gehen keine
   Zwischenstände verloren.

Konnte die Kapitelanzahl aus dem Gerüst nicht zuverlässig erkannt werden
(z. B. weil das Gerüst noch nicht ausgefüllt ist oder sehr frei formuliert
wurde), unterbleibt die automatische Zusammenführung stillschweigend – du
kannst sie jederzeit manuell nachholen:

```bash
./novelle.py export              # alle vorhandenen Kapitel
./novelle.py zusammenfassen      # dasselbe, jederzeit aufrufbar
./novelle.py zusammenfassen 1 3  # nur Kapitel 1 bis 3, als Zwischenstand
```

Die Titel- und Untertitelseite („Eine Geschichte aus dem Regency im Jahre
1815") wird nicht erst beim Zusammenfügen erzeugt, sondern steht bereits am
Anfang von `kapitel_01.md` selbst – sie erscheint also automatisch in jeder
zusammengefügten Datei, die Kapitel 1 einschließt.

## 7. Das Story-Gerüst (`geruest.md`)

Wird vom Architekten automatisch erzeugt und gespeichert. Enthält unter
anderem:

- **Jahr/Zeitangabe** – muss wörtlich mit „Jahr" davorstehen (z. B. „Jahr:
  1815" oder „Jahr 214 der Konkordanz-Zeitrechnung"), sonst finden die
  Prüfer sie nicht automatisch.
- **Jugendschutz-Stufe** – `Voll`, `Angedeutet` oder `Jugendfrei`. Steuert,
  wie explizit der Autor bei jedem Kapitel schreiben darf. Fehlt die Angabe
  (ältere Projekte), gilt automatisch „Voll".
- **Autor-Modell** – `Hermes3` oder `Qwen3`. Legt fest, welches installierte
  Modell die Geschichte tatsächlich schreibt. Fehlt die Angabe, gilt
  automatisch Hermes3 (siehe Abschnitt 9a).
- **Automatische Fortsetzung** – `Ein` oder `Aus`. Steuert, ob ein zu kurzes
  Kapitel automatisch weitergeschrieben wird. Fehlt die Angabe, gilt
  automatisch **Aus** (siehe Abschnitt 9b).
- **Kapitelplan** – Ziel-Ereignis und Zielwortzahl je Kapitel.

Wenn du das Gerüst nachträglich von Hand änderst, wirkt sich das ab dem
nächsten `schreiben`-Aufruf aus.

---

## 8. Die Jugendschutz-Stufe

Bei Frage 2 im Architekten-Interview:

| Stufe | Bedeutung |
|---|---|
| **Voll** | Explizite Szenen wie in der Autor-Persona beschrieben |
| **Angedeutet** | Nähe, Kuss, Andeutung – Szene wird vor dem eigentlichen Akt per Szenenwechsel beendet |
| **Jugendfrei** | Keine körperliche Intimität über Handhalten/Umarmung/einen keuschen Kuss hinaus |

Nach jedem `schreiben` prüft das Skript automatisch, ob trotz „Angedeutet"
oder „Jugendfrei" doch eindeutig explizites Vokabular auftaucht, und warnt
dich, falls ja. Das ersetzt nicht das eigene Gegenlesen, ist aber ein
schneller erster Hinweis.

---

## 9. Automatische Sicherheitsnetze

Das Skript verlässt sich nicht blind auf das Sprachmodell. Folgende Prüfungen
laufen automatisch mit, nach jedem `schreiben`:

- **Ausweichformulierungen** – erkennt vage Umschreibungen statt ausgeschriebener Szenen
- **Sprachdrift** – erkennt, wenn der Text unerwartet ins Englische kippt
- **Explizitheits-Check** – siehe Abschnitt 8
- **Rechtschreibprüfung (hunspell)** – prüft nach `schreiben` und `lektorieren` gegen
  ein echtes deutsches Wörterbuch, ob erfundene oder falsch geschriebene Wörter
  auftauchen (z. B. „Schmettelving" statt „Schmetterling"). Das ergänzt die
  anderen Checks um eine andere Fehlerart: Ein Sprachmodell prüft, ob ein Wort
  grammatisch plausibel wirkt, nicht ob es tatsächlich existiert – ein
  erfundenes, aber grammatisch passendes Wort fällt ihm oft nicht auf.
  Voraussetzung: `apt-get install hunspell hunspell-de-de`. Fehlt eines von
  beiden, wird die Prüfung einmalig übersprungen (mit Hinweis), ohne den
  restlichen Ablauf zu stören. Eigennamen und seltene Fachbegriffe tauchen
  zwangsläufig mit in der Liste auf – kein Fehler, einfach kurz durchsehen.
  Für die bequeme, interaktive Durchsicht siehe `./novelle.py rechtschreibung <n>`.
- **Kürzungs-Wächter** – bei `anwenden` und `lektorieren`: fällt die korrigierte Fassung deutlich kürzer aus als das Original, wird sie **nicht** automatisch übernommen, sondern nur angezeigt
- **Erzählperspektive-Check** – schreibt das Gerüst „Dritte Person" vor, aber
  taucht außerhalb wörtlicher Rede eindeutige Ich-Perspektive auf („meine
  Hand", „sagte ich"), wird gewarnt. Wörtliche Rede in Anführungszeichen darf
  natürlich „ich" enthalten – das ist normale direkte Rede, kein Fehler.
- **Anredeform-Check** – tauchen innerhalb desselben Kapitels sowohl
  förmliche Anrede (Sie/Ihnen) als auch informelle (du/dich/dir/dein) in
  wörtlicher Rede auf, wird gewarnt. Ein unbegründeter Wechsel mitten in
  einem Gespräch ist meist ein Ausrutscher, kein bewusstes Stilmittel.
- **Kapitel-Neustart-Erkennung** – taucht die Kapitelüberschrift ein zweites
  Mal im selben Kapiteltext auf, wird alles ab der zweiten Überschrift
  automatisch abgeschnitten. Kommt vor allem vor, wenn eine automatische
  Fortsetzung (siehe 9b) statt eines echten Anschlusses einen kompletten,
  oft widersprüchlichen zweiten Durchlauf des Kapitels erzeugt.
- **Vorzeitiges-Kapitelende-Erkennung** – erklärt sich der Text mitten drin
  selbst für beendet (z. B. „Das Kapitel endete damit, dass…"), schreibt
  danach aber noch substanziell weiter, wird alles ab dieser Stelle
  automatisch abgeschnitten. Meist eine ungeplante, neue Szene nach einer
  automatischen Fortsetzung.
- **Stand-Sicherstellung** – bevor Kapitel n geschrieben wird, prüft das
  Skript, ob `stand_(n-1).md` existiert. Fehlt sie, aber Kapitel n-1 wurde
  bereits geschrieben, wird `stand n-1` automatisch nachgeholt (vermutlich
  wurde es schlicht vergessen). Betrifft nicht Kapitel 1 – ein fehlendes
  `stand_00.md` ist dort der korrekte Normalfall.

### 9a. Autor-Modell wählen (Hermes3/Qwen3)

Frage 3 im Architekten-Interview legt fest, welches installierte Ollama-Modell
die Geschichte tatsächlich schreibt:

```
Autor-Modell: Hermes3
Autor-Modell: Qwen3
```

Gilt für **jeden** Schreib- und Fortsetzungsaufruf dieser Geschichte. Fehlt
die Angabe (ältere Projekte ohne diese Frage), wird automatisch Hermes3
verwendet. Das ist unabhängig vom `testen`-Befehl (Abschnitt 4), der immer
beide Modelle zum Vergleich nutzt, egal was im Gerüst steht.

### 9b. Automatische Fortsetzung (Standard: Aus)

Frage 4 im Architekten-Interview:

```
Automatische Fortsetzung: Ein
Automatische Fortsetzung: Aus
```

**Standard ist Aus**, auch wenn die Frage nie gestellt oder das Feld
vergessen wurde. Grund: Ein zu kurzes Kapitel automatisch weiterschreiben
zu lassen, war wiederholt die Ursache für schwere Fehler – das Modell
versucht dabei manchmal „auf Krampf", die Zielwortzahl zu erreichen, statt
die Szene organisch zu Ende zu erzählen, und erzeugt dabei doppelte
Kapitelüberschriften, unmotivierte neue Szenen oder sinnfreien Füll-Text.

Bleibt ein Kapitel bei ausgeschalteter Fortsetzung unter der Zielwortzahl,
zeigt das Skript nur einen Hinweis mit der aktuellen Wortzahl an – das
Kapitel bleibt unverändert. Du kannst dann von Hand ergänzen, mit einem
Zusatzhinweis neu schreiben lassen (Abschnitt 11), oder die Fortsetzung für
diese eine Geschichte im Gerüst gezielt einschalten.

Ist sie eingeschaltet, versucht das Skript bis zu dreimal automatisch
weiterzuschreiben, wenn ein Kapitel deutlich unter der Zielwortzahl bleibt.

---

## 10. Eine neue Epoche/ein neues Setting anlegen

```bash
./novelle.py epoche-erstellen
```

Reines Frageformular (12 Fragen, kein KI-Aufruf), fragt unter anderem:

- Name, reale Epoche oder erfundenes Setting
- Zeitraum, typische Schauplätze
- Zentrale Gesellschaftsordnung und die **eine** Statusregel als
  dramaturgisches Spannungsmittel (z. B. Primogenitur, ein
  Fraternisierungsverbot)
- Bei erfundenen Welten: von welchem bekannten Franchise Abstand gehalten
  werden soll

**Wichtig:** Das Ergebnis ist ein **Rohentwurf**, kein fertiges Setting. Die
Verbotsliste und die Prüfer-Checkliste sind nur mit „HIER ERGÄNZEN"
markiert – diesen Teil recherchiert man am besten mit einer Websuche (z. B.
in einem Gespräch mit einem größeren KI-Modell), nicht mit dem lokalen
Modell.

---

## 11. Wenn ein Kapitel zu weit vom Plan abweicht

Manchmal erfindet der Autor eine eigene, mit dem Gerüst unvereinbare
Auflösung – eine geplante Hauptfigur fehlt komplett, das zentrale Geheimnis
löst sich durch einen einzelnen Satz statt durch die vorgesehenen Indizien,
oder der emotionale Zustand springt unbegründet. Das zeigt sich meist
deutlich in `befunde_<n>.md` beim Kontinuitäts-Prüfer: viele, schwere
Widersprüche gleichzeitig, nicht nur eine einzelne Kleinigkeit.

**Bei so einem Fall: nicht von Hand reparieren.** Bei mehreren
gleichzeitigen, tiefgreifenden Brüchen ist das Kapitel schneller neu
geschrieben als geflickt.

```bash
./novelle.py schreiben 3
```

Ein erneuter Aufruf reicht oft schon, weil der Autor keinen festen Seed
verwendet und jeder Versuch anders ausfällt. Reicht das nicht, kannst du
dem nächsten Versuch einen **zusätzlichen, freien Hinweis** mitgeben, der
nur für diesen einen Durchlauf gilt:

```bash
./novelle.py schreiben 3 "Maggie muss anwesend sein und aktiv mitwirken. Das Geheimnis wird NICHT durch einen Kuss aufgelöst, sondern nur durch die Indizien aus dem Nebenstrang. Halte dich strikt an Ort, Figuren und Ereignis aus dem Kapitelplan."
```

Der Hinweis wird dem Autor-Prompt prominent angehängt und hat Vorrang, falls
er einem Detail widerspricht. Er gilt **nur für diesen einen Versuch** –
er wird nirgends dauerhaft gespeichert. Soll eine Korrektur dauerhaft
gelten, gehört sie stattdessen ins Gerüst selbst.

## 12. Häufige Probleme

| Symptom | Ursache | Lösung |
|---|---|---|
| `env: python3\r: No such file or directory` | Windows-Zeilenumbrüche (CRLF) in der Datei | `sed -i 's/\r$//' novelle.py` |
| Architekt stellt mehrere Fragen auf einmal | Modell hält sich nicht an die Ein-Frage-Regel | Wird automatisch abgefangen (Skript zeigt nur die erste Frage) |
| Kapitel bricht mitten in einer Szene ab | Zu kurze Zielwortzahl oder Modell-Unlust | Automatische Fortsetzung ist standardmäßig **aus** (Abschnitt 9b) – Kapitel bleibt kurz, mit Hinweis. Bei Bedarf im Gerüst „Automatische Fortsetzung: Ein" setzen, oder mit Zusatzhinweis neu schreiben lassen (Abschnitt 11) |
| `Ollama nicht erreichbar` | Ollama-Server läuft nicht oder falsche URL | `OLLAMA_URL` Umgebungsvariable prüfen, Standard: `http://localhost:11434` |
| Falsche Epoche in einem neuen Projekt | Falsche Auswahl bei `neu` getroffen | `personas/*.txt` und `projekt/verbotsliste.md` manuell aus dem richtigen `epochen/<Name>/`-Ordner überschreiben |
| Terminal zeigt nach `architekt` noch den alten Ordnernamen an | Projektordner wurde automatisch nach dem Titel umbenannt (passiert direkt nach dem Architekten-Gespräch, bevor ein Kapitel geschrieben wurde), das Terminal aktualisiert seine Anzeige aber nicht von selbst | Nur die Anzeige ist veraltet, keine echte Inkonsistenz – `cd .` oder ein neues Terminal beheben das |

---

## 13. Umgebungsvariablen (optional)

| Variable | Standard | Zweck |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Adresse des Ollama-Servers |
| `NOVELLE_PROJEKT` | `projekt` | Projektordner (relativ zum aktuellen Verzeichnis) |
| `NOVELLE_PERSONAS` | `personas` | Personas-Ordner des aktuellen Projekts |
| `NOVELLE_EPOCHEN` | `<Skript-Ordner>/epochen` | Zentrale Epochen-Bibliothek |
| `NOVELLE_GEMEINSAME_PERSONAS` | `<Skript-Ordner>/personas` | Zentrale, epochenlose Personas |

Normalerweise muss keine davon gesetzt werden – die Standardwerte passen für
den üblichen Aufbau.
