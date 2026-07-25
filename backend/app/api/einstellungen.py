"""Konfigurierbarer Speicherort fuer Story-Projekte (ToDo.md: "lokaler
Speicherort fuer Geschichte definierbar"). Der Override liegt in der
SQLite-DB (app/db.py, Tabelle einstellungen) statt in Settings, weil
Settings nur einmal beim Start aus Umgebungsvariablen gelesen wird und sich
zur Laufzeit ohne Neustart nicht mehr aendern liesse."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app import db
from app.config import Settings, get_settings
from app.schemas import EinstellungenAnfrage, EinstellungenAntwort
from app.services import projekte_wurzel_unskopiert

router = APIRouter(prefix="/api/einstellungen", tags=["einstellungen"])


def _antwort(settings: Settings) -> EinstellungenAntwort:
    override = db.einstellung_projects_dir_lesen(settings.database_path)
    aktuell = Path(override) if override else settings.projects_dir
    return EinstellungenAntwort(
        projects_dir=str(aktuell.resolve()),
        ist_standard=override is None,
        standard_projects_dir=str(settings.projects_dir.resolve()),
        unterordner_je_epoche=db.einstellung_unterordner_je_epoche_lesen(settings.database_path),
    )


@router.get("", response_model=EinstellungenAntwort)
def einstellungen_lesen(settings: Settings = Depends(get_settings)):
    return _antwort(settings)


@router.put("", response_model=EinstellungenAntwort)
def einstellungen_schreiben(anfrage: EinstellungenAnfrage, settings: Settings = Depends(get_settings)):
    db.einstellung_unterordner_je_epoche_schreiben(settings.database_path, anfrage.unterordner_je_epoche)

    neuer_pfad = (anfrage.projects_dir or "").strip()
    if not neuer_pfad:
        # Leerer Wert setzt den Override zurueck auf den Standardpfad.
        db.einstellung_projects_dir_schreiben(settings.database_path, None)
        projekte_wurzel_unskopiert(settings)
        return _antwort(settings)

    kandidat = Path(neuer_pfad)
    try:
        kandidat.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as e:
        raise HTTPException(400, f"Ordner '{neuer_pfad}' kann nicht angelegt/verwendet werden: {e}") from e
    if not kandidat.is_dir():
        raise HTTPException(400, f"'{neuer_pfad}' ist kein Ordner.")

    db.einstellung_projects_dir_schreiben(settings.database_path, str(kandidat.resolve()))
    return _antwort(settings)
