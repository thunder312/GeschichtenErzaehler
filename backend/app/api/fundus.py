"""Personen-Fundus: zentrale, benutzerweite Sammlung wiederverwendbarer
Figuren (siehe app/core/fundus.py und ToDo.md). Anders als projects.py/
pipeline.py/architekt.py betrifft das keinen einzelnen Projektordner,
sondern die (benutzerspezifische) Projekte-Wurzel als Ganzes - eigener
Prefix "/api/fundus", kollidiert nicht mit dem Catch-All aus projects.py.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import ValidationError

from app.auth import get_current_user
from app.config import Settings, get_settings
from app.core import architekt as arch
from app.core import fundus as fu
from app.core import geruest as g
from app.core import projekt_dateien as pd
from app.core.fundus_schema import FundusExtraktionAntwortLLM
from app.core.ollama_client import OllamaFehler, sammle_antwort
from app.schemas import Benutzer, FundusImportAntwort, GeruestSchreibenAnfrage
from app.services import fundus_datei, ollama_basis_url, projekte_wurzel, rollen_modell_override

router = APIRouter(prefix="/api/fundus", tags=["fundus"])


@router.get("", response_class=PlainTextResponse)
def fundus_lesen(settings: Settings = Depends(get_settings),
                  benutzer: Benutzer = Depends(get_current_user)):
    return pd.lies(fundus_datei(settings, benutzer.username), pflicht=False, ersatz=fu.leere_vorlage())


@router.put("")
def fundus_schreiben(anfrage: GeruestSchreibenAnfrage, settings: Settings = Depends(get_settings),
                      benutzer: Benutzer = Depends(get_current_user)):
    ziel_pfad, gesichert_als = pd.schreib(fundus_datei(settings, benutzer.username), anfrage.inhalt)
    return {"gespeichert": str(ziel_pfad), "gesichert_als": gesichert_als}


def _ist_projekt_ordner(pfad) -> bool:
    return pfad.is_dir() and (pfad / "projekt").is_dir()


def _projekt_ordner_alle(wurzel) -> list:
    """Direkte Projektordner UND eine Ebene Epoche-Unterordner darunter -
    dieselbe Iterationslogik wie app/api/projects.py:projekte_auflisten()."""
    ergebnis = []
    if not wurzel.is_dir():
        return ergebnis
    for eintrag in sorted(wurzel.iterdir()):
        if not eintrag.is_dir():
            continue
        if _ist_projekt_ordner(eintrag):
            ergebnis.append(eintrag)
            continue
        for unter_eintrag in sorted(eintrag.iterdir()):
            if _ist_projekt_ordner(unter_eintrag):
                ergebnis.append(unter_eintrag)
    return ergebnis


@router.post("/import", response_model=FundusImportAntwort)
async def fundus_importieren(ssh_ziel_id: str | None = Query(None),
                              settings: Settings = Depends(get_settings),
                              benutzer: Benutzer = Depends(get_current_user)):
    wurzel = projekte_wurzel(settings, benutzer.username)
    persona = pd.lies(settings.shared_personas_dir / "fundus_pfleger.txt")
    fundus_text = pd.lies(fundus_datei(settings, benutzer.username), pflicht=False, ersatz=fu.leere_vorlage())

    importierte_projekte = 0
    gefundene_figuren = 0
    uebersprungen: list[str] = []

    with ollama_basis_url(settings, ssh_ziel_id) as base_url:
        # Sequentiell statt parallel: ein lokales Ollama verarbeitet ohnehin
        # nur einen Chat-Request sinnvoll gleichzeitig (siehe Kommentar bei
        # ROLLEN in app/core/rollen.py zu KEEP_ALIVE).
        for projekt_ordner in _projekt_ordner_alle(wurzel):
            projekt = projekt_ordner / "projekt"
            geruest_text = pd.lies(pd.geruest_datei(projekt), pflicht=False, ersatz="")
            figuren_text = arch.figuren_abschnitt_erkennen(geruest_text) if geruest_text else None
            if not figuren_text:
                uebersprungen.append(projekt_ordner.name)
                continue

            epoche = pd.epoche_von_projekt(projekt_ordner)
            titel = g.titel_erkennen(geruest_text) or projekt_ordner.name
            if not epoche:
                uebersprungen.append(projekt_ordner.name)
                continue

            try:
                antwort_text, _ = await sammle_antwort(
                    base_url, "fundus_pfleger", persona, figuren_text, format="json",
                    modell_override=rollen_modell_override(settings, "fundus_pfleger"),
                )
                antwort = FundusExtraktionAntwortLLM.model_validate_json(antwort_text)
            except (OllamaFehler, ValidationError):
                uebersprungen.append(projekt_ordner.name)
                continue

            if not antwort.figuren:
                importierte_projekte += 1
                continue

            figuren = [fu.FigurEintrag(name=e.name, alter=e.alter, stand=e.stand, eigenschaften=e.eigenschaften)
                       for e in antwort.figuren]
            fundus_text = fu.figuren_zusammenfuehren(fundus_text, epoche, titel, figuren)
            importierte_projekte += 1
            gefundene_figuren += len(figuren)

    pd.schreib(fundus_datei(settings, benutzer.username), fundus_text, force=True)
    return FundusImportAntwort(
        importierte_projekte=importierte_projekte,
        gefundene_figuren=gefundene_figuren,
        uebersprungen=uebersprungen,
    )
