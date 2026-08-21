🇩🇪 [Deutsche Version](Bedienungsanleitung.md)

# User Guide: novelle.py

Automated five-role pipeline for AI-written short stories and novellas using
local Ollama models. This guide covers day-to-day use via the command line.

---

## Cheat sheet: the workflow in short

| Step | Command |
|---|---|
| Create a new story | `./novelle.py neu <title>` |
| Work out the outline (once per story) | `./novelle.py architekt` |
| **— per chapter —** | |
| Write chapter, auto-review | `./novelle.py schreiben <n>` |
| Read through the findings | `cat projekt/befunde_<n>.md` |
| Apply safe anachronism fixes | `./novelle.py anwenden <n>` |
| Remaining findings, your own judgment | *(review by hand)* |
| Smooth out grammar/spelling | `./novelle.py lektorieren <n>` |
| Go through unknown words one by one | `./novelle.py rechtschreibung <n>` |
| **Record state – always last** | `./novelle.py stand <n>` |
| **— at the end —** | |
| Final check over the whole text | `./novelle.py gesamt` |
| Pull an interim draft without being finished | `./novelle.py zusammenfassen` resp. `zusammenfassen 1 3` |

> **Alternative start:** Instead of `neu` (creates a new folder), you can also
> use `./novelle.py init` to populate the **current** folder – both ask for
> the desired era/setting ("Epoche").
>
> **Why is `stand` always last?** The chronicler role ("Chronist") is meant to
> summarize the final version, not one with still-open errors. On the last
> chapter planned per the outline, `stand` also automatically assembles
> everything into `projekt/gesamt.md` – `gesamt` afterwards is then just the
> optional fine-grained check over the complete text.

Details on each individual command: section 4. Details on automatic
assembly: section 6.

---

## 1. What the script does

`novelle.py` orchestrates several specialized AI roles that work on a story
one after another, instead of leaving everything to a single model:

| Role | Task |
|---|---|
| **Architect** ("Architekt") | Interviews you and creates the story outline (characters, conflict, chapter plan) |
| **Author** ("Autor") | Writes the actual chapters, one chapter per invocation |
| **Anachronism reviewer** ("Anachronismus-Prüfer") | Finds historical errors, or (for invented worlds) closeness to trademarks |
| **Continuity reviewer** ("Kontinuitäts-Prüfer") | Finds contradictions between chapters |
| **Chronicler** ("Chronist") | Summarizes the current state after each chapter (characters, open threads) |
| **Copy editor** ("Lektor") | Automatically corrects grammar/spelling |
| **Anachronism corrector** | Automatically works in only the safest reviewer findings |

Each role runs with its own model and its own parameters (temperature,
context length, etc.), tuned to its specific task.

---

## 2. Folder structure

```
Novellen-Setup/
├── novelle.py              ← the script (the only real file)
├── personas/                ← era-independent roles, apply to every setting
│   ├── chronist.txt
│   ├── pruefer_kontinuitaet.txt
│   ├── lektor.txt
│   └── anachronismen_korrektur.txt
├── epochen/                 ← one library per era/setting
│   ├── Mittelalter/
│   │   ├── architekt.txt
│   │   ├── autor.txt
│   │   ├── pruefer_anachronismus.txt
│   │   └── verbotsliste.md
│   ├── Regency/    (same four files)
│   └── Zukunft/    (same four files)
│
└── Meine-Geschichte/         ← a project folder, created with `neu`
    ├── novelle.py             ← symlink to the central script
    ├── personas/               ← copy of the 7 personas for the given setting
    └── projekt/
        ├── geruest.md            ← story outline
        ├── stand_00.md, stand_01.md, ...
        ├── kapitel_01.md, kapitel_02.md, ...
        ├── befunde_01.md, ...
        └── verbotsliste.md
```

**Important:** every project folder is self-contained once created. Changes
to `epochen/` or the shared `personas/` only affect **newly** created
projects, not existing ones retroactively.

---

## 3. Getting started

```bash
cd Novellen-Setup
./novelle.py neu Der Markt von Rothenfeld
```

The title may contain spaces and umlauts; a filesystem-safe folder name is
generated from it automatically (`Der-Markt-von-Rothenfeld`).

The script then asks for the setting:

```
Welche Epoche/welches Setting soll verwendet werden?
    1) Mittelalter
    2) Regency
    3) Zukunft
```

("Which era/setting should be used? 1) Middle Ages 2) Regency 3) Future")

Then:

```bash
cd Der-Markt-von-Rothenfeld
./novelle.py modelle       # check whether the required Ollama models are present
./novelle.py architekt     # work out the outline
```

---

## 4. Command overview

### Creating a project

| Command | Effect |
|---|---|
| `./novelle.py neu <title>` | Create a new, standalone project folder (asks for the era/setting) |
| `./novelle.py init` | Like `neu`, but populates the **current** folder instead of creating a new one |
| `./novelle.py epoche-erstellen` (alias `neueepoche`) | Pure questionnaire (no LLM) for creating a **new setting** under `epochen/` |

### Writing

| Command | Effect |
|---|---|
| `./novelle.py architekt` | Interactive conversation, automatically produces `projekt/geruest.md`. Also asks for the author model and whether automatic continuation should be allowed (see sections 8 and 9), suggests three title options at the end, and automatically renames the project folder after the chosen title |
| `./novelle.py schreiben <n>` | Write chapter n, then automatically run both reviewers. Automatically checks beforehand whether `stand <n-1>` exists, and generates it itself if needed (see section 9) |
| `./novelle.py schreiben <n> "..."` | Same as above, with an additional free-form hint for this one attempt only – see section 11 |
| `./novelle.py testen <n>` | Write chapter n once with Hermes, once with Qwen – comparison only, does not change `kapitel_<n>.md` |
| `./novelle.py stand <n>` | Chronicler: summarize the state after (the corrected!) chapter n. If n is the **last** chapter planned per the outline, all chapters are automatically assembled into `projekt/gesamt.md` – the individual `kapitel_NN.md` files remain unchanged. |

### Reviewing and correcting

| Command | Effect |
|---|---|
| `./novelle.py pruefen <n>` | Re-run only the two reviewers |
| `./novelle.py anwenden <n>` | Automatically apply only anachronism findings with "high" confidence **and** a concrete replacement suggestion |
| `./novelle.py lektorieren <n>` | Correct grammar/spelling/register and overwrite the chapter directly |
| `./novelle.py rechtschreibung <n>` | Interactive: go through unknown words (hunspell) one by one with sentence context. Enter = keep, type a replacement word = replace everywhere in the chapter |

### Wrap-up

| Command | Effect |
|---|---|
| `./novelle.py gesamt` | Final check: run both reviewers over the **entire** text so far |
| `./novelle.py export` | Assemble all chapters into one file, `projekt/gesamt.md` |
| `./novelle.py zusammenfassen` | Like `export`, but callable manually at any time, for interim states. With a range (`zusammenfassen 1 3`) only chapters 1–3, into a separate file `projekt/zusammen_01-03.md` |
| `./novelle.py modelle` | Shows loaded/available Ollama models and whether the required ones are present |

---

## 5. Recommended workflow per chapter

```
./novelle.py schreiben 3      → writes chapter 3, reviews automatically
cat projekt/befunde_03.md     → read through the findings
./novelle.py anwenden 3       → apply safe anachronism corrections
[fix up by hand if needed]
./novelle.py lektorieren 3    → smooth out grammar/spelling
./novelle.py stand 3          → record the state ONLY NOW
```

**Why `stand` comes last:** the chronicler is meant to summarize the
*final* text, not an interim version with still-uncorrected errors.

Every step that overwrites a file (`anwenden`, `lektorieren`, re-running
`schreiben`) automatically backs up the previous version as
`<file>.<timestamp>.bak` – nothing is ever lost.

---

## 6. Automatic assembly at the end

Target word counts and the total number of chapters are **not** hardcoded;
they are read directly from the chapter plan in `geruest.md` on every call
(lines like "Kapitel drei: ... Zielwortzahl: 1.600 Wörter." – "Chapter
three: ... target word count: 1,600 words."). This works regardless of
whether the architect wrote chapter numbers as digits or spelled out.

As soon as you call `./novelle.py stand <n>` for the **last** chapter
planned per the outline, the following happens automatically:

1. All existing `kapitel_NN.md` files are assembled into `projekt/gesamt.md`
   (in chapter order, separated by blank lines).
2. The individual chapter files **remain unchanged** – if something needs to
   be reworked later, no interim states are lost.

If the chapter count could not be reliably determined from the outline
(e.g. because the outline hasn't been filled in yet, or was phrased very
freely), the automatic assembly is silently skipped – you can always trigger
it manually:

```bash
./novelle.py export              # all existing chapters
./novelle.py zusammenfassen      # the same, callable at any time
./novelle.py zusammenfassen 1 3  # only chapters 1 to 3, as an interim state
```

The title and subtitle page ("Eine Geschichte aus dem Regency im Jahre
1815" – "A story from the Regency era in the year 1815") is not generated
only when assembling; it already sits at the very start of `kapitel_01.md`
itself – so it automatically appears in every assembled file that includes
chapter 1.

## 7. The story outline (`geruest.md`)

Automatically generated and saved by the architect. Contains, among other
things:

- **Year/time reference** – must literally be preceded by the word "Jahr"
  ("year", e.g. "Jahr: 1815" or "Jahr 214 der Konkordanz-Zeitrechnung"),
  otherwise the reviewers won't find it automatically.
- **Content rating ("Jugendschutz-Stufe")** – `Voll` (full), `Angedeutet`
  (implied) or `Jugendfrei` (no adult content). Controls how explicit the
  author may write in each chapter. If missing (older projects), `Voll` is
  used automatically.
- **Author model ("Autor-Modell")** – `Hermes3` or `Qwen3`. Determines which
  installed model actually writes the story. If missing, Hermes3 is used
  automatically (see section 9a).
- **Automatic continuation ("Automatische Fortsetzung")** – `Ein` (on) or
  `Aus` (off). Controls whether a too-short chapter is automatically
  continued. If missing, `Aus` (off) is used automatically (see section 9b).
- **Chapter plan ("Kapitelplan")** – target event and target word count per
  chapter.

If you edit the outline by hand afterwards, it takes effect starting with
the next `schreiben` call.

---

## 8. The content rating

Question 2 in the architect interview:

| Rating | Meaning |
|---|---|
| **Voll** (Full) | Explicit scenes as described in the author persona |
| **Angedeutet** (Implied) | Closeness, kiss, implication – the scene ends before the actual act via a scene change |
| **Jugendfrei** (No adult content) | No physical intimacy beyond holding hands/an embrace/a chaste kiss |

After every `schreiben`, the script automatically checks whether clearly
explicit vocabulary still shows up despite "Angedeutet" or "Jugendfrei", and
warns you if so. This does not replace your own proofreading, but is a
quick first signal.

---

## 9. Automatic safety nets

The script does not blindly rely on the language model. The following
checks run automatically after every `schreiben`:

- **Evasive phrasing** – detects vague paraphrasing instead of scenes
  actually written out
- **Language drift** – detects when the text unexpectedly slips into
  English
- **Explicitness check** – see section 8
- **Spell-check (hunspell)** – checks after `schreiben` and `lektorieren`
  against a real German dictionary for made-up or misspelled words (e.g.
  "Schmettelving" instead of "Schmetterling" – "butterfly"). This
  complements the other checks with a different kind of error: a language
  model checks whether a word looks grammatically plausible, not whether it
  actually exists – an invented but grammatically fitting word often
  slips past it. Requires: `apt-get install hunspell hunspell-de-de`. If
  either is missing, the check is skipped once (with a notice), without
  disrupting the rest of the workflow. Proper names and rare technical
  terms inevitably show up in the list too – not an error, just skim
  through. For a convenient, interactive review see
  `./novelle.py rechtschreibung <n>`.
- **Truncation guard** – for `anwenden` and `lektorieren`: if the corrected
  version comes out noticeably shorter than the original, it is **not**
  applied automatically, only shown
- **Narrative-perspective check** – the outline mandates "third person", but
  if a clear first-person perspective shows up outside of dialogue ("my
  hand", "I said"), a warning is shown. Dialogue in quotation marks may of
  course contain "I" – that's normal direct speech, not an error.
- **Form-of-address check** – if both the formal address (Sie/Ihnen) and the
  informal one (du/dich/dir/dein) show up within dialogue in the same
  chapter, a warning is shown. An unmotivated switch mid-conversation is
  usually a slip, not a deliberate stylistic device.
- **Chapter-restart detection** – if the chapter heading appears a second
  time within the same chapter text, everything from the second heading
  onward is automatically cut off. This mostly happens when an automatic
  continuation (see 9b) produces a complete, often contradictory second pass
  of the chapter instead of a genuine continuation.
- **Premature-chapter-ending detection** – if the text declares itself
  finished partway through (e.g. "The chapter ended with…") but then keeps
  writing substantially further, everything from that point on is
  automatically cut off. Usually an unplanned new scene following an
  automatic continuation.
- **State-file safeguard** – before chapter n is written, the script checks
  whether `stand_(n-1).md` exists. If it's missing but chapter n-1 has
  already been written, `stand n-1` is generated automatically (presumably
  it was simply forgotten). Does not apply to chapter 1 – a missing
  `stand_00.md` is the correct, normal case there.

### 9a. Choosing the author model (Hermes3/Qwen3)

Question 3 in the architect interview determines which installed Ollama
model actually writes the story:

```
Autor-Modell: Hermes3
Autor-Modell: Qwen3
```

Applies to **every** writing and continuation call for this story. If
missing (older projects without this question), Hermes3 is used
automatically. This is independent of the `testen` command (section 4),
which always uses both models for comparison regardless of what's in the
outline.

### 9b. Automatic continuation (default: off)

Question 4 in the architect interview:

```
Automatische Fortsetzung: Ein
Automatische Fortsetzung: Aus
```

**Default is off ("Aus")**, even if the question was never asked or the
field was forgotten. Reason: automatically continuing a too-short chapter
has repeatedly been the cause of serious errors – the model sometimes tries
"by force" to reach the target word count instead of organically finishing
the scene, producing duplicate chapter headings, unmotivated new scenes, or
meaningless filler text.

If a chapter stays under the target word count with continuation switched
off, the script just shows a notice with the current word count – the
chapter remains unchanged. You can then add to it by hand, have it rewritten
with an extra hint (section 11), or deliberately switch continuation on for
this one story in the outline.

If it's switched on, the script tries up to three times to automatically
continue writing when a chapter stays clearly under the target word count.

---

## 10. Creating a new era/setting

```bash
./novelle.py epoche-erstellen
```

Pure questionnaire (12 questions, no AI call), asks among other things for:

- Name, real era or invented setting
- Time period, typical locations
- The central social order and the **one** status rule as a dramaturgical
  source of tension (e.g. primogeniture, a fraternization ban)
- For invented worlds: which known franchise to keep a distance from

**Important:** the result is a **rough draft**, not a finished setting. The
forbidden list and the reviewer checklist are only marked with "HIER
ERGÄNZEN" ("ADD HERE") – this part is best researched with a web search
(e.g. in a conversation with a larger AI model), not with the local model.

---

## 11. When a chapter deviates too far from the plan

Sometimes the author invents its own resolution that's incompatible with
the outline – a planned main character is completely missing, the central
secret resolves through a single sentence instead of the intended clues, or
the emotional state jumps without motivation. This usually shows up clearly
in `befunde_<n>.md` from the continuity reviewer: many severe contradictions
at once, not just one small detail.

**In such a case, don't fix it by hand.** With several simultaneous, deep
breaks, the chapter is rewritten faster than it is patched.

```bash
./novelle.py schreiben 3
```

Often, simply running it again is enough, because the author doesn't use a
fixed seed and each attempt comes out differently. If that's not enough, you
can give the next attempt an **additional, free-form hint** that applies to
this one run only:

```bash
./novelle.py schreiben 3 "Maggie muss anwesend sein und aktiv mitwirken. Das Geheimnis wird NICHT durch einen Kuss aufgelöst, sondern nur durch die Indizien aus dem Nebenstrang. Halte dich strikt an Ort, Figuren und Ereignis aus dem Kapitelplan."
```

("Maggie must be present and actively involved. The secret is NOT resolved
by a kiss, but only through the clues from the subplot. Stick strictly to
the location, characters and event from the chapter plan.")

The hint is prominently appended to the author prompt and takes precedence
if it contradicts a detail. It applies **only to this one attempt** – it is
never stored permanently anywhere. If a correction should apply permanently,
it belongs in the outline itself instead.

## 12. Common problems

| Symptom | Cause | Solution |
|---|---|---|
| `env: python3\r: No such file or directory` | Windows line endings (CRLF) in the file | `sed -i 's/\r$//' novelle.py` |
| Architect asks several questions at once | Model doesn't follow the one-question rule | Automatically caught (script only shows the first question) |
| Chapter breaks off mid-scene | Target word count too short, or model reluctance | Automatic continuation is **off** by default (section 9b) – chapter stays short, with a notice. If needed, set "Automatische Fortsetzung: Ein" in the outline, or have it rewritten with an extra hint (section 11) |
| `Ollama nicht erreichbar` ("Ollama unreachable") | Ollama server isn't running, or wrong URL | Check the `OLLAMA_URL` environment variable, default: `http://localhost:11434` |
| Wrong era/setting in a new project | Wrong choice made during `neu` | Manually overwrite `personas/*.txt` and `projekt/verbotsliste.md` from the correct `epochen/<name>/` folder |
| Terminal still shows the old folder name after `architekt` | The project folder was automatically renamed after the title (happens right after the architect conversation, before any chapter was written), but the terminal doesn't refresh its display on its own | Only the display is stale, not an actual inconsistency – `cd .` or a new terminal fixes it |

---

## 13. Environment variables (optional)

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Address of the Ollama server |
| `NOVELLE_PROJEKT` | `projekt` | Project folder (relative to the current directory) |
| `NOVELLE_PERSONAS` | `personas` | Personas folder of the current project |
| `NOVELLE_EPOCHEN` | `<script folder>/epochen` | Central era/setting library |
| `NOVELLE_GEMEINSAME_PERSONAS` | `<script folder>/personas` | Central, era-independent personas |

Normally none of these need to be set – the defaults fit the usual setup.
