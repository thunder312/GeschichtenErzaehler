🇩🇪 [Deutsche Version](Anwendungsfall-Nachtlauf-lokal.md)

# Use case: start on the server, finish writing locally overnight

Short reference: [Quickstart-Nachtlauf.en.md](Quickstart-Nachtlauf.en.md).

> UI labels are translated for readability; the app itself shows the German
> texts (e.g. "Abgleich mit Server" = Sync with server, "Auf den PC" = To the
> PC, "Zum Server" = To the server, "Lokal entfernen" = Remove locally).

## What is this about?

The server (Strato, `https://geschichten.daniel-ertl.de`) is reachable from
anywhere and has spell checking (Hunspell) – but its AI runs on Athene (CPU)
or through the tunnel to the PC. The **local PC** (RTX 5070 Ti) writes a
chapter much faster, can **shut itself down** after the run, and has the AI
right there (`PC (lokal)`).

The workflow therefore has three parts:

1. **Server:** create the project, develop the outline (Architect interview).
2. **PC:** fetch the project via "Sync with server", let the automatic mode
   run overnight, the PC shuts down afterwards.
3. **PC → server:** upload the finished project, check and close it on the
   server.

> **Important:** every transfer starts **on the PC**. The server cannot reach
> the PC (NAT), so there is no "To the PC" button on the server.

## Prerequisites (one-time)

| What | Where / how to check |
|---|---|
| The server runs the sync feature (`/api/sync/*`) | Tab **Settings → "Sync with server" → Test connection** (see step 0) returns "Verbindung steht" (connection is up) |
| Local app is running (backend :8000, frontend :5173) | `start-dev.ps1` in the project root, then `http://localhost:5173` |
| Ollama runs on the PC, models `mistral-small3.2` (or the IQ4_XS variant) and `gemma4` are present | `docker exec ollama ollama list`; details in `pc/README.md` |
| Local AI target `PC (lokal)` (type `direct`, `http://127.0.0.1:11434`) | Tab **Settings → AI targets**, "Test connection" |
| The project's **era** exists in the local era library | Eras that only exist on the server are missing locally – see "Pitfalls" |
| Image-AI containers (Stable Diffusion) on the PC are stopped | they share the 16 GB VRAM with Mistral, otherwise Mistral partly runs on the CPU |

## Step 0 – one-time: enter the counterpart on the PC

Only the very first time (or after a password change):

1. Open the local app (`http://localhost:5173`), log in as admin.
2. Tab **Settings** → open the card **🔄 Sync with server**.
3. **Counterpart address:** `https://geschichten.daniel-ertl.de`
4. Enter **user name** and **password** of the server login.
5. **Save**, then **Test connection**.
   Expected: "Verbindung steht – N Projekt(e) auf der Gegenstelle."

On the server itself this card stays empty.

## Step 1 – on the server: create the project and develop the outline

1. Open `https://geschichten.daniel-ertl.de` and log in.
2. Tab **Projects** → create a new story (title, choose the **era**).
3. Tab **Architect / Outline**: run the interview and save the outline
   (including the chapter plan). Optionally maintain characters in the
   **Character pool** tab.
4. **Optional but recommended:** let chapter 1 be written on the server and
   check tone and length. If it is off, refine the outline now – nothing can
   be corrected at night.

Result: the project has an outline (and maybe chapter 1); nothing exists
locally yet.

## Step 2 – on the PC: fetch the project from the server

1. Open the local app → tab **Projects**.
2. Open the card **🔄 Sync with server** (it only appears once step 0 is
   done). The comparison loads automatically; otherwise **🔃 Compare again**.
3. The project's row shows status **"only on the server"**.
   Click **⬇ To the PC**.
4. Wait for the confirmation message. The row switches to **"✓ identical"**
   and the project appears in the local project list.

Check: open the project in the local list → tab **Architect / Outline** shows
the same outline as on the server.

## Step 3 – on the PC: prepare the night run

1. **Choose the AI target:** with the project open, click the
   **`PC (lokal)`** button in the header. The dot in front of it must be
   **green** (red = Ollama is not running).
2. **Stop image AIs** if they are running (`docker stop sd-server-dev` or via
   the BildKI queue service, see `pc/README.md`).
3. **Disable Windows sleep/hibernate** (otherwise the PC falls asleep mid-run).
   Dropbox may keep running.
4. Tab **Write** → scroll down to the **Automatic mode**.
5. Choose the options:
   - **"Max. passes per chapter"** (e.g. 3).
   - **🔔 Signal tone** – optional, only works if the browser tab stays open.
   - **⏻ Shut down PC afterwards** – tick the box (only shown on the local
     instance; applies to the next start only).
6. Alternatively, for a project that is already under way: block
   **"➕ Write more chapters"** → check **Load preview** →
   **"Write chapter N"**.
7. **Start** the automatic mode. If the question "Shut down image-AI
   containers?" appears: **Shut down & write** (or continue without shutting
   down if no image AI is running).
8. Watch the status window briefly: phase "writing chapter", the author text
   appears live. Only then leave the room.

> **Do not close:** the backend window (uvicorn) and Docker/Ollama must keep
> running all night. You may close the browser tab.

## Step 4 – overnight (nothing to do)

- The run writes all missing chapters and applies unambiguous reviewer
  corrections.
- Every three chapters it pauses if unresolved findings pile up
  ("intermediate stop"); on connection loss it retries 3× after 5/10/15 min.
  In both cases the PC stays **on** and the shutdown is **skipped** – the run
  is not finished.
- After a successful end: **60-second lead time**, then the PC shuts down.
  (Cancel with the red button while you are at the PC.)

## Step 5 – next morning: back to the server

1. Switch the PC on, run `start-dev.ps1`, wait for Ollama/Docker.
2. Local app → tab **Write**: check the status (all chapters done?).
   If "paused": look at the findings in **Check & Apply**, then **Resume**.
3. Tab **Projects** → **🔄 Sync with server** → the project's status must be
   **"⬆ PC is newer"** → **⬆ To the server**.
   - If the prompt "Overwrite newer version?" appears (status
     "⚠ both changed"), something was changed on the server in the meantime.
     **Do not confirm blindly** – see pitfalls. A backup is created
     automatically in `_sync_sicherung/`.
4. Log in on the **server** → open the project: all chapters must be there.
5. On the server: go through **Check & Apply** and **Spelling** (Hunspell
   exists only there), then **Finish check**. The "Clean up project?" dialog
   has a box "Clean up copy on the PC at the next sync" – tick it if the local
   copy may go.
6. Tab **State & Export**: create the state, export the PDF, optionally the
   cover image.
7. On the PC, in the sync: **🧹 Remove locally** (only possible once the
   server has all local changes; exported PDFs stay).

## Test scenario with acceptance criteria

To rehearse before the first real night run – preferably with a **short test
project** (outline with 2 chapters, e.g. era Regency).

| # | Action | Expected result |
|---|---|---|
| T1 | Step 0: enter counterpart, "Test connection" | "Verbindung steht – N Projekt(e)…" |
| T2 | On the server create test project "Nachtlauf-Test" with a 2-chapter outline | Project in the server list, outline saved |
| T3 | Open the sync on the PC | Row "Nachtlauf-Test": **only on the server**, 0 chapters |
| T4 | **⬇ To the PC** | Message without error; status **✓ identical**; project in the local list; outline identical |
| T5 | Select AI target `PC (lokal)` | Dot is green |
| T6 | Start automatic mode, do **not** tick **⏻ Shut down PC afterwards** for this test | Phase changes to "writing chapter", live text appears, chapters 1 and 2 are written; run ends "completed" |
| T7 | Measure time: chapter 1 on `PC (lokal)` vs. earlier on the server | PC clearly faster (rule of thumb: Mistral IQ4_XS ≈ 29 tok/s) |
| T8 | Compare again in the sync | Status **⬆ PC is newer**, local 2 ch., server 0 ch. |
| T9 | **⬆ To the server** | Message without error; status **✓ identical** |
| T10 | Open the project on the server | Both chapters present, readable; Spelling tab works |
| T11 | On the server **Finish check**, tick "clean up copy on the PC" | On the PC the sync shows "🧹 check finished on the server – local copy can go" |
| T12 | On the PC **🧹 Remove locally** | Local project folder gone, PDFs next to it stay, server project untouched |
| T13 | **Conflict test:** repeat T2–T4, then change one chapter on the server **and** one on the PC, sync | Status **⚠ both changed**; "To the server"/"To the PC" asks for confirmation; backup is created |
| T14 | **Shutdown (once, deliberately):** test with a 1-chapter project and the box ticked | After the run ends the notice "PC shuts down in N s", the cancel button works. *(A real shutdown has not been tested so far – only practise cancelling, while nothing unsaved is open.)* |

Passed if T1–T12 run without errors and server and PC are identical after T9.

## Pitfalls

- **Never work on both sides:** once the project is on the PC, do not change
  it on the server until it is back. Otherwise "⚠ both changed" – a merge is
  **not** provided, overwriting loses one side (the backup in
  `_sync_sicherung/` only helps to recover by hand).
- **Not transferred:** `.mp3` (audiobooks), `cover_log` (cover image history),
  `.bak`, Dropbox/Windows clutter. `fundus.md` and `orte.md` (per user) are
  **not** synced; the project's personas, however, belong to the project and
  are copied along.
- **Era missing locally:** if the server project's era is not in the local era
  library, the banned-word list/intro sentence are missing. Currently
  Harry-Potter-Universum, Star-Trek and Burg Schreckenstein have been
  imported; fetch new eras from prod first.
- **"Unsicher" (uncertain) on the first sync:** a project copied by hand has
  no common base, so the comparison only estimates by modification time
  ("noch nie abgeglichen"). Not after the first sync.
- **Models per AI target:** the persona assignment (author/reviewer model)
  applies per AI target. For `PC (lokal)` the author must be set to the
  desired model (currently Mistral IQ4_XS). Prompt changes in the repo do not
  reach existing projects – personas are copied per project.
- **Shared GPU:** if an image AI runs along overnight, the run becomes slow.
- **Sleep/Windows Update:** disable beforehand or set active hours.
- **Restart mid-run:** no loss – "Resume" continues exactly where it stopped,
  not at chapter 1.
