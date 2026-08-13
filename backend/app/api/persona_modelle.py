"""Globale Admin-Zuordnung Persona -> Ollama-Modell (Tab "KI-Ziele" ->
Persona-Modell-Zuordnung). Ueberschreibt pro ROLLEN-Key aus app/core/
rollen.py NUR das Feld "modell" - Sampling-Parameter/think-Flag bleiben wie
dort definiert. Gilt global fuer alle User/Projekte, aufgeloest bei jedem
Ollama-Aufruf ueber app/services.py:rollen_modell_override()."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import db
from app.config import Settings, get_settings
from app.core.rollen import ROLLEN
from app.schemas import PersonaModellAntwort, PersonaModellSetzenAnfrage

# Admin-Durchsetzung erfolgt zentral beim Registrieren in app/main.py
# (dependencies=[Depends(get_current_admin)] bei include_router), analog zu
# app/api/einstellungen.py und app/api/benutzer.py - dieser Router betrifft
# ausschliesslich globale, installationsweite Konfiguration.
router = APIRouter(prefix="/api/persona-modelle", tags=["persona-modelle"])


@router.get("", response_model=list[PersonaModellAntwort])
def liste(settings: Settings = Depends(get_settings)):
    db.init_db(settings.database_path)
    overrides = db.persona_modelle_alle_lesen(settings.database_path)
    ergebnis = []
    for persona, cfg in ROLLEN.items():
        default_modell = cfg["modell"]
        override_modell = overrides.get(persona)
        ergebnis.append(PersonaModellAntwort(
            persona=persona,
            default_modell=default_modell,
            override_modell=override_modell,
            effektives_modell=override_modell or default_modell,
        ))
    return ergebnis


@router.put("/{persona}", response_model=PersonaModellAntwort)
def setzen(persona: str, anfrage: PersonaModellSetzenAnfrage, settings: Settings = Depends(get_settings)):
    if persona not in ROLLEN:
        raise HTTPException(404, f"Unbekannte Persona '{persona}'.")
    db.init_db(settings.database_path)
    if anfrage.modell:
        db.persona_modell_schreiben(settings.database_path, persona, anfrage.modell)
    else:
        db.persona_modell_loeschen(settings.database_path, persona)

    default_modell = ROLLEN[persona]["modell"]
    override_modell = db.persona_modell_lesen(settings.database_path, persona)
    return PersonaModellAntwort(
        persona=persona,
        default_modell=default_modell,
        override_modell=override_modell,
        effektives_modell=override_modell or default_modell,
    )
