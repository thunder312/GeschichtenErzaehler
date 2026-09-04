"""Orte-Fundus: benutzerweite Sammlung wiederverwendbarer Schauplaetze,
gegliedert nach Epoche (siehe app/core/orte.py und ToDo.md). Analog zu
app/api/fundus.py (Personen-Fundus), aber ohne Import/Extraktions-Endpunkte -
Orte werden ausschliesslich manuell gepflegt. Eigener Prefix "/api/orte",
betrifft wie /api/fundus die (benutzerspezifische) Projekte-Wurzel als
Ganzes, keinen einzelnen Projektordner."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from app.auth import get_current_user
from app.config import Settings, get_settings
from app.core import orte as ort_modul
from app.core import projekt_dateien as pd
from app.schemas import (
    Benutzer,
    GeruestSchreibenAnfrage,
    OrtAktualisierenAnfrage,
    OrtAnlegenAnfrage,
    OrtAntwort,
    OrteAntwort,
)
from app.services import orte_datei

router = APIRouter(prefix="/api/orte", tags=["orte"])


@router.get("", response_class=PlainTextResponse)
def orte_lesen(settings: Settings = Depends(get_settings), benutzer: Benutzer = Depends(get_current_user)):
    return pd.lies(orte_datei(settings, benutzer.username), pflicht=False, ersatz=ort_modul.leere_vorlage())


@router.put("")
def orte_schreiben(anfrage: GeruestSchreibenAnfrage, settings: Settings = Depends(get_settings),
                    benutzer: Benutzer = Depends(get_current_user)):
    ziel_pfad, gesichert_als = pd.schreib(orte_datei(settings, benutzer.username), anfrage.inhalt)
    return {"gespeichert": str(ziel_pfad), "gesichert_als": gesichert_als}


def _strukturiert_lesen(settings: Settings, benutzer: Benutzer) -> tuple[str, list[ort_modul.Ort]]:
    text = pd.lies(orte_datei(settings, benutzer.username), pflicht=False, ersatz=ort_modul.leere_vorlage())
    return ort_modul.kopf_kommentar_extrahieren(text), ort_modul.orte_parsen(text)


def _strukturiert_schreiben(settings: Settings, benutzer: Benutzer, kopf: str, orte: list[ort_modul.Ort]) -> None:
    pd.schreib(orte_datei(settings, benutzer.username), kopf + ort_modul.orte_serialisieren(orte))


def _ort_finden(orte: list[ort_modul.Ort], epoche: str, name: str) -> ort_modul.Ort:
    for ort in orte:
        if ort.epoche == epoche and ort.name == name:
            return ort
    raise HTTPException(404, f"Ort '{name}' in Epoche '{epoche}' nicht gefunden.")


@router.get("/orte", response_model=OrteAntwort)
def orte_liste_lesen(settings: Settings = Depends(get_settings), benutzer: Benutzer = Depends(get_current_user)):
    _, orte = _strukturiert_lesen(settings, benutzer)
    return OrteAntwort(orte=[OrtAntwort(epoche=o.epoche, name=o.name, beschreibung=o.beschreibung) for o in orte])


@router.post("/orte", response_model=OrtAntwort, status_code=201)
def ort_anlegen(anfrage: OrtAnlegenAnfrage, settings: Settings = Depends(get_settings),
                 benutzer: Benutzer = Depends(get_current_user)):
    name = anfrage.name.strip()
    if not name:
        raise HTTPException(400, "Name darf nicht leer sein.")
    kopf, orte = _strukturiert_lesen(settings, benutzer)
    if any(o.epoche == anfrage.epoche and o.name.lower() == name.lower() for o in orte):
        raise HTTPException(409, f"Ort '{name}' existiert in Epoche '{anfrage.epoche}' bereits.")

    neuer_ort = ort_modul.Ort(epoche=anfrage.epoche, name=name, beschreibung=anfrage.beschreibung)
    orte.append(neuer_ort)
    _strukturiert_schreiben(settings, benutzer, kopf, orte)
    return OrtAntwort(epoche=neuer_ort.epoche, name=neuer_ort.name, beschreibung=neuer_ort.beschreibung)


@router.put("/orte", response_model=OrtAntwort)
def ort_aktualisieren(anfrage: OrtAktualisierenAnfrage, settings: Settings = Depends(get_settings),
                       benutzer: Benutzer = Depends(get_current_user)):
    kopf, orte = _strukturiert_lesen(settings, benutzer)
    ort = _ort_finden(orte, anfrage.epoche, anfrage.name)

    neuer_name = (anfrage.neuer_name or anfrage.name).strip()
    ziel_epoche = (anfrage.neue_epoche or anfrage.epoche).strip()
    if not neuer_name:
        raise HTTPException(400, "Name darf nicht leer sein.")
    if not ziel_epoche:
        raise HTTPException(400, "Epoche darf nicht leer sein.")
    if (ziel_epoche != anfrage.epoche or neuer_name.lower() != anfrage.name.lower()) and any(
        o is not ort and o.epoche == ziel_epoche and o.name.lower() == neuer_name.lower() for o in orte
    ):
        raise HTTPException(409, f"Ort '{neuer_name}' existiert in Epoche '{ziel_epoche}' bereits.")

    ort.name = neuer_name
    ort.epoche = ziel_epoche
    ort.beschreibung = anfrage.beschreibung
    _strukturiert_schreiben(settings, benutzer, kopf, orte)
    return OrtAntwort(epoche=ort.epoche, name=ort.name, beschreibung=ort.beschreibung)


@router.delete("/orte")
def ort_loeschen(epoche: str, name: str, settings: Settings = Depends(get_settings),
                  benutzer: Benutzer = Depends(get_current_user)):
    kopf, orte = _strukturiert_lesen(settings, benutzer)
    ort = _ort_finden(orte, epoche, name)
    orte.remove(ort)
    _strukturiert_schreiben(settings, benutzer, kopf, orte)
    return {"gelöscht": True}
