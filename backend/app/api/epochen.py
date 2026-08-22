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
from app.core.geruest import ordner_lesbarer_name, ordnername_aus_titel
from app.schemas import (
    EpocheDateiSchreibenAnfrage,
    EpocheErstellenAnfrage,
    EpocheErstellenAntwort,
    EpocheFarbeAnfrage,
    EpocheGenreAnfrage,
    EpocheNameAnfrage,
    EpocheUmbenennenAntwort,
)
from app.services import projekte_wurzel_unskopiert

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
    # ".name"-Marker von Anfang an setzen (siehe epoche_umbenennen() unten) -
    # damit steht der frei getippte Name (Leerzeichen, Umlaute, Grossschreibung)
    # von vornherein unveraendert zur Verfuegung, statt erst beim ersten
    # Umbenennen aus dem ASCII-Ordnernamen zurueckgeraten werden zu muessen.
    (ziel / ".name").write_text(anfrage.name.strip(), encoding="utf-8")

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


def _projekt_ordner_alle(wurzel: Path) -> list[Path]:
    """Alle tatsaechlichen Projektordner unter `wurzel`, inklusive der
    (bei aktiver "Unterordner je Epoche"-Einstellung moeglichen) einen
    Verschachtelungsebene - dieselbe Struktur wie
    app/api/projects.py:projekte_auflisten(), hier separat gehalten, weil
    _epoche_referenzen_aktualisieren() unten ALLE Benutzer durchsucht,
    nicht nur den gerade angemeldeten."""
    if not wurzel.is_dir():
        return []
    ergebnis = []
    for eintrag in sorted(wurzel.iterdir()):
        if not eintrag.is_dir():
            continue
        if (eintrag / "projekt").is_dir():
            ergebnis.append(eintrag)
            continue
        for unter_eintrag in sorted(eintrag.iterdir()):
            if unter_eintrag.is_dir() and (unter_eintrag / "projekt").is_dir():
                ergebnis.append(unter_eintrag)
    return ergebnis


def _epoche_referenzen_aktualisieren(settings: Settings, alt: str, neu: str) -> int:
    """Nach einem physischen Ordner-Umzug (siehe epoche_umbenennen() unten)
    tragen bestehende Projekte ALLER Benutzer den alten Ordnernamen noch in
    ihrem ".epoche"/".epoche_zweite"-Marker (siehe
    app/core/projekt_dateien.py:epoche_von_projekt) - ohne dieses Nachziehen
    wuerden sie in der Ordner-Ansicht der Projektuebersicht unter einem
    verwaisten, nicht mehr existierenden Epoche-Namen haengen bleiben.
    Zusaetzlich wird ein evtl. vorhandener "Unterordner je Epoche"-
    Gruppierungsordner (siehe app/services.py:neuer_projekt_pfad) je
    Benutzer mit umbenannt, falls das Ziel noch frei ist.

    Iteriert bewusst direkt ueber die Unterordner von
    projekte_wurzel_unskopiert() statt ueber db.benutzer_alle_auflisten() -
    bei deaktivierter Anmeldung (Settings.auth_aktiv=False, Standard fuer
    den Einzelbenutzer-Betrieb) existiert fuer den synthetischen
    default_username naemlich GAR KEINE Benutzer-Zeile in der DB (siehe
    app/auth.py:get_current_user), die Benutzertabelle waere dann leer und
    dessen Projekte wuerden faelschlich uebersprungen."""
    aktualisiert = 0
    projekte_root = projekte_wurzel_unskopiert(settings)
    for wurzel in sorted(p for p in projekte_root.iterdir() if p.is_dir()):
        for projekt_pfad in _projekt_ordner_alle(wurzel):
            geaendert = False
            for marker_name in (".epoche", ".epoche_zweite"):
                marker = projekt_pfad / marker_name
                if marker.exists() and marker.read_text(encoding="utf-8").strip() == alt:
                    marker.write_text(neu, encoding="utf-8")
                    geaendert = True
            if geaendert:
                aktualisiert += 1
        alter_gruppenordner = wurzel / alt
        neuer_gruppenordner = wurzel / neu
        if alter_gruppenordner.is_dir() and not neuer_gruppenordner.exists():
            alter_gruppenordner.rename(neuer_gruppenordner)
    return aktualisiert


@router.put("/{ordner}/name", response_model=EpocheUmbenennenAntwort)
def epoche_umbenennen(ordner: str, anfrage: EpocheNameAnfrage, settings: Settings = Depends(get_settings)):
    """Aendert den Anzeigenamen einer Epoche - schreibt IMMER den
    ".name"-Marker (siehe app/api/projects.py:_epoche_anzeigename_lesen).
    Zusaetzlich wird versucht, auch den tatsaechlichen Ordnernamen der
    zentralen Bibliothek an den neuen Namen anzugleichen (echte Leerzeichen
    statt Bindestriche sind auf Windows/NTFS wie auf Linux/ext4
    unproblematisch, siehe app/core/geruest.py:ordner_lesbarer_name) - dafuer
    muss dann ALLEN bereits bestehenden Projekten aller Benutzer der
    ".epoche"/".epoche_zweite"-Marker nachgezogen werden, da dort bisher der
    Ordnername (nicht der Anzeigename) als Identifikator gespeichert ist."""
    alter_pfad = _epoche_pfad(settings, ordner)
    neuer_name = anfrage.name.strip()
    if not neuer_name:
        raise HTTPException(422, "Name darf nicht leer sein.")

    (alter_pfad / ".name").write_text(neuer_name, encoding="utf-8")

    aktueller_ordner = ordner
    aktualisierte_projekte = 0
    neuer_ordner_name = ordner_lesbarer_name(neuer_name)
    if neuer_ordner_name != ordner:
        neuer_pfad = settings.epochen_dir / neuer_ordner_name
        if neuer_pfad.exists():
            raise HTTPException(409, f"Epoche '{neuer_ordner_name}' existiert bereits.")
        alter_pfad.rename(neuer_pfad)
        aktualisierte_projekte = _epoche_referenzen_aktualisieren(settings, ordner, neuer_ordner_name)
        aktueller_ordner = neuer_ordner_name

    return EpocheUmbenennenAntwort(
        ordner=aktueller_ordner, anzeigename=neuer_name, aktualisierte_projekte=aktualisierte_projekte,
    )


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


@router.put("/{ordner}/farbe")
def epoche_farbe_schreiben(ordner: str, anfrage: EpocheFarbeAnfrage, settings: Settings = Depends(get_settings)):
    """Setzt/loescht die Hex-Farbmarkierung dieser Epoche (".farbe"-Datei,
    gleiches Muster wie ".genre" oben) - dient nur der farbigen
    Unterscheidung in der Projektliste (siehe app/api/projects.py:
    _epoche_farbe_lesen), hat keinen Einfluss auf Prompt/Generierung."""
    pfad = _epoche_pfad(settings, ordner)
    farbe = anfrage.farbe.strip()
    marker = pfad / ".farbe"
    if farbe:
        marker.write_text(farbe, encoding="utf-8")
    else:
        marker.unlink(missing_ok=True)
    return {"farbe": farbe or None}
