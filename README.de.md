🇬🇧 [English version](README.md)

# Geschichten Erzähler

Browserbasierte GUI für die KI-Pipeline, die historische (und erfundene)
Novellen schreibt (ursprünglich `novelle.py`, CLI-basiert). Führt den Nutzer
durch Architekt/Analysator → Schreiben → Prüfen → Anwenden → Lektorieren →
Stand/Export, mit einem Merge-Editor für die manuellen Korrekturschritte und
einer SSH-Anbindung an entfernte Ollama-Server/Docker-Container.

## Projektstruktur

```
backend/    FastAPI-Backend (Python 3.12+) - Pipeline-Logik, Ollama-/SSH-Anbindung
frontend/   React + TypeScript + Vite + Tailwind - Tab-basierte Bedienoberfläche
docs/       Bedienungsanleitung + Schnittstellen-Übersicht (auch auf Englisch, siehe docs/*.en.md)
pre-GUI/    Unveränderte Sicherung des ursprünglichen CLI-Skripts (nicht mehr bearbeiten)
```

Tech-Stack-Begründung: Backend in Python, weil die komplette Prompt-/
Heuristik-Logik aus `novelle.py` 1:1 portiert werden konnte statt in einer
Zweitsprache neu erfunden zu werden.

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

## Funktionsumfang

- **Drei Wege zu einem Story-Gerüst:** geführtes Architekten-Interview
  (Multiple-Choice-Dialog), Gerüst von Hand schreiben, oder eine bestehende
  Geschichte importieren und vom "Analysator" automatisch ein komplettes
  Gerüst (inkl. Kapitelplan) daraus ableiten lassen.
- **Epochen/Settings-Verwaltung:** reale Epochen oder komplett erfundene
  Settings anlegen, inklusive vom Analysator abgeleiteter Settings (mit
  automatischem FanFic-/Rechte-Hinweis, falls ein bekanntes Franchise
  erkannt wird).
- **Kapitel schreiben:** live streamend, mit strukturiertem Kapitelplan-
  Editor und allen automatischen Sicherheitsnetzen aus der CLI-Zeit.
- **Automatikmodus:** schreibt, prüft und korrigiert mehrere Kapitel am
  Stück unbeaufsichtigt, mit Lauf-Historie und Fortsetzen-Funktion.
- **Prüf-Pipeline:** Anachronismus-, Kontinuitäts- und Satzbau-Prüfer plus
  Lektor, Ergebnisse per Merge-Editor anwendbar; Rechtschreibprüfung via
  hunspell (lokal oder per SSH-Remote-Exec).
- **Personen-Fundus:** projektübergreifend wiederverwendbare Figuren je
  Epoche.
- **Deckblatt-Generierung, PDF-Export, Stand/Export.**
- **Mehrbenutzerbetrieb** mit Login, **SSH-Ziel-Verwaltung** mit
  Verbindungstest für entfernte Ollama-Server.

Offene Punkte siehe `ToDo.md`.
