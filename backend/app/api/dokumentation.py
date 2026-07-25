"""Rendert die Markdown-Dokumentation (Anleitung, Hilfe) als eigenstaendige,
ins App-Farbschema passende HTML-Seite - zum Oeffnen in einem neuen
Browser-Tab (siehe Kopfbereich im Frontend, Buttons "Anleitung"/"Hilfe")."""
from __future__ import annotations

from pathlib import Path

import markdown
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from app.config import Settings, get_settings

router = APIRouter(prefix="/api/docs", tags=["dokumentation"])

# Platzhalter statt str.format()/f-string, damit die CSS-geschweiften-Klammern
# nicht mit den Format-Platzhaltern kollidieren.
_SEITEN_VORLAGE = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>__TITEL__</title>
<style>
  :root { color-scheme: dark; }
  body {
    margin: 0; padding: 2.5rem 1.5rem 4rem;
    background: #15181a; color: #e6e8e6;
    font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  main { max-width: 46rem; margin: 0 auto; }
  h1, h2, h3 { font-family: ui-serif, Georgia, serif; color: #7fe3b4; line-height: 1.3; }
  h1 { font-size: 2rem; border-bottom: 1px solid #2b3234; padding-bottom: 0.6rem; }
  h2 { font-size: 1.4rem; margin-top: 2.5rem; }
  h3 { font-size: 1.1rem; }
  a { color: #3ecf8e; }
  code { background: #1b1f20; padding: 0.15em 0.4em; border-radius: 4px; font-size: 0.9em; }
  pre { background: #1b1f20; padding: 1rem; border-radius: 10px; overflow-x: auto; }
  pre code { background: none; padding: 0; }
  blockquote {
    border-left: 3px solid #3ecf8e; margin: 1rem 0; padding: 0.2rem 1rem;
    color: #8b958f; background: rgba(29, 59, 44, 0.25); border-radius: 0 8px 8px 0;
  }
  table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
  th, td { border: 1px solid #2b3234; padding: 0.5rem 0.7rem; text-align: left; vertical-align: top; }
  th { background: #1b1f20; color: #7fe3b4; }
  hr { border: none; border-top: 1px solid #2b3234; margin: 2.5rem 0; }
</style>
</head>
<body><main>__INHALT__</main></body>
</html>"""


def _seite_rendern(pfad: Path, titel: str) -> str:
    if not pfad.exists():
        raise HTTPException(404, f"{pfad.name} nicht gefunden.")
    text = pfad.read_text(encoding="utf-8")
    inhalt = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    return _SEITEN_VORLAGE.replace("__TITEL__", titel).replace("__INHALT__", inhalt)


@router.get("/anleitung", response_class=HTMLResponse)
def anleitung(settings: Settings = Depends(get_settings)):
    return _seite_rendern(settings.anleitung_md, "Anleitung - Geschichten Erzähler")


@router.get("/hilfe", response_class=HTMLResponse)
def hilfe(settings: Settings = Depends(get_settings)):
    return _seite_rendern(settings.hilfe_md, "Hilfe - Geschichten Erzähler")
