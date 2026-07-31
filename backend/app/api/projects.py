"""Projektverwaltung: Epochen auflisten, Projekte anlegen/auflisten/lesen,
Gerüst und Verbotsliste bearbeiten, einzelne Kapitel-/Stand-/Befunde-Dateien
lesen. Reine Dateizugriffe nach dem Ordnervertrag aus
doc/Schnittstellen-Uebersicht.md Abschnitt 1 - kein Ollama-Aufruf hier
(siehe app/api/pipeline.py fuer die eigentlichen Schreib-/Pruef-Schritte)."""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from app.auth import get_current_user
from app.config import Settings, get_settings
from app.core import geruest as g
from app.core import projekt_dateien as pd
from app.schemas import (
    BefundeAntwort,
    Benutzer,
    EpocheKurz,
    GeruestSchreibenAnfrage,
    ProjektAnlegenAnfrage,
    ProjektDetail,
    ProjektKurz,
)
from app.services import neuer_projekt_pfad, ordner_nach_umbenennung, projekt_pfad, projekte_wurzel

router = APIRouter(prefix="/api/projects", tags=["projects"])

# Die "/{ordner:path}"-Route fuer die Projekt-Detailansicht ist ein
# Catch-All (matcht dank ":path" JEDEN Rest-Pfad, auch mit "/" darin - noetig
# fuer Epoche-Unterordner, siehe app/services.py:neuer_projekt_pfad). In
# EINEM Router wuerde sie spezifischere Routen wie ".../personas" oder
# ".../geruest" verdecken, egal in welcher Reihenfolge sie hier definiert
# sind, da FastAPI Router-uebergreifend in Einbindungsreihenfolge matcht
# (siehe app/main.py) - andere Router (pipeline, architekt) mit eigenen
# "/{ordner:path}/..."-Routen wuerden sonst nie erreicht. Deshalb ein
# eigener Router, der in main.py bewusst ALS LETZTER unter allen
# projekt-bezogenen Routern eingebunden wird.
fallback_router = APIRouter(prefix="/api/projects", tags=["projects"])


def _epoche_genre_lesen(epoche_ordner) -> str | None:
    marker = epoche_ordner / ".genre"
    if not marker.exists():
        return None
    return marker.read_text(encoding="utf-8").strip() or None


@router.get("/epochen", response_model=list[EpocheKurz])
def epochen_auflisten(settings: Settings = Depends(get_settings)):
    if not settings.epochen_dir.is_dir():
        return []
    return [
        EpocheKurz(name=p.name, genre=_epoche_genre_lesen(p))
        for p in sorted(settings.epochen_dir.iterdir()) if p.is_dir()
    ]


def _projekt_kurz(pfad, wurzel, settings: Settings) -> ProjektKurz:
    # pfad ist der AEUSSERE Projektordner (mit personas/ und projekt/) -
    # geruest.md und kapitel_*.md liegen im projekt/-Unterordner, siehe
    # projekt_lesen() unten. Ohne dieses Unterverzeichnis waren Titel,
    # Kapitelanzahl und geplante Kapitelzahl in der Projektliste immer
    # leer/0, obwohl die Projekt-Detailansicht (die korrekt in projekt/
    # nachschaut) sie richtig anzeigte.
    # ordner ist der Pfad relativ zur Speicherort-Wurzel (mit "/" als
    # Trenner) statt nur pfad.name - bei aktivierten Epoche-Unterordnern
    # (siehe app/services.py:neuer_projekt_pfad) liegt ein Projekt eine
    # Ebene tiefer, z.B. "Mittelalter/Im-Feuer-gestaehlt".
    projekt_unterordner = pfad / "projekt"
    geruest_text = pd.lies(pd.geruest_datei(projekt_unterordner), pflicht=False, ersatz="")
    titel = g.titel_erkennen(geruest_text) if geruest_text else None
    return ProjektKurz(
        ordner=pfad.relative_to(wurzel).as_posix(),
        titel=titel,
        epoche=pd.epoche_von_projekt(pfad),
        anzahl_kapitel=len(pd.vorhandene_kapitel(projekt_unterordner)),
        letztes_geplantes_kapitel=g.letztes_geplantes_kapitel(geruest_text) if geruest_text else None,
    )


def _ist_projekt_ordner(pfad) -> bool:
    return pfad.is_dir() and (pfad / "projekt").is_dir()


@router.get("", response_model=list[ProjektKurz])
def projekte_auflisten(settings: Settings = Depends(get_settings),
                        benutzer: Benutzer = Depends(get_current_user)):
    wurzel = projekte_wurzel(settings, benutzer.username)
    if not wurzel.is_dir():
        return []
    ergebnis = []
    for eintrag in sorted(wurzel.iterdir()):
        if not eintrag.is_dir():
            continue
        if _ist_projekt_ordner(eintrag):
            ergebnis.append(_projekt_kurz(eintrag, wurzel, settings))
            continue
        # Kein direktes Projekt - koennte ein Epoche-Unterordner sein
        # (siehe "Unterordner je Epoche"-Einstellung), eine Ebene tiefer
        # nachsehen.
        for unter_eintrag in sorted(eintrag.iterdir()):
            if _ist_projekt_ordner(unter_eintrag):
                ergebnis.append(_projekt_kurz(unter_eintrag, wurzel, settings))
    return ergebnis


@router.post("", response_model=ProjektKurz, status_code=201)
def projekt_anlegen(anfrage: ProjektAnlegenAnfrage, settings: Settings = Depends(get_settings),
                     benutzer: Benutzer = Depends(get_current_user)):
    epoche_ordner = settings.epochen_dir / anfrage.epoche
    if not epoche_ordner.is_dir():
        raise HTTPException(404, f"Epoche '{anfrage.epoche}' nicht gefunden.")
    # Ohne Titel (ergibt sich oft erst aus dem Architekten-Interview) einen
    # Platzhalter-Ordner "neu" anlegen - projektordner_umbenennen() benennt
    # ihn automatisch um, sobald das Interview einen Titel liefert.
    basis_titel = anfrage.titel.strip() or "neu"
    ziel = neuer_projekt_pfad(settings, benutzer.username, basis_titel, anfrage.epoche)
    pd.projekt_anlegen(ziel, epoche_ordner, settings.shared_personas_dir, anfrage.epoche)
    return _projekt_kurz(ziel, projekte_wurzel(settings, benutzer.username), settings)


@fallback_router.get("/{ordner:path}", response_model=ProjektDetail)
def projekt_lesen(ordner: str, settings: Settings = Depends(get_settings),
                   benutzer: Benutzer = Depends(get_current_user)):
    pfad = projekt_pfad(settings, benutzer.username, ordner)
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


@router.put("/{ordner:path}/geruest")
def geruest_schreiben(ordner: str, anfrage: GeruestSchreibenAnfrage,
                       settings: Settings = Depends(get_settings),
                       benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    ziel_pfad, gesichert_als = pd.schreib(pd.geruest_datei(projekt_root / "projekt"), anfrage.inhalt)
    # Der Ordner traegt nach der Projektanlage oft noch den Platzhalter-
    # Namen "neu" (siehe projekt_anlegen()) - das Architekten-Interview
    # benennt ihn zwar am Ende automatisch um, aber nicht, wenn der Titel
    # erst nachtraeglich hier im Gerueest-Editor gesetzt/geaendert wird.
    # Ohne diesen Aufruf bliebe der Ordner dann dauerhaft "neu".
    neuer_name = pd.projektordner_umbenennen(projekt_root, anfrage.inhalt)
    neuer_ordner = ordner_nach_umbenennung(ordner, neuer_name) if neuer_name else None
    return {"gespeichert": str(ziel_pfad), "gesichert_als": gesichert_als, "neuer_ordner": neuer_ordner}


@router.put("/{ordner:path}/verbotsliste")
def verbotsliste_schreiben(ordner: str, anfrage: GeruestSchreibenAnfrage,
                            settings: Settings = Depends(get_settings),
                            benutzer: Benutzer = Depends(get_current_user)):
    pfad = projekt_pfad(settings, benutzer.username, ordner) / "projekt"
    ziel_pfad, gesichert_als = pd.schreib(pd.verbotsliste_datei(pfad), anfrage.inhalt)
    return {"gespeichert": str(ziel_pfad), "gesichert_als": gesichert_als}


PERSONA_NAMEN = (
    "architekt", "autor", "pruefer_anachronismus",
    "chronist", "pruefer_kontinuitaet", "lektor", "pruefer_satzbau",
)


@router.get("/{ordner:path}/personas", response_model=list[str])
def personas_auflisten(ordner: str, settings: Settings = Depends(get_settings),
                        benutzer: Benutzer = Depends(get_current_user)):
    pfad = projekt_pfad(settings, benutzer.username, ordner) / "personas"
    return [name for name in PERSONA_NAMEN if (pfad / f"{name}.txt").exists()]


@router.get("/{ordner:path}/personas/{name}", response_class=PlainTextResponse)
def persona_lesen(ordner: str, name: str, settings: Settings = Depends(get_settings),
                   benutzer: Benutzer = Depends(get_current_user)):
    if name not in PERSONA_NAMEN:
        raise HTTPException(404, f"Unbekannte Persona '{name}'.")
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    try:
        return pd.persona_lesen(projekt_root, name)
    except pd.DateiFehlt as e:
        raise HTTPException(404, str(e)) from e


@router.put("/{ordner:path}/personas/{name}")
def persona_schreiben(ordner: str, name: str, anfrage: GeruestSchreibenAnfrage,
                       settings: Settings = Depends(get_settings),
                       benutzer: Benutzer = Depends(get_current_user)):
    if name not in PERSONA_NAMEN:
        raise HTTPException(404, f"Unbekannte Persona '{name}'.")
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    _, gesichert_als = pd.schreib(projekt_root / "personas" / f"{name}.txt", anfrage.inhalt)
    return {"gesichert_als": gesichert_als}


@router.get("/{ordner:path}/architekten-gespraech", response_class=PlainTextResponse)
def architekten_gespraech_lesen(ordner: str, settings: Settings = Depends(get_settings),
                                 benutzer: Benutzer = Depends(get_current_user)):
    pfad = projekt_pfad(settings, benutzer.username, ordner) / "projekt" / "architekten_gespraech.md"
    if not pfad.exists():
        raise HTTPException(404, "Noch kein abgeschlossenes Architekten-Gespräch für dieses Projekt gespeichert.")
    return pd.lies(pfad)


@router.get("/{ordner:path}/kapitel/{n}", response_class=PlainTextResponse)
def kapitel_lesen(ordner: str, n: int, settings: Settings = Depends(get_settings),
                   benutzer: Benutzer = Depends(get_current_user)):
    pfad = projekt_pfad(settings, benutzer.username, ordner) / "projekt"
    datei = pd.kapitel_datei(pfad, n)
    if not datei.exists():
        raise HTTPException(404, f"Kapitel {n} nicht gefunden.")
    return pd.lies(datei)


@router.put("/{ordner:path}/kapitel/{n}")
def kapitel_schreiben(ordner: str, n: int, anfrage: GeruestSchreibenAnfrage,
                       settings: Settings = Depends(get_settings),
                       benutzer: Benutzer = Depends(get_current_user)):
    """Speichert einen (ggf. im Merge-Editor von Hand nachbearbeiteten)
    Kapiteltext. Alte Fassung wird wie ueberall automatisch als .bak
    gesichert (siehe app/core/projekt_dateien.py:schreib)."""
    pfad = projekt_pfad(settings, benutzer.username, ordner) / "projekt"
    _, gesichert_als = pd.schreib(pd.kapitel_datei(pfad, n), anfrage.inhalt)
    return {"gesichert_als": gesichert_als}


@router.get("/{ordner:path}/stand/{n}", response_class=PlainTextResponse)
def stand_lesen(ordner: str, n: int, settings: Settings = Depends(get_settings),
                 benutzer: Benutzer = Depends(get_current_user)):
    pfad = projekt_pfad(settings, benutzer.username, ordner) / "projekt"
    datei = pd.stand_datei(pfad, n)
    if not datei.exists():
        raise HTTPException(404, f"Stand {n} nicht gefunden.")
    return pd.lies(datei)


@router.get("/{ordner:path}/befunde/{n}", response_model=BefundeAntwort)
def befunde_lesen(ordner: str, n: int, settings: Settings = Depends(get_settings),
                   benutzer: Benutzer = Depends(get_current_user)):
    pfad = projekt_pfad(settings, benutzer.username, ordner) / "projekt"
    datei = pd.befunde_datei(pfad, n)
    if not datei.exists():
        raise HTTPException(404, f"Befunde zu Kapitel {n} nicht gefunden.")
    antwort = BefundeAntwort.model_validate_json(pd.lies(datei))

    # Die start/end-Offsets in `antwort.befunde` wurden beim letzten
    # /pruefen-Lauf gegen den DAMALIGEN Kapiteltext berechnet. Wurde die
    # Kapiteldatei seither ueberschrieben (Regenerierung im Schreiben-Tab,
    # manuelles Speichern), zeigen sie auf falsche Stellen im JETZIGEN Text -
    # der klassische "Offsets aus Revision A auf Revision B angewandt"-Fehler.
    # Hash-Vergleich erkennt das billig, bevor das Frontend ueberhaupt erst
    # eine (dann falsch positionierte) Decoration anlegt; der Anker-Check in
    # befundReview.ts faengt es zusaetzlich pro Fund ab, falls hier doch mal
    # etwas durchrutscht (z.B. altes befunde_*.json ohne quelltext_sha256).
    kapitel_datei = pd.kapitel_datei(pfad, n)
    if kapitel_datei.exists():
        aktueller_hash = hashlib.sha256(pd.lies(kapitel_datei).encode("utf-8")).hexdigest()
        antwort.veraltet = antwort.quelltext_sha256 != aktueller_hash

    return antwort


@router.get("/{ordner:path}/gesamt", response_class=PlainTextResponse)
def gesamt_lesen(ordner: str, settings: Settings = Depends(get_settings),
                  benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    pfad = projekt_root / f"{projekt_root.name}.md"
    if not pfad.exists():
        raise HTTPException(404, "Noch nicht exportiert.")
    return pd.lies(pfad)
