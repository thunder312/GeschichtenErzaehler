🇩🇪 [Deutsche Version](Anleitung.md)

# Guide: Geschichten Erzähler

This guide describes how to use the **web interface** (not the CLI script
`novelle.py` — if you use that directly on the command line, see
`Bedienungsanleitung.md` instead).

---

## Cheat sheet: the workflow in short

| Step | Tab |
|---|---|
| Create a new story | **Projekte** (Projects) |
| Work out the outline ("Gerüst") (once per story) | **Architekt / Gerüst** (Architect / Outline) |
| **— per chapter —** | |
| Write the chapter, have it checked automatically | **Schreiben** (Write) |
| Apply safe reviewer corrections (anachronism, continuity, grammar) | **Prüfen & Anwenden** (Review & Apply) |
| Go through unknown words one by one | **Rechtschreibung** (Spelling) |
| Record the state — always last | **Stand & Export** (State & Export) |
| **— at the end —** | |
| Merge all chapters into one file, export as PDF, generate a cover image | **Stand & Export** (State & Export) |

> **Why "state" only after reviewing?** The Chronist ("Chronist") is meant
> to summarize the *final* version of a chapter, not one with still-open
> errors. For the last chapter planned according to the outline, "Stand
> erzeugen" (Generate state) additionally merges all chapters into one
> combined file automatically.

> **Shortcut for "write chapter" through "apply safe corrections":** the
> **Automatikmodus** (Automatic mode, at the bottom of the Write tab)
> handles this for all still-missing chapters in one go — see section 7
> below.

---

## 1. The AI roles

The story is not produced by a single model, but by several specialized
roles that work on it one after another or in parallel:

| Role | Task | Tab |
|---|---|---|
| **Architekt** (Architect) | Interviews you and builds the story outline | Architekt / Gerüst |
| **Autor** (Author) | Writes the actual chapters, one chapter per call | Schreiben |
| **Anachronismus-Prüfer** (Anachronism Reviewer) | Historical errors against the year and the forbidden list | runs automatically after every write, manually in Prüfen & Anwenden |
| **Kontinuitäts-Prüfer** (Continuity Reviewer) | Contradictions with the previous chapter or the subplot, open threads at the last chapter | runs automatically after every write, manually in Prüfen & Anwenden |
| **Lektor** (Copy Editor) | Grammar, spelling, sentence structure (among others, a dedicated reviewer solely for verb-final position in subordinate clauses) | runs automatically after every write, manually in Prüfen & Anwenden |
| **Chronist** (Chronicler) | Summarizes the current state after each chapter (characters, relationships, open threads) | Stand & Export |
| **Fundus-Pfleger** (Character Pool Curator) | Carries characters from finished stories over into the reusable character pool | Personen-Fundus |

All four reviewer roles (anachronism, continuity, copy editor, sentence
structure) run automatically **in parallel** after each chapter is
written; their findings end up together in a single, category-color-coded
list in the **Prüfen & Anwenden** (Review & Apply) tab.

Each role runs with its own model and its own parameters, tuned to its
respective task. The Author always writes with Mistral. Which AI
**target** (local, or reached over an SSH tunnel/network on another
machine) is used is set via the selector at the top of the header — it
applies to all pipeline steps at once and is retained when you switch
tabs.

---

## 2. Creating a new story

In the **Projekte** (Projects) tab: choose a title (optional — it often
only emerges from the Architect interview) and an era/setting, then click
"Anlegen" (Create). Without a title, the program creates a placeholder
folder "neu" ("new"), which is automatically renamed to the title chosen
during the Architect interview. Available for selection are the prepared
eras/settings (currently including Regency, Mittelalter (Middle Ages),
Altes Ägypten (Ancient Egypt), Jetzt-2026 (Now-2026), Zukunft (Future),
Shadowrun) as well as any custom era/setting you created yourself via the
**Epoche erstellen** (Create Era) tab.

Right after that: open the **Architekt / Gerüst** (Architect / Outline)
tab and click "Interview neu führen" (Start new interview). The
conversation proceeds step by step (one question at a time) and
automatically produces the story outline ("Gerüst") at the end. **The
conversation can be interrupted at any time** (close the tab, close the
browser) and resumed exactly where it left off the next time you open the
project — the chat history so far is automatically cached for this
purpose. One of the interview questions also lets you reuse characters
already saved in the **Personen-Fundus** (Character Pool) from earlier,
finished stories, instead of inventing every character from scratch (see
section 8). Every one of your own answers in the chat history has a small
✏️ icon next to it — this lets you edit it afterwards (e.g. if you
accidentally pressed Enter, or think of something else afterwards); all
questions asked since then are discarded, and the Architect asks again
from that point onward.

In the generated outline you set, among other things:

- **Jugendschutz-Stufe** (Content Rating) — *Voll* (Full), *Angedeutet*
  (Implied) or *Jugendfrei* (Family-Friendly). Controls how explicit the
  Author is allowed to write.
- **Automatische Fortsetzung** (Automatic Continuation) — **off** by
  default. Automatically continuing a chapter that turned out too short
  repeatedly caused duplicate chapter headings or nonsensical filler text;
  with continuation switched off, you instead just get a notice with the
  current word count.
- **Kapitelplan** (Chapter Plan) — the target event and target word count
  per chapter. According to the Architect's own rules, the **last**
  planned chapter must actually resolve the core conflict (and any
  subplot), not end on a cliffhanger.

The outline can also be edited by hand in the same tab — this takes
effect from the next write call onward. Frame/title/characters/conflict/
subplot as well as starting situation/open points/rules remain free text
(Monaco editor above and below), while the **Kapitelplan** (Chapter Plan)
in between is its own card per chapter with individual fields (location,
characters present, event, target word count, function in the story arc,
state of the romance plot, state at the end of the chapter) instead of a
free-text bullet list. Target word count is a required numeric field — if
it or another field is missing, "Speichern" (Save) marks the affected card
in red, instead of only noticing the error days later during automatic
writing. "+ Kapitel" (+ Chapter)/▲▼/"Löschen" (Delete) let you add, move
or remove chapters; the chapter number is derived automatically from its
position. An existing chapter plan in a previously unknown format is
never silently overwritten — it remains as free text with a warning
instead. Right below that you can also store **Stilproben** (Style
Samples): one to three short text excerpts whose language/sentence rhythm/
tone the Author should take as a guide, without adopting their plot or
characters.

---

## 3. Writing a chapter (the "Schreiben" tab)

Enter the chapter number (automatically incremented after each successful
chapter); optionally enter an **additional hint for this one attempt
only** — useful when a previous attempt strayed too far from the outline
(e.g. "Maggie must be present, the secret is NOT resolved with a kiss").
The hint only applies to this run and is never saved permanently — for
permanent changes, the correction belongs in the outline itself.

After "Schreiben starten" (Start writing), the following run automatically:

- **Spell-checking (hunspell)** against a real German dictionary
  (complements the language-model check with invented but grammatically
  plausible words)
- **All four reviewer roles** (anachronism, continuity, copy editor,
  sentence structure) directly afterward, in parallel
- **Chapter-restart, premature-chapter-end and repetition detection** —
  automatically cuts off duplicate chapter headings, prematurely
  concluded but still-continued scenes, and internally repeated paragraph
  blocks
- **State assurance** — if the state of the previous chapter is missing,
  it is automatically caught up on before the new chapter is written

Below the chapter text there is also the **"Frage zur Geschichte"**
(Question about the story) field — it answers comprehension questions
about the story so far (e.g. "what was the name of the supporting
character from chapter 2 again?") purely for information, without
continuing the story.

An already-written chapter is overwritten the next time "Schreiben
starten" is clicked — the old version is automatically backed up as a
`.bak` file, nothing is lost.

---

## 4. Reviewing, applying, spelling

| Tab | Effect |
|---|---|
| **Prüfen & Anwenden** (Review & Apply) | Shows the entire, cross-chapter chapter text in an editor, with all findings from all four reviewer roles (anachronism, plausibility, continuity, copy-editing) next to it, color-coded by category. Any finding with a concrete, unambiguous replacement suggestion can be applied with a click (editor widget or list button) — a plain text replacement in the browser, no further AI call. "Erneut prüfen" (Review again) per chapter restarts the four reviewer roles. "Ablehnen" (Reject) instead marks a finding permanently as "not an error" — e.g. an intentionally chosen canon deviation in a fan-fiction era (different characters/locations than the original). The finding disappears immediately and is not reported again on a future review, project-wide, not just for this chapter. |
| **Rechtschreibung** (Spelling) | Interactive: go through unknown words (hunspell) one by one with sentence context — clicking jumps to the spot in the editor, correct it there by hand |

Contradictory suggestions from two reviewers, as well as findings whose
text location can no longer be found (because the text has since
changed), are **not** applied automatically — they remain visible for a
manual decision.

Once automatic mode is finished and you click "Prüfung abschließen"
(Complete review), a dialog offers to **clean up** ("bereinigen") the
project: deletes all `.bak` backup files as well as all intermediate
states except the last one. Chapters, outline, forbidden list and
personas remain untouched. A checkbox in the same dialog (checked by
default, independent of cleanup) also updates the **Personen-Fundus**
(Character Pool) with this project's characters.

---

## 5. Recording state and exporting

**Stand & Export** (State & Export) tab:

- **"Stand erzeugen"** (Generate state) — the Chronist summarizes the
  state after the specified chapter (characters, relationships, open
  threads, images/phrasings already used). If it is the **last** chapter
  planned according to the outline, all chapters are automatically merged
  into one combined file. Next to it, "🔄 Neu laden" (Reload) — shows only
  the most recently saved state again, without invoking the Chronist (and
  thus an AI call) again; useful if you have since changed something in
  the chapter text, e.g. in the "Rechtschreibung" (Spelling) tab.
- **"Titelbild"** (Cover Image) — suggests a German image prompt from the
  outline (via AI), or enter your own prompt, then generate it. Requires
  an AI target with a configured **image port** (see section 8) — without
  such a target, this section stays hidden.
- **"Alle Kapitel zusammenfassen"** (Merge all chapters) — the same as
  the auto-export, available manually at any time.
- **"Als PDF-Buch herunterladen"** (Download as PDF book) — produces a
  designed PDF in paperback style, directly from the current chapter
  files.
- **"Zwischenstand zusammenfassen"** (Summarize interim state) (from/to
  chapter) — for an excerpt, without having to finish the whole story.
  Here too, "🔄 Neu laden" (Reload) next to the preview shows the most
  recently used of the two summaries again.

The combined file as well as named interim states end up in the story
folder itself, not in the internal working-files subfolder — so you can
easily find them again without having to dig through technical internals.

---

## 6. Creating personas and eras/settings

In the **Personas** tab you can individually adjust the role instructions
(Architect, Author, Anachronism Reviewer, Chronicler, Continuity
Reviewer, Copy Editor, Sentence-Structure Reviewer) for the currently
open project — changes only affect **this** project, not retroactively
other projects or the central era/setting library.

In the **Epoche erstellen** (Create Era) tab you create an entirely new
setting (questions about name, time period, social order, the one status
rule as a dramaturgic tension device, and for invented worlds also which
known franchise to keep a distance from). The result is a **rough draft**
— the forbidden list and reviewer checklist are only marked "HIER
ERGÄNZEN" (ADD HERE) and should still be researched before productive
use.

---

## 7. Automatic mode (all chapters in one go)

At the bottom of the **Schreiben** (Write) tab, **Automatikmodus**
(Automatic mode) writes all chapters still missing according to the
outline one after another, and afterward automatically applies all
unambiguous reviewer corrections for each chapter (up to the configured
number of **"Max. Durchläufe je Kapitel"** (Max. passes per chapter)).
Contradictory suggestions, locations that can no longer be found, and
unknown words are **not** decided automatically — as usual, they remain in
the **Prüfen & Anwenden** (Review & Apply) or **Rechtschreibung**
(Spelling) tab for manual review. The run keeps working in the background
on the server even if you close the tab or close the browser.

**Live progress:** the "Author" window shows the chapter text currently
being generated live in automatic mode too (not just during interactive
writing), and the status log reports an interim update roughly every 20
seconds for a slow AI target ("… still writing, approx. N words so far")
while a response is still pending — so even with several minutes of pure
writing time, it's clear that the run is actively working and not stuck.

**Automatic intermediate stops:** every three chapters, the run pauses by
itself if unresolved reviewer findings have accumulated since the run
began (conflicts, locations that can no longer be found, unknown words)
— so that problems don't silently continue over many further chapters
before you see them. Take a look at the log or at **Prüfen & Anwenden**
(Review & Apply), then continue normally with "Fortsetzen" (Continue).

**On a connection failure to the AI target** (e.g. Ollama briefly
unreachable), automatic mode does not give up immediately: it retries the
same step up to three times, 5 minutes apart (i.e. 5, 10 and 15 minutes
after the first failure). The run continues to count as active during
this time, and the "Stoppen" (Stop) button remains effective. Only once
the last attempt also fails does the run pause.

**If the run is interrupted** (after exhausting retry attempts, through
an intermediate stop, because you clicked "Stoppen" (Stop) yourself, or
even through a server restart in the middle of the run), the program
remembers exactly where this happened and offers its own **"Fortsetzen"**
(Continue) button that resumes the run exactly there — never starting
over from chapter 1. After being clicked, the "Stoppen" (Stop) button
shows "Wird gestoppt…" (Stopping…): an AI step already in progress is not
aborted mid-way, but is allowed to finish first before the run actually
pauses.

Under **"Lauf-Historie"** (Run History) you can also look up every past
automatic run of this project — date, time period, duration, and whether
it completed cleanly, aborted with an error, or was stopped.

---

## 8. Character pool ("Personen-Fundus")

The **Personen-Fundus** (Character Pool) tab holds a single file, bound to
the account rather than to a project, containing characters from
**finished** stories, organized by era/setting. "Importieren" (Import)
automatically brings characters from a completed story into the pool;
they can then be reused in the Architect interview for a new story in the
same era/setting, instead of inventing every character anew.

Every character has the same eight fields, and each one is always listed —
even when nothing is known for it, in which case it's simply left empty
(e.g. "- Aussehen: "):

| Field | Content |
|---|---|
| Alter (Age) | age, if known |
| Stand/Rolle (Standing/Role) | standing, rank, title, or social role |
| Eigenschaften (Traits) | character traits, personality |
| Aussehen (Appearance) | physical appearance |
| Ziel (Goal) | what the character wants to achieve |
| Angst (Fear) | their greatest fear |
| Geheimnis (Secret) | their secret |
| Geschichten (Stories) | titles of the stories they appear in — extended automatically on a repeat import |

Every field except "Geschichten" can be edited by hand in the editor at
any time; a later merge won't overwrite them, only the story list grows.

The free-text search in the character editor searches not just the name
but every field value of a character — "Ravenclaw" also finds characters
where that only appears in the Stand/Rolle field, not in the name.
Combined with the era filter, this lets you find groups like all
Ravenclaws in an era, or all maids in the Middle Ages.

---

## 9. AI targets and settings

In the **KI-Ziele** (AI Targets) tab you configure where Ollama runs:
locally, directly via a network address, or over an SSH tunnel on a
remote machine. A target can be marked as a favorite — it is then
automatically preselected the next time you start the app. In addition,
an **image port** can be configured per target if an image-generation
server also runs on the same machine — only then does the cover-image
section appear in the "Stand & Export" (State & Export) tab (see section
5).

In the **Einstellungen** (Settings) tab you set where new stories are
stored on disk, and whether a subfolder is automatically created per era/
setting. In the **Benutzer** (Users) tab you manage (as an admin) the
accounts that users log in with — each account sees only its own
projects. All three tabs are only visible to admin accounts.

---

See also: **Hilfe** (Help, in the header) for the step-by-step workflow of
a completely new story, as well as how to handle interrupted connections.
