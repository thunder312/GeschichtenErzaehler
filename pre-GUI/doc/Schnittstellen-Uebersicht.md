# Schnittstellen-Übersicht: novelle.py

Technisches Referenzdokument für die Entwicklung einer GUI. Beschreibt die
Datenstrukturen, Dateiformate und externen Schnittstellen, die `novelle.py`
verwendet – als Grundlage, um entweder (a) das Skript als Subprozess zu
kapseln, oder (b) die Kernlogik direkt in der GUI-Anwendung nachzubilden.

**Empfehlung vorab:** Weg (b) ist vermutlich der sauberere Ansatz für eine
GUI. Der Architekt und der Epochen-Ersteller laufen im CLI als blockierende
`input()`-Schleifen; das lässt sich zwar per Subprozess mit STDIN/STDOUT
ansteuern, ist aber unhandlich. Für eine GUI ist es einfacher, die
Ollama-HTTP-Schnittstelle direkt anzusprechen (Abschnitt 3) und die
Gesprächsführung in der GUI selbst zu übernehmen, während Dateiformat und
Ordnerstruktur (Abschnitte 1, 2, 5) exakt beibehalten werden, damit CLI und
GUI dieselben Projektordner lesen/schreiben können.

---

## 1. Ordnerstruktur (Vertrag zwischen CLI und GUI)

```
<Installationsordner>/
├── novelle.py
├── personas/                          epochenlos, 4 Dateien
│   ├── chronist.txt
│   ├── pruefer_kontinuitaet.txt
│   ├── lektor.txt
│   └── anachronismen_korrektur.txt
└── epochen/
    └── <EpochenName>/                 beliebig viele Unterordner
        ├── architekt.txt
        ├── autor.txt
        ├── pruefer_anachronismus.txt
        └── verbotsliste.md

<Projektordner>/                       ein Ordner pro Geschichte
├── novelle.py                         Symlink auf das zentrale Skript
├── personas/                          Kopie der 7 Dateien zum Zeitpunkt der Anlage
│   ├── architekt.txt
│   ├── autor.txt
│   ├── pruefer_anachronismus.txt
│   ├── chronist.txt
│   ├── pruefer_kontinuitaet.txt
│   ├── lektor.txt
│   └── anachronismen_korrektur.txt
└── projekt/
    ├── geruest.md
    ├── verbotsliste.md
    ├── stand_00.md, stand_01.md, stand_02.md, ...
    ├── kapitel_01.md, kapitel_02.md, ...
    ├── befunde_01.md, befunde_02.md, ...
    ├── befunde_gesamt.md              (nur nach `gesamt`)
    ├── gesamt.md                      (nach `export`, oder automatisch nach
    │                                   `stand` beim letzten geplanten Kapitel)
    └── vergleich_kapitel_<n>_hermes.md, _qwen.md   (nur nach `testen`)
```

Alle Pfade sind **UTF-8-Textdateien**, Zeilenumbrüche `\n` (Unix). Keine
Binärformate.

**Auflösung der Pfade zur Laufzeit** (relevant, falls die GUI die
Python-Logik nachbaut):

| Pfad | Bezugspunkt |
|---|---|
| `personas/`, `projekt/` (im Projektordner) | aktuelles Arbeitsverzeichnis (cwd) |
| `epochen/`, geteilte `personas/` (zentral) | Ort der **echten** `novelle.py`-Datei, Symlinks aufgelöst (`Path(__file__).resolve()`) |

Überschreibbar per Umgebungsvariablen: `NOVELLE_PROJEKT`, `NOVELLE_PERSONAS`,
`NOVELLE_EPOCHEN`, `NOVELLE_GEMEINSAME_PERSONAS`.

---

## 2. Dateiformate

### 2.1 `geruest.md`

Freitext-Markdown, von der Architekten-Rolle erzeugt. Vier Felder werden vom
Skript per Regex ausgelesen und müssen **wörtlich** vorkommen:

```python
# Jahr/Zeitangabe (Fallback-Kette):
re.search(r"Jahr\s*[:\-]?\s*(\d{1,5})", geruest, re.IGNORECASE)
# falls kein Treffer:
re.search(r"\b([12][0-9]{3})\b", geruest)
# Ergebnis, falls kein Treffer: "unbekannt"

# Jugendschutz-Stufe:
re.search(r"Jugendschutz-Stufe\s*[:\-]?\s*([A-Za-zÄÖÜäöüß/ ]+)",
          geruest, re.IGNORECASE)
# wert.lower() enthält "jugendfrei" -> "jugendfrei"
# wert.lower() enthält "angedeutet" oder "romantisch" -> "angedeutet"
# sonst (auch wenn kein Treffer) -> "voll"

# Autor-Modell (Frage 3 im Architekten-Interview, siehe 5.2a):
re.search(r"Autor-Modell\s*[:\-]?\s*([A-Za-z0-9 ]+)", geruest, re.IGNORECASE)
# wert.lower() enthaelt "qwen" -> Rolle "autor_qwen_test" (qwen3:14b)
# sonst (auch wenn kein Treffer) -> Rolle "autor" (hermes3:8b) - Standard

# Automatische Fortsetzung (Frage 4 im Architekten-Interview, siehe 5.4):
re.search(r"Automatische Fortsetzung\s*[:\-]?\s*([A-Za-zÄÖÜäöüß]+)",
          geruest, re.IGNORECASE)
# wert.lower() beginnt mit "ein" -> True (Fortsetzung aktiv)
# sonst (auch wenn kein Treffer) -> False - Standard, bewusst sicherer als
# ein automatisches "Ein"
```

Struktur (von der Architekten-Persona vorgegeben, nicht vom Code erzwungen):
`# STORY-GERUEST`, `## Rahmen`, `## Titel`, `## Unerhoerte Begebenheit`,
`## Figuren`, `## Konflikt`, `## Nebenstrang`, `## Kapitelplan`,
`## Ausgangslage vor Kapitel eins` (siehe 5.3), `## Offene Punkte`, `## Regeln`.

Der `## Titel`-Abschnitt wird zusaetzlich fuer zwei weitere Automatismen
ausgelesen, die NICHT im Geruest selbst wirken, sondern an anderer Stelle
(siehe 5.2b Titelseite und 5.11 Projektordner-Umbenennung):

```python
re.search(r"##\s*Titel\s*\n+(.+)", geruest)
```

### 2.2 `verbotsliste.md`

Freitext-Markdown. Wird bei jeder Anachronismus-Prüfung **komplett** als
Kontext mitgeschickt (kein Parsing, keine Struktur-Pflicht).

### 2.3 `stand_<NN>.md`

Zweistellige, nullgepolsterte Nummer (`stand_00.md`, `stand_07.md`,
`stand_12.md`). `stand_00.md` ist die Ausgangslage vor Kapitel 1. Freitext,
vom Chronisten erzeugt.

### 2.4 `kapitel_<NN>.md`

Gleiche Nummerierung. Reiner Kapiteltext. Formatregeln (von der
Autor-Persona durchgesetzt, nicht vom Code):
- Überschrift erste Zeile: `Kapitel <ausgeschriebene Zahl>: <Untertitel>`
- Keine Gedankenstriche (`–`, `—`) als Satzzeichen
- Deutsche Anführungszeichen `„..."`

### 2.5 `befunde_<NN>.md`

Wird von `_pruefe()` erzeugt, enthält zwei Abschnitte:

```markdown
# Befunde zu Kapitel <n>

Erzeugt: <YYYY-MM-DD HH:MM>
Jahr laut Geruest: <jahr>

---

## Anachronismen

| Fundstelle (Zitat, hoechstens 10 Woerter) | Problem | Sicherheit | Vorschlag |
| :--- | :--- | :--- | :--- |
| ... | ... | hoch/mittel/gering | ... |

---

## Kontinuitaet und Logik

<Freitext-Liste oder "Keine Widersprueche gefunden.">
```

**Wichtig für eine GUI, die `anwenden` nachbaut:** Ein Fund wird nur
automatisch übernommen, wenn Sicherheit = „hoch" **und** die Vorschlag-Spalte
einen konkreten Ersatz enthält (kein `-`, kein Text wie „Nachprüfung nötig").
Diese Filterlogik steckt aktuell im Prompt der Korrektur-Rolle, nicht in
parsierbarem Code – siehe Abschnitt 4.

---

## 3. Ollama-HTTP-Schnittstelle

Basis-URL: `OLLAMA_URL` (Standard `http://localhost:11434`).

### 3.1 Chat-Aufruf

```
POST {OLLAMA_URL}/api/chat
Content-Type: application/json
```

Request-Body:

```json
{
  "model": "<modellname>",
  "messages": [
    {"role": "system", "content": "<persona-text>"},
    {"role": "user", "content": "<aufgabentext>"}
  ],
  "stream": true,
  "keep_alive": "30m",
  "think": false,
  "options": {
    "temperature": 0.85,
    "top_p": 1.0,
    "min_p": 0.05,
    "top_k": 0,
    "repeat_penalty": 1.1,
    "repeat_last_n": 256,
    "num_ctx": 8192,
    "num_predict": 4096
  }
}
```

Response: newline-delimited JSON-Stream. Jede Zeile:

```json
{"message": {"role": "assistant", "content": "...", "thinking": "..."}, "done": false}
```

Letzte Zeile enthält zusätzlich `"done": true` sowie
`"eval_count"`, `"eval_duration"` (Nanosekunden), optional `"done_reason"`
(`"stop"` oder `"length"`).

**Wichtig:** `thinking` und `content` sind getrennte Felder. Reasoning-fähige
Modelle (Qwen3, teils Gemma) füllen zuerst `thinking`, dann `content`. Beide
teilen sich denselben `num_predict`-Tokenbudget-Topf – bei zu knappem Budget
kann `content` leer bleiben, obwohl `done: true` gemeldet wird. Deshalb steht
in der Rollenkonfiguration bei mehreren Rollen `"think": false` (siehe
Abschnitt 4), obwohl das Modell Denkmodus könnte.

### 3.2 Weitere verwendete Endpunkte

```
GET {OLLAMA_URL}/api/ps      → aktuell geladene Modelle (Speicherbedarf)
GET {OLLAMA_URL}/api/tags    → alle lokal verfügbaren Modelle
```

---

## 4. Rollenkonfiguration

Sieben feste Rollen plus eine optionale Testrolle. Jede Rolle hat eigenes
Modell, eigenen Denkmodus-Schalter, eigene Sampling-Parameter:

| Rolle | Modell | think | temperature | num_ctx | num_predict | seed |
|---|---|---|---|---|---|---|
| `architekt` | gemma4 | true | 0.4 | 8192 | 4096 | 42 |
| `autor` | hermes3:8b | false | 0.85 | 8192 | 4096 | – |
| `chronist` | gemma4 | false | 0.2 | 16384 | 1024 | 42 |
| `anachronismus` | gemma4 | true | 0.1 | 16384 | 6144 | 42 |
| `kontinuitaet` | gemma4 | true | 0.1 | 16384 | 6144 | 42 |
| `lektor` | gemma4 | false | 0.15 | 16384 | 6144 | 42 |
| `anachronismen_korrektur` | gemma4 | false | 0.1 | 16384 | 6144 | 42 |
| `autor_qwen_test` (optional) | qwen3:14b | false | 0.7 | 16384 | 6144 | – |

Vollständige Sampling-Parameter je Rolle (top_p, min_p, top_k,
repeat_penalty, repeat_last_n, ggf. presence_penalty) stehen im Quelltext im
Dictionary `ROLLEN`. Eine GUI, die eigene Ollama-Aufrufe macht, sollte diese
Werte 1:1 übernehmen, sonst weicht das Verhalten vom CLI ab.

**Warum `think` bei den meisten Rollen `false` ist, obwohl `gemma4`
Denkmodus kann:** Rollen, deren Antwort selbst ein langer Fließtext ist
(Lektor, Korrektur-Rollen), würden bei aktivem Denkmodus riskieren, dass das
Tokenbudget im Denken aufgebraucht wird, bevor der eigentliche Text beginnt.
Nur `architekt`, `anachronismus`, `kontinuitaet` behalten Denkmodus, weil
ihre Antwort kürzer und die Aufgabe (Fragen stellen, Tabellen prüfen)
mehrschrittiges Denken sinnvoll nutzen kann.

---

## 5. Kernalgorithmen (für eine Reimplementierung wichtig)

### 5.1 Ordnername aus Titel

```python
def ordnername_aus_titel(titel: str) -> str:
    ersatz = {"ä":"ae","ö":"oe","ü":"ue","Ä":"Ae","Ö":"Oe","Ü":"Ue","ß":"ss"}
    for a, b in ersatz.items():
        titel = titel.replace(a, b)
    titel = re.sub(r"\s+", "-", titel.strip())
    titel = re.sub(r"[^A-Za-z0-9\-_.]", "", titel)
    titel = re.sub(r"-{2,}", "-", titel).strip("-")
    return titel or "Neues-Projekt"
```

Wird an zwei Stellen verwendet: beim `neu`-Befehl (neuer Ordnername aus
eingetipptem Titel) und bei der automatischen Projektordner-Umbenennung
nach dem Architekten-Gespräch (siehe 5.16).

### 5.2 Autor-Modell-Auswahl (Hermes3/Qwen3)

Frage 3 im Architekten-Interview legt fest, welches Modell die Geschichte
tatsächlich schreibt. `_autor_rolle_erkennen(geruest)` liest das Feld aus
dem Rahmen-Abschnitt:

```python
def _autor_rolle_erkennen(geruest: str) -> str:
    treffer = re.search(r"Autor-Modell\s*[:\-]?\s*([A-Za-z0-9 ]+)",
                         geruest, re.IGNORECASE)
    if not treffer:
        return "autor"
    wert = treffer.group(1).lower()
    if "qwen" in wert:
        return "autor_qwen_test"
    return "autor"
```

Der Rückgabewert ist direkt ein Schlüssel in `ROLLEN` (siehe Abschnitt 4) und
wird sowohl an den Haupt-Schreibaufruf als auch an jeden Fortsetzungsaufruf
in `_bei_bedarf_fortsetzen` durchgereicht - dieselbe Story bleibt also über
alle Kapitel und Fortsetzungsversuche hinweg beim einmal gewählten Modell.

Die Rolle `autor_qwen_test` existierte bereits vorher als reine
Vergleichsrolle für `./novelle.py testen <n>` und wird jetzt doppelt
genutzt: einerseits weiterhin für den expliziten A/B-Vergleichsbefehl
(der immer beide Modelle nutzt, unabhängig vom Geruest), andererseits jetzt
auch produktiv, wenn das Geruest Qwen3 als Autor-Modell festlegt.

Fehlt die Angabe (ältere Projekte ohne diese Frage), lautet der Rückgabewert
immer `"autor"` (Hermes) - unverändertes Verhalten für Bestandsprojekte.

### 5.3 Zusaetzlicher Hinweis fuer einzelne Schreibversuche (`schreiben <n> [hinweis...]`)

`cmd_schreiben` nimmt ab `args[1:]` optional einen frei formulierten,
mit Leerzeichen verbundenen Hinweistext entgegen. Anwendungsfall: der
Kontinuitaets-Pruefer meldet schwere, gehaeufte Widerspruechen (z.B. eine
geplante Figur fehlt komplett, das Geheimnis loest sich unmotiviert auf) -
in diesem Fall ist Nachbearbeiten von Hand meist aufwendiger als ein neuer
Schreibversuch, und der Hinweis erlaubt es, dem naechsten Versuch gezielt
zu sagen, was zu vermeiden ist.

Der Hinweis wird als eigener, klar markierter Block ans Ende sowohl des
Haupt-Prompts als auch jedes Fortsetzungs-Prompts angehaengt (`_bei_bedarf_
fortsetzen` bekommt ihn als zusaetzliches Argument durchgereicht, damit er
bei einer automatischen Fortsetzung nicht verloren geht):

```python
zusatz_block = (
    f"\n\n=== ZUSAETZLICHER HINWEIS FUER DIESEN VERSUCH ===\n{zusatzhinweis}\n"
    f"Dieser Hinweis gilt nur fuer diesen einen Schreibversuch und hat "
    f"Vorrang, falls er einem Detail des Geruests widerspricht."
    if zusatzhinweis else ""
)
```

Wichtig: Der Hinweis wird **nirgends persistiert** - er existiert nur fuer
den aktuellen Prozessaufruf und ist nach Abschluss von `cmd_schreiben`
wieder verschwunden. Eine GUI, die eine "diesen Versuch neu schreiben, mit
folgendem Zusatz"-Funktion anbieten will, muss den Text bei jedem Retry
selbst erneut mitschicken.

### 5.4 Zielwortzahl je Kapitel: dynamisch aus dem Gerüst gelesen

**Frühere Fassung (inzwischen entfernt):** ein fest einprogrammiertes
Dictionary `ZIELWOERTER = {1: 1500, 2: 1600, ...}`, das nur zur allerersten
Testgeschichte (6 Kapitel) passte und bei jeder anderen Kapitelanzahl keinen
Zielwert lieferte.

**Aktuelle Fassung:** `_kapitelplan_erkennen(geruest: str) -> dict[int, int]`
liest Kapitelnummern und Zielwortzahlen direkt aus dem Freitext des
Kapitelplan-Abschnitts:

```python
_ZAHLWORT = {"eins":1, "zwei":2, ..., "zwanzig":20}   # deutsche Zahlwoerter 1-20

kapitel_muster = r"Kapitel\s+(\d{1,2}|eins|zwei|...)\b"
# fuer jeden Treffer: Text bis zum naechsten Treffer als "Block" nehmen,
# darin suchen nach:
wort_muster = r"([\d][\d.,]*)\s*w(?:oe|ö)rter"   # deckt "Wörter" UND "Woerter" ab
```

Ergebnis: `{1: 1500, 2: 1600, 6: 1300}` – auch bei Lücken (z. B. wenn
Kapitel 3–5 im Text nicht sauber erkannt wurden) bleiben die erkannten
Einträge gültig, fehlende liefern schlicht keinen Zielwert (kein Fehler).

**Für eine Reimplementierung wichtig:** `max(ergebnis.keys())` liefert die
Gesamtzahl der geplanten Kapitel und wird auch für die automatische
Zusammenführung (5.17) verwendet. Ist das Dictionary leer (Kapitelplan noch
nicht ausgefüllt oder nicht erkennbar), liefert die Funktion `{}`, und alle
davon abhängigen Automatismen (Zielwortzahl-Anzeige, automatische
Fortsetzung, Auto-Export) bleiben inaktiv, ohne Fehler zu werfen.

### 5.5 Automatische Fortsetzung bei zu kurzen Kapiteln (Opt-in, Standard Aus)

**Wichtige Verhaltensänderung gegenüber früheren Versionen:** Die
automatische Fortsetzung lief ursprünglich unbedingt bei jedem zu kurzen
Kapitel. Sie ist jetzt **standardmäßig deaktiviert** und muss im Geruest
gezielt eingeschaltet werden, weil sie wiederholt die Ursache für schwere
Fehler war (siehe 5.10 und 5.11).

```python
def _automatische_fortsetzung_aktiviert(geruest: str) -> bool:
    treffer = re.search(r"Automatische Fortsetzung\s*[:\-]?\s*([A-Za-zÄÖÜäöüß]+)",
                         geruest, re.IGNORECASE)
    if not treffer:
        return False          # Standard: AUS, auch ohne Feld
    wert = treffer.group(1).lower()
    return wert.startswith("ein")
```

`cmd_schreiben` prüft dieses Flag, bevor `_bei_bedarf_fortsetzen` überhaupt
aufgerufen wird:

```python
if ziel and _automatische_fortsetzung_aktiviert(geruest):
    text = _bei_bedarf_fortsetzen(n, text, ziel, geruest, vorher, stufe,
                                   zusatzhinweis, autor_rolle)
elif ziel and woerter(text) < ziel * FORTSETZEN_SCHWELLE:
    info(...)   # nur ein Hinweis, Kapitel bleibt unveraendert
```

**Ist die Fortsetzung aktiviert**, läuft der bisherige Mechanismus
unverändert: Ist `wortzahl(text) < ziel * 0.70`, wird bis zu **3-mal** ein
Fortsetzungsaufruf gemacht. Jeder Aufruf bekommt nur die letzten 600 Zeichen
des bisherigen Texts als Anschlusspunkt (nicht den gesamten Text, spart
Kontext) sowie dieselbe Jugendschutz-Direktive (Abschnitt 5.12) und den
gleichen Autor-Modell-Rolle (Abschnitt 5.2). Nach jedem Fortsetzungsaufruf:

1. Meta-Zeilen entfernen (Trennstriche, Wortzahl-Angaben wie
   „Gedankenerhebung - 1300 Wörter." oder „495 Wörter. Halte dich an die
   Vorgaben.")
2. Führende Duplikate entfernen: die ersten *k* Absätze der Fortsetzung
   werden gegen die letzten *k* Absätze des bisherigen Texts verglichen
   (`difflib.SequenceMatcher`, Ähnlichkeit > 0.75), absteigend von *k=4* bis
   *k=1*. Grund: Modelle wiederholen trotz Anweisung manchmal den
   Vorgänger-Absatz, bevor sie tatsächlich neuen Text liefern.
3. Kapitel-Neustart-Erkennung (5.10) und Vorzeitiges-Kapitelende-Erkennung
   (5.11) laufen nach JEDEM Merge-Schritt erneut - eine Fortsetzung kann
   auch mehrfach hintereinander entgleisen.

**Für eine GUI-Reimplementierung wichtig:** Die Warnmeldung bei
ausgeschalteter Fortsetzung ist informativ, keine Fehlermeldung - `schreib()`
läuft trotzdem normal weiter und speichert das kürzere Kapitel.

### 5.6 Sprachdrift-Erkennung

Zählt Vorkommen häufiger englischer Funktionswörter
(`the, and, was, were, with, his, her, ...`) relativ zur Gesamtwortzahl.
Schwelle: 3 %. Reiner Heuristik-Alarm, kein hartes Sprach-Tool.

### 5.7 Ausweichformulierungs-Erkennung

Feste Liste bekannter vager Umschreibungen (z. B. „Sprache des Samens",
„Blumenkelch", „eins wurden"), einfache Teilstring-Suche in
kleingeschriebenem Text.

### 5.8 Erzählperspektive-Check (Ich-Perspektive-Drift)

Prüft, ob das Geruest im Rahmen-Abschnitt „Dritte Person" vorschreibt, aber
außerhalb wörtlicher Rede eindeutige Ich-Perspektive auftaucht (z.B. „meine
Hand", „sagte ich") - ein Anzeichen dafür, dass der Text (meist während
einer automatischen Fortsetzung) unbeabsichtigt in Ich-Perspektive
gekippt ist.

```python
_ICH_PRONOMEN_MUSTER = re.compile(
    r"\b(ich|mein|meine|meinen|meiner|meinem|meines|mir|mich)\b", re.IGNORECASE)

def _erzaehlperspektive_pruefen(text, geruest, kontext="", schwellwert=2):
    if not re.search(r"Dritte Person", geruest, re.IGNORECASE):
        return   # nur relevant, wenn explizit dritte Person vorgeschrieben ist
    ohne_dialog = re.sub(r'„[^"“]*["“]', ' ', text)      # deutsche Anfuehrungszeichen
    ohne_dialog = re.sub(r'"[^"]*"', ' ', ohne_dialog)   # ASCII-Anfuehrungszeichen
    treffer = _ICH_PRONOMEN_MUSTER.findall(ohne_dialog)
    if len(treffer) >= schwellwert:
        warn(...)
```

Wörtliche Rede in Anführungszeichen wird vorher entfernt, da „ich" dort
normale direkte Rede ist, kein Perspektivwechsel der Erzählstimme. Beide
gängigen Anführungszeichen-Stile (deutsch „..." und ASCII "...") werden
abgedeckt. Schwellwert 2: ein einzelnes „ich" außerhalb der Rede (z. B. bei
freier indirekter Rede) löst noch keinen Alarm aus, erst ab zwei Treffern.

### 5.9 Anredeform-Check (Sie/du-Konsistenz)

Prüft, ob innerhalb desselben Kapitels sowohl förmliche Anrede (Sie/Ihnen)
als auch informelle (du/dich/dir/dein) in wörtlicher Rede vorkommen:

```python
_FORMELL_ANREDE_MUSTER = re.compile(r"\b(Sie|Ihnen)\b")
_INFORMELL_ANREDE_MUSTER = re.compile(r"\b(du|dich|dir|dein\w*)\b")

def _anredeform_pruefen(text, kontext=""):
    dialogzeilen = re.findall(r'„([^"“]*)["“]', text)   # deutsche Anfuehrungszeichen
    dialogzeilen += re.findall(r'"([^"]*)"', text)        # ASCII-Anfuehrungszeichen
    dialogtext = " ".join(dialogzeilen)
    foermlich = _FORMELL_ANREDE_MUSTER.findall(dialogtext)
    informell = _INFORMELL_ANREDE_MUSTER.findall(dialogtext)
    if foermlich and informell:
        warn(...)
```

**Wichtige Detail-Falle, falls das in der GUI nachgebaut wird:** Nur
Anrede-Wörter INNERHALB von Anführungszeichen zählen - Erzähltext außerhalb
der wörtlichen Rede enthält „sie" naturgemäß häufig als normales
Personalpronomen und wäre sonst ein ständiger Fehlalarm. Die
Dialog-Extraktion muss **beide** Anführungszeichen-Stile abdecken (deutsch
„..." und ASCII "..."), sonst übersieht der Check jeden Dialog, der korrekt
im geforderten deutschen Format geschrieben wurde - genau das ist bei einem
echten Testfall passiert: eine erste Fassung prüfte nur auf ASCII-Zeichen
und blieb bei sauber formatiertem deutschem Dialog stumm, obwohl ein
Sie/du-Wechsel klar vorhanden war.

Ein Wechsel kann über mehrere Kapitel hinweg durchaus beabsichtigt sein
(wachsende Vertrautheit), ist aber innerhalb eines einzelnen Kapitels -
insbesondere bei einer ersten Begegnung - meist ein unbeabsichtigter
Ausrutscher.

### 5.10 Kapitel-Neustart-Erkennung (doppelte Kapitelüberschrift)

```python
_KAPITEL_UEBERSCHRIFT_MUSTER = re.compile(r"^\s*Kapitel\s+\S+\s*:",
                                           re.IGNORECASE | re.MULTILINE)

def _kapitel_neustart_abschneiden(text, kontext=""):
    treffer = list(_KAPITEL_UEBERSCHRIFT_MUSTER.finditer(text))
    if len(treffer) <= 1:
        return text
    grenze = treffer[1].start()
    warn(...)
    return text[:grenze].rstrip()
```

Hintergrund: Bei einer automatischen Fortsetzung (5.5) schreibt das Modell
manchmal trotz expliziter Anweisung keinen echten Anschluss, sondern einen
komplett neuen, oft inhaltlich widersprechenden zweiten Durchlauf des
ganzen Kapitels - inklusive eigener, wiederholter Überschrift. Der
bestehende Duplikat-Filter (führende Duplikate, siehe 5.5 Punkt 2) erkennt
das nicht, weil er nur wortwörtliche Wiederholungen abgleicht - eine neu
formulierte, andere zweite Fassung fällt dort durch.

**Wichtige Detail-Falle:** Das Muster benötigt zwingend `re.MULTILINE`,
damit `^` den Anfang jeder Zeile matcht statt nur den Anfang des gesamten
Texts - ein früher Testlauf während der Entwicklung schlug genau daran
fehl (die Funktion erkannte gar nichts, bis das Flag ergänzt wurde).

Wird zweimal aufgerufen: direkt nach dem ersten Entwurf, und nach jedem
einzelnen Fortsetzungs-Merge in `_bei_bedarf_fortsetzen`.

### 5.11 Vorzeitiges-Kapitelende-Erkennung

```python
_KAPITEL_ENDE_ERKLAERUNG_MUSTER = re.compile(
    r"(das kapitel (endete|endet|ist zu ende|erreichte seinen abschluss)|"
    r"und damit (endete|hatte) (das )?kapitel)",
    re.IGNORECASE,
)

def _vorzeitige_kapitelende_abschneiden(text, kontext="", mindest_rest=50):
    treffer = _KAPITEL_ENDE_ERKLAERUNG_MUSTER.search(text)
    if not treffer:
        return text
    satzende = text.find(".", treffer.end())
    grenze = satzende + 1 if satzende != -1 else treffer.end()
    rest = text[grenze:].strip()
    if woerter(rest) < mindest_rest:
        return text     # kurzer, runder Schlusssatz - vermutlich legitim
    warn(...)
    return text[:grenze].rstrip()
```

Dritte Ausprägung desselben Grundproblems wie 5.10: Der Text erklärt sich
mitten drin selbst für beendet (z. B. „Das Kapitel endete damit, dass sie
ihre Tassen Tee tranken…"), schreibt danach aber trotzdem mit einer
komplett neuen, ungeplanten Szene weiter (typischerweise „Zwei Tage
später…"). Anders als bei 5.10 ist der Marker keine eigene Zeile, sondern
in einen normalen Erzählsatz eingebettet - deshalb Volltextsuche
(`re.search`) statt zeilenweisem Abgleich wie beim Meta-Zeilen-Filter.

Schneidet erst nach dem Satzende (nächster Punkt nach der Fundstelle) ab,
nicht direkt an der Fundstelle - der Satz mit der Selbstaussage bleibt
selbst erhalten, nur was danach kommt, verschwindet.

Wird wie 5.10 zweimal aufgerufen: nach dem ersten Entwurf und nach jedem
Fortsetzungs-Merge.

### 5.12 Jugendschutz-Direktiven

Drei feste Textblöcke (`STUFE_DIREKTIVEN["voll"|"angedeutet"|"jugendfrei"]`),
die dem Autor-Prompt bei **jedem** Schreib- und Fortsetzungsaufruf angehängt
werden. Nur `voll` lässt die Autor-Persona unverändert wirken, die beiden
anderen Stufen weisen das Modell an, die persona-eigenen Explizitheits-
Vorgaben für diesen Aufruf zu ignorieren.

Ergänzend: `_explizitheit_pruefen()` prüft nach dem Schreiben mit
Wortgrenzen-Regex (`\b...\b`) auf eine feste Liste eindeutig expliziter
Begriffe (z. B. „oralsex", „klitoris", „penetration"). Nur relevant, wenn
Stufe ≠ „voll".

### 5.13 Rechtschreibprüfung via hunspell (externe Systemabhängigkeit)

Die hunspell-Abfrage selbst steckt in einer gemeinsamen Hilfsfunktion,
`_hunspell_unbekannte_woerter(text)`, die von zwei verschiedenen Stellen
genutzt wird (5.13 fuer den automatischen Hinweis, 5.13a fuer die
interaktive Durchsicht). Sie ist die einzige Stelle im Skript, die einen
**externen Systembefehl** aufruft statt reiner Python-Logik oder der
Ollama-API:

```python
subprocess.run(
    ["hunspell", "-d", "de_DE", "-l"],
    input=text, capture_output=True, text=True, timeout=30,
    env={**os.environ, "LC_ALL": "C.UTF-8"},
)
```

Rueckgabewert: `None` bei Fehler/hunspell nicht verfuegbar (unterscheidet
sich bewusst von einer leeren Liste, die "sauber geprueft, nichts gefunden"
bedeutet), sonst eine sortierte, deduplizierte Liste unbekannter Woerter.

Voraussetzung auf dem System: `apt-get install hunspell hunspell-de-de`.

**Wichtige Detail-Falle, falls das in der GUI nachgebaut wird:** Ohne
`LC_ALL=C.UTF-8` (oder eine andere UTF-8-Locale) zerlegt hunspell deutsche
Umlaute falsch und ein Grossteil der Ausgabe wird zu Datenmuell (z.B. wird
„während" zu „hrend" zerschnitten). Das liegt nicht am Woerterbuch (das
deklariert korrekt `SET UTF-8` in der `.aff`-Datei), sondern an der
Systemumgebung, in der der Prozess laeuft.

Der Flag `-l` (list) gibt genau die Woerter aus, die hunspell nicht kennt,
eine pro Zeile. Das Skript filtert Woerter mit weniger als drei Zeichen
heraus (meist Satzzeichen-Reste) - es gibt **keine automatische
Unterscheidung** zwischen echten Tippfehlern und Eigennamen/Fachbegriffen,
die schlicht nicht im Woerterbuch stehen. Das Melden bleibt bewusst grob;
die Einordnung macht der Mensch.

**Fehlerbehandlung:** Ist `hunspell` nicht installiert
(`FileNotFoundError`) oder schlaegt der Aufruf fehl, wird die Pruefung
**global fuer den Rest des Prozesses** deaktiviert
(Modul-Variable `_HUNSPELL_VERFUEGBAR`), nach einer einmaligen Warnung. Das
verhindert, dass bei jedem einzelnen Kapitel erneut eine Fehlermeldung
erscheint, wenn das Werkzeug grundsaetzlich fehlt.

`_rechtschreibpruefung(text, kontext)` (der automatische, nicht-interaktive
Hinweis) ruft `_hunspell_unbekannte_woerter()` auf und gibt bei Funden nur
eine Warnzeile mit der kompletten Wortliste aus, ohne Interaktion.
Aufrufstellen: am Ende von `cmd_schreiben` (nach dem fertigen Kapiteltext,
inklusive etwaiger automatischer Fortsetzungen) und am Ende von
`cmd_lektorieren` (nach der grammatikalischen Korrektur, auf dem bereits
bereinigten Text).

### 5.13a Interaktive Rechtschreib-Durchsicht (`rechtschreibung`)

`cmd_rechtschreibung(args)` ist einer von zwei Befehlen (neben `architekt`,
`neu`/`init` und `epoche-erstellen`), der **interaktiv per `input()`**
laeuft - relevant fuer eine GUI, die alle anderen Befehle bislang
non-interaktiv per Subprozess aufrufen kann.

Ablauf:
1. `_hunspell_unbekannte_woerter(text)` liefert die Wortliste (siehe 5.13).
2. Fuer jedes Wort: `_satz_mit_wort_finden(text, wort)` sucht per grober
   Satzgrenzen-Regex (`(?<=[.!?])\s+`) einen Satz, der das Wort als
   eigenes Wort (`\b...\b`) enthaelt, und kuerzt ihn bei Bedarf auf ca. 220
   Zeichen um die Fundstelle herum. Liefert `None`, wenn keine klare
   Satzgrenze gefunden wurde (das Wort existiert dann trotzdem im Text -
   kein Fehlerfall, nur weniger Kontext in der Anzeige).
3. Ausgabe von Wort + Satz, dann `input()`-Prompt.
4. Leere Eingabe: Wort bleibt unveraendert, weiter zum naechsten Fund.
5. Nicht-leere Eingabe: `re.sub(r"\b" + re.escape(wort) + r"\b", eingabe, text)`
   ersetzt **alle** Vorkommen des Worts im gesamten Kapiteltext (nicht nur
   die aktuell angezeigte Stelle), case-sensitiv wie im Original.
6. `Strg+C`/EOF waehrend der Eingabe bricht die Durchsicht ab, **behaelt
   aber bereits vorgenommene Ersetzungen** und speichert sie.
7. Nur falls mindestens eine Ersetzung erfolgt ist, wird die Datei
   ueberschrieben (`schreib()`, mit automatischer `.bak`-Sicherung der
   alten Fassung). Ohne Aenderungen bleibt die Datei unangetastet.

**Fuer eine GUI-Reimplementierung:** Dieser Befehl eignet sich besonders
gut fuer eine eigene GUI-Ansicht statt einer Terminal-Emulation - die GUI
kann `_hunspell_unbekannte_woerter()` und `_satz_mit_wort_finden()` direkt
uebernehmen (reine Funktionen ohne Interaktions-Logik) und die eigentliche
Review-Schleife (Liste von Wort+Satz+Eingabefeld) im eigenen UI abbilden,
statt die Terminal-`input()`-Schleife nachzubauen.

### 5.14 Stand-Sicherstellung (automatische Nachholung von `stand`)

```python
def _stand_sicherstellen(n: int):
    if n <= 1:
        return   # stand_00.md ist optional, kein Nachholbedarf
    vorheriger_stand = stand_datei(n - 1)
    if vorheriger_stand.exists():
        return
    vorheriges_kapitel = kapitel_datei(n - 1)
    if not vorheriges_kapitel.exists():
        warn(...)   # Kapitel n-1 wurde nie geschrieben - nicht heilbar
        return
    warn(...)   # stand n-1 wird jetzt automatisch nachgeholt
    cmd_stand([str(n - 1)])
```

Wird am Anfang von `cmd_schreiben` aufgerufen, noch vor dem Lesen des
Geruests. Deckt den Fall ab, dass `stand <n-1>` schlicht vergessen wurde,
bevor `schreiben <n>` aufgerufen wird - ohne diese Absicherung würde
Kapitel n auf einem veralteten oder fehlenden Stand aufbauen.

**Zwei bewusste Ausnahmen:**
- Kapitel 1 wird nie geprüft - ein fehlendes `stand_00.md` ist der korrekte
  Normalfall, wenn der Architekt keine Ausgangslage produziert hat (siehe
  Abschnitt 2.1/`## Ausgangslage vor Kapitel eins`).
- Fehlen sowohl Stand als auch Kapitel n-1, wird nur gewarnt, nichts
  automatisch erzeugt - das ist ein anderes Problem (Kapitel nicht der
  Reihe nach geschrieben), das sich nicht automatisch heilen lässt.

`cmd_stand` selbst gibt beim Aufruf eine Warnung aus ("Der Chronist sollte
erst nach der Korrektur laufen..."), die auch bei diesem automatischen
Aufruf erscheint - das ist beabsichtigt, da der nachgeholte Stand ja auf
dem aktuellen (möglicherweise noch unkorrigierten) Kapiteltext basiert.

### 5.15 Titelseite in Kapitel 1 (nicht mehr beim Export)

**Frühere Fassung (inzwischen entfernt):** Die Titelseite wurde erst von
`cmd_export` erzeugt und der zusammengefügten `gesamt.md` vorangestellt -
Kapitel 1 für sich allein hatte also nie einen Titel.

**Aktuelle Fassung:** `_titelseite_erzeugen(geruest)` wird direkt in
`cmd_schreiben` aufgerufen, nur für `n == 1`, nach allen anderen
Korrekturen/Abschnitten, kurz vor dem Speichern:

```python
if n == 1:
    titelseite = _titelseite_erzeugen(geruest)
    if titelseite:
        erste_zeile_titelseite = titelseite.strip().split("\n")[0]
        if not text.lstrip().startswith(erste_zeile_titelseite):
            text = titelseite + text
    else:
        warn("Keine Titelseite erzeugt - '## Titel' wurde im Geruest "
             "nicht gefunden.")
```

Die Idempotenz-Prüfung (erste Zeile der Titelseite bereits vorhanden?)
verhindert eine doppelte Titelseite, falls `schreiben 1` erneut aufgerufen
wird. `cmd_export`/`cmd_zusammenfassen` fügen die Kapitel jetzt nur noch
roh zusammen, ohne eigene Titel-Logik - die Titelseite kommt automatisch
mit, sobald `kapitel_01.md` Teil der Zusammenführung ist.

`_titelseite_erzeugen` selbst baut den Untertitel aus Titel + Jahr +
Epoche (aus der bei Projekterstellung hinterlegten Marker-Datei
`projekt/.epoche`), z. B. „Eine Geschichte aus dem Regency im Jahre 1815".
Fehlt der Titel im Geruest, wird ein leerer String zurückgegeben (kein
Fehler) - die Titelseite bleibt dann schlicht weg.

### 5.16 Projektordner-Umbenennung nach Titel

```python
def _projektordner_nach_titel_umbenennen(geruest: str):
    if list(PROJEKT.glob("kapitel_*.md")):
        return   # es gibt schon Kapitel - nicht mehr automatisch umbenennen
    titel_treffer = re.search(r"##\s*Titel\s*\n+(.+)", geruest)
    if not titel_treffer:
        return
    neuer_name = _ordnername_aus_titel(titel_treffer.group(1).strip())
    aktueller_pfad = Path.cwd()
    if aktueller_pfad.name == neuer_name:
        return
    neuer_pfad = aktueller_pfad.parent / neuer_name
    if neuer_pfad.exists():
        warn(...)   # Zielname existiert bereits - nicht umbenennen
        return
    aktueller_pfad.rename(neuer_pfad)   # in try/except OSError
```

Wird am Ende von `cmd_architekt` aufgerufen, direkt nachdem `geruest.md`
und ggf. `stand_00.md` gespeichert wurden, noch **vor** dem `break`, das
das Architekten-Gespräch beendet.

**Sicherheitsnetz:** Existieren bereits `kapitel_*.md`-Dateien im
Projektordner, wird nicht mehr umbenannt - das kann nur passieren, wenn
`architekt` ein zweites Mal auf einem bereits begonnenen Projekt aufgerufen
wird. Zu diesem Zeitpunkt liefe die Umbenennung Gefahr, aktiv in
Bearbeitung befindliche Dateipfade zu verändern.

**Für eine GUI-Reimplementierung wichtig:** `Path.cwd()` wird umbenannt,
nicht `PROJEKT` (das Unterverzeichnis `projekt/`) - der gesamte äußere
Projektordner (inklusive `personas/`, `projekt/`, dem Symlink auf
`novelle.py`) wandert mit. Unter POSIX bleibt das Arbeitsverzeichnis des
laufenden Prozesses nach der Umbenennung gültig (über den Inode verfolgt,
nicht den Pfadnamen) - alle weiteren relativen Dateizugriffe im selben
Prozess funktionieren unverändert weiter. Eine GUI, die stattdessen einen
eigenen Dateisystem-Handle/Pfad-String für den Projektordner hält, muss
diesen nach der Umbenennung selbst aktualisieren, da sie den Inode-Trick
des Betriebssystems nicht automatisch mitbekommt.

Rein informell und best-effort: Ein `OSError` bei der eigentlichen
Umbenennung (z. B. Berechtigungsproblem) wird nur als Warnung ausgegeben,
nichts abgebrochen - das Architekten-Gespräch gilt trotzdem als
erfolgreich beendet.

### 5.17 Automatische Zusammenführung bei Story-Abschluss und manuelles Zusammenfassen

```python
geplant = _kapitelplan_erkennen(geruest)
letztes_geplantes_kapitel = max(geplant.keys()) if geplant else None
vorhandene_kapitel = sorted(PROJEKT.glob("kapitel_*.md"))

if letztes_geplantes_kapitel and n == letztes_geplantes_kapitel \
        and len(vorhandene_kapitel) >= letztes_geplantes_kapitel:
    cmd_export([])   # entspricht ./novelle.py export
```

`cmd_export` **liest nur** die vorhandenen `kapitel_*.md`-Dateien und fügt
sie zu `projekt/gesamt.md` zusammen (`schreib(..., force=True)`, überschreibt
also eine ältere `gesamt.md` ohne Backup, da sie rein abgeleitet ist). Die
einzelnen Kapitel-Dateien werden dabei **nicht verändert oder gelöscht**.

**Trigger-Bedingung im Detail:** Das aktuelle `n` muss mit der höchsten im
Gerüst erkannten Kapitelnummer übereinstimmen, UND es müssen mindestens so
viele `kapitel_*.md`-Dateien vorhanden sein wie geplant. Konnte der
Kapitelplan nicht geparst werden (`geplant == {}`), passiert nichts – weder
ein Fehler noch eine Warnung, die Automatik bleibt einfach inaktiv und
`export` muss manuell aufgerufen werden.

**Manuelles Zwischenstands-Zusammenfassen (`zusammenfassen`):** Neuer
Befehl, der dieselbe Zusammenführung jederzeit erlaubt, nicht nur am
Schluss:

```python
def cmd_zusammenfassen(args):
    if not args:
        cmd_export([])          # identisch zu 'export': projekt/gesamt.md
        return
    von, bis = int(args[0]), int(args[1])
    if von > bis:
        von, bis = bis, von     # Reihenfolge wird normalisiert
    alle_kapitel = sorted(PROJEKT.glob("kapitel_*.md"),
                           key=_kapitelnummer_aus_dateiname)
    ausgewaehlt = [p for p in alle_kapitel
                   if von <= _kapitelnummer_aus_dateiname(p) <= bis]
    # fehlende Nummern im Bereich -> Warnung, kein Abbruch
    ziel_name = f"zusammen_{von:02d}-{bis:02d}.md"
    schreib(PROJEKT / ziel_name, ganz, force=True)
```

Ohne Argumente ist `zusammenfassen` identisch zu `export` (schreibt
`gesamt.md`). Mit zwei Zahlen entsteht eine eigene Datei
`zusammen_<von>-<bis>.md` (zweistellig, nullgepolstert), damit
Zwischenstände nicht mit der finalen `gesamt.md` kollidieren. Fehlt eine
Kapitelnummer innerhalb des angegebenen Bereichs, wird gewarnt und mit den
vorhandenen weitergemacht statt abzubrechen.

**Für eine GUI-Reimplementierung:** Dieselbe Logik lässt sich unabhängig vom
CLI nachbauen, sofern die GUI ebenfalls `_kapitelplan_erkennen()` (oder ein
Äquivalent) auf den aktuellen `geruest.md`-Inhalt anwendet und die Anzahl der
vorhandenen `kapitel_*.md`-Dateien im Projektordner zählt.

### 5.18 Epochen-Ersteller (`epoche-erstellen`)

Reines Python-Frageformular, **kein LLM-Aufruf**. Sammelt zwölf Antworten in
ein Dictionary, erzeugt daraus vier Dateien über String-Templates:
`architekt.txt`, `autor.txt`, `pruefer_anachronismus.txt`, `verbotsliste.md`.
Unabhängig vom eigentlichen Architekten-Interview (das inzwischen 13 Fragen
umfasst, siehe 5.2 und 2.1) - `epoche-erstellen` legt lediglich die
Grundlage für eine neue Epoche an, bevor irgendein Architekten-Gespräch
für eine konkrete Geschichte stattfindet.

Zweige nach Frage 2 („real oder erfunden"):
- **Real:** `pruefer_anachronismus.txt` bekommt die historische Variante
  (prüft gegen echte Zeitgeschichte).
- **Erfunden:** bekommt die Konsistenz-/Markenabstand-Variante (prüft gegen
  selbst festgelegte Weltregeln und Nähe zu bekannten Franchises).

Das Ergebnis ist bewusst ein **Rohentwurf** mit „HIER ERGÄNZEN"-Markierungen
in `verbotsliste.md` und `pruefer_anachronismus.txt` – diese Inhalte
erfordern Recherche, die das lokale Modell nicht zuverlässig liefern kann.

---

## 6. CLI-Befehle (Referenz für Subprozess-Aufrufe)

Alle Befehle: `./novelle.py <befehl> [argumente]`

| Befehl | Argumente | Interaktiv? | Verändert Dateien |
|---|---|---|---|
| `init` | – | ja (Epochen-Auswahl) | personas/, projekt/ (aktueller Ordner) |
| `neu` | `<Titel...>` | ja (Epochen-Auswahl) | neuer Ordner |
| `epoche-erstellen` / `neueepoche` | – | ja (12 Fragen) | epochen/\<neu\>/ |
| `architekt` | – | ja (Interview, 13 Fragen) | projekt/geruest.md, ggf. projekt/stand_00.md, benennt den Projektordner ggf. um (siehe 5.16) |
| `schreiben` | `<n> [zusatzhinweis...]` | nein | projekt/kapitel_\<n\>.md, befunde_\<n\>.md |
| `testen` | `<n>` | nein | projekt/vergleich_kapitel_\<n\>_{hermes,qwen}.md |
| `pruefen` | `<n>` | nein | projekt/befunde_\<n\>.md |
| `anwenden` | `<n>` | nein | projekt/kapitel_\<n\>.md (+ .bak) |
| `lektorieren` | `<n>` | nein | projekt/kapitel_\<n\>.md (+ .bak) |
| `rechtschreibung` | `<n>` | **ja** (input je Fund) | projekt/kapitel_\<n\>.md (+ .bak), nur falls mind. eine Ersetzung erfolgte |
| `stand` | `<n>` | nein | projekt/stand_\<n\>.md (+ ggf. automatisch projekt/gesamt.md, siehe 5.17) |
| `gesamt` | – | nein | projekt/befunde_gesamt.md |
| `export` | – | nein | projekt/gesamt.md |
| `zusammenfassen` | – oder `<von> <bis>` | nein | projekt/gesamt.md (ohne Argumente) oder projekt/zusammen_\<von\>-\<bis\>.md |
| `modelle` | – | nein | – (nur Ausgabe) |

**Exit-Codes:** `0` bei Erfolg, `1` bei Fehler (`fehler()`-Funktion ruft
`sys.exit(1)`). Bei Abbruch durch Strg+C: Exit-Code `130`.

**Ausgabe-Konvention:** Nutzerlesbare Statusmeldungen (`info`, `ok`, `warn`,
`fehler`) gehen nach **stderr**, mit Präfixen `==>`, ` ok`, `  !`, `FEHLER`.
Eine GUI, die stdout/stderr parst, sollte sich auf diese Präfixe stützen,
nicht auf exakten Wortlaut (der kann sich ändern).

**Interaktive Befehle** (`init`, `neu`, `epoche-erstellen`, `architekt`,
`rechtschreibung`) lesen über `input()` von stdin. Bei Subprozess-Einbindung
muss die GUI stdin offen halten und zeilenweise Antworten schreiben, nachdem
der jeweilige Prompt-Text auf stderr erschienen ist.

---

## 7. Bekannte Grenzen (relevant für GUI-Fehlerbehandlung)

- Die Filterlogik für `anwenden` (nur „hoch" + konkreter Vorschlag) ist
  **Prompt-Anweisung**, keine deterministische Code-Prüfung. Ein Modell kann
  sich abweichend verhalten; die GUI sollte nach jedem `anwenden` einen Diff
  anzeigen (das CLI tut das bereits über `_aenderungen_anzeigen()`).
- `_kapitelplan_erkennen()` (Abschnitt 5.4) ist ebenfalls Regex auf
  Freitext, nicht auf ein festes Datenformat. Ungewöhnliche Formulierungen
  des Architekten (z. B. „Zielumfang ca. 1.500" statt „Zielwortzahl: 1.500
  Wörter") werden nicht erkannt. Das betrifft sowohl die
  Zielwortzahl-Anzeige als auch die automatische Zusammenführung am Ende
  (Abschnitt 5.17) – im Zweifel bleibt die Automatik einfach aus, es gibt
  keinen Fehlerfall, der stillschweigend falsche Werte liefert.
- Die Jahres- und Jugendschutz-Erkennung ist Regex-basiert und erwartet
  bestimmte Wortmuster im Gerüst. Freitext-Abweichungen der Architekten-Rolle
  können dazu führen, dass Standardwerte greifen (Jahr „unbekannt",
  Jugendschutz-Stufe „voll", Autor-Modell „Hermes3", Automatische
  Fortsetzung „Aus"). Bei den beiden letztgenannten Feldern ist der
  Fallback-Wert bewusst so gewählt, dass er dem sichereren/etablierten
  Verhalten entspricht, nicht zufällig.
- Es gibt keine Datenbank, keine Locks, keine Mehrbenutzerfähigkeit. Zwei
  gleichzeitige Schreibzugriffe auf denselben Projektordner sind nicht
  abgesichert.
- Symlinks: `neu` versucht einen Symlink für `novelle.py` im neuen Ordner
  anzulegen; schlägt das fehl (z. B. auf manchen Netzlaufwerken), wird
  ersatzweise kopiert, mit Warnung. Eine GUI unter Windows sollte das
  berücksichtigen (Symlinks brauchen dort ggf. Admin-Rechte oder
  Developer-Mode). Dieselbe Einschränkung gilt für die automatische
  Projektordner-Umbenennung (Abschnitt 5.16) - sie verwendet
  `Path.rename()`, was unter Windows bei geöffneten Dateihandles im Ordner
  fehlschlagen kann; unter Linux/POSIX (dem eigentlichen Zielsystem dieses
  Skripts) ist das unproblematisch.
- Alle mechanischen Sicherheitsnetze in Abschnitt 5 (5.8-5.11) sind
  **Heuristiken auf Regex-Basis**, keine semantische Prüfung. Sie fangen
  bekannte, wiederkehrende Fehlermuster ab, garantieren aber nicht, dass ein
  Kapitel frei von inhaltlichen Fehlern ist - das eigene Gegenlesen bzw. der
  LLM-basierte Kontinuitäts-Prüfer bleiben notwendig.
