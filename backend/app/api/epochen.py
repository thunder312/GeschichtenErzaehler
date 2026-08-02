"""Epochen-Erstellung: reines Frageformular (kein LLM-Aufruf), portiert aus
pre-GUI/novelle.py's cmd_epoche_erstellen(). Legt einen Rohentwurf mit vier
Dateien unter der zentralen Epochen-Bibliothek an - siehe
app/core/epoche.py fuer die Vorlagen-Generatoren."""
from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.core.epoche import EpocheAntworten, epoche_dateien_erzeugen
from app.core.geruest import ordnername_aus_titel
from app.schemas import EpocheErstellenAnfrage, EpocheErstellenAntwort

router = APIRouter(prefix="/api/epochen", tags=["epochen"])


@router.post("", response_model=EpocheErstellenAntwort, status_code=201)
def epoche_erstellen(anfrage: EpocheErstellenAnfrage, settings: Settings = Depends(get_settings)):
    ordner_name = ordnername_aus_titel(anfrage.name)
    ziel = settings.epochen_dir / ordner_name
    if ziel.exists():
        raise HTTPException(409, f"Epoche '{ordner_name}' existiert bereits.")

    antworten = EpocheAntworten(
        name=anfrage.name,
        erfunden=anfrage.erfunden,
        beschreibung=anfrage.beschreibung,
        zeitraum=anfrage.zeitraum,
        orte=anfrage.orte,
        gesellschaft=anfrage.gesellschaft,
        statusregel=anfrage.statusregel,
        genre=anfrage.genre,
        rang_wort=anfrage.rang_wort.strip() or "Stand",
        anreden=anfrage.anreden.strip() or "(noch keine Angabe)",
        nebenstrang_typen=anfrage.nebenstrang_typen.strip() or "ein zum Setting passender Nebenstrang",
        vorbild_franchise=anfrage.vorbild_franchise,
        verbote_start=anfrage.verbote_start,
    )
    dateien = epoche_dateien_erzeugen(antworten)

    ziel.mkdir(parents=True)
    for dateiname, inhalt in dateien.items():
        (ziel / dateiname).write_text(inhalt, encoding="utf-8")
    if anfrage.genre.strip():
        (ziel / ".genre").write_text(anfrage.genre.strip(), encoding="utf-8")

    return EpocheErstellenAntwort(name=anfrage.name, ordner=ordner_name, dateien=dateien)


@router.delete("/{ordner}", status_code=204)
def epoche_loeschen(ordner: str, settings: Settings = Depends(get_settings)):
    """Loescht die zentrale Epoche komplett aus der Bibliothek - betrifft nur
    settings.epochen_dir, NICHT bereits angelegte Projekte: deren personas/
    und projekt/verbotsliste.md sind eigene Kopien (siehe
    app/core/projekt_dateien.py:projekt_anlegen), die beim Anlegen einmalig
    aus der Epoche kopiert wurden und seither unabhaengig von ihr existieren."""
    ziel = settings.epochen_dir / ordner
    if not ziel.is_dir():
        raise HTTPException(404, f"Epoche '{ordner}' nicht gefunden.")
    shutil.rmtree(ziel)
