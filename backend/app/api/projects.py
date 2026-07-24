"""Projektverwaltung: Epochen auflisten, Projekte anlegen/auflisten/lesen,
Gerüst und Verbotsliste bearbeiten, einzelne Kapitel-/Stand-/Befunde-Dateien
lesen. Reine Dateizugriffe nach dem Ordnervertrag aus
doc/Schnittstellen-Uebersicht.md Abschnitt 1 - kein Ollama-Aufruf hier
(siehe app/api/pipeline.py fuer die eigentlichen Schreib-/Pruef-Schritte)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from app.config import Settings, get_settings
from app.core import geruest as g
from app.core import projekt_dateien as pd
from app.schemas import (
    EpocheKurz,
    GeruestSchreibenAnfrage,
    ProjektAnlegenAnfrage,
    ProjektDetail,
    ProjektKurz,
)
from app.services import neuer_projekt_pfad, projekt_pfad, projekte_wurzel

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("/epochen", response_model=list[EpocheKurz])
def epochen_auflisten(settings: Settings = Depends(get_settings)):
    if not settings.epochen_dir.is_dir():
        return []
    return [EpocheKurz(name=p.name) for p in sorted(settings.epochen_dir.iterdir()) if p.is_dir()]


def _projekt_kurz(pfad, settings: Settings) -> ProjektKurz:
    # pfad ist der AEUSSERE Projektordner (mit personas/ und projekt/) -
    # geruest.md und kapitel_*.md liegen im projekt/-Unterordner, siehe
    # projekt_lesen() unten. Ohne dieses Unterverzeichnis waren Titel,
    # Kapitelanzahl und geplante Kapitelzahl in der Projektliste immer
    # leer/0, obwohl die Projekt-Detailansicht (die korrekt in projekt/
    # nachschaut) sie richtig anzeigte.
    projekt_unterordner = pfad / "projekt"
    geruest_text = pd.lies(pd.geruest_datei(projekt_unterordner), pflicht=False, ersatz="")
    titel = g.titel_erkennen(geruest_text) if geruest_text else None
    return ProjektKurz(
        ordner=pfad.name,
        titel=titel,
        epoche=pd.epoche_von_projekt(pfad),
        anzahl_kapitel=len(pd.vorhandene_kapitel(projekt_unterordner)),
        letztes_geplantes_kapitel=g.letztes_geplantes_kapitel(geruest_text) if geruest_text else None,
    )


@router.get("", response_model=list[ProjektKurz])
def projekte_auflisten(settings: Settings = Depends(get_settings)):
    wurzel = projekte_wurzel(settings)
    if not wurzel.is_dir():
        return []
    ergebnis = []
    for eintrag in sorted(wurzel.iterdir()):
        if eintrag.is_dir() and (eintrag / "projekt").is_dir():
            ergebnis.append(_projekt_kurz(eintrag, settings))
    return ergebnis


@router.post("", response_model=ProjektKurz, status_code=201)
def projekt_anlegen(anfrage: ProjektAnlegenAnfrage, settings: Settings = Depends(get_settings)):
    epoche_ordner = settings.epochen_dir / anfrage.epoche
    if not epoche_ordner.is_dir():
        raise HTTPException(404, f"Epoche '{anfrage.epoche}' nicht gefunden.")
    # Ohne Titel (ergibt sich oft erst aus dem Architekten-Interview) einen
    # Platzhalter-Ordner "neu" anlegen - projektordner_umbenennen() benennt
    # ihn automatisch um, sobald das Interview einen Titel liefert.
    basis_titel = anfrage.titel.strip() or "neu"
    ziel = neuer_projekt_pfad(settings, basis_titel)
    pd.projekt_anlegen(ziel, epoche_ordner, settings.shared_personas_dir, anfrage.epoche)
    return _projekt_kurz(ziel, settings)


@router.get("/{ordner}", response_model=ProjektDetail)
def projekt_lesen(ordner: str, settings: Settings = Depends(get_settings)):
    pfad = projekt_pfad(settings, ordner)
    projekt_unterordner = pfad / "projekt"
    geruest_text = pd.lies(pd.geruest_datei(projekt_unterordner), pflicht=False, ersatz="")
    verbotsliste_text = pd.lies(pd.verbotsliste_datei(projekt_unterordner), pflicht=False, ersatz="")
    kapitel = [pd.kapitelnummer_aus_dateiname(p) for p in pd.vorhandene_kapitel(projekt_unterordner)]
    return ProjektDetail(
        ordner=ordner,
        epoche=pd.epoche_von_projekt(pfad),
        geruest=geruest_text or None,
        verbotsliste=verbotsliste_text or None,
        kapitel=kapitel,
        jahr=g.jahr_erkennen(geruest_text) if geruest_text else None,
        jugendschutz_stufe=g.jugendschutz_stufe_erkennen(geruest_text) if geruest_text else None,
        autor_modell=g.autor_rolle_erkennen(geruest_text) if geruest_text else None,
        automatische_fortsetzung=g.automatische_fortsetzung_aktiviert(geruest_text) if geruest_text else None,
        letztes_geplantes_kapitel=g.letztes_geplantes_kapitel(geruest_text) if geruest_text else None,
        kapitelplan=g.kapitelplan_erkennen(geruest_text) if geruest_text else {},
    )


@router.put("/{ordner}/geruest")
def geruest_schreiben(ordner: str, anfrage: GeruestSchreibenAnfrage,
                       settings: Settings = Depends(get_settings)):
    pfad = projekt_pfad(settings, ordner) / "projekt"
    ziel_pfad, gesichert_als = pd.schreib(pd.geruest_datei(pfad), anfrage.inhalt)
    return {"gespeichert": str(ziel_pfad), "gesichert_als": gesichert_als}


@router.put("/{ordner}/verbotsliste")
def verbotsliste_schreiben(ordner: str, anfrage: GeruestSchreibenAnfrage,
                            settings: Settings = Depends(get_settings)):
    pfad = projekt_pfad(settings, ordner) / "projekt"
    ziel_pfad, gesichert_als = pd.schreib(pd.verbotsliste_datei(pfad), anfrage.inhalt)
    return {"gespeichert": str(ziel_pfad), "gesichert_als": gesichert_als}


PERSONA_NAMEN = (
    "architekt", "autor", "pruefer_anachronismus",
    "chronist", "pruefer_kontinuitaet", "lektor", "anachronismen_korrektur",
)


@router.get("/{ordner}/personas", response_model=list[str])
def personas_auflisten(ordner: str, settings: Settings = Depends(get_settings)):
    pfad = projekt_pfad(settings, ordner) / "personas"
    return [name for name in PERSONA_NAMEN if (pfad / f"{name}.txt").exists()]


@router.get("/{ordner}/personas/{name}", response_class=PlainTextResponse)
def persona_lesen(ordner: str, name: str, settings: Settings = Depends(get_settings)):
    if name not in PERSONA_NAMEN:
        raise HTTPException(404, f"Unbekannte Persona '{name}'.")
    projekt_root = projekt_pfad(settings, ordner)
    try:
        return pd.persona_lesen(projekt_root, name)
    except pd.DateiFehlt as e:
        raise HTTPException(404, str(e)) from e


@router.put("/{ordner}/personas/{name}")
def persona_schreiben(ordner: str, name: str, anfrage: GeruestSchreibenAnfrage,
                       settings: Settings = Depends(get_settings)):
    if name not in PERSONA_NAMEN:
        raise HTTPException(404, f"Unbekannte Persona '{name}'.")
    projekt_root = projekt_pfad(settings, ordner)
    _, gesichert_als = pd.schreib(projekt_root / "personas" / f"{name}.txt", anfrage.inhalt)
    return {"gesichert_als": gesichert_als}


@router.get("/{ordner}/architekten-gespraech", response_class=PlainTextResponse)
def architekten_gespraech_lesen(ordner: str, settings: Settings = Depends(get_settings)):
    pfad = projekt_pfad(settings, ordner) / "projekt" / "architekten_gespraech.md"
    if not pfad.exists():
        raise HTTPException(404, "Noch kein abgeschlossenes Architekten-Gespräch für dieses Projekt gespeichert.")
    return pd.lies(pfad)


@router.get("/{ordner}/kapitel/{n}", response_class=PlainTextResponse)
def kapitel_lesen(ordner: str, n: int, settings: Settings = Depends(get_settings)):
    pfad = projekt_pfad(settings, ordner) / "projekt"
    datei = pd.kapitel_datei(pfad, n)
    if not datei.exists():
        raise HTTPException(404, f"Kapitel {n} nicht gefunden.")
    return pd.lies(datei)


@router.put("/{ordner}/kapitel/{n}")
def kapitel_schreiben(ordner: str, n: int, anfrage: GeruestSchreibenAnfrage,
                       settings: Settings = Depends(get_settings)):
    """Speichert einen (ggf. im Merge-Editor von Hand nachbearbeiteten)
    Kapiteltext. Alte Fassung wird wie ueberall automatisch als .bak
    gesichert (siehe app/core/projekt_dateien.py:schreib)."""
    pfad = projekt_pfad(settings, ordner) / "projekt"
    _, gesichert_als = pd.schreib(pd.kapitel_datei(pfad, n), anfrage.inhalt)
    return {"gesichert_als": gesichert_als}


@router.get("/{ordner}/stand/{n}", response_class=PlainTextResponse)
def stand_lesen(ordner: str, n: int, settings: Settings = Depends(get_settings)):
    pfad = projekt_pfad(settings, ordner) / "projekt"
    datei = pd.stand_datei(pfad, n)
    if not datei.exists():
        raise HTTPException(404, f"Stand {n} nicht gefunden.")
    return pd.lies(datei)


@router.get("/{ordner}/befunde/{n}", response_class=PlainTextResponse)
def befunde_lesen(ordner: str, n: int, settings: Settings = Depends(get_settings)):
    pfad = projekt_pfad(settings, ordner) / "projekt"
    datei = pd.befunde_datei(pfad, n)
    if not datei.exists():
        raise HTTPException(404, f"Befunde zu Kapitel {n} nicht gefunden.")
    return pd.lies(datei)


@router.get("/{ordner}/gesamt", response_class=PlainTextResponse)
def gesamt_lesen(ordner: str, settings: Settings = Depends(get_settings)):
    pfad = projekt_pfad(settings, ordner) / "projekt" / "gesamt.md"
    if not pfad.exists():
        raise HTTPException(404, "gesamt.md nicht gefunden - noch nicht exportiert.")
    return pd.lies(pfad)
