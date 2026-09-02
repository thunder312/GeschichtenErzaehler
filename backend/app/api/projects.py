"""Projektverwaltung: Epochen auflisten, Projekte anlegen/auflisten/lesen,
Gerüst und Verbotsliste bearbeiten, einzelne Kapitel-/Stand-/Befunde-Dateien
lesen. Reine Dateizugriffe nach dem Ordnervertrag aus
doc/Schnittstellen-Uebersicht.md Abschnitt 1 - kein Ollama-Aufruf hier
(siehe app/api/pipeline.py fuer die eigentlichen Schreib-/Pruef-Schritte)."""
from __future__ import annotations

import hashlib
import shutil
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from app.auth import get_current_user
from app.config import Settings, get_settings
from app.core import architekt as arch
from app.core import automatik
from app.core import befunde_ablehnung
from app.core import geruest as g
from app.core import projekt_dateien as pd
from app.core.fundstellen import befunde_neu_verankern, finde_fundstelle
from app.schemas import (
    BefundAblehnenAnfrage,
    BefundeAntwort,
    BefundUebernehmenAnfrage,
    Benutzer,
    EpocheKurz,
    GeruestSchreibenAnfrage,
    ProjektAnlegenAnfrage,
    ProjektBereinigenAntwort,
    ProjektDetail,
    ProjektEpocheAnfrage,
    ProjektKurz,
)
from app.services import (
    neuer_projekt_pfad,
    ordner_nach_umbenennung,
    projekt_epoche_verschieben,
    projekt_pfad,
    projekte_wurzel,
)

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


def _zeitstempel(sekunden: float) -> str:
    return datetime.fromtimestamp(sekunden).strftime("%Y-%m-%d %H:%M")


def _erstellt_am(pfad) -> str | None:
    # st_ctime ist unter Windows (NTFS) die tatsaechliche Erstellungszeit und
    # bleibt beim spaeteren Umbenennen des Projektordners (siehe
    # projektordner_umbenennen(), nach Abschluss des Architekten-Interviews)
    # unveraendert - auf Linux waere st_ctime stattdessen die Zeit der
    # letzten Metadatenaenderung und wuerde durch das Umbenennen verfaelscht.
    if not pfad.exists():
        return None
    return _zeitstempel(pfad.stat().st_ctime)


def _zuletzt_bearbeitet_am(geruest_pfad, projekt_ordner) -> str | None:
    if geruest_pfad.exists():
        return _zeitstempel(geruest_pfad.stat().st_mtime)
    if projekt_ordner.exists():
        return _zeitstempel(projekt_ordner.stat().st_mtime)
    return None


def _epoche_genre_lesen(epoche_ordner) -> str | None:
    marker = epoche_ordner / ".genre"
    if not marker.exists():
        return None
    return marker.read_text(encoding="utf-8").strip() or None


def _epoche_farbe_lesen(epoche_ordner) -> str | None:
    marker = epoche_ordner / ".farbe"
    if not marker.exists():
        return None
    return marker.read_text(encoding="utf-8").strip() or None


def _epoche_anzeigename_lesen(epoche_ordner) -> str:
    # ".name"-Marker (siehe app/api/epochen.py:epoche_umbenennen) haelt den
    # frei editierbaren Anzeigenamen GETRENNT vom Ordnernamen - dieser bleibt
    # der stabile Identifikator (Projekt-".epoche"-Marker, Filter,
    # Farbzuordnung) und aendert sich beim Umbenennen nicht zwangslaeufig.
    # Ohne Marker (Epochen aus der Zeit vor diesem Feature) ersatzweise die
    # Bindestriche im Ordnernamen wieder in Leerzeichen zurueckwandeln.
    marker = epoche_ordner / ".name"
    if marker.exists():
        text = marker.read_text(encoding="utf-8").strip()
        if text:
            return text
    return epoche_ordner.name.replace("-", " ")


@router.get("/epochen", response_model=list[EpocheKurz])
def epochen_auflisten(settings: Settings = Depends(get_settings)):
    if not settings.epochen_dir.is_dir():
        return []
    return [
        EpocheKurz(
            name=p.name,
            anzeigename=_epoche_anzeigename_lesen(p),
            genre=_epoche_genre_lesen(p),
            farbe=_epoche_farbe_lesen(p),
        )
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
    geruest_pfad = pd.geruest_datei(projekt_unterordner)
    geruest_text = pd.lies(geruest_pfad, pflicht=False, ersatz="")
    titel = g.titel_erkennen(geruest_text) if geruest_text else None
    return ProjektKurz(
        ordner=pfad.relative_to(wurzel).as_posix(),
        titel=titel,
        epoche=pd.epoche_von_projekt(pfad),
        zweite_epoche=pd.zweite_epoche_von_projekt(pfad),
        anzahl_kapitel=len(pd.vorhandene_kapitel(projekt_unterordner)),
        letztes_geplantes_kapitel=g.letztes_geplantes_kapitel(geruest_text) if geruest_text else None,
        automatik_zustand=automatik.zustand_zusammenfassen(automatik.status_lesen(pfad)),
        neu_geschrieben_aus=pd.neuschreiben_quelle(pfad),
        erstellt_am=_erstellt_am(pfad),
        zuletzt_bearbeitet_am=_zuletzt_bearbeitet_am(geruest_pfad, projekt_unterordner),
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
    zweite_epoche_ordner = None
    zweite_epoche_name = anfrage.zweite_epoche.strip() if anfrage.zweite_epoche else None
    if zweite_epoche_name:
        if zweite_epoche_name == anfrage.epoche:
            raise HTTPException(422, "Zweite Epoche muss sich von der ersten unterscheiden.")
        zweite_epoche_ordner = settings.epochen_dir / zweite_epoche_name
        if not zweite_epoche_ordner.is_dir():
            raise HTTPException(404, f"Zweite Epoche '{zweite_epoche_name}' nicht gefunden.")
    # Ohne Titel (ergibt sich oft erst aus dem Architekten-Interview) einen
    # Platzhalter-Ordner "neu" anlegen - projektordner_umbenennen() benennt
    # ihn automatisch um, sobald das Interview einen Titel liefert.
    basis_titel = anfrage.titel.strip() or "neu"
    ziel = neuer_projekt_pfad(settings, benutzer.username, basis_titel, anfrage.epoche)
    pd.projekt_anlegen(ziel, epoche_ordner, settings.shared_personas_dir, anfrage.epoche,
                        zweite_epoche_ordner, zweite_epoche_name)
    return _projekt_kurz(ziel, projekte_wurzel(settings, benutzer.username), settings)


@router.put("/{ordner:path}/epoche", response_model=ProjektKurz)
def projekt_epoche_aendern(ordner: str, anfrage: ProjektEpocheAnfrage, settings: Settings = Depends(get_settings),
                            benutzer: Benutzer = Depends(get_current_user)):
    """Ordnet ein bestehendes Projekt einer anderen Epoche zu (Drag&Drop
    zwischen den Epoche-Ordnern in der Projektuebersicht). Verschiebt bei
    aktiver "Unterordner je Epoche"-Einstellung auch den physischen
    Projektordner (siehe app/services.py:projekt_epoche_verschieben) - die
    personas/ und verbotsliste.md des Projekts bleiben dabei bewusst
    unveraendert (siehe pd.epoche_setzen), das Projekt wird also NICHT
    rueckwirkend mit den Persona-/Verbotslisten-Texten der neuen Epoche
    ueberschrieben."""
    pfad = projekt_pfad(settings, benutzer.username, ordner)
    if automatik.status_lesen(pfad)["laeuft"]:
        raise HTTPException(409, "Automatikmodus läuft für dieses Projekt gerade - bitte zuerst stoppen.")
    neue_epoche_ordner = settings.epochen_dir / anfrage.epoche
    if not neue_epoche_ordner.is_dir():
        raise HTTPException(404, f"Epoche '{anfrage.epoche}' nicht gefunden.")
    neuer_pfad = projekt_epoche_verschieben(settings, benutzer.username, pfad, anfrage.epoche)
    pd.epoche_setzen(neuer_pfad, anfrage.epoche)
    return _projekt_kurz(neuer_pfad, projekte_wurzel(settings, benutzer.username), settings)


@router.delete("/{ordner:path}", status_code=204)
def projekt_loeschen(ordner: str, settings: Settings = Depends(get_settings),
                      benutzer: Benutzer = Depends(get_current_user)):
    """Loescht den KOMPLETTEN Projektordner (personas/, projekt/, alles) -
    unumkehrbar, es gibt keine .bak-Sicherung wie bei einzelnen Dateien.
    Blockiert, waehrend fuer dieses Projekt gerade ein Automatikmodus-Lauf
    aktiv ist (siehe app/core/automatik.py) - sonst wuerde der Hintergrund-
    Task versuchen, in einen gerade geloeschten Ordner zu schreiben, und
    status_schreiben() wuerde ihn per mkdir(parents=True) teilweise
    wiederauferstehen lassen."""
    pfad = projekt_pfad(settings, benutzer.username, ordner)
    if automatik.status_lesen(pfad)["laeuft"]:
        raise HTTPException(409, "Automatikmodus läuft für dieses Projekt gerade - bitte zuerst stoppen.")
    shutil.rmtree(pfad)


@router.post("/{ordner:path}/neu-schreiben", response_model=ProjektKurz, status_code=201)
def projekt_neu_schreiben(ordner: str, settings: Settings = Depends(get_settings),
                           benutzer: Benutzer = Depends(get_current_user)):
    """Dupliziert ein bestehendes Projekt (Ordnername + '_v2', siehe
    app/core/projekt_dateien.py:projekt_fuer_neuschreiben_duplizieren) auf
    Basis nur der noetigen Ausgangsdaten (personas/, verbotsliste.md,
    geruest.md, stand_00.md) - Zustand direkt nach Abschluss des
    Architekten-Interviews, BEVOR irgendein Kapitel geschrieben wurde. Der
    Automatikmodus wird NICHT automatisch gestartet - das macht der Nutzer
    bewusst selbst ueber den bestehenden POST .../automatik/start-Endpoint
    (app/api/pipeline.py), falls und wann er will. Hier ist bewusst nur die
    Dateikopie noetig, kein Ollama-Aufruf."""
    pfad = projekt_pfad(settings, benutzer.username, ordner)
    if automatik.status_lesen(pfad)["laeuft"]:
        raise HTTPException(409, "Automatikmodus läuft für dieses Projekt gerade - bitte zuerst stoppen.")
    ziel = pd.projekt_fuer_neuschreiben_duplizieren(pfad, ordner)
    return _projekt_kurz(ziel, projekte_wurzel(settings, benutzer.username), settings)


@router.post("/{ordner:path}/bereinigen", response_model=ProjektBereinigenAntwort)
def projekt_bereinigen(ordner: str, settings: Settings = Depends(get_settings),
                        benutzer: Benutzer = Depends(get_current_user)):
    """Raeumt ein fertig geprueftes Projekt auf (Dialog 'Projekt bereinigen'
    beim Abschliessen der Pruefung, siehe frontend/src/pages/
    PruefenAnwendenPage.tsx und app/core/projekt_dateien.py:
    projekt_bereinigen). Reine Dateizugriffe, kein Ollama-Aufruf - anders
    als die Personen-Fundus-Aktualisierung, die dasselbe Dialog-Fenster
    unabhaengig davon anbietet (siehe app/api/fundus.py)."""
    pfad = projekt_pfad(settings, benutzer.username, ordner)
    if automatik.status_lesen(pfad)["laeuft"]:
        raise HTTPException(409, "Automatikmodus läuft für dieses Projekt gerade - bitte zuerst stoppen.")
    return pd.projekt_bereinigen(pfad)


@fallback_router.get("/{ordner:path}", response_model=ProjektDetail)
def projekt_lesen(ordner: str, settings: Settings = Depends(get_settings),
                   benutzer: Benutzer = Depends(get_current_user)):
    pfad = projekt_pfad(settings, benutzer.username, ordner)
    projekt_unterordner = pfad / "projekt"
    geruest_text = pd.lies(pd.geruest_datei(projekt_unterordner), pflicht=False, ersatz="")
    verbotsliste_text = pd.lies(pd.verbotsliste_datei(projekt_unterordner), pflicht=False, ersatz="")
    stilproben_text = pd.lies(pd.stilproben_datei(projekt_unterordner), pflicht=False, ersatz="")
    kapitel = [pd.kapitelnummer_aus_dateiname(p) for p in pd.vorhandene_kapitel(projekt_unterordner)]
    return ProjektDetail(
        ordner=ordner,
        epoche=pd.epoche_von_projekt(pfad),
        zweite_epoche=pd.zweite_epoche_von_projekt(pfad),
        geruest=geruest_text or None,
        verbotsliste=verbotsliste_text or None,
        stilproben=stilproben_text or None,
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
    # Verhindert, dass ein Kapitelplan mit fehlender Zielwortzahl oder
    # doppelt deklarierter Kapitelnummer klaglos gespeichert wird - beides
    # macht kapitelplan_erkennen() das betroffene Kapitel unsichtbar, der
    # Fehler faellt sonst erst Tage spaeter beim Automatik-Schreiben auf
    # (Vorfall a-Blut-und-Ahornlaub-Die-Ehre-des-Verbotenen). Bewusst VOR
    # dem Schreiben geprueft, damit eine bereits gespeicherte gueltige
    # Fassung bei einem fehlerhaften Speicherversuch unangetastet bleibt.
    kapitelplan_fehler = g.kapitelplan_pruefen(anfrage.inhalt)
    if kapitelplan_fehler:
        raise HTTPException(400, "Kapitelplan unvollständig:\n" + "\n".join(kapitelplan_fehler))

    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    ziel_pfad, gesichert_als = pd.schreib(pd.geruest_datei(projekt_root / "projekt"), anfrage.inhalt)

    # stand_00.md ist NUR eine Momentaufnahme von "## Ausgangslage vor
    # Kapitel eins", angefertigt beim Abschluss des Architekten-Interviews
    # (siehe app/api/architekt.py) oder beim Duplizieren per "Neu schreiben"
    # (siehe projekt_fuer_neuschreiben_duplizieren) - Kapitel eins bekommt
    # sie 1:1 als Kontext vorgesetzt (app/api/pipeline.py:
    # _kapitel_schreiben_kern). Wird die Ausgangslage HIER manuell
    # nachbearbeitet (z.B. nach "Neu schreiben", um Jahreszeit/Gegenstaende
    # zu aendern), muss stand_00.md synchron nachgezogen werden - sonst
    # bekommt der Autor zwei widerspruechliche Quellen (aktuelles Geruest
    # UND die alte Momentaufnahme) und greift im Zweifel zur alten
    # (Vorfall: a-Blut-und-Ahornlaub-Die-Ehre-des-Verbotenen, Jahreszeit
    # blieb trotz Aenderung auf "Herbst", weil nur das Geruest, nicht aber
    # stand_00.md aktualisiert wurde). Bleibt der Abschnitt unveraendert
    # oder fehlt er (kein Kapitel-eins-Bezug im Gerueest), bleibt ein
    # bestehendes stand_00.md unangetastet statt geloescht zu werden.
    ausgangslage = arch.ausgangslage_erkennen(anfrage.inhalt)
    stand_00_aktualisiert = False
    if ausgangslage:
        pd.schreib(
            pd.stand_datei(projekt_root / "projekt", 0),
            "# STAND VOR KAPITEL EINS\n\n" + ausgangslage,
            force=True,
        )
        stand_00_aktualisiert = True

    # Der Ordner traegt nach der Projektanlage oft noch den Platzhalter-
    # Namen "neu" (siehe projekt_anlegen()) - das Architekten-Interview
    # benennt ihn zwar am Ende automatisch um, aber nicht, wenn der Titel
    # erst nachtraeglich hier im Gerueest-Editor gesetzt/geaendert wird.
    # Ohne diesen Aufruf bliebe der Ordner dann dauerhaft "neu".
    neuer_name = pd.projektordner_umbenennen(projekt_root, anfrage.inhalt)
    neuer_ordner = ordner_nach_umbenennung(ordner, neuer_name) if neuer_name else None
    return {
        "gespeichert": str(ziel_pfad),
        "gesichert_als": gesichert_als,
        "neuer_ordner": neuer_ordner,
        "stand_00_aktualisiert": stand_00_aktualisiert,
    }


@router.put("/{ordner:path}/verbotsliste")
def verbotsliste_schreiben(ordner: str, anfrage: GeruestSchreibenAnfrage,
                            settings: Settings = Depends(get_settings),
                            benutzer: Benutzer = Depends(get_current_user)):
    pfad = projekt_pfad(settings, benutzer.username, ordner) / "projekt"
    ziel_pfad, gesichert_als = pd.schreib(pd.verbotsliste_datei(pfad), anfrage.inhalt)
    return {"gespeichert": str(ziel_pfad), "gesichert_als": gesichert_als}


@router.put("/{ordner:path}/stilproben")
def stilproben_schreiben(ordner: str, anfrage: GeruestSchreibenAnfrage,
                          settings: Settings = Depends(get_settings),
                          benutzer: Benutzer = Depends(get_current_user)):
    pfad = projekt_pfad(settings, benutzer.username, ordner) / "projekt"
    ziel_pfad, gesichert_als = pd.schreib(pd.stilproben_datei(pfad), anfrage.inhalt)
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


@router.post("/{ordner:path}/befunde/{n}/ablehnen")
def befund_ablehnen(ordner: str, n: int, anfrage: BefundAblehnenAnfrage,
                     settings: Settings = Depends(get_settings),
                     benutzer: Benutzer = Depends(get_current_user)):
    """Button "Ablehnen" im Tab "Pruefen & Anwenden" (parallel zu
    "Uebernehmen") - entfernt den Fund SOFORT aus dem gespeicherten
    befunde_{n}.json (damit er nicht durch einen simplen Reload wieder
    auftaucht) UND merkt sich (Kategorie, Fundstelle) dauerhaft projektweit
    vor (app/core/befunde_ablehnung.py), damit er bei einer kuenftigen
    erneuten Pruefung dieses oder eines anderen Kapitels nicht wieder
    gemeldet wird - z.B. fuer eine in einer FanFic-Epoche bewusst
    gewuenschte Kanon-Abweichung, die der Nutzer ein fuer alle Mal nicht
    mehr sehen will."""
    pfad = projekt_pfad(settings, benutzer.username, ordner) / "projekt"
    datei = pd.befunde_datei(pfad, n)
    if not datei.exists():
        raise HTTPException(404, f"Befunde zu Kapitel {n} nicht gefunden.")
    antwort = BefundeAntwort.model_validate_json(pd.lies(datei))
    ziel = next((b for b in antwort.befunde if b.id == anfrage.befund_id), None)
    if ziel is None:
        raise HTTPException(404, f"Fund {anfrage.befund_id} nicht gefunden.")

    befunde_ablehnung.hinzufuegen(pfad, ziel.kategorien, ziel.fundstelle)

    antwort.befunde = [b for b in antwort.befunde if b.id != anfrage.befund_id]
    datei.write_text(antwort.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return {"abgelehnt": True}


@router.post("/{ordner:path}/befunde/{n}/uebernehmen", response_model=BefundeAntwort)
def befund_uebernehmen(ordner: str, n: int, anfrage: BefundUebernehmenAnfrage,
                        settings: Settings = Depends(get_settings),
                        benutzer: Benutzer = Depends(get_current_user)):
    """Uebernimmt EINEN Fund serverseitig (Text-Splice in kapitel_NN.md +
    Speichern), OHNE dass dafuer ein Monaco-Editor im Browser laufen muss -
    fuer die Mobil-Ansicht (MobilPage.tsx), wo bei schmaler Aufloesung statt
    des Volltext-Editors nur eine einfache Funde-Liste mit "Übernehmen"-
    Buttons angezeigt wird. Der Desktop-Pfad (Tab "Prüfen & Anwenden") nutzt
    das bewusst NICHT weiter - dort bleibt der bestehende Monaco-Editor
    (befundReview.ts) die Quelle der Wahrheit, u.a. weil er live mitverschobene
    Decorations und Undo unterstuetzt.

    `vorschlag_override` erlaubt eine leichte Abaenderung des Vorschlags vor
    dem Uebernehmen (Button "kleine Verbesserung"). Position wird IMMER frisch
    per finde_fundstelle() gegen den aktuellen Kapiteltext verankert statt dem
    gespeicherten start/end blind zu vertrauen - die Datei kann sich seit der
    letzten Pruefung veraendert haben (siehe befunde_lesen()/`veraltet`-Flag).
    Verankert anschliessend alle UEBRIGEN offenen Funde neu (siehe
    app/core/fundstellen.py:befunde_neu_verankern) und schreibt eine
    aktualisierte befunde_NN.json - derselbe Mechanismus wie nach dem
    automatischen Anwenden im Automatikmodus (app/api/pipeline.py:
    _kapitel_befunde_neu_verankern)."""
    pfad = projekt_pfad(settings, benutzer.username, ordner) / "projekt"
    befunde_pfad = pd.befunde_datei(pfad, n)
    if not befunde_pfad.exists():
        raise HTTPException(404, f"Befunde zu Kapitel {n} nicht gefunden.")
    antwort = BefundeAntwort.model_validate_json(pd.lies(befunde_pfad))
    ziel = next((b for b in antwort.befunde if b.id == anfrage.befund_id), None)
    if ziel is None:
        raise HTTPException(404, f"Fund {anfrage.befund_id} nicht gefunden.")

    kapitel_pfad = pd.kapitel_datei(pfad, n)
    if not kapitel_pfad.exists():
        raise HTTPException(404, f"Kapitel {n} nicht gefunden.")
    kapiteltext = pd.lies(kapitel_pfad)

    vorschlag = (anfrage.vorschlag_override or ziel.vorschlag or "").strip()
    if not vorschlag:
        raise HTTPException(400, "Kein Vorschlag zum Übernehmen vorhanden.")

    stelle = finde_fundstelle(kapiteltext, ziel.fundstelle)
    if stelle is None:
        raise HTTPException(409, "Textstelle nicht mehr im Kapitel auffindbar - bitte erneut prüfen.")
    start, end = stelle

    neuer_text = kapiteltext[:start] + vorschlag + kapiteltext[end:]
    pd.schreib(kapitel_pfad, neuer_text)

    offene_befunde = befunde_neu_verankern(
        neuer_text, [b for b in antwort.befunde if b.id != anfrage.befund_id],
    )
    aktualisiert = antwort.model_copy(update={
        "erzeugt_am": time.strftime("%Y-%m-%d %H:%M"),
        "befunde": offene_befunde,
        "quelltext_sha256": hashlib.sha256(neuer_text.encode("utf-8")).hexdigest(),
        "veraltet": False,
    })
    pd.schreib(befunde_pfad, aktualisiert.model_dump_json(indent=2))
    return aktualisiert


@router.get("/{ordner:path}/gesamt", response_class=PlainTextResponse)
def gesamt_lesen(ordner: str, settings: Settings = Depends(get_settings),
                  benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    pfad = projekt_root / f"{projekt_root.name}.md"
    if not pfad.exists():
        raise HTTPException(404, "Noch nicht exportiert.")
    return pd.lies(pfad)
