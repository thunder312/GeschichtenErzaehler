🇩🇪 [Deutsche Version](Schnittstellen-Uebersicht.md)

# Interface Overview: novelle.py

Technical reference document for developing a GUI. Describes the data
structures, file formats, and external interfaces used by `novelle.py` – as
a foundation for either (a) wrapping the script as a subprocess, or (b)
reimplementing the core logic directly inside the GUI application.

**Recommendation up front:** approach (b) is probably the cleaner route for
a GUI. The Architect and the era creator run as blocking `input()` loops in
the CLI; that can technically be driven via subprocess with STDIN/STDOUT,
but it's unwieldy. For a GUI it's simpler to talk to the Ollama HTTP
interface directly (section 3) and handle the conversation flow in the GUI
itself, while keeping the file format and folder structure (sections 1, 2,
5) exactly as they are, so that the CLI and the GUI can read/write the same
project folders.

---

## 1. Folder structure (contract between CLI and GUI)

```
<installation folder>/
├── novelle.py
├── personas/                          era-independent, 4 files
│   ├── chronist.txt
│   ├── pruefer_kontinuitaet.txt
│   ├── lektor.txt
│   └── anachronismen_korrektur.txt
└── epochen/
    └── <era name>/                    any number of subfolders
        ├── architekt.txt
        ├── autor.txt
        ├── pruefer_anachronismus.txt
        └── verbotsliste.md

<project folder>/                      one folder per story
├── novelle.py                         symlink to the central script
├── personas/                          copy of the 7 files at creation time
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
    ├── befunde_gesamt.md              (only after `gesamt`)
    ├── gesamt.md                      (after `export`, or automatically after
    │                                   `stand` on the last planned chapter)
    └── vergleich_kapitel_<n>_hermes.md, _qwen.md   (only after `testen`)
```

All paths are **UTF-8 text files**, line endings `\n` (Unix). No binary
formats.

**Runtime path resolution** (relevant if the GUI reimplements the Python
logic):

| Path | Reference point |
|---|---|
| `personas/`, `projekt/` (inside the project folder) | current working directory (cwd) |
| `epochen/`, shared `personas/` (central) | location of the **real** `novelle.py` file, symlinks resolved (`Path(__file__).resolve()`) |

Overridable via environment variables: `NOVELLE_PROJEKT`, `NOVELLE_PERSONAS`,
`NOVELLE_EPOCHEN`, `NOVELLE_GEMEINSAME_PERSONAS`.

---

## 2. File formats

### 2.1 `geruest.md` (outline)

Free-text Markdown, produced by the Architect role. Four fields are read
out by the script via regex and **must** appear verbatim:

```python
# Year/time period (fallback chain):
re.search(r"Jahr\s*[:\-]?\s*(\d{1,5})", geruest, re.IGNORECASE)
# if no match:
re.search(r"\b([12][0-9]{3})\b", geruest)
# result if still no match: "unbekannt" (unknown)

# Content rating (Jugendschutz-Stufe):
re.search(r"Jugendschutz-Stufe\s*[:\-]?\s*([A-Za-zÄÖÜäöüß/ ]+)",
          geruest, re.IGNORECASE)
# value.lower() contains "jugendfrei" (family-friendly) -> "jugendfrei"
# value.lower() contains "angedeutet" (implied) or "romantisch" -> "angedeutet"
# otherwise (even without a match) -> "voll" (full/explicit)

# Author model (question 3 in the Architect interview, see 5.2a):
re.search(r"Autor-Modell\s*[:\-]?\s*([A-Za-z0-9 ]+)", geruest, re.IGNORECASE)
# value.lower() contains "mistral" -> role "autor_mistral" (mistral-small3.2:latest)
# otherwise value.lower() contains "qwen" -> role "autor_qwen" (qwen3:14b)
# otherwise (even without a match) -> role "autor" (hermes3:8b) - default

# Automatic continuation (question 4 in the Architect interview, see 5.4):
re.search(r"Automatische Fortsetzung\s*[:\-]?\s*([A-Za-zÄÖÜäöüß]+)",
          geruest, re.IGNORECASE)
# value.lower() starts with "ein" (on) -> True (continuation active)
# otherwise (even without a match) -> False - default, deliberately safer than
# an automatic "on"
```

Structure (dictated by the Architect persona, not enforced by the code):
`# STORY-GERUEST`, `## Rahmen` (frame/setup), `## Titel` (title),
`## Unerhoerte Begebenheit` (the inciting incident), `## Figuren`
(characters), `## Konflikt`, `## Nebenstrang` (subplot), `## Kapitelplan`
(chapter plan), `## Ausgangslage vor Kapitel eins` (starting situation
before chapter one, see 5.3), `## Offene Punkte` (open points), `## Regeln`
(rules).

The `## Titel` section is additionally read out for two further
automations that do NOT act on the outline itself, but elsewhere (see 5.2b
title page and 5.11 project-folder renaming):

```python
re.search(r"##\s*Titel\s*\n+(.+)", geruest)
```

### 2.2 `verbotsliste.md` (forbidden list)

Free-text Markdown. Sent **in full** as context on every anachronism review
(no parsing, no required structure).

### 2.3 `stand_<NN>.md` (story state)

Two-digit, zero-padded number (`stand_00.md`, `stand_07.md`,
`stand_12.md`). `stand_00.md` is the starting situation before chapter 1.
Free text, produced by the chronicler role.

### 2.4 `kapitel_<NN>.md` (chapter)

Same numbering. Plain chapter text. Format rules (enforced by the Author
persona, not by the code):
- First line is a heading: `Kapitel <spelled-out number>: <subtitle>`
- No em/en dashes (`–`, `—`) as punctuation
- German quotation marks `„..."`

### 2.5 `befunde_<NN>.md` (findings)

Produced by `_pruefe()`, contains two sections:

```markdown
# Befunde zu Kapitel <n>

Erzeugt: <YYYY-MM-DD HH:MM>
Jahr laut Geruest: <year>

---

## Anachronismen

| Fundstelle (Zitat, hoechstens 10 Woerter) | Problem | Sicherheit | Vorschlag |
| :--- | :--- | :--- | :--- |
| ... | ... | hoch/mittel/gering | ... |

---

## Kontinuitaet und Logik

<free-text list or "Keine Widersprueche gefunden." (no contradictions found)>
```

**Important for a GUI reimplementing `anwenden` (apply):** a finding is
only applied automatically when certainty = "hoch" (high) **and** the
suggestion column contains a concrete replacement (not `-`, not text like
"Nachprüfung nötig" / "needs review"). This filter logic currently lives in
the correction role's prompt, not in parseable code – see section 4.

---

## 3. Ollama HTTP interface

Base URL: `OLLAMA_URL` (default `http://localhost:11434`).

### 3.1 Chat call

```
POST {OLLAMA_URL}/api/chat
Content-Type: application/json
```

Request body:

```json
{
  "model": "<model name>",
  "messages": [
    {"role": "system", "content": "<persona text>"},
    {"role": "user", "content": "<task text>"}
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

Response: newline-delimited JSON stream. Each line:

```json
{"message": {"role": "assistant", "content": "...", "thinking": "..."}, "done": false}
```

The last line additionally contains `"done": true` as well as
`"eval_count"`, `"eval_duration"` (nanoseconds), optionally `"done_reason"`
(`"stop"` or `"length"`).

**Important:** `thinking` and `content` are separate fields. Reasoning-
capable models (Qwen3, some Gemma variants) fill `thinking` first, then
`content`. Both share the same `num_predict` token budget – if the budget
is too tight, `content` can end up empty even though `done: true` is
reported. That's why several roles in the role configuration have
`"think": false` (see section 4), even though the model itself could use
thinking mode.

### 3.2 Other endpoints used

```
GET {OLLAMA_URL}/api/ps      → currently loaded models (memory usage)
GET {OLLAMA_URL}/api/tags    → all locally available models
```

---

## 4. Role configuration

Seven fixed roles plus one optional test role. Each role has its own model,
its own thinking-mode switch, its own sampling parameters:

| Role | Model | think | temperature | num_ctx | num_predict | seed |
|---|---|---|---|---|---|---|
| `architekt` | gemma4 | true | 0.4 | 32768 | 12288 | 42 |
| `autor` | hermes3:8b | false | 0.85 | 8192 | 4096 | – |
| `chronist` | gemma4 | false | 0.2 | 16384 | 1024 | 42 |
| `anachronismus` | gemma4 | true | 0.1 | 16384 | 6144 | 42 |
| `kontinuitaet` | gemma4 | true | 0.1 | 16384 | 6144 | 42 |
| `lektor` | gemma4 | false | 0.15 | 16384 | 6144 | 42 |
| `anachronismen_korrektur` | gemma4 | false | 0.1 | 16384 | 6144 | 42 |
| `autor_qwen` (optional) | qwen3:14b | false | 0.7 | 16384 | 6144 | – |
| `autor_mistral` (optional, GUI backend only) | mistral-small3.2:latest | false | 0.7 | 16384 | 6144 | – |

Full sampling parameters per role (top_p, min_p, top_k, repeat_penalty,
repeat_last_n, and, where applicable, presence_penalty) live in the source
code in the `ROLLEN` dictionary. A GUI that makes its own Ollama calls
should adopt these values 1:1, otherwise its behavior will diverge from the
CLI's.

**GUI backend deviation (as of 2026-08-13):** the table above still
describes `pre-GUI/novelle.py` (CLI, unchanged). In the GUI backend
(`app/core/rollen.py`), `autor_qwen` and `autor_mistral` were removed and
`autor` itself was switched to `mistral-small3.2:latest` (options as
previously used for `autor_mistral`) - there is now only ONE writer
(Mistral) there, with no selection field in the Architect interview anymore.
Reason: Mistral clearly proved superior to Hermes3/Qwen3 in practice. See
section 5.2 for details on author-model detection (now trivial in the GUI
backend).

**Why `think` is `false` for most roles even though `gemma4` supports
thinking mode:** roles whose response is itself a long piece of running
text (copy editor, correction roles) would risk having the token budget
consumed by thinking before the actual text even begins, if thinking mode
were active. Only `architekt`, `anachronismus`, `kontinuitaet` keep
thinking mode, because their answer is shorter and the task (asking
questions, checking tables) can meaningfully use multi-step reasoning.

---

## 5. Core algorithms (important for a reimplementation)

### 5.1 Folder name from title

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

Used in two places: for the `neu` (new) command (new folder name from the
typed title) and for the automatic project-folder rename after the
Architect conversation (see 5.16).

### 5.2 Author-model selection (Hermes3/Qwen3/Mistral)

Question 3 in the Architect interview determines which model actually
writes the story. `autor_rolle_erkennen(geruest)` (GUI backend:
`app/core/geruest.py`) reads the field from the frame section:

```python
def autor_rolle_erkennen(geruest: str) -> str:
    treffer = re.search(r"Autor-Modell\s*[:\-]?\s*([A-Za-z0-9 ]+)",
                         geruest, re.IGNORECASE)
    if not treffer:
        return "autor"
    wert = treffer.group(1).lower()
    if "mistral" in wert:
        return "autor_mistral"
    if "qwen" in wert:
        return "autor_qwen"
    return "autor"
```

The return value is directly a key into `ROLLEN` (see section 4) and is
passed both to the main writing call and to every continuation call in
`_bei_bedarf_fortsetzen` - so the same story stays with the once-chosen
model across all chapters and continuation attempts.

The `autor_qwen` role (in the GUI backend `app/core/rollen.py`, originally
called `autor_qwen_test`) initially existed in the CLI predecessor only as
a pure comparison role for `./novelle.py testen <n>`. In the GUI backend,
Qwen3 is usable as a fully equal second Author choice alongside Hermes3,
not just as a test/comparison mode - the A/B comparison command itself is
pure CLI history and was not reimplemented in the GUI backend.

The `autor_mistral` role was a pure GUI-backend addition with no CLI
predecessor (no counterpart in `pre-GUI/novelle.py`) - a third, equally
valid Author choice alongside Hermes3 and Qwen3, selected via
"Autor-Modell: Mistral" in the outline.

If the field is missing (older projects predating this question), the
return value is always `"autor"` (Hermes) - unchanged behavior for existing
projects.

**GUI backend deviation (as of 2026-08-13):** everything described above
still applies to the CLI. In the GUI backend, `autor_rolle_erkennen()`
(`app/core/geruest.py`) is now trivial - it no longer reads the outline
text at all and always returns `"autor"` (= Mistral, see section 4). There
is no longer an author-model question in the Architect interview; the
`autor_qwen`/`autor_mistral` roles no longer exist in the GUI backend.

### 5.3 Additional note for individual writing attempts (`schreiben <n> [hint...]`)

`cmd_schreiben` optionally accepts a freely worded, space-joined hint text
starting from `args[1:]`. Use case: the continuity reviewer reports severe,
accumulated contradictions (e.g. a planned character is missing entirely,
the secret resolves without motivation) - in that case, reworking by hand
is usually more effort than a new writing attempt, and the hint lets you
tell the next attempt specifically what to avoid.

The hint is appended as its own, clearly marked block at the end of both
the main prompt and every continuation prompt (`_bei_bedarf_fortsetzen`
receives it as an additional argument so it isn't lost during an automatic
continuation):

```python
zusatz_block = (
    f"\n\n=== ZUSAETZLICHER HINWEIS FUER DIESEN VERSUCH ===\n{zusatzhinweis}\n"
    f"Dieser Hinweis gilt nur fuer diesen einen Schreibversuch und hat "
    f"Vorrang, falls er einem Detail des Geruests widerspricht."
    if zusatzhinweis else ""
)
```

Important: the hint is **never persisted** - it exists only for the current
process invocation and is gone again once `cmd_schreiben` finishes. A GUI
that wants to offer a "rewrite this attempt with the following addition"
feature must resend the text itself on every retry.

### 5.4 Target word count per chapter: read dynamically from the outline

**Earlier version (since removed):** a hard-coded dictionary
`ZIELWOERTER = {1: 1500, 2: 1600, ...}` that only fit the very first test
story (6 chapters) and provided no target value for any other chapter
count.

**Current version:** `_kapitelplan_erkennen(geruest: str) -> dict[int, int]`
reads chapter numbers and target word counts directly from the free text of
the chapter-plan section:

```python
_ZAHLWORT = {"eins":1, "zwei":2, ..., "zwanzig":20}   # German number words 1-20

kapitel_muster = r"Kapitel\s+(\d{1,2}|eins|zwei|...)\b"
# for every match: take the text up to the next match as a "block",
# and search within it for:
wort_muster = r"([\d][\d.,]*)\s*w(?:oe|ö)rter"   # covers both "Wörter" AND "Woerter"
```

Result: `{1: 1500, 2: 1600, 6: 1300}` – even with gaps (e.g. if chapters
3-5 weren't recognized cleanly in the text), the recognized entries remain
valid; missing ones simply yield no target value (not an error).

**Important for a reimplementation:** `max(ergebnis.keys())` gives the
total number of planned chapters and is also used for the automatic
merge-on-completion (5.17). If the dictionary is empty (chapter plan not
yet filled in, or not recognizable), the function returns `{}`, and all
automations that depend on it (target-word-count display, automatic
continuation, auto-export) simply stay inactive, without throwing an
error.

**GUI backend extension (since 2026-08-20):** `kapitelplan_pruefen(geruest)`
(`app/core/geruest.py`) additionally checks, when an outline is saved
manually (`PUT .../geruest`), ONLY the `## Kapitelplan` section for two
silent failure modes that `kapitelplan_erkennen()` otherwise swallows
without complaint: a chapter heading with no recognizable target word
count, and the same chapter number declared twice (`kapitelplan_erkennen()`
then silently keeps only the first declaration). Unlike the pure read path
above, such a save attempt is actively **rejected** with a concrete error
message (HTTP 400) before anything is written - the trigger was an
incident where, during manual chapter-plan editing, all target-word-count
lines were accidentally removed and the automatic mode subsequently
falsely reported "no chapter structure". The frontend additionally offers a
structured card editor JUST for the chapter plan
(`frontend/src/utils/kapitelplan.ts` + `KapitelplanEditor.tsx`) with target
word count as a required numeric field, which prevents this error
client-side before every save attempt already - the server-side check
still remains in place as a second line of defense, e.g. in case the
client-side parser fails on a chapter-plan format it doesn't recognize (in
that case it falls back to plain free text instead of losing data).

**"Vergangene Zeit" (time elapsed) field (since 2026-08-28):** An additional
optional field per chapter block (not required, not part of
`kapitelplan_pruefen()`), e.g. `Vergangene Zeit: three days later, a new
evening`. Evaluated by the Author persona (empty -> the Author picks the
shortest still logically plausible time jump itself) and additionally
extracted via a new function `vergangene_zeit_fuer_kapitel_erkennen(geruest,
n)` (`app/core/geruest.py`, analogous to `jahr_fuer_kapitel_erkennen()`) and
passed to the continuity reviewer as its own context block
(`app/api/pipeline.py: _pruefe_kapitel`), so it can flag a contradiction
between the planned and the actually narrated time span.

### 5.5 Automatic continuation for chapters that are too short (opt-in, default off)

**Important behavior change compared to earlier versions:** automatic
continuation originally ran unconditionally for every chapter that was too
short. It is now **disabled by default** and must be deliberately turned on
in the outline, because it repeatedly turned out to be the cause of severe
errors (see 5.10 and 5.11).

```python
def _automatische_fortsetzung_aktiviert(geruest: str) -> bool:
    treffer = re.search(r"Automatische Fortsetzung\s*[:\-]?\s*([A-Za-zÄÖÜäöüß]+)",
                         geruest, re.IGNORECASE)
    if not treffer:
        return False          # default: OFF, even without the field
    wert = treffer.group(1).lower()
    return wert.startswith("ein")
```

`cmd_schreiben` checks this flag before `_bei_bedarf_fortsetzen` is even
called:

```python
if ziel and _automatische_fortsetzung_aktiviert(geruest):
    text = _bei_bedarf_fortsetzen(n, text, ziel, geruest, vorher, stufe,
                                   zusatzhinweis, autor_rolle)
elif ziel and woerter(text) < ziel * FORTSETZEN_SCHWELLE:
    info(...)   # just a hint, chapter is left unchanged
```

**If continuation is enabled**, the existing mechanism runs unchanged: if
`wortzahl(text) < ziel * 0.70`, up to **3** continuation calls are made.
Each call only receives the last 600 characters of the text so far as an
anchor point (not the entire text, to save context), plus the same content-
rating directive (section 5.12) and the same author-model role (section
5.2). After every continuation call:

1. Remove meta lines (separator dashes, word-count notes like
   "Gedankenerhebung - 1300 Wörter." or "495 Wörter. Halte dich an die
   Vorgaben.")
2. Remove leading duplicates: the first *k* paragraphs of the continuation
   are compared against the last *k* paragraphs of the text so far
   (`difflib.SequenceMatcher`, similarity > 0.75), descending from *k=4*
   down to *k=1*. Reason: models sometimes repeat the previous paragraph
   despite the instruction, before actually delivering new text.
3. Chapter-restart detection (5.10) and premature-chapter-ending detection
   (5.11) run again after EVERY merge step - a continuation can also go off
   the rails multiple times in a row.

**Important for a GUI reimplementation:** the warning shown when
continuation is turned off is informational, not an error - `schreib()`
still runs normally and saves the shorter chapter.

### 5.6 Language-drift detection

Counts occurrences of common English function words
(`the, and, was, were, with, his, her, ...`) relative to total word count.
Threshold: 3%. A pure heuristic alarm, not a hard language-detection tool.

### 5.7 Evasive-phrasing detection

Fixed list of known vague euphemisms (e.g. "Sprache des Samens", "Blumenkelch",
"eins wurden"), simple substring search on lowercased text.

### 5.8 Narrative-perspective check (first-person drift)

Checks whether the outline prescribes "Dritte Person" (third person) in the
frame section, but a clear first-person perspective appears outside quoted
dialogue (e.g. "meine Hand" / "my hand", "sagte ich" / "I said") - a sign
that the text (usually during an automatic continuation) has unintentionally
slipped into first person.

```python
_ICH_PRONOMEN_MUSTER = re.compile(
    r"\b(ich|mein|meine|meinen|meiner|meinem|meines|mir|mich)\b", re.IGNORECASE)

def _erzaehlperspektive_pruefen(text, geruest, kontext="", schwellwert=2):
    if not re.search(r"Dritte Person", geruest, re.IGNORECASE):
        return   # only relevant if third person is explicitly prescribed
    ohne_dialog = re.sub(r'„[^"“]*["“]', ' ', text)      # German quotation marks
    ohne_dialog = re.sub(r'"[^"]*"', ' ', ohne_dialog)   # ASCII quotation marks
    treffer = _ICH_PRONOMEN_MUSTER.findall(ohne_dialog)
    if len(treffer) >= schwellwert:
        warn(...)
```

Quoted dialogue is stripped out beforehand, since "ich" (I) there is normal
direct speech, not a shift in the narrating voice's perspective. Both
common quotation-mark styles are covered (German „..." and ASCII "...").
Threshold 2: a single "ich" outside dialogue (e.g. in free indirect
speech) does not yet trigger an alarm - only from two matches onward.

### 5.9 Form-of-address check (Sie/du consistency)

Checks whether, within the same chapter, both formal address (Sie/Ihnen -
"you" formal) and informal address (du/dich/dir/dein - "you" informal)
occur in quoted dialogue:

```python
_FORMELL_ANREDE_MUSTER = re.compile(r"\b(Sie|Ihnen)\b")
_INFORMELL_ANREDE_MUSTER = re.compile(r"\b(du|dich|dir|dein\w*)\b")

def _anredeform_pruefen(text, kontext=""):
    dialogzeilen = re.findall(r'„([^"“]*)["“]', text)   # German quotation marks
    dialogzeilen += re.findall(r'"([^"]*)"', text)        # ASCII quotation marks
    dialogtext = " ".join(dialogzeilen)
    foermlich = _FORMELL_ANREDE_MUSTER.findall(dialogtext)
    informell = _INFORMELL_ANREDE_MUSTER.findall(dialogtext)
    if foermlich and informell:
        warn(...)
```

**Important detail trap if this is reimplemented in the GUI:** only
address words INSIDE quotation marks count - narrative text outside quoted
dialogue naturally contains "sie" (she/they) frequently as a normal
personal pronoun and would otherwise be a constant false alarm. The dialogue
extraction must cover **both** quotation-mark styles (German „..." and
ASCII "..."), otherwise the check misses every piece of dialogue that was
correctly written in the required German format - that's exactly what
happened in a real test case: an early version only checked for ASCII
characters and stayed silent on cleanly formatted German dialogue, even
though a Sie/du switch was clearly present.

A switch can well be intentional across multiple chapters (growing
familiarity), but within a single chapter - especially during a first
encounter - it's usually an unintentional slip.

### 5.10 Chapter-restart detection (duplicate chapter heading)

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

Background: during an automatic continuation (5.5), the model sometimes
writes, despite explicit instructions, not a real continuation but an
entirely new, often contradictory second pass over the whole chapter -
including its own, repeated heading. The existing duplicate filter (leading
duplicates, see 5.5 point 2) doesn't catch this, because it only compares
verbatim repetitions - a newly worded, different second version slips
through there.

**Important detail trap:** the pattern absolutely requires
`re.MULTILINE`, so that `^` matches the start of every line instead of only
the start of the whole text - an early test run during development failed
exactly on this (the function recognized nothing until the flag was added).

Called twice: right after the first draft, and after every single
continuation merge in `_bei_bedarf_fortsetzen`.

### 5.11 Premature-chapter-ending detection

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
        return text     # short, rounded closing sentence - probably legitimate
    warn(...)
    return text[:grenze].rstrip()
```

A third manifestation of the same underlying problem as 5.10: the text
declares itself finished partway through (e.g. "The chapter ended with
them drinking their cups of tea…"), but then keeps writing anyway with a
completely new, unplanned scene (typically "Two days later…"). Unlike
5.10, the marker is not its own line but embedded in a normal narrative
sentence - hence a full-text search (`re.search`) rather than a line-by-line
comparison like the meta-line filter.

Cuts off only after the end of the sentence (the next period after the
match), not directly at the match location - the sentence containing the
self-declaration itself is kept, only what comes after it disappears.

Called twice, like 5.10: after the first draft and after every
continuation merge.

### 5.12 Content-rating directives

Three fixed text blocks (`STUFE_DIREKTIVEN["voll"|"angedeutet"|"jugendfrei"]`
- "full"/"implied"/"family-friendly"), appended to the Author prompt on
**every** writing and continuation call. Only `voll` (full) leaves the
Author persona's own behavior unchanged; the other two levels instruct the
model to ignore the persona's own explicitness guidelines for this call.

In addition: `_explizitheit_pruefen()` checks the text after writing, using
word-boundary regex (`\b...\b`), against a fixed list of unambiguously
explicit terms (e.g. "oralsex", "klitoris", "penetration"). Only relevant
when the level is not "voll".

### 5.13 Spell-checking via hunspell (external system dependency)

The hunspell query itself lives in a shared helper function,
`_hunspell_unbekannte_woerter(text)` (unknown words), used from two
different places (5.13 for the automatic hint, 5.13a for the interactive
review). It is the only place in the script that invokes an **external
system command** instead of pure Python logic or the Ollama API:

```python
subprocess.run(
    ["hunspell", "-d", "de_DE", "-l"],
    input=text, capture_output=True, text=True, timeout=30,
    env={**os.environ, "LC_ALL": "C.UTF-8"},
)
```

Return value: `None` on error/hunspell unavailable (deliberately
distinguished from an empty list, which means "checked cleanly, nothing
found"), otherwise a sorted, deduplicated list of unknown words.

System prerequisite: `apt-get install hunspell hunspell-de-de`.

**Important detail trap if this is reimplemented in the GUI:** without
`LC_ALL=C.UTF-8` (or another UTF-8 locale), hunspell mis-splits German
umlauts and a large portion of the output turns into garbage (e.g.
"während" gets cut down to "hrend"). This is not caused by the dictionary
(which correctly declares `SET UTF-8` in its `.aff` file), but by the
system environment the process runs in.

The `-l` (list) flag outputs exactly the words hunspell doesn't know, one
per line. The script filters out words shorter than three characters
(usually leftover punctuation) - there is **no automatic distinction**
between real typos and proper nouns/technical terms that simply aren't in
the dictionary. Reporting deliberately stays coarse; the human does the
classification.

**Error handling:** if `hunspell` is not installed (`FileNotFoundError`) or
the call fails, the check is disabled **globally for the rest of the
process** (module variable `_HUNSPELL_VERFUEGBAR`), after a one-time
warning. This prevents an error message from reappearing for every single
chapter if the tool is fundamentally missing.

`_rechtschreibpruefung(text, kontext)` (the automatic, non-interactive
hint) calls `_hunspell_unbekannte_woerter()` and, if there are findings,
only prints a single warning line with the full word list, with no
interaction. Call sites: at the end of `cmd_schreiben` (after the finished
chapter text, including any automatic continuations) and at the end of
`cmd_lektorieren` (after the grammatical correction, on the already
cleaned-up text).

### 5.13a Interactive spell-check review (`rechtschreibung`)

`cmd_rechtschreibung(args)` is one of two commands (alongside `architekt`,
`neu`/`init`, and `epoche-erstellen`) that run **interactively via
`input()`** - relevant for a GUI that can otherwise call every other
command non-interactively via subprocess.

Flow:
1. `_hunspell_unbekannte_woerter(text)` provides the word list (see 5.13).
2. For every word: `_satz_mit_wort_finden(text, wort)` uses a rough
   sentence-boundary regex (`(?<=[.!?])\s+`) to find a sentence that
   contains the word as its own word (`\b...\b`), and shortens it if
   needed to about 220 characters around the match. Returns `None` if no
   clear sentence boundary was found (the word still exists in the text
   regardless - not an error, just less context in the display).
3. Outputs word + sentence, then an `input()` prompt.
4. Empty input: word is left unchanged, move to the next finding.
5. Non-empty input: `re.sub(r"\b" + re.escape(wort) + r"\b", eingabe, text)`
   replaces **all** occurrences of the word in the entire chapter text (not
   just the currently displayed spot), case-sensitively as in the original.
6. `Ctrl+C`/EOF during input aborts the review, but **keeps any
   replacements already made** and saves them.
7. Only if at least one replacement was made is the file overwritten
   (`schreib()`, with automatic `.bak` backup of the previous version).
   Without changes, the file is left untouched.

**For a GUI reimplementation:** this command is particularly well suited to
a dedicated GUI view instead of a terminal emulation - the GUI can adopt
`_hunspell_unbekannte_woerter()` and `_satz_mit_wort_finden()` directly
(pure functions with no interaction logic) and implement the actual review
loop (list of word+sentence+input field) in its own UI, instead of
reimplementing the terminal `input()` loop.

### 5.14 State backfilling (automatic catch-up of `stand`)

```python
def _stand_sicherstellen(n: int):
    if n <= 1:
        return   # stand_00.md is optional, no catch-up needed
    vorheriger_stand = stand_datei(n - 1)
    if vorheriger_stand.exists():
        return
    vorheriges_kapitel = kapitel_datei(n - 1)
    if not vorheriges_kapitel.exists():
        warn(...)   # chapter n-1 was never written - not recoverable
        return
    warn(...)   # state n-1 is now being backfilled automatically
    cmd_stand([str(n - 1)])
```

Called at the start of `cmd_schreiben`, before the outline is even read.
Covers the case where `stand <n-1>` was simply forgotten before
`schreiben <n>` was called - without this safeguard, chapter n would build
on an outdated or missing state.

**Two deliberate exceptions:**
- Chapter 1 is never checked - a missing `stand_00.md` is the correct
  normal case if the Architect did not produce a starting situation (see
  section 2.1/`## Ausgangslage vor Kapitel eins`).
- If both the state and chapter n-1 are missing, only a warning is issued,
  nothing is generated automatically - that's a different problem
  (chapters not written in order) that can't be healed automatically.

`cmd_stand` itself prints a warning on invocation ("The chronicler should
only run after the correction step..."), which also appears on this
automatic invocation - that's intentional, since the backfilled state is
based on the current (possibly still uncorrected) chapter text.

### 5.15 Title page in chapter 1 (no longer added at export time)

**Earlier version (since removed):** the title page was only generated by
`cmd_export` and prepended to the combined `gesamt.md` - chapter 1 on its
own therefore never had a title.

**Current version:** `_titelseite_erzeugen(geruest)` (generate title page)
is called directly inside `cmd_schreiben`, only for `n == 1`, after all
other corrections/sections, shortly before saving:

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

The idempotency check (is the title page's first line already present?)
prevents a duplicate title page if `schreiben 1` is called again.
`cmd_export`/`cmd_zusammenfassen` now only concatenate the chapters raw,
without their own title logic - the title page comes along automatically
as soon as `kapitel_01.md` is part of the merge.

`_titelseite_erzeugen` itself builds the subtitle from title + year + era
(from the marker file `projekt/.epoche` stored at project creation), e.g.
"Eine Geschichte aus dem Regency im Jahre 1815" ("A story from the Regency
era, in the year 1815"). If the title is missing from the outline, an
empty string is returned (not an error) - the title page is then simply
omitted.

**GUI backend extension (since 2026-08-19):** `titelseite_erzeugen()`
(`app/core/geruest.py`) additionally accepts an optional third parameter
`einleitungssatz_vorlage` (intro-sentence template) - the content of
`projekt/einleitungssatz.txt`, a 5th file per era (alongside
architekt.txt/autor.txt/pruefer_anachronismus.txt/verbotsliste.md, see
`app/api/epochen.py`) with a `{jahr}` placeholder, copied 1:1 at project
creation just like verbotsliste.md. If the template is present, it
replaces the generic "Eine Geschichte aus dem {epoche}..." ("A story
from the {era}...") text - reason: the raw era folder name can't always be
inserted grammatically correctly into the sentence (e.g. "aus dem
Altes-Aegypten" instead of "aus dem alten Ägypten" / "from ancient
Egypt"). If the file is missing (older eras/projects), the folder-name-
based fallback applies unchanged. A later change to the central era does
NOT affect already-created projects (same decoupling as with the personas).

### 5.16 Project-folder renaming based on title

```python
def _projektordner_nach_titel_umbenennen(geruest: str):
    if list(PROJEKT.glob("kapitel_*.md")):
        return   # chapters already exist - no longer auto-rename
    titel_treffer = re.search(r"##\s*Titel\s*\n+(.+)", geruest)
    if not titel_treffer:
        return
    neuer_name = _ordnername_aus_titel(titel_treffer.group(1).strip())
    aktueller_pfad = Path.cwd()
    if aktueller_pfad.name == neuer_name:
        return
    neuer_pfad = aktueller_pfad.parent / neuer_name
    if neuer_pfad.exists():
        warn(...)   # target name already exists - do not rename
        return
    aktueller_pfad.rename(neuer_pfad)   # wrapped in try/except OSError
```

Called at the end of `cmd_architekt`, right after `geruest.md` and,
where applicable, `stand_00.md` have been saved, still **before** the
`break` that ends the Architect conversation.

**Safety net:** if `kapitel_*.md` files already exist in the project
folder, no more renaming happens - this can only occur if `architekt` is
called a second time on an already-started project. At that point, renaming
would risk changing file paths that are actively being worked on.

**GUI backend deviation (since 2026-08-20):** `titel_erkennen()`
(`app/core/geruest.py`, the counterpart to `titel_treffer` above) strips a
leading option label (`a)`/`b)`/`c)`/`d)`) from the detected title.
Reason: the Architect persona is instructed to provide ONE title, but
occasionally responds with the unresolved multiple-choice list from the
title question ("a) suggestion ... b) own title") instead of committing to
one - especially when an already fully filled-in offline template document
is passed through in the first turn without any follow-up question.
Without this stripping, the raw option label "a) " ended up unchanged in
the slugified folder name (incident:
a-Blut-und-Ahornlaub-Die-Ehre-des-Verbotenen).

**Important for a reimplementation:** `Path.cwd()` is renamed, not
`PROJEKT` (the `projekt/` subdirectory) - the entire outer project folder
(including `personas/`, `projekt/`, the symlink to `novelle.py`) moves
along with it. On POSIX, the running process's working directory remains
valid after the rename (tracked via the inode, not the path name) - all
further relative file access within the same process continues to work
unchanged. A GUI that instead holds its own filesystem handle/path string
for the project folder must update it itself after the rename, since it
doesn't automatically benefit from the operating system's inode trick.

Purely informational and best-effort: an `OSError` during the actual rename
(e.g. a permissions issue) is only reported as a warning, nothing is
aborted - the Architect conversation is still considered successfully
finished.

### 5.17 Automatic merge on story completion, and manual summarizing

```python
geplant = _kapitelplan_erkennen(geruest)
letztes_geplantes_kapitel = max(geplant.keys()) if geplant else None
vorhandene_kapitel = sorted(PROJEKT.glob("kapitel_*.md"))

if letztes_geplantes_kapitel and n == letztes_geplantes_kapitel \
        and len(vorhandene_kapitel) >= letztes_geplantes_kapitel:
    cmd_export([])   # equivalent to ./novelle.py export
```

`cmd_export` only **reads** the existing `kapitel_*.md` files and merges
them into `projekt/gesamt.md` (`schreib(..., force=True)`, i.e. it
overwrites an older `gesamt.md` with no backup, since it's purely derived).
The individual chapter files themselves are **not modified or deleted**.

**Trigger condition in detail:** the current `n` must match the highest
chapter number recognized in the outline, AND at least as many
`kapitel_*.md` files must exist as planned. If the chapter plan couldn't be
parsed (`geplant == {}`), nothing happens – neither an error nor a
warning, the automation simply stays inactive and `export` must be called
manually.

**Manual interim summarizing (`zusammenfassen`):** a new command that
allows the same merge at any time, not just at the end:

```python
def cmd_zusammenfassen(args):
    if not args:
        cmd_export([])          # identical to 'export': projekt/gesamt.md
        return
    von, bis = int(args[0]), int(args[1])
    if von > bis:
        von, bis = bis, von     # order gets normalized
    alle_kapitel = sorted(PROJEKT.glob("kapitel_*.md"),
                           key=_kapitelnummer_aus_dateiname)
    ausgewaehlt = [p for p in alle_kapitel
                   if von <= _kapitelnummer_aus_dateiname(p) <= bis]
    # missing numbers within the range -> warning, no abort
    ziel_name = f"zusammen_{von:02d}-{bis:02d}.md"
    schreib(PROJEKT / ziel_name, ganz, force=True)
```

Without arguments, `zusammenfassen` is identical to `export` (writes
`gesamt.md`). With two numbers, a separate file
`zusammen_<from>-<to>.md` is created (two digits, zero-padded), so that
interim states don't collide with the final `gesamt.md`. If a chapter
number is missing within the given range, a warning is issued and the
process continues with what's available instead of aborting.

**For a GUI reimplementation:** the same logic can be reimplemented
independently of the CLI, as long as the GUI also applies
`_kapitelplan_erkennen()` (or an equivalent) to the current `geruest.md`
content and counts the existing `kapitel_*.md` files in the project folder.

### 5.18 Era creator (`epoche-erstellen`)

Pure Python question form, **no LLM call**. Collects twelve answers into a
dictionary, generates four files from them via string templates:
`architekt.txt`, `autor.txt`, `pruefer_anachronismus.txt`, `verbotsliste.md`.
Independent of the actual Architect interview (which now covers 13
questions, see 5.2 and 2.1) - `epoche-erstellen` merely lays the groundwork
for a new era, before any Architect conversation for a specific story takes
place.

Branches after question 2 ("real or invented"):
- **Real:** `pruefer_anachronismus.txt` gets the historical variant (checks
  against real-world history).
- **Invented:** gets the consistency/brand-distance variant (checks against
  self-defined world rules and closeness to known franchises).

The result is deliberately a **rough draft** with "HIER ERGÄNZEN" ("ADD
HERE") markers in `verbotsliste.md` and `pruefer_anachronismus.txt` – this
content requires research that the local model can't reliably provide.

---

## 6. CLI commands (reference for subprocess calls)

All commands: `./novelle.py <command> [arguments]`

| Command | Arguments | Interactive? | Modifies files |
|---|---|---|---|
| `init` | – | yes (era selection) | personas/, projekt/ (current folder) |
| `neu` | `<title...>` | yes (era selection) | new folder |
| `epoche-erstellen` / `neueepoche` | – | yes (12 questions) | epochen/\<new\>/ |
| `architekt` | – | yes (interview, 13 questions) | projekt/geruest.md, possibly projekt/stand_00.md, possibly renames the project folder (see 5.16) |
| `schreiben` | `<n> [hint...]` | no | projekt/kapitel_\<n\>.md, befunde_\<n\>.md |
| `testen` | `<n>` | no | projekt/vergleich_kapitel_\<n\>_{hermes,qwen}.md |
| `pruefen` | `<n>` | no | projekt/befunde_\<n\>.md |
| `anwenden` | `<n>` | no | projekt/kapitel_\<n\>.md (+ .bak) |
| `lektorieren` | `<n>` | no | projekt/kapitel_\<n\>.md (+ .bak) |
| `rechtschreibung` | `<n>` | **yes** (input per finding) | projekt/kapitel_\<n\>.md (+ .bak), only if at least one replacement was made |
| `stand` | `<n>` | no | projekt/stand_\<n\>.md (+ possibly automatically projekt/gesamt.md, see 5.17) |
| `gesamt` | – | no | projekt/befunde_gesamt.md |
| `export` | – | no | projekt/gesamt.md |
| `zusammenfassen` | – or `<from> <to>` | no | projekt/gesamt.md (without arguments) or projekt/zusammen_\<from\>-\<to\>.md |
| `modelle` | – | no | – (output only) |

**Exit codes:** `0` on success, `1` on error (the `fehler()` function calls
`sys.exit(1)`). On abort via Ctrl+C: exit code `130`.

**Output convention:** user-readable status messages (`info`, `ok`, `warn`,
`fehler`) go to **stderr**, with prefixes `==>`, ` ok`, `  !`, `FEHLER`
(ERROR). A GUI parsing stdout/stderr should rely on these prefixes, not on
the exact wording (which can change).

**Interactive commands** (`init`, `neu`, `epoche-erstellen`, `architekt`,
`rechtschreibung`) read from stdin via `input()`. When embedding via
subprocess, the GUI must keep stdin open and write answers line by line,
after the respective prompt text has appeared on stderr.

---

## 7. Known limitations (relevant for GUI error handling)

- The filter logic for `anwenden` (apply) (only "hoch"/high + a concrete
  suggestion) is a **prompt instruction**, not a deterministic code check.
  A model can behave differently; the GUI should show a diff after every
  `anwenden` call (the CLI already does this via
  `_aenderungen_anzeigen()`).
- `_kapitelplan_erkennen()` (section 5.4) is likewise regex over free
  text, not a fixed data format. Unusual phrasing by the Architect (e.g.
  "Zielumfang ca. 1.500" instead of "Zielwortzahl: 1.500 Wörter") is not
  recognized. This affects both the target-word-count display and the
  automatic merge at the end (section 5.17) – when in doubt, the automation
  simply stays off; there is no failure mode that silently produces wrong
  values. **Exception in the GUI backend:** when an outline is saved
  manually via the chapter-plan editor, `kapitelplan_pruefen()` (see 5.4)
  actively rejects an incomplete chapter plan with an error message,
  instead of saving it without complaint - so there IS a genuine failure
  mode there.
- Year and content-rating detection is regex-based and expects certain word
  patterns in the outline. Free-text deviations by the Architect role can
  cause default values to kick in (year "unbekannt"/unknown, content rating
  "voll"/full, author model "Hermes3", automatic continuation "Aus"/off).
  For the latter two fields, the fallback value is deliberately chosen to
  match the safer/established behavior, not arbitrarily.
- There is no database, no locks, no multi-user capability. Two
  simultaneous write accesses to the same project folder are not
  safeguarded.
- Symlinks: `neu` attempts to create a symlink for `novelle.py` in the new
  folder; if that fails (e.g. on some network drives), it falls back to
  copying instead, with a warning. A GUI on Windows should take this into
  account (symlinks there may need admin rights or developer mode). The
  same limitation applies to the automatic project-folder rename (section
  5.16) - it uses `Path.rename()`, which can fail on Windows when file
  handles are open within the folder; on Linux/POSIX (the actual target
  system for this script) this is not an issue.
- All mechanical safety nets in section 5 (5.8-5.11) are **regex-based
  heuristics**, not semantic checks. They catch known, recurring error
  patterns, but do not guarantee that a chapter is free of content errors -
  proofreading it yourself, or the LLM-based continuity reviewer, both
  remain necessary.
