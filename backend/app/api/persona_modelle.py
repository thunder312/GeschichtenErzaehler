"""Admin-Zuordnung Persona -> Ollama-Modell JE KI-ZIEL (Tab "KI-Ziele" ->
Persona-Modell-Zuordnung). Ueberschreibt pro ROLLEN-Key aus app/core/
rollen.py NUR das Feld "modell" - Sampling-Parameter/think-Flag bleiben wie
dort definiert. Gilt fuer alle User/Projekte, aber nur auf dem jeweiligen
KI-Ziel (jedes Ziel hat andere Modelle installiert); aufgeloest bei jedem
Ollama-Aufruf ueber app/services.py:rollen_modell_override()."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app import db
from app.config import Settings, get_settings
from app.core.rollen import ROLLEN
from app.schemas import PersonaModellAntwort, PersonaModellSetzenAnfrage

# Admin-Durchsetzung erfolgt zentral beim Registrieren in app/main.py
# (dependencies=[Depends(get_current_admin)] bei include_router), analog zu
# app/api/einstellungen.py und app/api/benutzer.py - dieser Router betrifft
# ausschliesslich globale, installationsweite Konfiguration.
router = APIRouter(prefix="/api/persona-modelle", tags=["persona-modelle"])


def _ziel_pruefen(settings: Settings, ziel_id: str) -> None:
    if db.ssh_ziel_lesen(settings.database_path, ziel_id) is None:
        raise HTTPException(404, "KI-Ziel nicht gefunden.")


@router.get("", response_model=list[PersonaModellAntwort])
def liste(ziel_id: str = Query(..., description="KI-Ziel, dessen Zuordnung gelesen wird"),
          settings: Settings = Depends(get_settings)):
    db.init_db(settings.database_path)
    _ziel_pruefen(settings, ziel_id)
    overrides = db.persona_modelle_alle_lesen(settings.database_path, ziel_id)
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
def setzen(persona: str, anfrage: PersonaModellSetzenAnfrage,
           ziel_id: str = Query(..., description="KI-Ziel, fuer das die Zuordnung gilt"),
           settings: Settings = Depends(get_settings)):
    if persona not in ROLLEN:
        raise HTTPException(404, f"Unbekannte Persona '{persona}'.")
    db.init_db(settings.database_path)
    _ziel_pruefen(settings, ziel_id)
    if anfrage.modell:
        db.persona_modell_schreiben(settings.database_path, ziel_id, persona, anfrage.modell)
    else:
        db.persona_modell_loeschen(settings.database_path, ziel_id, persona)

    default_modell = ROLLEN[persona]["modell"]
    override_modell = db.persona_modell_lesen(settings.database_path, ziel_id, persona)
    return PersonaModellAntwort(
        persona=persona,
        default_modell=default_modell,
        override_modell=override_modell,
        effektives_modell=override_modell or default_modell,
    )
