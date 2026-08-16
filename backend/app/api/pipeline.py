"""Die eigentlichen Pipeline-Schritte: Schreiben (WebSocket, streamend),
Pruefen (Anachronismus/Stimmigkeit, Kontinuitaet, Lektorat UND der
dedizierte Satzbau-Pruefer laufen parallel und liefern eine gemeinsame
Fund-Liste, siehe _pruefe_kapitel), Stand, Export/Zusammenfassen,
Rechtschreibpruefung.

Portiert aus pre-GUI/novelle.py (cmd_schreiben, _pruefe, cmd_anwenden,
cmd_lektorieren, cmd_stand, cmd_export, cmd_zusammenfassen,
cmd_rechtschreibung) - Prompt-Aufbau und Reihenfolge der Nachbearbeitungs-
Schritte sind bewusst wortgleich zum Original, damit dieselbe Geschichte in
CLI und GUI gleich behandelt wird (siehe doc/Schnittstellen-Uebersicht.md).

Automatische Fortsetzung bei zu kurzen Kapiteln (Abschnitt 5.5, siehe
_bei_bedarf_fortsetzen) ist implementiert, siehe Bedienungsanleitung
Abschnitt 9b.
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import logging
import re
import time
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile,
    WebSocket, WebSocketDisconnect,
)
from pydantic import ValidationError

from app.auth import get_current_user, get_current_user_ws
from app.config import Settings, get_settings
from app.core import automatik
from app.core import bild_generierung
from app.core import geruest as g
from app.core import heuristik as h
from app.core import projekt_dateien as pd
from app.core import ssh_manager
from app.core.befunde_merge import RoherBefund, befunde_zusammenfuehren, vorschlag_verdaechtig
from app.core.bild_generierung import BildGenerierungFehler
from app.core.fundstellen import finde_fundstelle
from app.core.ollama_client import OllamaFehler, chat_stream
from app.core.ollama_client import sammle_antwort as _sammle_antwort
from app.core.pdf_export import buch_pdf_erzeugen
from app.core.pruef_schema import AnachronismusAntwortLLM, KontinuitaetAntwortLLM, LektorAntwortLLM
from app.core.rollen import ROLLEN, STUFE_DIREKTIVEN
from app.core.textutil import woerter
from app.schemas import (
    AutomatikStartAnfrage,
    AutomatikStatusAntwort,
    AutomatikVerlaufEintrag,
    Befund,
    BefundeAntwort,
    Benutzer,
    CoverGenerierenAnfrage,
    CoverPromptAntwort,
    RechtschreibAntwort,
    RechtschreibWort,
    StoryFrageAnfrage,
    StoryFrageAntwort,
)
from app.services import bild_basis_url, ollama_basis_url, projekt_pfad, rollen_modell_override, ssh_ziel_aus_db

OnEvent = Callable[[dict], Awaitable[None]]

router = APIRouter(prefix="/api/projects", tags=["pipeline"])
logger = logging.getLogger(__name__)

# Unter dieser Schwelle (Anteil der Zielwortzahl) wird bei eingeschalteter
# automatischer Fortsetzung weitergeschrieben, bzw. ohne Fortsetzung nur
# gewarnt (siehe Bedienungsanleitung Abschnitt 9b).
FORTSETZEN_SCHWELLE = 0.70
FORTSETZEN_MAX_VERSUCHE = 3

# Konservativere Sampling-Parameter NUR fuer die Fortsetzungsversuche
# (siehe _bei_bedarf_fortsetzen), ueberschreiben die Autor-Rollen-Werte aus
# rollen.py fuer genau diesen Aufruf (chat_stream()'s `ueberschreibe`-Param).
# Grund: Die Architekten-Persona selbst warnt bei dieser Option ausdruecklich
# ("Frage 4b" in app/core/epoche.py), dass automatische Fortsetzung haeufig
# zu sinnfreien/widerspruechlichen Texten fuehrt, weil das Modell "auf
# Krampf" auf die Zielwortzahl hinschreibt statt die Szene organisch zu
# Ende zu erzaehlen. Niedrigere temperature/top_p und ein enger top_k halten
# das Modell naeher an der wahrscheinlichsten Fortsetzung statt an einer
# freien, abschweifenden Erfindung; der leicht hoehere repeat_penalty wirkt
# zusaetzlich den formelhaften Wiederholungsschleifen entgegen, die gerade
# bei mehreren Fortsetzungsversuchen hintereinander beobachtet wurden (siehe
# heuristik.py:interne_wiederholung_abschneiden als bestehendes Sicherheits-
# netz dagegen).
FORTSETZEN_OPTIONEN_UEBERSCHREIBE = {
    "temperature": 0.45,
    "top_p": 0.85,
    "top_k": 40,
    "repeat_penalty": 1.15,
}


async def _sammle_stream(
    settings: Settings, base_url: str, rolle: str, system: str, user: str,
    format: dict | str | None = None,
) -> tuple[str, dict]:
    """Duenner Wrapper um app.core.ollama_client.sammle_antwort() fuer die
    reinen HTTP-Endpunkte dieses Routers: uebersetzt das dort bewusst
    FastAPI-freie OllamaFehler in eine HTTPException, wie es dieser Router
    schon immer getan hat (siehe app/main.py - andere Router wie
    app/api/architekt.py fangen OllamaFehler dagegen direkt ab, da sie als
    WebSocket keine HTTP-Antwort liefern). Loest zusaetzlich den globalen
    Admin-Modell-Override fuer die Rolle auf (Tab KI-Ziele -> Persona-Modell-
    Zuordnung, siehe app/services.py:rollen_modell_override)."""
    try:
        return await _sammle_antwort(
            base_url, rolle, system, user, format=format,
            modell_override=rollen_modell_override(settings, rolle),
        )
    except OllamaFehler as e:
        raise HTTPException(502, str(e)) from e


def _ohne_eigene_duplikate(eintraege: list, schluessel: tuple[str, ...]) -> list:
    """Ein einzelner Pruefer-Aufruf wiederholt gelegentlich denselben Fund
    innerhalb der EIGENEN Antwort (z.B. wortgleiche fundstelle+vorschlag
    zweimal in einer JSON-Liste) - beobachtet beim Lektor auf einem echten
    Kapitel. Filtert das VOR der Weiterverarbeitung heraus, damit nicht
    zwei identische, oft gleichermassen nicht auffindbare Eintraege im
    Frontend nebeneinander auftauchen. Vergleicht nur die uebergebenen
    Attributnamen (z.B. ("fundstelle", "vorschlag")), nicht das ganze
    Objekt."""
    gesehen: set[tuple] = set()
    ergebnis = []
    for eintrag in eintraege:
        schluesselwert = tuple(getattr(eintrag, feld) for feld in schluessel)
        if schluesselwert in gesehen:
            continue
        gesehen.add(schluesselwert)
        ergebnis.append(eintrag)
    return ergebnis


def _ist_echte_korrektur(fundstelle: str, vorschlag: str | None) -> bool:
    """False, wenn "vorschlag" (nach Normalisierung von Leerraum) wortgleich
    mit "fundstelle" ist - beobachtet beim Lektor auf einem echten Kapitel:
    ueber die Haelfte der gemeldeten Funde schlug woertlich denselben Text
    als 'Korrektur' vor, obwohl die Persona explizit anweist, nur echte
    Verstoesse zu melden. Ein Prompt-Hinweis allein reicht dagegen nicht
    zuverlaessig - dieser Check filtert deterministisch, unabhaengig davon,
    ob sich das Modell an die Anweisung haelt."""
    if vorschlag is None:
        return True
    return " ".join(vorschlag.split()) != " ".join(fundstelle.split())


def _anachronismus_roh_befunde(kapiteltext: str, antwort_text: str) -> list[RoherBefund]:
    try:
        antwort = AnachronismusAntwortLLM.model_validate_json(antwort_text)
    except ValidationError:
        return [RoherBefund(
            kategorie="anachronismus", fundstelle="", sicherheit="gering", vorschlag=None,
            beschreibung="Antwort des Anachronismus-/Stimmigkeits-Pruefers konnte nicht gelesen werden (kein gueltiges JSON).",
            start=None, end=None,
        )]
    ergebnis = []
    for eintrag in _ohne_eigene_duplikate(antwort.befunde, ("fundstelle", "vorschlag")):
        vorschlag = eintrag.vorschlag
        if vorschlag and vorschlag_verdaechtig(eintrag.fundstelle, vorschlag):
            vorschlag = None
        if not _ist_echte_korrektur(eintrag.fundstelle, vorschlag):
            continue
        bereich = finde_fundstelle(kapiteltext, eintrag.fundstelle)
        ergebnis.append(RoherBefund(
            kategorie=eintrag.kategorie,
            fundstelle=eintrag.fundstelle,
            beschreibung=eintrag.problem,
            sicherheit=eintrag.sicherheit,
            vorschlag=vorschlag,
            start=bereich[0] if bereich else None,
            end=bereich[1] if bereich else None,
        ))
    return ergebnis


def _kontinuitaet_roh_befunde(kapiteltext: str, antwort_text: str) -> list[RoherBefund]:
    try:
        antwort = KontinuitaetAntwortLLM.model_validate_json(antwort_text)
    except ValidationError:
        return [RoherBefund(
            kategorie="kontinuitaet", fundstelle="", sicherheit=None, vorschlag=None,
            beschreibung="Antwort des Kontinuitaets-Pruefers konnte nicht gelesen werden (kein gueltiges JSON).",
            start=None, end=None,
        )]
    ergebnis = []
    for eintrag in _ohne_eigene_duplikate(antwort.befunde, ("zitat", "vorschlag")):
        vorschlag = None if eintrag.unsicher else eintrag.vorschlag
        if vorschlag and vorschlag_verdaechtig(eintrag.zitat, vorschlag):
            vorschlag = None
        if not _ist_echte_korrektur(eintrag.zitat, vorschlag):
            continue
        bereich = finde_fundstelle(kapiteltext, eintrag.zitat)
        beschreibung = eintrag.widerspruch
        if eintrag.beleg:
            beschreibung += f" (Beleg: {eintrag.beleg})"
        ergebnis.append(RoherBefund(
            kategorie="kontinuitaet",
            fundstelle=eintrag.zitat,
            beschreibung=beschreibung,
            sicherheit=None,
            vorschlag=vorschlag,
            start=bereich[0] if bereich else None,
            end=bereich[1] if bereich else None,
        ))
    return ergebnis


def _lektor_roh_befunde(kapiteltext: str, antwort_text: str) -> list[RoherBefund]:
    try:
        antwort = LektorAntwortLLM.model_validate_json(antwort_text)
    except ValidationError:
        return [RoherBefund(
            kategorie="lektorat", fundstelle="", sicherheit="hoch", vorschlag=None,
            beschreibung="Antwort des Lektors konnte nicht gelesen werden (kein gueltiges JSON).",
            start=None, end=None,
        )]
    ergebnis = []
    for eintrag in _ohne_eigene_duplikate(antwort.befunde, ("fundstelle", "vorschlag")):
        vorschlag = eintrag.vorschlag
        if vorschlag and vorschlag_verdaechtig(eintrag.fundstelle, vorschlag):
            vorschlag = None
        if not _ist_echte_korrektur(eintrag.fundstelle, vorschlag):
            continue
        bereich = finde_fundstelle(kapiteltext, eintrag.fundstelle)
        ergebnis.append(RoherBefund(
            kategorie="lektorat",
            fundstelle=eintrag.fundstelle,
            beschreibung=eintrag.problem,
            # Lektor meldet laut Persona nur, was er auch sicher als echten
            # Duden-Verstoss erkennt (kein Sicherheits-Feld im Modell noetig,
            # anders als bei Anachronismus/Stimmigkeit) - daher konstant
            # "hoch", damit die Merge-Logik es wie die anderen "hoch"-Funde
            # behandelt.
            sicherheit="hoch",
            vorschlag=vorschlag,
            start=bereich[0] if bereich else None,
            end=bereich[1] if bereich else None,
        ))
    return ergebnis


def _satzbau_roh_befunde(kapiteltext: str, antwort_text: str) -> list[RoherBefund]:
    """Dediziert eigener, schmaler Pruefer NUR fuer Verb-Letzt-Stellung in
    Nebensaetzen (Rolle "satzbau", siehe rollen.py) - dieselbe Antwort-Form
    wie beim Lektor, deshalb dasselbe Pydantic-Schema (LektorAntwortLLM).
    Kategorie bewusst ebenfalls "lektorat", damit sich ein hier gefundener
    Fund nahtlos ins bestehende Lektorat-Farbschema/-Merge einreiht, statt
    eine eigene, dem Nutzer neu zu erklaerende Kategorie zu brauchen."""
    try:
        antwort = LektorAntwortLLM.model_validate_json(antwort_text)
    except ValidationError:
        return [RoherBefund(
            kategorie="lektorat", fundstelle="", sicherheit="hoch", vorschlag=None,
            beschreibung="Antwort des Satzbau-Pruefers konnte nicht gelesen werden (kein gueltiges JSON).",
            start=None, end=None,
        )]
    ergebnis = []
    for eintrag in _ohne_eigene_duplikate(antwort.befunde, ("fundstelle", "vorschlag")):
        vorschlag = eintrag.vorschlag
        if vorschlag and vorschlag_verdaechtig(eintrag.fundstelle, vorschlag):
            vorschlag = None
        if not _ist_echte_korrektur(eintrag.fundstelle, vorschlag):
            continue
        bereich = finde_fundstelle(kapiteltext, eintrag.fundstelle)
        ergebnis.append(RoherBefund(
            kategorie="lektorat",
            fundstelle=eintrag.fundstelle,
            beschreibung=eintrag.problem,
            sicherheit="hoch",
            vorschlag=vorschlag,
            start=bereich[0] if bereich else None,
            end=bereich[1] if bereich else None,
        ))
    return ergebnis


def _autor_system_prompt(projekt_root: Path) -> str:
    """Haengt an die Autor-Persona optional die vom Nutzer gepflegten
    Stilproben an (siehe app/core/projekt_dateien.py:stilproben_datei) -
    kurze Vorbild-Ausschnitte aus Geschichten, deren Sprache/Rhythmus/Ton
    gefallen haben, damit sich der Autor (Mistral, siehe rollen.py) beim
    Formulieren daran orientieren kann, ohne dass dafuer ein echtes
    Fine-Tuning noetig waere. Leeres oder fehlendes stilproben.md aendert
    nichts am Prompt."""
    persona = pd.persona_lesen(projekt_root, "autor")
    stilproben = pd.lies(pd.stilproben_datei(projekt_root / "projekt"), pflicht=False, ersatz="")
    if not stilproben.strip():
        return persona
    return (
        f"{persona}\n\n"
        f"## Stilproben (Vorbild für Sprache, NICHT für Inhalt)\n"
        f"Die folgenden Ausschnitte sind vom Nutzer ausgewählte Beispiele für "
        f"Wortwahl, Satzrhythmus und Ton, die gut funktioniert haben. "
        f"Orientiere dich beim Schreiben daran, wie hier erzählt wird. "
        f"Übernimm NICHT die konkreten Ereignisse, Namen, Figuren oder "
        f"Handlungen aus den Ausschnitten - dafür gelten ausschließlich "
        f"Geruest und Stand.\n\n{stilproben}"
    )


async def _bei_bedarf_fortsetzen(
    on_event: OnEvent, settings: Settings, base_url: str, projekt_root: Path, n: int, text: str,
    ziel: int, geruest_text: str, vorher: str, stufe: str, zusatzhinweis: str,
    autor_rolle: str,
) -> tuple[str, list[h.Finding]]:
    """Lässt den Autor nahtlos weiterschreiben, wenn ein Kapitel deutlich zu
    kurz ausfällt - portiert aus pre-GUI/novelle.py:_bei_bedarf_fortsetzen
    (siehe Bedienungsanleitung Abschnitt 9b). `on_event` liefert Fortschritt
    entweder an eine offene WebSocket (interaktives Schreiben) oder ins
    Status-Log des Automatikmodus (siehe _kapitel_schreiben_kern). Nur
    aktiv, wenn 'Automatische Fortsetzung: Ein' im Geruest steht."""
    findings: list[h.Finding] = []
    versuch = 0
    aktueller_block = g.kapitel_block_erkennen(geruest_text, n)
    aktueller_hinweis = (
        f"\n\n=== NUR DIESES KAPITEL FORTSETZEN (Kapitel {n}) ===\n{aktueller_block}\n\n"
        f"Bleibe ausschließlich in der oben für DIESES Kapitel beschriebenen "
        f"Stufe der Liebeshandlung. Erfinde KEINE neue Szene und springe zu "
        f"KEINEM anderen Beziehungsstand (z.B. Heirat, körperliche Vereinigung "
        f"oder ein gemeinsames Erwachen als Paar), auch wenn ein späteres "
        f"Kapitel im Gesamtplan das vorsieht - das gehört nicht hierher. "
        f"Führe exakt die laufende Szene fort."
        if aktueller_block else ""
    )
    zusatz_block = (
        f"\n\n=== ZUSÄTZLICHER HINWEIS FÜR DIESEN VERSUCH ===\n{zusatzhinweis}\n"
        f"Dieser Hinweis gilt nur für diesen einen Schreibversuch und hat "
        f"Vorrang, falls er einem Detail des Geruests widerspricht."
        if zusatzhinweis else ""
    )

    while woerter(text) < ziel * FORTSETZEN_SCHWELLE and versuch < FORTSETZEN_MAX_VERSUCHE:
        versuch += 1
        fehlend = ziel - woerter(text)
        # Nur das Ende als Anschlusspunkt mitgeben, nicht den ganzen Text
        # erneut - spart Kontext und verhindert, dass der Autor von vorn
        # beginnt.
        anschluss = text[-600:]

        await on_event({
            "phase": "autor_fortsetzung", "typ": "start",
            "versuch": versuch, "max_versuche": FORTSETZEN_MAX_VERSUCHE,
            "woerter": woerter(text), "ziel_woerter": ziel,
        })

        teile: list[str] = []
        async for event in chat_stream(
            base_url, autor_rolle, _autor_system_prompt(projekt_root),
            f"=== STORY-GERUEST ===\n{geruest_text}\n\n"
            f"=== STAND NACH DEM VORIGEN KAPITEL ===\n{vorher}\n\n"
            f"=== BISHERIGER TEXT DIESES KAPITELS (Ende) ===\n...{anschluss}\n\n"
            f"=== AUFTRAG ===\n"
            f"Der obige Text ist noch nicht zu Ende. Schreibe NAHTLOS weiter, "
            f"genau ab der letzten Zeile, ohne sie zu wiederholen und ohne "
            f"neu zu beginnen. Führe die Szene tatsächlich aus, statt sie "
            f"nur anzudeuten oder abzukürzen. Noch etwa {fehlend} Wörter, "
            f"bis das Kapitel gemäß Geruest inhaltlich abgeschlossen ist. "
            f"Gib ausschließlich die Fortsetzung aus, keine Wiederholung "
            f"des bisherigen Textes. Schreibe ausschließlich auf Deutsch, "
            f"auch wenn im bisherigen Text ein anderer Sprachanteil "
            f"vorkommen sollte.\n\n"
            f"{STUFE_DIREKTIVEN[stufe]}{aktueller_hinweis}{zusatz_block}",
            ueberschreibe=FORTSETZEN_OPTIONEN_UEBERSCHREIBE,
            modell_override=rollen_modell_override(settings, autor_rolle),
        ):
            if event.typ == "error":
                raise OllamaFehler(event.text)
            if event.typ in ("thinking", "content"):
                if event.typ == "content":
                    teile.append(event.text)
                await on_event({"phase": "autor_fortsetzung", "typ": event.typ, "text": event.text})
            if event.typ == "done":
                await on_event({"phase": "autor_fortsetzung", "typ": "done", "versuch": versuch})

        fortsetzung = h.meta_zeilen_entfernen("".join(teile).strip())
        fortsetzung, dup_findings = h.fuehrende_duplikate_entfernen(text, fortsetzung)
        findings += dup_findings
        text = text.rstrip() + "\n\n" + fortsetzung.strip()
        text, findings_neustart = h.kapitel_neustart_abschneiden(text)
        text, findings_ende = h.vorzeitige_kapitelende_abschneiden(text)
        text, findings_wiederholung = h.interne_wiederholung_abschneiden(text)
        text, findings_block = h.wiederholten_absatzblock_ausschneiden(text)
        findings += findings_neustart + findings_ende + findings_wiederholung + findings_block

    if woerter(text) < ziel * FORTSETZEN_SCHWELLE:
        findings.append(h.Finding(
            "zu_kurz",
            f"Auch nach {versuch} Fortsetzungsversuchen bleibt Kapitel {n} "
            f"kurz ({woerter(text)} von {ziel} Wörtern). Persona oder "
            f"Gerüststruktur prüfen, statt weiter automatisch zu versuchen.",
            schwere="info",
        ))

    return text, findings


# Zielgroesse fuer die Satzbau-Abschnitte (siehe _text_in_abschnitte_teilen)
# - per Live-Test an der Mars-Fluesterns-Geschichte ermittelt: bei einem
# kompletten Kapitel (~6700 Zeichen) uebersah gemma4 den bekannten Verb-
# Letzt-Fehler zweimal reproduzierbar, bei einem kurzen 3-Satz-Testfall
# fand es ihn zuverlaessig. Kleinere Abschnitte statt des ganzen Kapitels
# sollen die Trefferquote erhoehen, auf Kosten mehrerer statt eines
# Ollama-Aufrufs fuer diese eine Rolle.
SATZBAU_ABSCHNITT_ZEICHEN = 1500


def _text_in_abschnitte_teilen(text: str, ziel_zeichen: int = SATZBAU_ABSCHNITT_ZEICHEN) -> list[str]:
    """Teilt an Absatzgrenzen (Leerzeile) in Abschnitte von je bis zu
    ziel_zeichen Laenge - schneidet also nie mitten in einem Satz. Ein
    einzelner Absatz, der fuer sich schon laenger als ziel_zeichen ist,
    bleibt trotzdem als eigener (dann groesserer) Abschnitt erhalten, statt
    ihn zu zerreissen."""
    absaetze = [a for a in text.split("\n\n") if a.strip()]
    if not absaetze:
        return [text] if text.strip() else []

    abschnitte: list[str] = []
    aktuell: list[str] = []
    laenge = 0
    for absatz in absaetze:
        if aktuell and laenge + len(absatz) > ziel_zeichen:
            abschnitte.append("\n\n".join(aktuell))
            aktuell = []
            laenge = 0
        aktuell.append(absatz)
        laenge += len(absatz) + 2
    if aktuell:
        abschnitte.append("\n\n".join(aktuell))
    return abschnitte


async def _pruefe_kapitel(settings: Settings, projekt: Path, base_url: str, n: int, kapiteltext: str,
                           zusatzhinweis: str = "") -> BefundeAntwort:
    geruest_text = pd.lies(pd.geruest_datei(projekt))
    verbote = pd.lies(pd.verbotsliste_datei(projekt), pflicht=False, ersatz="")
    vorher = pd.lies(pd.stand_datei(projekt, n - 1), pflicht=False,
                      ersatz="(Kein vorheriger Stand vorhanden. Dies ist das erste Kapitel.)")
    jahr = g.jahr_fuer_kapitel_erkennen(geruest_text, n)
    nebenstrang = g.nebenstrang_abschnitt_erkennen(geruest_text)
    nebenstrang_block = (
        f"\n\n=== GEPLANTER NEBENSTRANG (gesamtes Geruest, nicht nur dieses "
        f"Kapitel) ===\n{nebenstrang}" if nebenstrang else ""
    )
    figuren = g.figuren_abschnitt_erkennen(geruest_text)
    figuren_block = (
        f"\n\n=== FIGUREN-REFERENZ (Namen und Titel laut Geruest) ===\n{figuren}"
        if figuren else ""
    )
    zusatzhinweis_block = (
        f"\n\n=== ZUSÄTZLICHER HINWEIS FÜR DIESEN VERSUCH ===\n{zusatzhinweis}"
        if zusatzhinweis else ""
    )
    # Aktiviert den Abschluss-Check in pruefer_kontinuitaet.txt: nur beim
    # letzten geplanten Kapitel soll der Pruefer gezielt gegen "Offene
    # Faeden" und den Nebenstrang abgleichen, statt bei jedem Kapitel ein
    # fehlendes Happy End zu vermuten.
    letztes = g.letztes_geplantes_kapitel(geruest_text)
    letztes_kapitel_block = (
        "\n\n=== DIES IST DAS LETZTE GEPLANTE KAPITEL ===\n"
        "Fuehre zusaetzlich den Abschluss-Check aus."
        if letztes and n == letztes else ""
    )

    # Anachronismus/Kontinuitaet/Lektor bekommen weiterhin je EINEN Aufruf
    # mit dem ganzen Kapitel. Satzbau bekommt dagegen mehrere Aufrufe, je
    # einen pro Textabschnitt (siehe _text_in_abschnitte_teilen) - ein
    # Live-Test zeigte, dass gemma4 bei einem kompletten, mehrere tausend
    # Zeichen langen Kapitel nicht mehr jeden Nebensatz zuverlaessig prueft,
    # bei kuerzeren Abschnitten aber doch. Alle Aufrufe (fest + pro Abschnitt)
    # laufen in einem gemeinsamen asyncio.gather, um die Wartezeit pro
    # Kapitel zu verkuerzen. "format=json" erzwingt eine strukturierte
    # Antwort, die deterministisch geparst werden kann statt
    # freiformuliertes Markdown/Fliesstext zu interpretieren.
    satzbau_persona = pd.persona_lesen(projekt.parent, "pruefer_satzbau")
    satzbau_abschnitte = _text_in_abschnitte_teilen(kapiteltext)

    ergebnisse = await asyncio.gather(
        _sammle_stream(
            settings, base_url, "anachronismus", pd.persona_lesen(projekt.parent, "pruefer_anachronismus"),
            f"JAHR: {jahr}\n\n=== VERBOTSLISTE ===\n{verbote}\n\n=== KAPITELTEXT ===\n{kapiteltext}",
            format="json",
        ),
        _sammle_stream(
            settings, base_url, "kontinuitaet", pd.persona_lesen(projekt.parent, "pruefer_kontinuitaet"),
            f"=== STAND NACH DEM VORIGEN KAPITEL ===\n{vorher}{nebenstrang_block}{figuren_block}\n\n"
            f"=== NEUES KAPITEL {n} ===\n{kapiteltext}{zusatzhinweis_block}{letztes_kapitel_block}",
            format="json",
        ),
        _sammle_stream(
            settings, base_url, "lektor", pd.persona_lesen(projekt.parent, "lektor"),
            f"=== STORY-GERUEST ===\n{geruest_text}\n\n=== KAPITELTEXT ===\n{kapiteltext}",
            format="json",
        ),
        *[
            _sammle_stream(
                settings, base_url, "satzbau", satzbau_persona,
                f"=== KAPITELTEXT ===\n{abschnitt}",
                format="json",
            )
            for abschnitt in satzbau_abschnitte
        ],
    )
    (anachronismen_text, _), (kontinuitaet_text, _), (lektor_text, _) = ergebnisse[:3]
    satzbau_antworten = ergebnisse[3:]

    roh_befunde = (
        _anachronismus_roh_befunde(kapiteltext, anachronismen_text)
        + _kontinuitaet_roh_befunde(kapiteltext, kontinuitaet_text)
        + _lektor_roh_befunde(kapiteltext, lektor_text)
    )
    for (satzbau_text, _) in satzbau_antworten:
        roh_befunde += _satzbau_roh_befunde(kapiteltext, satzbau_text)
    # Zusaetzlich zur Deduplizierung INNERHALB jeder einzelnen Pruefer-
    # Antwort (siehe _ohne_eigene_duplikate) hier noch ein Durchgang UEBER
    # alle Quellen hinweg - relevant seit Satzbau in mehreren Abschnitten
    # laeuft: verschiedene Abschnitte (oder Satzbau und Lektor) koennten
    # sonst denselben Fund doppelt melden, wenn sich Text ueberschneidet
    # oder derselbe Satz wortgleich mehrfach im Kapitel vorkommt.
    roh_befunde = _ohne_eigene_duplikate(roh_befunde, ("kategorie", "fundstelle", "vorschlag"))
    befunde = [Befund(**b) for b in befunde_zusammenfuehren(kapiteltext, roh_befunde)]

    antwort = BefundeAntwort(
        kapitel=n, erzeugt_am=time.strftime("%Y-%m-%d %H:%M"), jahr=jahr, befunde=befunde,
        quelltext_sha256=hashlib.sha256(kapiteltext.encode("utf-8")).hexdigest(),
    )
    pd.schreib(pd.befunde_datei(projekt, n), antwort.model_dump_json(indent=2))
    return antwort


async def _stand_ausfuehren(settings: Settings, projekt_root: Path, base_url: str, n: int) -> tuple[str, bool]:
    projekt = projekt_root / "projekt"
    kapiteltext = pd.lies(pd.kapitel_datei(projekt, n))
    vorher = pd.lies(pd.stand_datei(projekt, n - 1), pflicht=False,
                      ersatz="(Kein vorheriger Stand vorhanden.)")
    text, _ = await _sammle_stream(
        settings, base_url, "chronist", pd.persona_lesen(projekt_root, "chronist"),
        f"=== BISHERIGER STAND ===\n{vorher}\n\n=== KAPITEL {n} ===\n{kapiteltext}\n\n"
        f"=== AUFTRAG ===\nAktualisiere den Stand auf Kapitel {n}.",
    )
    pd.schreib(pd.stand_datei(projekt, n), text)

    geruest_text = pd.lies(pd.geruest_datei(projekt), pflicht=False, ersatz="")
    letztes = g.letztes_geplantes_kapitel(geruest_text) if geruest_text else None
    vorhandene = pd.vorhandene_kapitel(projekt)
    auto_export = bool(letztes and n == letztes and len(vorhandene) >= letztes)
    if auto_export:
        _export_ausfuehren(projekt_root)
    return text, auto_export


def _export_ausfuehren(projekt_root: Path) -> str:
    """Schreibt die Gesamtdatei in den Story-Root (NICHT in den projekt/-
    Arbeitsdateien-Unterordner) - dort sollen nur Arbeitsdateien liegen,
    Exporte/Endergebnisse eine Ebene hoeher, siehe ToDo.md Deployment.
    Dateiname folgt dem aktuellen Projekttitel (= Ordnername), nicht mehr
    hartcodiert "gesamt.md"."""
    projekt = projekt_root / "projekt"
    kapitel = pd.vorhandene_kapitel(projekt)
    if not kapitel:
        raise HTTPException(404, "Keine Kapitel gefunden.")
    ganz = "\n\n".join(pd.lies(p) for p in kapitel)
    ziel = projekt_root / f"{projekt_root.name}.md"
    pd.schreib(ziel, ganz, force=True)
    # Altlast aus einer frueheren Version (fester Dateiname "gesamt.md")
    # aufraeumen, damit nicht zwei widerspruechliche Exporte nebeneinander
    # liegen bleiben.
    alte_datei = projekt_root / "gesamt.md"
    if alte_datei != ziel and alte_datei.exists():
        alte_datei.unlink()
    return ganz


async def _kapitel_schreiben_kern(
    settings: Settings, projekt_root: Path, base_url: str, n: int,
    zusatzhinweis: str, ssh_ziel_id: str | None, on_event: OnEvent,
) -> dict:
    """Kernlogik von Schreiben + Nachbearbeitung + Pruefen fuer EIN Kapitel,
    unabhaengig von der Uebertragung. `on_event` bekommt dieselben
    Ereignis-Dicts wie zuvor per websocket.send_json - der interaktive Pfad
    (ws_schreiben) leitet sie direkt an eine offene WebSocket weiter, der
    Automatikmodus (_automatik_lauf) haengt daraus lesbare Zeilen ins
    Status-Log (siehe _automatik_log_zeile). Wirft OllamaFehler/ValueError
    bei Fehlern - die Fehlerbehandlung bleibt bewusst beim jeweiligen
    Aufrufer (WebSocket-Fehlermeldung vs. Status-Datei), nicht hier."""
    projekt = projekt_root / "projekt"

    # Stand-Sicherstellung (siehe Schnittstellen-Uebersicht 5.14): fehlt
    # stand_(n-1).md, aber Kapitel n-1 existiert, wird er zuerst nachgeholt.
    if n > 1 and not pd.stand_datei(projekt, n - 1).exists():
        if not pd.kapitel_datei(projekt, n - 1).exists():
            raise ValueError(
                f"Weder stand_{n-1:02d}.md noch kapitel_{n-1:02d}.md "
                f"vorhanden - Kapitel müssen der Reihe nach geschrieben werden."
            )

    geruest_text = pd.lies(pd.geruest_datei(projekt))
    stufe = g.jugendschutz_stufe_erkennen(geruest_text)
    autor_rolle = g.autor_rolle_erkennen(geruest_text)
    ziel = g.kapitelplan_erkennen(geruest_text).get(n)
    kapitel_block = g.kapitel_block_erkennen(geruest_text, n)
    vorher = pd.lies(pd.stand_datei(projekt, n - 1), pflicht=False,
                      ersatz="(Kein vorheriger Stand. Dies ist das erste Kapitel.)")

    if n > 1 and not pd.stand_datei(projekt, n - 1).exists() \
            and pd.kapitel_datei(projekt, n - 1).exists():
        await on_event({"phase": "stand_nachholen", "typ": "start", "kapitel": n - 1})
        await _stand_ausfuehren(settings, projekt_root, base_url, n - 1)
        await on_event({"phase": "stand_nachholen", "typ": "done", "kapitel": n - 1})
        vorher = pd.lies(pd.stand_datei(projekt, n - 1))

    zielsatz = f"Zielumfang: etwa {ziel} Wörter." if ziel else ""
    aktueller_hinweis = (
        f"\n\n=== NUR DIESES KAPITEL SCHREIBEN (Kapitel {n}) ===\n{kapitel_block}\n\n"
        f"Bleibe ausschließlich in der oben für DIESES Kapitel beschriebenen "
        f"Stufe der Liebeshandlung. Verwende KEINE Ereignisse, keine Explizitheit "
        f"und keinen Beziehungsstand aus einem ANDEREN Kapitel des Gesamtplans."
        if kapitel_block else ""
    )
    zusatz_block = (
        f"\n\n=== ZUSÄTZLICHER HINWEIS FÜR DIESEN VERSUCH ===\n{zusatzhinweis}\n"
        f"Dieser Hinweis gilt nur für diesen einen Schreibversuch und hat "
        f"Vorrang, falls er einem Detail des Geruests widerspricht."
        if zusatzhinweis else ""
    )
    user_prompt = (
        f"=== STORY-GERUEST ===\n{geruest_text}\n\n"
        f"=== STAND NACH DEM VORIGEN KAPITEL ===\n{vorher}\n\n"
        f"=== AUFTRAG ===\nSchreibe Kapitel {n}. {zielsatz}\n"
        f"Gib ausschließlich den Kapiteltext aus.\n\n"
        f"{STUFE_DIREKTIVEN[stufe]}{aktueller_hinweis}{zusatz_block}"
    )

    teile: list[str] = []
    await on_event({
        "phase": "autor", "typ": "start",
        "modell": ROLLEN[autor_rolle]["modell"], "ziel_woerter": ziel,
    })
    async for event in chat_stream(
        base_url, autor_rolle, _autor_system_prompt(projekt_root), user_prompt,
        modell_override=rollen_modell_override(settings, autor_rolle),
    ):
        if event.typ == "error":
            raise OllamaFehler(event.text)
        if event.typ in ("thinking", "content"):
            teile.append(event.text) if event.typ == "content" else None
            await on_event({"phase": "autor", "typ": event.typ, "text": event.text})
        if event.typ == "done":
            await on_event({"phase": "autor", "typ": "done", "meta": event.meta})

    text = "".join(teile).strip()
    text, findings_neustart = h.kapitel_neustart_abschneiden(text)
    text, findings_ende = h.vorzeitige_kapitelende_abschneiden(text)
    text, findings_wiederholung = h.interne_wiederholung_abschneiden(text)
    text, findings_block = h.wiederholten_absatzblock_ausschneiden(text)
    findings = findings_neustart + findings_ende + findings_wiederholung + findings_block

    if ziel and g.automatische_fortsetzung_aktiviert(geruest_text):
        text, findings_fortsetzung = await _bei_bedarf_fortsetzen(
            on_event, settings, base_url, projekt_root, n, text, ziel,
            geruest_text, vorher, stufe, zusatzhinweis, autor_rolle,
        )
        findings += findings_fortsetzung
    elif ziel and woerter(text) < ziel * FORTSETZEN_SCHWELLE:
        findings.append(h.Finding(
            "zu_kurz",
            f"Kapitel {n} liegt bei {woerter(text)} von {ziel} Wörtern "
            f"({woerter(text)/ziel:.0%}). Automatische Fortsetzung ist "
            f"deaktiviert - Kapitel bleibt so, wie es ist.",
            schwere="info",
        ))

    titelseite_hinzugefuegt = False
    if n == 1:
        epoche = pd.epoche_von_projekt(projekt_root)
        titelseite = g.titelseite_erzeugen(geruest_text, epoche)
        if titelseite:
            erste_zeile = titelseite.strip().split("\n")[0]
            if not text.lstrip().startswith(erste_zeile):
                text = titelseite + text
                titelseite_hinzugefuegt = True

    _, gesichert_als = pd.schreib(pd.kapitel_datei(projekt, n), text)

    if ziel:
        ist = woerter(text)
        abw = (ist - ziel) / ziel * 100
        if abs(abw) > 25:
            findings.append(h.Finding(
                "umfang_abweichung",
                f"Umfang weicht deutlich ab: {ist} statt {ziel} Wörter ({abw:+.0f} %).",
            ))

    findings += h.alle_nachbearbeitungs_checks(text, geruest_text, stufe)

    unbekannt = h.hunspell_unbekannte_woerter(
        text, exec_fn=_hunspell_exec_fn(settings, ssh_ziel_id),
    )
    if unbekannt:
        findings.append(h.Finding(
            "rechtschreibung",
            f"hunspell kennt folgende Wörter nicht (Eigennamen, "
            f"Fachbegriffe oder Tippfehler): {', '.join(unbekannt)}",
            schwere="info",
        ))

    await on_event({
        "phase": "nachbearbeitung", "typ": "done",
        "findings": [f.__dict__ for f in findings],
        "gesichert_als": gesichert_als,
        "titelseite_hinzugefuegt": titelseite_hinzugefuegt,
    })

    await on_event({"phase": "pruefen", "typ": "start"})
    befunde_antwort = await _pruefe_kapitel(settings, projekt, base_url, n, text, zusatzhinweis)
    await on_event({"phase": "pruefen", "typ": "done", "befunde": befunde_antwort.model_dump()})

    await on_event({"phase": "abgeschlossen", "kapitel_text": text})

    return {
        "text": text, "findings": findings, "befunde_antwort": befunde_antwort,
        "gesichert_als": gesichert_als, "titelseite_hinzugefuegt": titelseite_hinzugefuegt,
    }


@router.websocket("/{ordner:path}/ws/schreiben/{n}")
async def ws_schreiben(websocket: WebSocket, ordner: str, n: int,
                        zusatzhinweis: str = "", ssh_ziel_id: str | None = None,
                        benutzer: Benutzer = Depends(get_current_user_ws),
                        settings: Settings = Depends(get_settings)):
    # settings per Depends() statt direktem get_settings()-Aufruf - siehe
    # gleicher Kommentar in app/api/architekt.py:ws_architekt.
    await websocket.accept()
    try:
        projekt_root = projekt_pfad(settings, benutzer.username, ordner)
        with ollama_basis_url(settings, ssh_ziel_id) as base_url:
            await _kapitel_schreiben_kern(
                settings, projekt_root, base_url, n, zusatzhinweis, ssh_ziel_id,
                on_event=websocket.send_json,
            )

    except OllamaFehler as e:
        logger.warning("ws_schreiben: OllamaFehler fuer %s/%s: %s", ordner, n, e)
        try:
            await websocket.send_json({"phase": "fehler", "typ": "error", "text": str(e)})
        except Exception:
            logger.warning("ws_schreiben: konnte OllamaFehler-Meldung nicht mehr senden (Verbindung schon weg)")
    except HTTPException as e:
        logger.warning("ws_schreiben: HTTPException fuer %s/%s: %s", ordner, n, e.detail)
        try:
            await websocket.send_json({"phase": "fehler", "typ": "error", "text": e.detail})
        except Exception:
            logger.warning("ws_schreiben: konnte HTTPException-Meldung nicht mehr senden (Verbindung schon weg)")
    except WebSocketDisconnect as e:
        # Client (oder ein dazwischenliegender Proxy/Tunnel) hat die
        # Verbindung beendet - es gibt niemanden mehr, an den eine
        # Fehlermeldung geschickt werden koennte. Bewusst mit Code/Grund
        # geloggt, damit ein Verbindungsabbruch waehrend des Schreibens
        # (siehe Bedienungsanleitung/ToDo: "Kapiteltext verschwindet") im
        # Server-Log auffindbar ist, statt spurlos zu verschwinden.
        logger.warning("ws_schreiben: WebSocketDisconnect fuer %s/%s (code=%s)", ordner, n, getattr(e, "code", "?"))
        return
    except Exception as e:
        # Sicherheitsnetz gegen unerwartete Fehler (z.B. ein zukuenftiger Bug
        # wie der SSHVerbindungsFehler-Absturz durch hunspell auf einem
        # "direct"-KI-Ziel): lieber eine Fehlermeldung ans Frontend schicken,
        # als dass FastAPI versucht, auf die schon offene WebSocket-
        # Verbindung noch eine HTTP-Fehlerantwort zu schreiben (kracht mit
        # "Unexpected ASGI message" und reisst die Verbindung ohne jede
        # Frontend-Nachricht ab).
        logger.exception("ws_schreiben: unerwarteter Fehler fuer %s/%s", ordner, n)
        try:
            await websocket.send_json({"phase": "fehler", "typ": "error", "text": str(e)})
        except Exception:
            logger.warning("ws_schreiben: konnte generische Fehlermeldung nicht mehr senden (Verbindung schon weg)")
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass


def _hunspell_exec_fn(settings: Settings, ssh_ziel_id: str | None):
    if not ssh_ziel_id:
        return None
    ziel = ssh_ziel_aus_db(settings, ssh_ziel_id)
    if ziel.auth_method == "direct":
        # "Direkt"-Ziele haben nur eine HTTP-Basis-URL fuer Ollama, keine
        # echte SSH-Verbindung - exec_command (fuer hunspell) kann hier
        # nicht laufen. Ohne diese Abfrage versuchte ssh_manager._connect()
        # buchstaeblich "http://127.0.0.1:18321" als SSH-Hostnamen aufzuloesen
        # und krachte mit einer nicht abgefangenen SSHVerbindungsFehler mitten
        # im WebSocket-Handler (siehe ws_schreiben) - das Kapitel war zu dem
        # Zeitpunkt zwar schon gespeichert, aber die "abgeschlossen"-Nachricht
        # kam nie beim Frontend an.
        return None
    return functools.partial(ssh_manager.exec_command, ziel)


def _automatik_log_zeile(payload: dict) -> str | None:
    """Uebersetzt ein on_event-Ereignis (dieselbe Form wie websocket.send_json
    im interaktiven Schreiben-Pfad) in eine lesbare Log-Zeile fuer den
    Automatikmodus-Status. Streaming-Chunks (thinking/content) werden
    bewusst NICHT geloggt, sonst waeren es tausende Zeilen pro Kapitel."""
    phase, typ = payload.get("phase"), payload.get("typ")
    if phase == "stand_nachholen":
        return f"Stand für Kapitel {payload.get('kapitel')} wird nachgeholt ({typ})."
    if phase == "autor" and typ == "start":
        ziel = payload.get("ziel_woerter")
        return f"Autor schreibt (Ziel ~{ziel} Wörter)..." if ziel else "Autor schreibt..."
    if phase == "autor" and typ == "done":
        meta = payload.get("meta") or {}
        zeile = f"Kapitel-Entwurf fertig ({meta.get('woerter', '?')} Wörter, {meta.get('token_pro_sekunde', '?')} Tok/s)."
        # Ollamas eigener Abbruchgrund - "stop" ist der normale Fall (Modell
        # hat selbst einen Stop-Token gewaehlt), "length" heisst: num_predict
        # war ausgeschoepft, der Text wurde hart mitten drin gekappt. Vorher
        # wurde dieses Feld zwar in chat_stream() erfasst, aber nirgends
        # geloggt - ein zu kurz abgebrochenes Kapitel (siehe "zu_kurz"-Hinweis
        # unten) liess sich dadurch nicht von einem Budget- vs. einem
        # Modell-Problem unterscheiden (siehe Vorfall "Das-Echo-der-
        # Verpflichtung-Ein-Geheimnis-in-Winterbottom-Hall").
        grund = meta.get("done_reason")
        if grund and grund != "stop":
            zeile += f" ⚠ Ollama-Abbruchgrund: {grund}."
        return zeile
    if phase == "autor_fortsetzung" and typ == "start":
        return f"Kapitel zu kurz, Fortsetzungsversuch {payload.get('versuch')}/{payload.get('max_versuche')}..."
    if phase == "nachbearbeitung" and typ == "done":
        findings = payload.get("findings") or []
        if not findings:
            return "Nachbearbeitung fertig (keine Hinweise)."
        # Vorher nur eine inhaltsleere Zaehlung ("N Hinweis(e)") - der Text
        # jedes Hinweises (u.a. "zu_kurz": Kapitel X liegt bei Y von Z
        # Woertern, Automatische Fortsetzung deaktiviert) ging dadurch im
        # Automatikmodus komplett verloren, weil hier niemand live zuschaut
        # wie beim interaktiven Schreiben (siehe gleicher Vorfall wie oben).
        hinweise = " | ".join(f"{f.get('code')}: {f.get('meldung')}" for f in findings)
        return f"Nachbearbeitung fertig ({len(findings)} Hinweis(e)): {hinweise}"
    if phase == "pruefen" and typ == "start":
        return "Prüfer laufen..."
    if phase == "pruefen" and typ == "done":
        anzahl = len((payload.get("befunde") or {}).get("befunde", []))
        return f"Prüfung fertig ({anzahl} Fund/Funde)."
    if phase == "abgeschlossen":
        return "Kapitel gespeichert."
    return None


def _automatik_stop_angefordert(status: dict, projekt_root: Path) -> bool:
    """Liest das Stop-Flag FRISCH von der Platte statt nur aus dem im
    Speicher gehaltenen `status`-Dict des laufenden Hintergrund-Tasks - der
    "Stoppen"-Endpunkt (automatik_stop) laeuft in einem eigenen Request und
    kann das In-Memory-Objekt des Background-Tasks gar nicht erreichen, nur
    die Datei. Synchronisiert `status["stop_angefordert"]` gleich mit,
    damit ein nachfolgendes status_schreiben() ein von aussen gesetztes
    Flag nicht wieder auf False zurueckschreibt."""
    aktuell = automatik.status_lesen(projekt_root)["stop_angefordert"]
    status["stop_angefordert"] = aktuell
    return aktuell


def _automatik_status_schreiben(status: dict, projekt_root: Path) -> None:
    """Ersetzt INNERHALB von _automatik_lauf() jedes automatik.status_
    schreiben() (bis auf den initialen Reset ganz am Anfang eines Laufs):
    ein per /automatik/stop-Endpunkt in der Datei gesetztes stop_angefordert
    wuerde sonst von hier aus mit dem noch veralteten In-Memory-Wert wieder
    auf False ueberschrieben, wenn der Klick zwischen zwei _automatik_stop_
    angefordert()-Aufrufen liegt (z.B. WAEHREND eines einzelnen Pruef-
    Durchlaufs, nicht nur zwischen Kapiteln). Odert deshalb IMMER mit dem
    aktuellen Datei-Stand - einmal gesetzt, kann das Flag dadurch nicht mehr
    verloren gehen, ganz gleich an welcher Stelle im Ablauf geklickt wurde."""
    status["stop_angefordert"] = status.get("stop_angefordert") or automatik.status_lesen(projekt_root)["stop_angefordert"]
    automatik.status_schreiben(projekt_root, status)


T = TypeVar("T")

# Nach einem Fehlschlag (z.B. 502/503 - siehe Vorfall 2026-08-02, wo ein
# unerreichbares Ollama den Lauf stundenlang mit "fehler" pausiert liess,
# obwohl der Container kurz danach schon wieder lief) wird nicht sofort
# aufgegeben: bis zu AUTOMATIK_RETRY_VERSUCHE weitere Versuche im Abstand
# von AUTOMATIK_RETRY_WARTEZEIT_SEK, also 5/10/15 Minuten NACH dem ersten
# Fehlschlag. Erst wenn auch der letzte Versuch scheitert, pausiert der Lauf
# wie bisher ueber den bestehenden Fehler-Pfad in _automatik_lauf().
# Vorfall "Das-Echo-der-Verpflichtung-Ein-Geheimnis-in-Winterbottom-Hall"
# (2026-08-10): Der Automatikmodus schrieb unbeaufsichtigt alle 6 Kapitel
# durch, obwohl schon nach Kapitel 3 39% aller Pruefer-Funde (u.a. echte
# Kontinuitaetsbrueche - eine im Nebenstrang verankerte Figur, die spurlos
# verschwand) uebersprungen wurden. Ohne Zwischenstopp haeufen sich solche
# Probleme unbemerkt über mehrere weitere Kapitel, bevor der Nutzer sie
# ueberhaupt sehen kann. Alle AUTOMATIK_CHECKPOINT_INTERVALL Kapitel wird der
# Lauf deshalb angehalten (wie ein regulaerer Stop - ueber den bestehenden
# "Fortsetzen"-Button wieder aufnehmbar, siehe fortsetzbar()), WENN das
# Protokoll seit Laufbeginn uebersprungene Funde enthaelt.
AUTOMATIK_CHECKPOINT_INTERVALL = 3

AUTOMATIK_RETRY_VERSUCHE = 3
AUTOMATIK_RETRY_WARTEZEIT_SEK = 5 * 60


class _AutomatikGestoppt(Exception):
    """Interne Steuer-Exception, NICHT von OllamaFehler/HTTPException
    abgeleitet: signalisiert einen waehrend der Wartezeit zwischen zwei
    Retry-Versuchen (siehe _automatik_mit_retry) per /automatik/stop
    angeforderten Abbruch. Getrennt von echten Fehlern, damit
    _automatik_lauf() ihn wie einen regulaeren Stop behandelt (Status
    "gestoppt", kein status["fehler"]), nicht wie einen gescheiterten Lauf."""


def _automatik_fehler_nummer(e: Exception) -> str:
    """Extrahiert einen Fehlercode fuers Frontend (kompakte Fortsetzen-
    Zeile): HTTPException traegt ihn direkt (z.B. 502 aus _sammle_stream,
    siehe dort), bei OllamaFehler-Meldungen wie "Ollama antwortet mit HTTP
    502: ..." steckt er im Text. Ohne erkennbaren Code (z.B. "Ollama nicht
    erreichbar" oder "Leere Antwort") faellt es auf den Exception-Namen
    zurueck, statt nichts anzuzeigen."""
    status_code = getattr(e, "status_code", None)
    if status_code:
        return str(status_code)
    treffer = re.search(r"\bHTTP (\d{3})\b", str(e))
    if treffer:
        return treffer.group(1)
    return type(e).__name__


async def _automatik_warte_oder_stop(sekunden: float, status: dict, projekt_root: Path) -> bool:
    """Wartet `sekunden` in kurzen Schritten statt einem einzigen
    asyncio.sleep, damit ein waehrenddessen per /automatik/stop gesetztes
    Flag nicht erst nach der vollen Wartezeit bemerkt wird. Gibt True
    zurueck, wenn zwischenzeitlich gestoppt wurde."""
    schritt = 10.0
    verstrichen = 0.0
    while verstrichen < sekunden:
        if _automatik_stop_angefordert(status, projekt_root):
            return True
        await asyncio.sleep(min(schritt, sekunden - verstrichen))
        verstrichen += schritt
    return _automatik_stop_angefordert(status, projekt_root)


async def _automatik_mit_retry(
    schritt_fn: Callable[[], Awaitable[T]], status: dict, projekt_root: Path, beschreibung: str,
) -> T:
    """Fuehrt schritt_fn() aus und haengt bei einem Fehler bis zu
    AUTOMATIK_RETRY_VERSUCHE weitere Versuche an (siehe Modul-Kommentar bei
    AUTOMATIK_RETRY_VERSUCHE). Der Lauf gilt waehrend der Wartezeit
    weiterhin als "laeuft" (Stoppen-Button bleibt wirksam, siehe
    _automatik_warte_oder_stop). Scheitert auch der letzte Versuch, wird
    dessen Exception unveraendert weitergereicht, damit der bestehende
    Fehler-Pfad in _automatik_lauf() greift; wird waehrend einer Wartezeit
    gestoppt, wird stattdessen _AutomatikGestoppt geworfen."""
    for versuch in range(AUTOMATIK_RETRY_VERSUCHE + 1):
        try:
            ergebnis = await schritt_fn()
            if versuch > 0:
                status["log"].append(f"{beschreibung}: Wiederholung erfolgreich (Versuch {versuch + 1}).")
                _automatik_status_schreiben(status, projekt_root)
            return ergebnis
        except Exception as e:
            if versuch >= AUTOMATIK_RETRY_VERSUCHE:
                raise
            minuten = AUTOMATIK_RETRY_WARTEZEIT_SEK // 60
            status["log"].append(
                f"Fehler bei {beschreibung}: {e} - erneuter Versuch "
                f"{versuch + 1}/{AUTOMATIK_RETRY_VERSUCHE} in {minuten} Minuten."
            )
            _automatik_status_schreiben(status, projekt_root)
            if await _automatik_warte_oder_stop(AUTOMATIK_RETRY_WARTEZEIT_SEK, status, projekt_root):
                status["log"].append(
                    f"Gestoppt (Benutzeranforderung) während Warten auf Wiederholung bei {beschreibung}."
                )
                _automatik_status_schreiben(status, projekt_root)
                raise _AutomatikGestoppt() from e
    raise AssertionError("unreachable")  # pragma: no cover


# Mindestabstand zwischen zwei Fortschritts-Log-Zeilen waehrend des reinen
# Streamens (siehe _automatik_on_event) - klein genug, um auf einem
# langsamen KI-Ziel sichtbar zu bleiben, gross genug, um das Log nicht mit
# Zwischenstaenden vollzuspammen.
AUTOMATIK_FORTSCHRITT_INTERVALL_SEK = 20.0


def _automatik_on_event(status: dict, projekt_root: Path) -> OnEvent:
    # Geschlossen ueber den gesamten Lauf (mehrere Kapitel) hinweg, aber bei
    # jedem "start"-Ereignis unten zurueckgesetzt - verfolgt NUR die gerade
    # laufende Streaming-Antwort.
    fortschritt = {"teile": [], "letzte_zeit": 0.0, "start_zeit": 0.0, "log_index": None}

    async def _on_event(payload: dict) -> None:
        phase, typ = payload.get("phase"), payload.get("typ")

        # Live-Fortschritt waehrend des Streamens: OHNE das sah der
        # Automatikmodus auf einem langsamen KI-Ziel (z.B. CPU-Inferenz ohne
        # dedizierte GPU) ueber mehrere Minuten wie haengengeblieben aus, weil
        # zwischen "Autor schreibt..." und "Kapitel-Entwurf fertig" bisher
        # KEINE einzige Log-Zeile erschien (Streaming-Chunks wurden komplett
        # verworfen, siehe _automatik_log_zeile). Vorfall 2026-08-12: Kapitel 1
        # brauchte bei ~5 Tok/s knapp 5 Minuten reine Autor-Zeit ohne jedes
        # Zwischen-Update - wurde faelschlich fuer einen Haenger gehalten und
        # abgebrochen. Ersetzt dieselbe Log-Zeile per gemerktem Index statt bei
        # jedem Chunk eine neue anzuhaengen, damit das Log nicht mit hunderten
        # Zwischenstaenden vollrauscht.
        if phase in ("autor", "autor_fortsetzung") and typ == "start":
            fortschritt.update(teile=[], letzte_zeit=time.time(), start_zeit=time.time(), log_index=None)
            status["aktueller_text"] = ""
        elif phase in ("autor", "autor_fortsetzung") and typ == "content":
            fortschritt["teile"].append(payload.get("text") or "")
            jetzt = time.time()
            if jetzt - fortschritt["letzte_zeit"] >= AUTOMATIK_FORTSCHRITT_INTERVALL_SEK:
                fortschritt["letzte_zeit"] = jetzt
                gesamter_text = "".join(fortschritt["teile"])
                bisher_woerter = woerter(gesamter_text)
                vergangen = int(jetzt - fortschritt["start_zeit"])
                zeile = f"... schreibt noch (ca. {bisher_woerter} Wörter bisher, {vergangen}s)."
                if fortschritt["log_index"] is not None:
                    status["log"][fortschritt["log_index"]] = zeile
                else:
                    fortschritt["log_index"] = len(status["log"])
                    status["log"].append(zeile)
                # Damit das "Autor"-Fenster im Frontend (siehe SchreibenPage.tsx)
                # auch waehrend des Automatikmodus live mitlaeuft, nicht nur
                # beim interaktiven Schreiben ueber die WebSocket-Verbindung.
                status["aktueller_text"] = gesamter_text
                _automatik_status_schreiben(status, projekt_root)
            return
        elif phase in ("autor", "autor_fortsetzung") and typ == "done":
            fortschritt["log_index"] = None
            # Letzter Sync: Chunks zwischen dem letzten Throttle-Tick und dem
            # Ende der Antwort fehlten sonst im "Autor"-Fenster.
            status["aktueller_text"] = "".join(fortschritt["teile"])

        zeile = _automatik_log_zeile(payload)
        if zeile:
            status["log"].append(zeile)
            _automatik_status_schreiben(status, projekt_root)
    return _on_event


async def _automatik_lauf(settings: Settings, projekt_root: Path, ssh_ziel_id: str | None,
                           max_durchlaeufe: int, fortsetzen: bool = False,
                           automatisch_bestaetigen: bool = False) -> None:
    """Hintergrund-Job (siehe automatik_start(), per FastAPI BackgroundTasks
    gestartet - laeuft unabhaengig von einer offenen Browser-Verbindung
    weiter): schreibt zuerst alle fehlenden Kapitel, wendet dann pro
    Kapitel alle uebernehmbaren Pruefer-Korrekturen an (siehe
    app/core/automatik.py:befunde_anwenden - alles ausser Konflikt/nicht
    gefunden), wiederholt das je Kapitel bis zu `max_durchlaeufe` mal oder
    bis nichts mehr angewendet wird, und listet abschliessend unbekannte
    Woerter (hunspell) OHNE Auto-Korrektur im Protokoll.

    `fortsetzen=True` (Button "Fortsetzen" im Frontend statt "Automatikmodus
    starten"): Phase 1 ueberspringt bereits geschriebene Kapitel ohnehin
    schon anhand vorhandener Dateien - der einzige Fall, den ein normaler
    Neustart NICHT von selbst richtig macht, ist Phase 2, die sonst immer
    wieder bei Kapitel 1 anfaengt. Bei fortsetzen=True wird deshalb der
    genaue Unterbrechungspunkt (Kapitel + Durchlauf) aus dem VORHERIGEN
    Status gelesen und Phase 2 steigt dort direkt wieder ein, statt bereits
    fertig geprüfte/korrigierte Kapitel erneut abzuklappern.

    `automatisch_bestaetigen=True` (Button "Bestätige alles auf dem Weg"):
    unterdrueckt den weiter unten beschriebenen Reste-Zwischenstopp (alle
    AUTOMATIK_CHECKPOINT_INTERVALL Kapitel) - der Lauf schreibt und prueft
    unbeaufsichtigt bis zum letzten Kapitel durch, uebersprungene
    Pruefer-Funde sammeln sich wie gewohnt im Protokoll/Tab "Pruefen & Anwenden"
    fuer die Durchsicht danach, statt den Lauf zu unterbrechen."""
    projekt = projekt_root / "projekt"
    vorheriger_status = automatik.status_lesen(projekt_root)
    fortsetzen_ab_kapitel: int | None = None
    fortsetzen_ab_durchlauf = 1
    if fortsetzen and automatik.fortsetzbar(vorheriger_status) and vorheriger_status.get("phase") == "pruefen" \
            and vorheriger_status.get("aktuelles_kapitel"):
        fortsetzen_ab_kapitel = vorheriger_status["aktuelles_kapitel"]
        fortsetzen_ab_durchlauf = vorheriger_status.get("aktueller_durchlauf") or 1

    status = automatik.status_lesen(projekt_root)
    status.update({
        "laeuft": True, "gestartet_am": time.strftime("%Y-%m-%d %H:%M"),
        "phase": "schreiben", "aktuelles_kapitel": None, "gesamt_kapitel": None,
        "aktueller_durchlauf": None,
        "log": list(vorheriger_status.get("log", [])) if fortsetzen_ab_kapitel else [],
        "protokoll": list(vorheriger_status.get("protokoll", [])) if fortsetzen_ab_kapitel else [],
        "stop_angefordert": False,
        "abgeschlossen": False, "fehler": None,
        "resten_bestaetigt": False,
        "fehler_schritt": None,
    })
    if fortsetzen_ab_kapitel:
        status["log"].append(
            f"--- Fortgesetzt ab Kapitel {fortsetzen_ab_kapitel}, Durchlauf "
            f"{fortsetzen_ab_durchlauf} ---"
        )
    automatik.status_schreiben(projekt_root, status)
    start_zeit = time.time()

    try:
        geruest_text = pd.lies(pd.geruest_datei(projekt))
        letztes = g.letztes_geplantes_kapitel(geruest_text)
        if not letztes:
            raise ValueError(
                "Kein Kapitelplan im Gerüst gefunden - der Automatikmodus "
                "braucht eine geplante Gesamtzahl an Kapiteln."
            )
        status["gesamt_kapitel"] = letztes
        _automatik_status_schreiben(status, projekt_root)
        on_event = _automatik_on_event(status, projekt_root)

        with ollama_basis_url(settings, ssh_ziel_id) as base_url:
            # Phase 1: fehlende Kapitel der Reihe nach schreiben. Anhand der
            # vorhandenen Dateien statt eines expliziten Flags - dadurch
            # macht das auch ein einfacher Neustart (fortsetzen=False) nach
            # einem waehrend des Schreibens abgebrochenen Lauf automatisch
            # richtig, ganz ohne die Unterscheidung hier zu brauchen.
            start_n = 1
            while start_n <= letztes and pd.kapitel_datei(projekt, start_n).exists():
                start_n += 1

            for n in range(start_n, letztes + 1):
                if _automatik_stop_angefordert(status, projekt_root):
                    status["log"].append(f"Gestoppt (Benutzeranforderung) vor Kapitel {n}.")
                    return
                status["phase"] = "schreiben"
                status["aktuelles_kapitel"] = n
                status["log"].append(f"Schreibe Kapitel {n}/{letztes}...")
                status["fehler_schritt"] = {"kapitel": n, "phase": "schreiben", "durchlauf": None}
                _automatik_status_schreiben(status, projekt_root)
                await _automatik_mit_retry(
                    lambda n=n: _kapitel_schreiben_kern(settings, projekt_root, base_url, n, "", ssh_ziel_id, on_event),
                    status, projekt_root, f"Schreiben von Kapitel {n}",
                )
                status["fehler_schritt"] = None

            # Phase 2: jedes Kapitel pruefen und Korrekturen anwenden -
            # auch bereits vorher manuell geschriebene, nicht nur die
            # gerade in Phase 1 neu entstandenen. Bei einer Fortsetzung
            # werden Kapitel VOR dem Unterbrechungspunkt uebersprungen, da
            # deren Korrekturen im vorigen Lauf bereits vollstaendig
            # angewendet wurden (das Protokoll dafuer wurde oben schon
            # uebernommen).
            for n in range(1, letztes + 1):
                if fortsetzen_ab_kapitel and n < fortsetzen_ab_kapitel:
                    continue
                if not pd.kapitel_datei(projekt, n).exists():
                    continue
                if _automatik_stop_angefordert(status, projekt_root):
                    status["log"].append(f"Gestoppt (Benutzeranforderung) vor Prüfung von Kapitel {n}.")
                    return

                status["phase"] = "pruefen"
                status["aktuelles_kapitel"] = n
                _automatik_status_schreiben(status, projekt_root)

                # Nur beim ERSTEN in dieser Phase-2-Runde bearbeiteten Kapitel
                # (also genau dem, bei dem der vorige Lauf unterbrochen wurde)
                # beim vermerkten Durchlauf weitermachen statt bei 1 - dieser
                # Durchlauf selbst war beim Absturz garantiert noch nicht
                # abgeschlossen (befunde_anwenden() und damit das Speichern
                # der Korrekturen passiert erst NACH dem jetzt wiederholten
                # _pruefe_kapitel-Aufruf), ein erneuter Versuch dupliziert
                # also nichts.
                durchlauf = (fortsetzen_ab_durchlauf if n == fortsetzen_ab_kapitel and fortsetzen_ab_kapitel else 1) - 1
                while True:
                    durchlauf += 1
                    # Schon HIER setzen, nicht erst nach dem Stop-Check unten:
                    # steht ein Stop an, soll fortsetzen_ab_durchlauf beim
                    # naechsten Lauf genau bei DIESEM (noch nicht begonnenen)
                    # Durchlauf weitermachen, statt den bereits abgeschlossenen
                    # vorigen unnoetig zu wiederholen.
                    status["aktueller_durchlauf"] = durchlauf
                    # Frisch von der Platte pruefen (nicht nur beim
                    # Kapitelwechsel oben): sonst kann ein "Stoppen"-Klick
                    # WAEHREND eines laufenden Durchlaufs verloren gehen - der
                    # naechste status_schreiben() weiter unten wuerde sonst
                    # den extern gesetzten Flag mit dem veralteten
                    # In-Memory-Wert (noch False) wieder ueberschreiben, bevor
                    # die Schleife hier je wieder danach schaut.
                    if _automatik_stop_angefordert(status, projekt_root):
                        status["log"].append(
                            f"Gestoppt (Benutzeranforderung) während Kapitel {n}, vor Durchlauf {durchlauf}."
                        )
                        _automatik_status_schreiben(status, projekt_root)
                        return
                    # Vorfall 2026-08-12: Dieser Aufruf startet vier parallele
                    # Pruefer-Rollen (siehe _pruefe_kapitel) und liefert bis zu
                    # deren gemeinsamem Abschluss KEINERLEI Log-Zeile - anders
                    # als beim Autor (siehe _automatik_on_event) gibt es hier
                    # kein Streaming, das sich fuer Zwischen-Updates anzapfen
                    # liesse, aber zumindest der Beginn muss sichtbar sein,
                    # sonst wirkt ein laengerer Pruef-Durchlauf auf einem
                    # langsamen KI-Ziel wie ein Haenger (wurde live so
                    # gemeldet, obwohl der Lauf kurz danach sauber fertig war).
                    status["log"].append(f"Kapitel {n}, Durchlauf {durchlauf}: Prüfer laufen...")
                    _automatik_status_schreiben(status, projekt_root)
                    kapiteltext = pd.lies(pd.kapitel_datei(projekt, n))
                    status["fehler_schritt"] = {"kapitel": n, "phase": "pruefen", "durchlauf": durchlauf}
                    befunde_antwort = await _automatik_mit_retry(
                        lambda n=n, kapiteltext=kapiteltext: _pruefe_kapitel(settings, projekt, base_url, n, kapiteltext),
                        status, projekt_root, f"Prüfung von Kapitel {n}, Durchlauf {durchlauf}",
                    )
                    status["fehler_schritt"] = None
                    befunde_dicts = [b.model_dump() for b in befunde_antwort.befunde]
                    korrigiert, protokoll_eintraege = automatik.befunde_anwenden(kapiteltext, befunde_dicts)
                    for eintrag in protokoll_eintraege:
                        eintrag["kapitel"] = n
                        eintrag["durchlauf"] = durchlauf
                    status["protokoll"] += protokoll_eintraege

                    angewendet = sum(1 for e in protokoll_eintraege if e["art"] == "angewendet")
                    status["log"].append(
                        f"Kapitel {n}, Durchlauf {durchlauf}: {angewendet} Korrektur(en) "
                        f"angewendet, {len(protokoll_eintraege) - angewendet} übersprungen."
                    )

                    # Ein gespliceter "vorschlag" kann trotz aller Sicherheits-
                    # netze (vorschlag_verdaechtig, _ist_echte_korrektur) eine
                    # Ueberschrift oder einen Absatzblock duplizieren (siehe
                    # kapitel_neustart_abschneiden()/wiederholter_absatzblock_
                    # ausschneiden() weiter oben) - diese Strukturchecks liefen
                    # bisher nur direkt nach der Erst-Generierung, nie nach dem
                    # Anwenden von Pruefer-Vorschlaegen. Denselben Check hier
                    # zu wiederholen schliesst diese Luecke, ohne den
                    # Frisch-Anwenden-Pfad selbst anzufassen.
                    if angewendet > 0:
                        korrigiert, struktur_neustart = h.kapitel_neustart_abschneiden(korrigiert)
                        korrigiert, struktur_block = h.wiederholten_absatzblock_ausschneiden(korrigiert)
                        for finding in struktur_neustart + struktur_block:
                            status["log"].append(
                                f"Kapitel {n}, Durchlauf {durchlauf}: {finding.meldung}"
                            )

                    _automatik_status_schreiben(status, projekt_root)

                    if korrigiert != kapiteltext:
                        pd.schreib(pd.kapitel_datei(projekt, n), korrigiert)

                    if angewendet == 0 or durchlauf >= max_durchlaeufe:
                        break

                status["aktueller_durchlauf"] = None
                finaler_text = pd.lies(pd.kapitel_datei(projekt, n))
                status["fehler_schritt"] = {"kapitel": n, "phase": "rechtschreibung", "durchlauf": None}

                async def _hunspell_schritt(finaler_text=finaler_text) -> list[str] | None:
                    return h.hunspell_unbekannte_woerter(
                        finaler_text, exec_fn=_hunspell_exec_fn(settings, ssh_ziel_id),
                    )

                unbekannt = await _automatik_mit_retry(
                    _hunspell_schritt, status, projekt_root, f"Rechtschreibprüfung Kapitel {n}",
                )
                status["fehler_schritt"] = None
                if unbekannt:
                    status["protokoll"].append({
                        "art": "rechtschreibung", "kapitel": n, "unbekannte_woerter": unbekannt,
                    })
                    status["log"].append(
                        f"Kapitel {n}: {len(unbekannt)} unbekannte(s) Wort/Wörter (hunspell) "
                        f"- keine automatische Korrektur, siehe Protokoll."
                    )
                _automatik_status_schreiben(status, projekt_root)

                if n < letztes and n % AUTOMATIK_CHECKPOINT_INTERVALL == 0 \
                        and automatik.reste_vorhanden(status) and not automatisch_bestaetigen:
                    status["aktuelles_kapitel"] = n + 1
                    status["log"].append(
                        f"Angehalten nach Kapitel {n}: ungelöste Prüfer-Funde seit "
                        f"Laufbeginn vorhanden (siehe Protokoll). Bitte im Tab "
                        f"\"Prüfen & Anwenden\" durchsehen, dann mit \"Fortsetzen\" "
                        f"weitermachen."
                    )
                    _automatik_status_schreiben(status, projekt_root)
                    return
                elif n < letztes and n % AUTOMATIK_CHECKPOINT_INTERVALL == 0 \
                        and automatik.reste_vorhanden(status) and automatisch_bestaetigen:
                    status["log"].append(
                        f"Kapitel {n}: ungelöste Prüfer-Funde vorhanden, wird dank "
                        f"\"Bestätige alles auf dem Weg\" ohne Zwischenstopp fortgesetzt."
                    )
                    _automatik_status_schreiben(status, projekt_root)

        status["phase"] = "abgeschlossen"
        status["abgeschlossen"] = True
        status["log"].append("Automatikmodus abgeschlossen.")
    except _AutomatikGestoppt:
        pass  # Log-Zeile bereits in _automatik_mit_retry gesetzt; kein status["fehler"].
    except Exception as e:
        logger.exception("Automatikmodus: Fehler in Projekt %s", projekt_root)
        status["fehler"] = str(e)
        status["log"].append(f"Fehler: {e}")
        if status.get("fehler_schritt"):
            status["fehler_schritt"]["fehler_nummer"] = _automatik_fehler_nummer(e)
    finally:
        status["laeuft"] = False
        automatik.status_schreiben(projekt_root, status)
        if status.get("abgeschlossen"):
            lauf_status = "abgeschlossen"
        elif status.get("fehler"):
            lauf_status = "fehler"
        else:
            lauf_status = "gestoppt"
        automatik.verlauf_eintrag_anhaengen(projekt_root, {
            "datum": status["gestartet_am"].split(" ")[0],
            "von": status["gestartet_am"],
            "bis": time.strftime("%Y-%m-%d %H:%M"),
            "dauer_sekunden": round(time.time() - start_zeit),
            "status": lauf_status,
            "fehler": status.get("fehler"),
            "fortgesetzt": bool(fortsetzen_ab_kapitel),
        })


@router.post("/{ordner:path}/automatik/start")
async def automatik_start(ordner: str, anfrage: AutomatikStartAnfrage,
                           background_tasks: BackgroundTasks,
                           ssh_ziel_id: str | None = Query(None),
                           settings: Settings = Depends(get_settings),
                           benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    if automatik.status_lesen(projekt_root)["laeuft"]:
        raise HTTPException(409, "Automatikmodus läuft für dieses Projekt bereits.")
    background_tasks.add_task(
        _automatik_lauf, settings, projekt_root, ssh_ziel_id, anfrage.max_durchlaeufe, anfrage.fortsetzen,
        anfrage.automatisch_bestaetigen,
    )
    return {"gestartet": True}


@router.get("/{ordner:path}/automatik/status", response_model=AutomatikStatusAntwort)
def automatik_status(ordner: str, settings: Settings = Depends(get_settings),
                      benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    status = automatik.status_lesen(projekt_root)
    return AutomatikStatusAntwort(**status, fortsetzbar=automatik.fortsetzbar(status))


@router.get("/{ordner:path}/automatik/verlauf", response_model=list[AutomatikVerlaufEintrag])
def automatik_verlauf(ordner: str, settings: Settings = Depends(get_settings),
                       benutzer: Benutzer = Depends(get_current_user)):
    """Dauerhaftes Protokoll aller bisherigen Automatik-Laeufe dieses
    Projekts (siehe app/core/automatik.py:verlauf_eintrag_anhaengen) -
    unabhaengig vom aktuellen Status, der nur den letzten Lauf zeigt."""
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    return automatik.verlauf_lesen(projekt_root)


@router.post("/{ordner:path}/automatik/stop")
def automatik_stop(ordner: str, settings: Settings = Depends(get_settings),
                    benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    status = automatik.status_lesen(projekt_root)
    if status["laeuft"]:
        status["stop_angefordert"] = True
        automatik.status_schreiben(projekt_root, status)
    return {"stop_angefordert": True}


@router.post("/{ordner:path}/automatik/resten-bestaetigen")
def automatik_resten_bestaetigen(ordner: str, settings: Settings = Depends(get_settings),
                                  benutzer: Benutzer = Depends(get_current_user)):
    """Quittiert die im Protokoll des letzten Laufs verbliebenen Reste
    (uebersprungene Funde, unbekannte Woerter) manuell als erledigt - sonst
    zeigt die Projektliste "Automatik fertig - Reste pruefen" dauerhaft an,
    auch nachdem sie im Tab "Pruefen & Anwenden"/"Rechtschreibung" laengst
    durchgesehen wurden (das Protokoll ist ein eingefrorener Schnappschuss
    des Laufs, kein live mitgefuehrter Zustand)."""
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    status = automatik.status_lesen(projekt_root)
    if status["laeuft"]:
        raise HTTPException(409, "Automatikmodus läuft noch für dieses Projekt.")
    status["resten_bestaetigt"] = True
    automatik.status_schreiben(projekt_root, status)
    return {"resten_bestaetigt": True}


@router.post("/{ordner:path}/pruefen/{n}", response_model=BefundeAntwort)
async def pruefen(ordner: str, n: int, ssh_ziel_id: str | None = Query(None),
                   settings: Settings = Depends(get_settings),
                   benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    projekt = projekt_root / "projekt"
    kapiteltext = pd.lies(pd.kapitel_datei(projekt, n))
    with ollama_basis_url(settings, ssh_ziel_id) as base_url:
        return await _pruefe_kapitel(settings, projekt, base_url, n, kapiteltext)


@router.post("/{ordner:path}/stand/{n}")
async def stand(ordner: str, n: int, ssh_ziel_id: str | None = Query(None),
                 settings: Settings = Depends(get_settings),
                 benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    with ollama_basis_url(settings, ssh_ziel_id) as base_url:
        text, auto_export = await _stand_ausfuehren(settings, projekt_root, base_url, n)
    return {"stand": text, "auto_export": auto_export}


@router.post("/{ordner:path}/export")
def export(ordner: str, settings: Settings = Depends(get_settings),
           benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    ganz = _export_ausfuehren(projekt_root)
    # projekt_root.name statt hartcodiert "gesamt" - traegt (nach dem Fix
    # der Ordner-Umbenennung) den eigentlichen Geschichtennamen, siehe
    # app/core/projekt_dateien.py:projektordner_umbenennen.
    return {"gesamt": ganz, "dateiname": f"{projekt_root.name}.md"}


@router.get("/{ordner:path}/export/pdf")
def export_pdf(ordner: str, settings: Settings = Depends(get_settings),
                benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    projekt = projekt_root / "projekt"
    kapitel_dateien = pd.vorhandene_kapitel(projekt)
    if not kapitel_dateien:
        raise HTTPException(404, "Keine Kapitel gefunden.")
    geruest_text = pd.lies(pd.geruest_datei(projekt), pflicht=False, ersatz="")
    epoche = pd.epoche_von_projekt(projekt_root)
    kapitel = [(pd.kapitelnummer_aus_dateiname(p), pd.lies(p)) for p in kapitel_dateien]
    cover_datei = pd.cover_datei(projekt)
    cover_bytes = cover_datei.read_bytes() if cover_datei.exists() else None
    pdf_bytes = buch_pdf_erzeugen(geruest_text, epoche, kapitel, cover_bytes=cover_bytes)
    # ordner kann bei aktivierten Epoche-Unterordnern einen "/" enthalten
    # (z.B. "Mittelalter/Im-Feuer-gestaehlt") - als Dateiname nur den
    # eigentlichen Projektnamen verwenden, kein "/" im Dateinamen.
    dateiname = projekt_root.name
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{dateiname}.pdf"'},
    )


def _neuester_stand_text(projekt: Path) -> str:
    """Kompaktester verfuegbarer Kontext ueber den aktuellen Stand der
    Geschichte, fuer story_frage() unten - bevorzugt den vom Chronisten
    erzeugten Stand nach dem zuletzt geschriebenen Kapitel (siehe
    pd.stand_datei) statt aller rohen Kapiteltexte, damit auch eine lange
    Geschichte mit vielen Kapiteln innerhalb von num_ctx passt. Faellt auf
    den rohen Kapiteltext zurueck, falls fuer das letzte Kapitel (noch) kein
    Stand erzeugt wurde."""
    kapitel_dateien = pd.vorhandene_kapitel(projekt)
    if not kapitel_dateien:
        return "(Noch keine Kapitel geschrieben.)"
    letzte_nummer = max(pd.kapitelnummer_aus_dateiname(p) for p in kapitel_dateien)
    stand = pd.lies(pd.stand_datei(projekt, letzte_nummer), pflicht=False, ersatz="")
    if stand:
        return stand
    return pd.lies(pd.kapitel_datei(projekt, letzte_nummer))


@router.post("/{ordner:path}/frage", response_model=StoryFrageAntwort)
async def story_frage(ordner: str, anfrage: StoryFrageAnfrage, ssh_ziel_id: str | None = Query(None),
                       settings: Settings = Depends(get_settings),
                       benutzer: Benutzer = Depends(get_current_user)):
    """Beantwortet eine Nutzerfrage ZU der laufenden Geschichte (z.B. "wie
    hiess nochmal die Nebenfigur aus Kapitel 2?"), OHNE die Geschichte
    fortzuschreiben - siehe app/core/geruest.py:STORY_FRAGE_SYSTEM. Getrennt
    vom "Zusätzlicher Hinweis"-Feld beim Kapitel-Schreiben (das WUENSCHE für
    das naechste Kapitel entgegennimmt, siehe ws_schreiben/
    zusatzhinweis) - hier geht es rein um Informationsabruf ueber bereits
    Etabliertes, ohne neuen Text zu erzeugen."""
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    projekt = projekt_root / "projekt"
    geruest_text = pd.lies(pd.geruest_datei(projekt), pflicht=False, ersatz="")
    if not geruest_text:
        raise HTTPException(404, "Kein Gerüst gefunden.")
    stand_text = _neuester_stand_text(projekt)
    user_text = (
        f"=== STORY-GERUEST ===\n{geruest_text}\n\n"
        f"=== AKTUELLER STAND DER GESCHICHTE ===\n{stand_text}\n\n"
        f"=== FRAGE ===\n{anfrage.frage.strip()}"
    )
    with ollama_basis_url(settings, ssh_ziel_id) as base_url:
        modell = rollen_modell_override(settings, "story_frage")
        try:
            antwort, _meta = await _sammle_antwort(
                base_url, "story_frage", g.STORY_FRAGE_SYSTEM, user_text,
                modell_override=modell,
            )
        except OllamaFehler as e:
            raise HTTPException(502, str(e)) from e
    return StoryFrageAntwort(antwort=antwort.strip())


@router.post("/{ordner:path}/cover/prompt-vorschlagen", response_model=CoverPromptAntwort)
async def cover_prompt_vorschlagen(ordner: str, ssh_ziel_id: str | None = Query(None),
                                    settings: Settings = Depends(get_settings),
                                    benutzer: Benutzer = Depends(get_current_user)):
    """Fasst geruest.md per Text-KI-Ziel (ssh_ziel_id, wie bei /pruefen und
    /stand) zu einem deutschen Bildprompt-Entwurf zusammen - siehe
    app/core/geruest.py:COVER_PROMPT_SYSTEM. Liefert nur den Prompt-Text,
    generiert noch KEIN Bild (siehe cover_generieren(), die den Prompt vor
    der sd-server-Anfrage erst ins Englische uebersetzt)."""
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    projekt = projekt_root / "projekt"
    geruest_text = pd.lies(pd.geruest_datei(projekt), pflicht=False, ersatz="")
    if not geruest_text:
        raise HTTPException(404, "Kein Gerüst gefunden.")
    with ollama_basis_url(settings, ssh_ziel_id) as base_url:
        modell = rollen_modell_override(settings, "cover_prompt")
        try:
            prompt, _meta = await _sammle_antwort(
                base_url, "cover_prompt", g.COVER_PROMPT_SYSTEM, geruest_text,
                modell_override=modell,
            )
        except OllamaFehler as e:
            raise HTTPException(502, str(e)) from e
    return CoverPromptAntwort(prompt=prompt.strip())


@router.post("/{ordner:path}/cover/generieren")
async def cover_generieren(ordner: str, anfrage: CoverGenerierenAnfrage,
                            bild_ziel_id: str = Query(...),
                            ssh_ziel_id: str | None = Query(None),
                            settings: Settings = Depends(get_settings),
                            benutzer: Benutzer = Depends(get_current_user)):
    """Erzeugt das eigentliche Deckblattbild ueber sd-server (siehe
    app/core/bild_generierung.py) und speichert es als projekt/cover.png.
    bild_ziel_id waehlt das KI-Ziel mit konfiguriertem bildki_port (siehe
    app/services.py:bild_basis_url) - unabhaengig vom Text-KI-Ziel aus
    cover_prompt_vorschlagen(), auch wenn in der Praxis meist dasselbe
    KI-Ziel (Athene) beides bedient. anfrage.prompt ist Deutsch (der User
    tippt/korrigiert im Frontend auf Deutsch, siehe
    g.COVER_PROMPT_SYSTEM) - wird hier per ssh_ziel_id erst ins Englische
    uebersetzt (g.COVER_PROMPT_UEBERSETZEN_SYSTEM), bevor sd-server ihn
    bekommt, das nur englische Prompts sauber versteht."""
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    projekt = projekt_root / "projekt"
    with ollama_basis_url(settings, ssh_ziel_id) as text_base_url:
        modell = rollen_modell_override(settings, "cover_prompt")
        try:
            prompt_englisch, _meta = await _sammle_antwort(
                text_base_url, "cover_prompt", g.COVER_PROMPT_UEBERSETZEN_SYSTEM,
                g.COVER_PROMPT_HOCHFORMAT_PRAEFIX + anfrage.prompt,
                modell_override=modell,
            )
        except OllamaFehler as e:
            raise HTTPException(502, str(e)) from e
    with bild_basis_url(settings, bild_ziel_id) as base_url:
        try:
            bild_bytes = await bild_generierung.generiere_cover(base_url, prompt_englisch.strip())
        except BildGenerierungFehler as e:
            raise HTTPException(502, str(e)) from e
    pd.cover_datei(projekt).write_bytes(bild_bytes)
    return {"gespeichert": True}


@router.post("/{ordner:path}/cover/hochladen")
async def cover_hochladen(ordner: str, datei: UploadFile = File(...),
                           settings: Settings = Depends(get_settings),
                           benutzer: Benutzer = Depends(get_current_user)):
    """Alternative zur KI-Generierung oben: ein von Hand erzeugtes Titelbild
    (z.B. kostenlos ueber eine Web-Oberflaeche wie Google AI Studio erstellt
    und heruntergeladen) direkt als cover.png uebernehmen, ohne dass das
    Projekt ein eigenes Bild-KI-Ziel braucht. Nimmt PNG/JPEG/WEBP entgegen,
    normalisiert intern immer zu PNG (siehe
    app/core/bild_generierung.py:cover_aus_upload_normalisieren)."""
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    projekt = projekt_root / "projekt"
    rohdaten = await datei.read()
    try:
        png_bytes = bild_generierung.cover_aus_upload_normalisieren(rohdaten)
    except BildGenerierungFehler as e:
        raise HTTPException(400, str(e)) from e
    pd.cover_datei(projekt).write_bytes(png_bytes)
    return {"gespeichert": True}


@router.get("/{ordner:path}/cover")
def cover_lesen(ordner: str, settings: Settings = Depends(get_settings),
                 benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    cover_datei = pd.cover_datei(projekt_root / "projekt")
    if not cover_datei.exists():
        raise HTTPException(404, "Kein Titelbild vorhanden.")
    return Response(content=cover_datei.read_bytes(), media_type="image/png")


@router.post("/{ordner:path}/zusammenfassen")
def zusammenfassen(ordner: str, von: int | None = None, bis: int | None = None,
                    settings: Settings = Depends(get_settings),
                    benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    projekt = projekt_root / "projekt"
    if von is None or bis is None:
        return {"gesamt": _export_ausfuehren(projekt_root), "dateiname": f"{projekt_root.name}.md"}
    if von > bis:
        von, bis = bis, von
    alle = pd.vorhandene_kapitel(projekt)
    ausgewaehlt = [p for p in alle if von <= pd.kapitelnummer_aus_dateiname(p) <= bis]
    if not ausgewaehlt:
        raise HTTPException(404, f"Keine Kapitel im Bereich {von}-{bis} gefunden.")
    ganz = "\n\n".join(pd.lies(p) for p in ausgewaehlt)
    # Geschichtenname + Kapitelnummern als Suffix (z.B. "Die-Reise_2_3.md")
    # statt generischem "zusammen_02-03.md" - so bleibt auch bei mehreren
    # Zwischenstaenden erkennbar, zu welcher Geschichte und welchem
    # Kapitelbereich die Datei gehoert. Landet im Story-Root, nicht im
    # projekt/-Arbeitsdateien-Unterordner (siehe _export_ausfuehren).
    ziel_name = f"{projekt_root.name}_{von}_{bis}.md"
    pd.schreib(projekt_root / ziel_name, ganz, force=True)
    return {"datei": ziel_name, "inhalt": ganz}


@router.get("/{ordner:path}/rechtschreibung/{n}", response_model=RechtschreibAntwort)
def rechtschreibung(ordner: str, n: int, ssh_ziel_id: str | None = Query(None),
                     settings: Settings = Depends(get_settings),
                     benutzer: Benutzer = Depends(get_current_user)):
    projekt = projekt_pfad(settings, benutzer.username, ordner) / "projekt"
    text = pd.lies(pd.kapitel_datei(projekt, n))
    unbekannt = h.hunspell_unbekannte_woerter(text, exec_fn=_hunspell_exec_fn(settings, ssh_ziel_id))
    if unbekannt is None:
        return RechtschreibAntwort(unbekannte_woerter=[], hunspell_verfuegbar=False)
    woerter_mit_satz = []
    for w in unbekannt:
        position = h.wort_position_finden(text, w)
        woerter_mit_satz.append(RechtschreibWort(
            wort=w, satz=h.satz_mit_wort_finden(text, w),
            start=position[0] if position else None,
            end=position[1] if position else None,
        ))
    return RechtschreibAntwort(unbekannte_woerter=woerter_mit_satz, hunspell_verfuegbar=True)
