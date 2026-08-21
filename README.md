🇩🇪 [Deutsche Version](README.de.md)

# Geschichten Erzähler ("Storyteller")

Browser-based GUI for an AI pipeline that writes historical (and invented)
novellas (originally `novelle.py`, a CLI script). Guides the user through
Architect/Analyzer → Write → Review → Apply → Copy-edit → State/Export,
with a merge editor for manual correction steps and SSH connectivity to
remote Ollama servers/Docker containers.

The app's own user interface is currently German-only; this README and the
`/docs` folder are also available in English for anyone browsing the
repository. See [Language scope](#language-scope) below.

## Project structure

```
backend/    FastAPI backend (Python 3.12+) - pipeline logic, Ollama/SSH connectivity
frontend/   React + TypeScript + Vite + Tailwind - tab-based user interface
docs/       User guide + interface overview (German originals + English translations, *.en.md)
pre-GUI/    Unmodified backup of the original CLI script (no longer edited)
```

Tech stack rationale: the backend is in Python because the entire prompt/
heuristics logic from `novelle.py` could be ported 1:1 instead of being
reinvented in a second language.

## Running the backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows; on Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

Tests: `python -m pytest` (inside the activated venv, from `backend/`).

Without further configuration, the backend talks to `http://localhost:11434`
(local Ollama). For remote servers: create an SSH target under the "SSH
Targets" tab and select it in the individual pipeline steps.

## Running the frontend

```bash
cd frontend
npm install
npm run dev
```

Runs at `http://localhost:5173`; the Vite dev server automatically proxies
`/api/*` to the backend on port 8000 (see `frontend/vite.config.ts`).

## Feature overview

- **Three ways to get a story outline ("Gerüst"):** a guided Architect
  interview (multiple-choice dialogue), writing the outline by hand, or
  importing an existing story and letting the "Analyzer" ("Analysator")
  automatically derive a complete outline (including a chapter plan) from
  it.
- **Era/setting management:** create real historical eras or entirely
  invented settings, including settings derived by the Analyzer (with an
  automatic fan-fiction/rights disclaimer when a known franchise is
  detected).
- **Chapter writing:** live-streamed, with a structured chapter-plan
  editor and all the automatic safety nets carried over from the CLI era.
- **Automatic mode:** writes, reviews and corrects several chapters in a
  row unattended, with run history and a resume function.
- **Review pipeline:** anachronism, continuity and sentence-structure
  reviewers plus a copy editor, results applicable via a merge editor;
  spell-checking via hunspell (local or remote over SSH).
- **Character pool:** characters reusable across projects within the same
  era/setting.
- **Cover generation, PDF export, state/export.**
- **Multi-user support** with login, **SSH target management** with a
  connection test for remote Ollama servers.

See `ToDo.md` for open items (German only).

## Language scope

This project's UI, AI personas and generated stories are German. Only the
repository-facing documentation (this README and `/docs`) has been
translated to English for accessibility on GitHub - the running
application itself does not currently offer an English interface or
English story generation.
