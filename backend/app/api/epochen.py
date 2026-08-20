"""Epochen-Erstellung und -Bearbeitung: reines Frageformular (kein LLM-
Aufruf) zum Anlegen, portiert aus pre-GUI/novelle.py's
cmd_epoche_erstellen(). Legt einen Rohentwurf mit vier Dateien unter der
zentralen Epochen-Bibliothek an - siehe app/core/epoche.py fuer die
Vorlagen-Generatoren. Die Datei-Endpunkte (auflisten/lesen/schreiben)
erlauben, diesen Rohentwurf direkt in der Bibliothek nachzuschaerfen, statt
ihn nur ueber den Umweg eines neuen Projekts (Tab Personas) verfeinern zu
koennen - Aenderungen dort landen naemlich nur in der Projekt-eigenen
Kopie, nie zurueck in der Bibliothek (siehe epoche_loeschen() weiter
unten)."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from app.config import Settings, get_settings
from app.core.epoche import EpocheAntworten, epoche_dateien_erzeugen
from app.core.geruest import ordnername_aus_titel
from app.schemas import EpocheDateiSchreibenAnfrage, EpocheErstellenAnfrage, EpocheErstellenAntwort, EpocheGenreAnfrage

router = APIRouter(prefix="/api/epochen", tags=["epochen"])

# Die vier Dateien, aus denen ein Epochen-Rohentwurf besteht (siehe
# app/core/epoche.py:epoche_dateien_erzeugen) - bewusst dieselbe Menge wie
# beim Anlegen, damit auflisten/lesen/schreiben nie eine Datei ausserhalb
# dieses bekannten Satzes anfassen.
EPOCHE_DATEINAMEN = ("architekt.txt", "autor.txt", "pruefer_anachronismus.txt", "verbotsliste.md", "einleitungssatz.txt")


def _epoche_pfad(settings: Settings, ordner: str) -> Path:
    pfad = settings.epochen_dir / ordner
    if not pfad.is_dir():
        raise HTTPException(404, f"Epoche '{ordner}' nicht gefunden.")
    return pfad


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


@router.get("/{ordner}/dateien", response_model=list[str])
def epoche_dateien_auflisten(ordner: str, settings: Settings = Depends(get_settings)):
    pfad = _epoche_pfad(settings, ordner)
    return [name for name in EPOCHE_DATEINAMEN if (pfad / name).exists()]


@router.get("/{ordner}/dateien/{name}", response_class=PlainTextResponse)
def epoche_datei_lesen(ordner: str, name: str, settings: Settings = Depends(get_settings)):
    if name not in EPOCHE_DATEINAMEN:
        raise HTTPException(404, f"Unbekannte Epochen-Datei '{name}'.")
    pfad = _epoche_pfad(settings, ordner) / name
    if not pfad.is_file():
        raise HTTPException(404, f"Datei '{name}' in Epoche '{ordner}' nicht gefunden.")
    return pfad.read_text(encoding="utf-8")


@router.put("/{ordner}/dateien/{name}")
def epoche_datei_schreiben(ordner: str, name: str, anfrage: EpocheDateiSchreibenAnfrage,
                            settings: Settings = Depends(get_settings)):
    """Schreibt EINE der vier Rohentwurf-Dateien in der zentralen
    Bibliothek - wirkt sich NUR auf zukuenftig damit angelegte Projekte
    aus, nicht auf bereits bestehende (siehe epoche_loeschen())."""
    if name not in EPOCHE_DATEINAMEN:
        raise HTTPException(404, f"Unbekannte Epochen-Datei '{name}'.")
    pfad = _epoche_pfad(settings, ordner)
    (pfad / name).write_text(anfrage.inhalt, encoding="utf-8")
    return {"gespeichert": True}


@router.put("/{ordner}/genre")
def epoche_genre_schreiben(ordner: str, anfrage: EpocheGenreAnfrage, settings: Settings = Depends(get_settings)):
    pfad = _epoche_pfad(settings, ordner)
    genre = anfrage.genre.strip()
    marker = pfad / ".genre"
    if genre:
        marker.write_text(genre, encoding="utf-8")
    else:
        marker.unlink(missing_ok=True)
    return {"genre": genre or None}
