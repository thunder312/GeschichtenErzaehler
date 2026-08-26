"""Personen-Fundus: zentrale, benutzerweite Sammlung wiederverwendbarer
Figuren (siehe app/core/fundus.py und ToDo.md). Anders als projects.py/
pipeline.py/architekt.py betrifft das keinen einzelnen Projektordner,
sondern die (benutzerspezifische) Projekte-Wurzel als Ganzes - eigener
Prefix "/api/fundus", kollidiert nicht mit dem Catch-All aus projects.py.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
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
from app.schemas import (
    Benutzer,
    FundusFeldHinzufuegenAnfrage,
    FundusFigurAktualisierenAnfrage,
    FundusFigurAnlegenAnfrage,
    FundusFigurAntwort,
    FundusFigurenAntwort,
    FundusFigurKopierenAnfrage,
    FundusImportAntwort,
    FundusProjektAntwort,
    GeruestSchreibenAnfrage,
)
from app.services import fundus_datei, ollama_basis_url, projekt_pfad, projekte_wurzel, rollen_modell_override

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


def _strukturiert_lesen(settings: Settings, benutzer: Benutzer) -> tuple[str, list[fu.Figur]]:
    text = pd.lies(fundus_datei(settings, benutzer.username), pflicht=False, ersatz=fu.leere_vorlage())
    return fu.kopf_kommentar_extrahieren(text), fu.fundus_parsen(text)


def _strukturiert_schreiben(settings: Settings, benutzer: Benutzer, kopf: str, figuren: list[fu.Figur]) -> None:
    pd.schreib(fundus_datei(settings, benutzer.username), kopf + fu.fundus_serialisieren(figuren))


def _figur_finden(figuren: list[fu.Figur], epoche: str, name: str) -> fu.Figur:
    for figur in figuren:
        if figur.epoche == epoche and figur.name == name:
            return figur
    raise HTTPException(404, f"Figur '{name}' in Epoche '{epoche}' nicht gefunden.")


@router.get("/figuren", response_model=FundusFigurenAntwort)
def fundus_figuren_lesen(settings: Settings = Depends(get_settings),
                          benutzer: Benutzer = Depends(get_current_user)):
    """Strukturierte Sicht auf den kompletten Fundus fuer den Personen-
    Editor (siehe FundusPage.tsx) - Browsing/Filtern/Suchen/Bearbeiten
    laeuft clientseitig auf dieser einen Liste, der Datensatz ist mit
    aktuell rund 100 Figuren klein genug dafuer."""
    _, figuren = _strukturiert_lesen(settings, benutzer)
    return FundusFigurenAntwort(
        figuren=[FundusFigurAntwort(epoche=f.epoche, name=f.name, felder=f.felder) for f in figuren],
        standard_felder=fu.STANDARD_FELDER + ["Geschichten"],
    )


@router.post("/figuren", response_model=FundusFigurAntwort, status_code=201)
def fundus_figur_anlegen(anfrage: FundusFigurAnlegenAnfrage, settings: Settings = Depends(get_settings),
                          benutzer: Benutzer = Depends(get_current_user)):
    name = anfrage.name.strip()
    if not name or not fu.ist_plausibler_figurenname(name):
        raise HTTPException(400, f"'{anfrage.name}' ist kein gültiger Figurenname.")
    kopf, figuren = _strukturiert_lesen(settings, benutzer)
    if any(f.epoche == anfrage.epoche and f.name.lower() == name.lower() for f in figuren):
        raise HTTPException(409, f"Figur '{name}' existiert in Epoche '{anfrage.epoche}' bereits.")

    # Standardfelder immer alle anlegen (auch leer) - konsistent mit
    # figur_block_erzeugen() fuer automatisch angelegte Figuren; vom Nutzer
    # mitgegebene Werte (auch fuer eigene Zusatzfelder) haben Vorrang.
    felder = dict.fromkeys(fu.STANDARD_FELDER, "")
    felder.update(anfrage.felder)
    felder["Geschichten"] = felder.pop("Geschichten", "")

    neue_figur = fu.Figur(epoche=anfrage.epoche, name=name, felder=felder)
    figuren.append(neue_figur)
    _strukturiert_schreiben(settings, benutzer, kopf, figuren)
    return FundusFigurAntwort(epoche=neue_figur.epoche, name=neue_figur.name, felder=neue_figur.felder)


@router.put("/figuren", response_model=FundusFigurAntwort)
def fundus_figur_aktualisieren(anfrage: FundusFigurAktualisierenAnfrage, settings: Settings = Depends(get_settings),
                                benutzer: Benutzer = Depends(get_current_user)):
    """Bearbeitet Felder/Name einer Figur - gesetztes neue_epoche VERSCHIEBT
    sie zusaetzlich in eine andere Epoche (siehe FundusFigurAktualisierenAnfrage;
    fuer eine Kopie stattdessen fundus_figur_kopieren unten)."""
    kopf, figuren = _strukturiert_lesen(settings, benutzer)
    figur = _figur_finden(figuren, anfrage.epoche, anfrage.name)

    neuer_name = (anfrage.neuer_name or anfrage.name).strip()
    ziel_epoche = (anfrage.neue_epoche or anfrage.epoche).strip()
    if not neuer_name or not fu.ist_plausibler_figurenname(neuer_name):
        raise HTTPException(400, f"'{anfrage.neuer_name}' ist kein gültiger Figurenname.")
    if not ziel_epoche:
        raise HTTPException(400, "Epoche darf nicht leer sein.")
    if (ziel_epoche != anfrage.epoche or neuer_name.lower() != anfrage.name.lower()) and any(
        f is not figur and f.epoche == ziel_epoche and f.name.lower() == neuer_name.lower() for f in figuren
    ):
        raise HTTPException(409, f"Figur '{neuer_name}' existiert in Epoche '{ziel_epoche}' bereits.")

    figur.name = neuer_name
    figur.epoche = ziel_epoche
    figur.felder = anfrage.felder
    _strukturiert_schreiben(settings, benutzer, kopf, figuren)
    return FundusFigurAntwort(epoche=figur.epoche, name=figur.name, felder=figur.felder)


@router.post("/figuren/kopieren", response_model=FundusFigurAntwort, status_code=201)
def fundus_figur_kopieren(anfrage: FundusFigurKopierenAnfrage, settings: Settings = Depends(get_settings),
                           benutzer: Benutzer = Depends(get_current_user)):
    """Dupliziert eine Figur (alle Felder inkl. 'Geschichten') in eine
    (i.d.R. andere) Epoche - anders als fundus_figur_aktualisieren mit
    neue_epoche bleibt das Original dabei unangetastet."""
    kopf, figuren = _strukturiert_lesen(settings, benutzer)
    quelle = _figur_finden(figuren, anfrage.epoche, anfrage.name)

    ziel_epoche = anfrage.ziel_epoche.strip()
    ziel_name = (anfrage.neuer_name or quelle.name).strip()
    if not ziel_epoche:
        raise HTTPException(400, "Ziel-Epoche darf nicht leer sein.")
    if not ziel_name or not fu.ist_plausibler_figurenname(ziel_name):
        raise HTTPException(400, f"'{anfrage.neuer_name}' ist kein gültiger Figurenname.")
    if any(f.epoche == ziel_epoche and f.name.lower() == ziel_name.lower() for f in figuren):
        raise HTTPException(409, f"Figur '{ziel_name}' existiert in Epoche '{ziel_epoche}' bereits.")

    kopie = fu.Figur(epoche=ziel_epoche, name=ziel_name, felder=dict(quelle.felder))
    figuren.append(kopie)
    _strukturiert_schreiben(settings, benutzer, kopf, figuren)
    return FundusFigurAntwort(epoche=kopie.epoche, name=kopie.name, felder=kopie.felder)


@router.delete("/figuren")
def fundus_figur_loeschen(epoche: str, name: str, settings: Settings = Depends(get_settings),
                           benutzer: Benutzer = Depends(get_current_user)):
    kopf, figuren = _strukturiert_lesen(settings, benutzer)
    figur = _figur_finden(figuren, epoche, name)
    figuren.remove(figur)
    _strukturiert_schreiben(settings, benutzer, kopf, figuren)
    return {"gelöscht": True}


@router.post("/felder")
def fundus_feld_hinzufuegen(anfrage: FundusFeldHinzufuegenAnfrage, settings: Settings = Depends(get_settings),
                             benutzer: Benutzer = Depends(get_current_user)):
    """Fuegt EIN neues, freies Feld hinzu - entweder nur bei der genannten
    Figur (fuer_alle=False) oder (mit leerem Startwert) bei jeder anderen
    Figur im gesamten Fundus gleich mit, die es noch nicht hat
    (fuer_alle=True). Ort der Vorschlags-Sortierung ist die Feld-Reihenfolge
    selbst: neue Felder landen immer direkt vor 'Geschichten', siehe
    app/core/fundus.py:feld_setzen."""
    feld_name = anfrage.feld_name.strip()
    if not feld_name:
        raise HTTPException(400, "Feldname darf nicht leer sein.")
    kopf, figuren = _strukturiert_lesen(settings, benutzer)
    figur = _figur_finden(figuren, anfrage.epoche, anfrage.name)

    fu.feld_setzen(figur.felder, feld_name, anfrage.wert)
    if anfrage.fuer_alle:
        for andere in figuren:
            if andere is figur or feld_name in andere.felder:
                continue
            fu.feld_setzen(andere.felder, feld_name, "")

    _strukturiert_schreiben(settings, benutzer, kopf, figuren)
    return FundusFigurAntwort(epoche=figur.epoche, name=figur.name, felder=figur.felder)


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


async def _projekt_figuren_importieren(
    base_url: str, settings: Settings, persona: str, fundus_text: str, projekt_ordner,
) -> tuple[str, int, bool]:
    """Extrahiert die Figuren EINES Projekts und fuehrt sie in fundus_text
    ein - gemeinsamer Kern fuer den Bibliotheks-weiten Import unten und die
    Einzelprojekt-Aktualisierung (siehe fundus_projekt_aktualisieren).
    Rueckgabe: (aktualisierter fundus_text, Anzahl gefundener Figuren, ob
    das Projekt uebersprungen wurde - z.B. weil es keinen Figuren-Abschnitt
    oder keine erkannte Epoche hat)."""
    projekt = projekt_ordner / "projekt"
    geruest_text = pd.lies(pd.geruest_datei(projekt), pflicht=False, ersatz="")
    figuren_text = arch.figuren_abschnitt_erkennen(geruest_text) if geruest_text else None
    if not figuren_text:
        return fundus_text, 0, True

    epoche = pd.epoche_von_projekt(projekt_ordner)
    titel = g.titel_erkennen(geruest_text) or projekt_ordner.name
    if not epoche:
        return fundus_text, 0, True

    try:
        antwort_text, _ = await sammle_antwort(
            base_url, "fundus_pfleger", persona, figuren_text, format="json",
            modell_override=rollen_modell_override(settings, "fundus_pfleger"),
        )
        antwort = FundusExtraktionAntwortLLM.model_validate_json(antwort_text)
    except (OllamaFehler, ValidationError):
        return fundus_text, 0, True

    if not antwort.figuren:
        return fundus_text, 0, False

    figuren = [
        fu.FigurEintrag(
            name=e.name, alter=e.alter, stand=e.stand, eigenschaften=e.eigenschaften,
            aussehen=e.aussehen, ziel=e.ziel, angst=e.angst, geheimnis=e.geheimnis,
        )
        for e in antwort.figuren if fu.ist_plausibler_figurenname(e.name)
    ]
    if not figuren:
        return fundus_text, 0, False
    fundus_text = fu.figuren_zusammenfuehren(fundus_text, epoche, titel, figuren)
    return fundus_text, len(figuren), False


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
            fundus_text, anzahl, ueberspringen = await _projekt_figuren_importieren(
                base_url, settings, persona, fundus_text, projekt_ordner,
            )
            if ueberspringen:
                uebersprungen.append(projekt_ordner.name)
            else:
                importierte_projekte += 1
                gefundene_figuren += anzahl

    pd.schreib(fundus_datei(settings, benutzer.username), fundus_text, force=True)
    return FundusImportAntwort(
        importierte_projekte=importierte_projekte,
        gefundene_figuren=gefundene_figuren,
        uebersprungen=uebersprungen,
    )


@router.post("/projekt/{ordner:path}", response_model=FundusProjektAntwort)
async def fundus_projekt_aktualisieren(ordner: str, ssh_ziel_id: str | None = Query(None),
                                        settings: Settings = Depends(get_settings),
                                        benutzer: Benutzer = Depends(get_current_user)):
    """Aktualisiert den Personen-Fundus NUR mit den Figuren EINES Projekts -
    fuer den Haken 'Personen-Fundus aktualisieren' im 'Projekt bereinigen'-
    Dialog beim Abschliessen der Pruefung (siehe PruefenAnwendenPage.tsx).
    Bewusst ein eigener, einzelner Ollama-Aufruf statt des kompletten
    Bibliotheks-Imports oben (fundus_importieren) - der wuerde sequentiell
    JEDES Projekt des Nutzers erneut abklappern, obwohl hier nur eines neu
    dazugekommen ist."""
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    persona = pd.lies(settings.shared_personas_dir / "fundus_pfleger.txt")
    fundus_text = pd.lies(fundus_datei(settings, benutzer.username), pflicht=False, ersatz=fu.leere_vorlage())

    with ollama_basis_url(settings, ssh_ziel_id) as base_url:
        fundus_text, gefundene_figuren, uebersprungen = await _projekt_figuren_importieren(
            base_url, settings, persona, fundus_text, projekt_root,
        )

    if gefundene_figuren > 0:
        pd.schreib(fundus_datei(settings, benutzer.username), fundus_text, force=True)
    return FundusProjektAntwort(gefundene_figuren=gefundene_figuren, uebersprungen=uebersprungen)
