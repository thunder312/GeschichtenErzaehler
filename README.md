# Geschichten Erzähler

Browserbasierte GUI für die KI-Pipeline, die historische Novellen schreibt
(ursprünglich `novelle.py`, CLI-basiert). Führt den Nutzer schrittweise
durch Architekt → Schreiben → Prüfen → Anwenden → Lektorieren → Stand/Export,
mit einem Merge-Editor für die manuellen Korrekturschritte und einer
SSH-Anbindung an entfernte Ollama-Server/Docker-Container.

## Projektstruktur

```
backend/    FastAPI-Backend (Python 3.12+) - Pipeline-Logik, Ollama-/SSH-Anbindung
frontend/   React + TypeScript + Vite + Tailwind - Tab-basierte Bedienoberfläche
docs/       Bedienungsanleitung + Schnittstellen-Übersicht (Referenz aus der CLI-Zeit)
pre-GUI/    Unveränderte Sicherung des ursprünglichen CLI-Skripts (nicht mehr bearbeiten)
```

Tech-Stack-Begründung siehe Gesprächsverlauf; Kurzfassung: Backend in Python,
weil die komplette Prompt-/Heuristik-Logik aus `novelle.py` 1:1 portiert
werden konnte statt in einer Zweitsprache neu erfunden zu werden.

## Backend starten

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows; unter Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

Tests: `python -m pytest` (im aktivierten venv, aus `backend/`).

Ohne weitere Konfiguration spricht das Backend `http://localhost:11434`
(lokales Ollama) an. Für entfernte Server: SSH-Ziel im Tab „SSH-Ziele"
anlegen und bei den einzelnen Schritten auswählen.

## Frontend starten

```bash
cd frontend
npm install
npm run dev
```

Läuft unter `http://localhost:5173`, der Vite-Dev-Server proxied `/api/*`
automatisch zum Backend auf Port 8000 (siehe `frontend/vite.config.ts`).

## Stand dieser ersten Fassung

Bereits vorhanden: Projekte anlegen/verwalten, Gerüst bearbeiten (als
Markdown, noch kein geführtes Architekten-Interview), Kapitel schreiben
(live streamend inkl. aller automatischen Sicherheitsnetze), Prüfen,
Anachronismen automatisch anwenden, Lektorieren, Rechtschreibprüfung via
hunspell (lokal oder per SSH-Remote-Exec), Stand/Export, SSH-Ziel-Verwaltung
mit Verbindungstest.

Noch offen (siehe auch `ToDo.md`): geführtes Architekten-Interview als Dialog
statt Rohtext-Editor, geführte Epochen-Erstellung, automatische Fortsetzung
bei zu kurzen Kapiteln, Hermes-vs-Qwen-Vergleich (`testen`), Persona-/
Verbotsliste-Editor, Installer/Docker-Compose.
