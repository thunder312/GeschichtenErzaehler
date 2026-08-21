🇩🇪 [Deutsche Version](Hilfe.md)

# Help

## 1. A brand-new story — step by step

1. **Projekte** (Projects) → choose a title (optional) and an era/setting
   (Epoche) → „Anlegen“ (Create).
2. **Architekt / Gerüst** (Architect / Outline) → „Interview neu führen“
   (Start new interview) → answer the questions one after another. At the
   end the story outline (Gerüst) is created automatically, and the
   project folder is renamed after the chosen title.
3. **Schreiben** (Write) → have Chapter 1 written. This automatically
   includes: spell-checking as well as all four reviewer roles
   (anachronism, continuity, copy editor, sentence structure).
4. If needed: **Prüfen & Anwenden** (Review & Apply) — all reviewer
   findings in one list, color-coded by category, each finding can be
   applied with a concrete replacement suggestion by clicking it.
   **Rechtschreibung** (Spelling) — go through unknown words one by one
   with context.
5. **Stand & Export** (State & Export) → „Stand erzeugen“ (Generate
   state) for Chapter 1 — *always as the last step for this chapter*, so
   that the captured state really is the final version.
6. Go back to step 3 for the next chapter — the chapter number is
   automatically incremented after each successful chapter.
7. After the last chapter planned in the outline, „Stand erzeugen“
   (Generate state) automatically merges everything into one file. Under
   **Stand & Export** (State & Export) the story can additionally be
   downloaded as a formatted PDF, or a cover image can be generated for
   it.

Instead of manually repeating steps 3–6 for every chapter, the
**Automatikmodus** (Automatic Mode, at the bottom of the Schreiben/Write
tab) does this for all missing chapters in one go — see section 4 below.

For a detailed explanation of every tab, see **Anleitung** (User Guide, in
the header).

---

## 2. When a chapter doesn't fit the outline

Sometimes the author (Autor) invents its own, unfitting resolution — this
is usually clearly recognizable from several, simultaneously serious
contradictions in the continuity finding (Kontinuitäts-Befund). In such a
case, manually patching it up rarely pays off: since the writer model
doesn't use a fixed random seed, even a simple retry in the **Schreiben**
(Write) tab usually turns out differently. If that isn't enough, an
**additional hint for just this one attempt** helps (a field below the
chapter number), which gets prominently appended to the author prompt and
takes precedence over conflicting outline details.

An additional rule applies to the **last** planned chapter: it must
actually resolve the core conflict (and any subplot). An event forced via
such a hint that isn't itself a real resolution (but only a new,
unresolved twist) is specifically flagged as such by the continuity
reviewer (Kontinuitäts-Prüfer).

---

## 3. Asynchrony: what to watch out for

The AI steps run in the background (streaming over WebSocket, or as a
running server request) while you can keep clicking around in the
interface. That's convenient, but it has a few pitfalls:

**Connection drops during "Schreiben" (Write) (network gone, tab closed,
server restarted):** the chapter text is only saved once the AI's answer
has arrived **completely** — if it's interrupted midway, the text
generated so far in this attempt is lost, but nothing half-finished is
written to disk either. Just click „Schreiben starten“ (Start writing)
again. The **Architekten-Interview** (Architect interview) deliberately
behaves differently: it automatically saves the conversation history
after every turn and lets you resume exactly where you left off the next
time you open the project.

**Don't work on the same chapter in several tabs at once:** every tab
(Schreiben/Write, Prüfen & Anwenden/Review & Apply, Rechtschreibung/
Spelling) keeps running in the background when you switch away from it.
If you e.g. start "Prüfen" (Review) for Chapter 3 while Chapter 3 is still
being written in the Schreiben (Write) tab, the system will inevitably
check the **old** version, because the new one isn't saved until it's
finished. The simplest approach: wait for one step to finish (the footer
shows "what the AI is currently doing") before starting the next one for
the same chapter.

**Don't open the same project in two browser windows/tabs at the same
time:** there's no lock between two parallel sessions — if e.g. window A
is currently writing Chapter 3 while window B is also saving Chapter 3,
whichever finishes last simply wins. The automatic `.bak` backup of every
overwritten state is the safety net here, in case something does seem to
get lost.

**"Ollama nicht erreichbar" (Ollama unreachable) or "SSH-Verbindung
fehlgeschlagen" (SSH connection failed):** the selected AI target (KI-Ziel,
at the top of the header) isn't currently running, or isn't reachable over
the network. Test the connection under the **KI-Ziele** (AI Targets) tab;
for a remote target, also check whether the Ollama container is running
on the target machine.

**Browser reload during a running write/review step:** aborts the running
request just like a connection loss (see above) — nothing half-finished
is left behind, the step just needs to be started again.

---

## 4. Automatic mode: when a run is interrupted or takes a long time

The **Automatikmodus** (Automatic Mode, at the bottom of the Schreiben/
Write tab) writes all missing chapters in one go and then automatically
applies all unambiguous reviewer corrections for each chapter — it runs in
the background on the server, even with the browser closed.

**"This is taking a really long time, is that still normal?"** Without a
dedicated GPU on the AI target, a single chapter (writing plus all four
reviewer roles) can easily take several minutes — that's not a hang. How
to tell the difference:

- The **"Autor" (Author) window** in the Schreiben (Write) tab shows the
  text currently being generated live, even in automatic mode.
- The **status log** reports an intermediate line roughly every 20
  seconds while a response is in progress, with an approximate word count
  and elapsed time.

If truly **no** new line appears at all for several minutes (not even a
progress line) and the word count in the Author window also stops
changing, something has actually gotten stuck — in that case, "Stoppen"
(Stop) helps, along with a look at "Lauf-Historie" (Run History) to see
whether an error was recorded.

**Connection loss to the AI target:** especially with a remote AI target
over an SSH tunnel (e.g. your own machine at home), the connection can
drop mid-way — at night, for instance, due to some internet connections'
daily forced disconnect. In the event of such a connection loss, the run
doesn't give up immediately, but retries the same step up to three times,
5 minutes apart (5, 10 and 15 minutes after the first failure) — the run
continues to count as active during this time. Only once the last attempt
also fails does the run stop cleanly with an error message, and **nothing
is lost**: all chapters written so far and corrections already applied
are retained.

**Automatic intermediate stop every three chapters:** if unresolved
reviewer findings pile up since the start of the run (conflicts, passages
that can no longer be found, unknown words), the run stops on its own
instead of continuing unattended and dragging the problem along through
many more chapters. This isn't a bug, it's intentional — briefly review it
in the "Prüfen & Anwenden" (Review & Apply) tab, then resume normally.

**In none of these cases should you click "Automatikmodus starten" (Start
automatic mode) again** — that would run through the entire review phase
again starting from Chapter 1, unnecessarily re-checking chapters that are
already done. Instead, a **"Fortsetzen"** (Resume) button appears in its
place (or in addition to it), right next to which it shows exactly where
the run stopped (error code, chapter, phase, pass). Clicking it resumes
exactly there. The same applies if you interrupted it yourself via
"Stoppen" (Stop) midway — the button then shows "Wird gestoppt…"
(Stopping…), because an AI step that's already running isn't cut off
mid-way, but is allowed to finish first. Even after a server restart
mid-run (e.g. due to an update), the state cleans itself up the next time
the program starts and offers "Fortsetzen" (Resume), instead of staying
stuck as "running" forever.

Via **"Lauf-Historie"** (Run History) in the same area, all of this
project's previous automatic runs can be looked up (date, time span,
duration, status) — handy for checking the next morning how long an
overnight run took and whether it completed cleanly.

---

## 5. Generating a cover image

In the **Stand & Export** (State & Export) tab, a cover image can be
generated for any story — provided that at least one target under **KI-
Ziele** (AI Targets) has an **image port** (Bild-Port) configured (a
separately running image-generation server on the same machine). Without
such a target, this area stays hidden in the tab.

„Prompt vorschlagen“ (Suggest prompt) has an AI formulate a short, German
image prompt from the outline (title, setting, characters, conflict) —
deliberately without proper names and without any text-in-image, since the
image model can't do anything useful with those. The prompt remains freely
editable and is only automatically translated into English immediately
before the actual generation.
