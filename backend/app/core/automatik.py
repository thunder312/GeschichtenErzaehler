"""Automatikmodus: alle fehlenden Kapitel am Stueck schreiben, danach alle
Pruefer-Korrekturen automatisch anwenden - siehe app/api/pipeline.py fuer
den eigentlichen Ablauf (_automatik_lauf). Dieses Modul haelt bewusst nur
framework-freie Logik (kein FastAPI/Settings), analog zu
app/core/heuristik.py und app/core/befunde_merge.py:
- befunde_anwenden(): das serverseitige Pendant zum bisher rein im Browser
  (Monaco-Editor-Decorations, siehe frontend/src/components/befundReview.ts)
  laufenden "Uebernehmen" - noetig, weil der Automatikmodus unbeaufsichtigt
  ohne offenen Browser laufen soll.
- status_lesen/status_schreiben(): einfache JSON-Datei-Persistenz fuer den
  Fortschritt, abfragbar ueber GET .../automatik/status auch nachdem der
  Browser-Tab geschlossen wurde.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from app.core.befunde_merge import vorschlag_dupliziert_kontext, vorschlag_verdaechtig

AUTOMATIK_STATUS_DATEINAME = "automatik_status.json"
AUTOMATIK_VERLAUF_DATEINAME = "automatik_verlauf.json"
AUTOMATIK_GEPRUEFT_DATEINAME = "automatik_geprueft.json"


def _automatik_status_datei(projekt_root: Path) -> Path:
    return projekt_root / "projekt" / AUTOMATIK_STATUS_DATEINAME


def _automatik_verlauf_datei(projekt_root: Path) -> Path:
    return projekt_root / "projekt" / AUTOMATIK_VERLAUF_DATEINAME


def _automatik_geprueft_datei(projekt_root: Path) -> Path:
    return projekt_root / "projekt" / AUTOMATIK_GEPRUEFT_DATEINAME


def geprueft_lesen(projekt_root: Path) -> dict[str, str]:
    """Liefert {kapitelnummer_als_string: sha256_des_konvergierten_texts} -
    siehe geprueft_markieren()/kapitel_bereits_konvergiert()."""
    pfad = _automatik_geprueft_datei(projekt_root)
    if not pfad.exists():
        return {}
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def geprueft_markieren(projekt_root: Path, n: int, text: str) -> None:
    """Vermerkt Kapitel n als von Phase 2 (Pruefen/Auto-Korrektur, siehe
    app/api/pipeline.py:_automatik_lauf) bis zur Konvergenz abgearbeitet -
    NUR dort aufrufen, direkt NACHDEM die Durchlauf-Schleife fuer dieses
    Kapitel beendet wurde (angewendet == 0 ODER max_durchlaeufe erreicht),
    nie aus dem einmaligen Diagnose-Check direkt nach dem Schreiben (siehe
    _kapitel_schreiben_kern) - dessen Aufruf von _pruefe_kapitel schreibt
    zwar ebenfalls einen Hash (befunde_NN.json:quelltext_sha256), prueft
    aber nur EINMAL und wendet nie Korrekturen an; wuerde dieser Hash hier
    fuer die Konvergenz-Markierung wiederverwendet, wuerde Phase 2 jedes
    frisch geschriebene Kapitel faelschlich als "fertig" ueberspringen -
    inklusive tatsaechlich noch offener, nie angewendeter Pruefer-Funde
    (im Test test_automatik_fortsetzen_ueberspringt_bereits_geprueftes_kapitel
    am 2026-09-02 so aufgefallen, bevor dieser dedizierte Marker eingefuehrt
    wurde)."""
    pfad = _automatik_geprueft_datei(projekt_root)
    daten = geprueft_lesen(projekt_root)
    daten[str(n)] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")


def kapitel_bereits_konvergiert(projekt_root: Path, n: int, aktueller_text: str) -> bool:
    """True, wenn Kapitel n laut geprueft_markieren() bereits bis zur
    Konvergenz geprueft wurde UND `aktueller_text` seither unveraendert ist -
    _automatik_lauf ueberspringt ein solches Kapitel in Phase 2, unabhaengig
    vom nur_neue_kapitel-Flag. Deckt insbesondere den Fall ab, dass der
    normale "Automatikmodus starten"-Button (nicht "Weitere Kapitel
    schreiben") auf einer im Geruest um Kapitel ergaenzten, laengst fertig
    geprueften Geschichte gestartet wird - Phase 2 soll dann trotzdem nicht
    wieder bei Kapitel 1 anfangen (Vorfall 2026-09-02: 11-Kapitel-Geschichte,
    Kapitel 11 neu ergaenzt, Phase 2 lief erst wieder komplett Kapitel 1-3
    durch, bis der Nutzer stoppte)."""
    gespeichert = geprueft_lesen(projekt_root).get(str(n))
    if not gespeichert:
        return False
    return gespeichert == hashlib.sha256(aktueller_text.encode("utf-8")).hexdigest()


def status_lesen(projekt_root: Path) -> dict[str, Any]:
    """Liefert den zuletzt gespeicherten Status, oder einen Leerzustand,
    wenn noch nie ein Automatik-Lauf gestartet wurde."""
    pfad = _automatik_status_datei(projekt_root)
    if not pfad.exists():
        return {
            "laeuft": False,
            "gestartet_am": None,
            "phase": None,
            "aktuelles_kapitel": None,
            "gesamt_kapitel": None,
            "aktueller_durchlauf": None,
            "log": [],
            "protokoll": [],
            "stop_angefordert": False,
            "abgeschlossen": False,
            "fehler": None,
            "resten_bestaetigt": False,
            "fehler_schritt": None,
            "aktueller_text": None,
            "kapitel_letzter_durchlauf": {},
        }
    status = json.loads(pfad.read_text(encoding="utf-8"))
    status.setdefault("aktueller_durchlauf", None)
    status.setdefault("resten_bestaetigt", False)
    # Erst mit den 502/503-Retries (siehe app/api/pipeline.py:
    # _automatik_mit_retry) eingefuehrt - setdefault fuer Status-Dateien
    # aelterer, noch laufender/pausierter Automatik-Laeufe.
    status.setdefault("fehler_schritt", None)
    # Erst mit der Live-Fortschrittsanzeige (siehe app/api/pipeline.py:
    # _automatik_on_event) eingefuehrt - Text, den der Autor gerade im
    # Automatikmodus schreibt, damit das "Autor"-Fenster im Frontend auch
    # unbeaufsichtigt live mitlaufen kann statt nur waehrend interaktiven
    # Schreibens (siehe SchreibenPage.tsx).
    status.setdefault("aktueller_text", None)
    # Erst mit der Neuverankerung/Rest-Erkennungs-Praezisierung (siehe
    # reste_vorhanden()) eingefuehrt - {} statt eines fehlenden Schluessels
    # macht das Verhalten fuer aeltere Status-Dateien konservativ (kein
    # bekannter "letzter Durchlauf", also faellt reste_vorhanden() dort auf
    # die reine Protokoll-Heuristik zurueck).
    status.setdefault("kapitel_letzter_durchlauf", {})
    return status


def status_schreiben(projekt_root: Path, status: dict[str, Any]) -> None:
    pfad = _automatik_status_datei(projekt_root)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def fortsetzbar(status: dict[str, Any]) -> bool:
    """Ein Lauf ist fortsetzbar, wenn schon einmal gestartet wurde, er aber
    weder gerade laeuft noch sauber abgeschlossen ist (also nach einem
    Fehler oder einem Stop-Wunsch abgebrochen wurde) - siehe
    app/api/pipeline.py:_automatik_lauf fuer die Wiederaufnahme selbst."""
    return bool(status.get("gestartet_am")) and not status.get("laeuft") and not status.get("abgeschlossen")


def verwaiste_laeufe_zuruecksetzen(projects_root: Path) -> int:
    """Setzt jeden automatik_status.json unterhalb von projects_root mit
    laeuft=true auf laeuft=false zurueck - wird EINMALIG beim Start des
    Backends aufgerufen (siehe app/main.py). Ein "laeuft: true" kann beim
    Prozessstart NIEMALS mehr echt sein: der zugehoerige Hintergrund-Task
    lief im VORHERIGEN Prozess (siehe app/api/pipeline.py:_automatik_lauf)
    und existiert nach einem Neustart (Deploy, Absturz, Server-Reboot) nicht
    mehr - er bekommt insbesondere NIE die Chance, sein eigenes
    finally: status["laeuft"] = False auszufuehren, weil der komplette
    Python-Prozess beendet wird, nicht nur eine einzelne Anfrage.

    Ohne dieses Zuruecksetzen bleibt ein unterbrochener Lauf im Frontend fuer
    immer als "laeuft" haengen (es kommen nie wieder neue Log-Zeilen), UND
    fortsetzbar() bietet "Fortsetzen" gar nicht erst an, weil es explizit
    "not laeuft" voraussetzt - der Nutzer sitzt komplett fest, ohne jeden
    Ausweg ausser einem manuellen Datei-Edit auf dem Server.

    Vorfall 2026-08-12: Ein Backend-Deploy waehrend eines laufenden
    Automatik-Laufs killte den Hintergrund-Task mitten in Kapitel 5 (Autor-
    Streaming), der Status blieb dauerhaft auf "laeuft" haengen - vom
    Frontend aus nicht mehr zu unterscheiden von einem echten, sehr langsamen
    KI-Ziel."""
    zurueckgesetzt = 0
    for pfad in projects_root.rglob(AUTOMATIK_STATUS_DATEINAME):
        try:
            status: dict[str, Any] = json.loads(pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not status.get("laeuft"):
            continue

        status["laeuft"] = False
        status["aktueller_durchlauf"] = None
        status["log"] = list(status.get("log", [])) + [
            "Automatik-Lauf durch einen Backend-Neustart unterbrochen (z.B. "
            "Deploy, Absturz oder Server-Neustart) - über \"Fortsetzen\" "
            "wieder aufnehmbar."
        ]
        try:
            pfad.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            continue

        projekt_root = pfad.parent.parent
        gestartet_am = status.get("gestartet_am")
        dauer = None
        if gestartet_am:
            try:
                dauer = round(time.time() - time.mktime(time.strptime(gestartet_am, "%Y-%m-%d %H:%M")))
            except ValueError:
                dauer = None
        verlauf_eintrag_anhaengen(projekt_root, {
            "datum": gestartet_am.split(" ")[0] if gestartet_am else time.strftime("%Y-%m-%d"),
            "von": gestartet_am,
            "bis": time.strftime("%Y-%m-%d %H:%M"),
            "dauer_sekunden": dauer,
            "status": "gestoppt",
            "fehler": "Backend-Neustart während des Laufs (z.B. Deploy).",
            "fortgesetzt": False,
        })
        zurueckgesetzt += 1
    return zurueckgesetzt


def verlauf_lesen(projekt_root: Path) -> list[dict[str, Any]]:
    """Liste aller bisherigen Automatik-Laeufe dieses Projekts (neueste
    zuletzt) - unabhaengig vom aktuellen Status, der nur den LETZTEN Lauf
    zeigt. Dient als dauerhaftes Protokoll ueber Nacht laufender Automatik-
    Durchgaenge (Datum, Status, Laufzeit, Zeitraum), siehe verlauf_eintrag_anhaengen()."""
    pfad = _automatik_verlauf_datei(projekt_root)
    if not pfad.exists():
        return []
    return json.loads(pfad.read_text(encoding="utf-8"))


def verlauf_eintrag_anhaengen(projekt_root: Path, eintrag: dict[str, Any]) -> None:
    eintraege = verlauf_lesen(projekt_root)
    eintraege.append(eintrag)
    pfad = _automatik_verlauf_datei(projekt_root)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(eintraege, ensure_ascii=False, indent=2), encoding="utf-8")


def zustand_zusammenfassen(status: dict[str, Any]) -> str | None:
    """Fasst den Status zu EINEM Wort fuer die Projektliste zusammen (siehe
    app/api/projects.py:_projekt_kurz), damit man ohne den Schreiben-Tab zu
    oeffnen sieht, ob ein ueber Nacht laufender Automatik-Lauf fertig ist
    und ob noch manuelle Nacharbeit noetig ist:
    - None: noch nie gestartet
    - "laeuft": aktuell aktiv
    - "fehler": abgebrochen mit Fehler
    - "gestoppt": per Benutzeranforderung angehalten, BEVOR alle Kapitel
      durchgelaufen sind - wie "fehler" per fortsetzbar() ueber den
      "Fortsetzen"-Button wieder aufnehmbar, siehe app/api/pipeline.py:
      _automatik_lauf. Bewusst NICHT unter "abgeschlossen_*" einsortiert,
      auch wenn das Protokoll bereits Eintraege enthaelt - sonst wuerde die
      Projektliste einen unterbrochenen, noch fortsetzbaren Lauf faelschlich
      als fertig anzeigen.
    - "abgeschlossen_mit_resten": fertig, aber Protokoll enthaelt
      uebersprungene Funde (Konflikt/nicht gefunden) oder unbekannte
      Woerter - manuelle Durchsicht im Tab "Pruefen & Anwenden" noetig, ODER
      per "Pruefung abschliessen"-Button (siehe reste_bestaetigen()) noch
      nicht als erledigt bestaetigt
    - "abgeschlossen_sauber": fertig, nichts uebrig (oder Reste wurden
      manuell als erledigt bestaetigt)"""
    if status.get("gestartet_am") is None:
        return None
    if status.get("laeuft"):
        return "laeuft"
    if status.get("fehler"):
        return "fehler"
    if not status.get("abgeschlossen"):
        return "gestoppt"
    if reste_vorhanden(status) and not status.get("resten_bestaetigt"):
        return "abgeschlossen_mit_resten"
    return "abgeschlossen_sauber"


def _aktuell_uebersprungene(status: dict[str, Any]) -> list[dict[str, Any]]:
    """Reduziert die "uebersprungen"-Eintraege auf den jeweils LETZTEN
    tatsaechlich gelaufenen Durchlauf pro Kapitel - ein Fund aus einem
    frueheren, laengst durch einen spaeteren Durchlauf desselben Kapitels
    ueberholten Zwischenstand zaehlt NICHT mehr als aktuell offen. Ohne das
    haeufte sich in status["protokoll"] (das ueber "Fortsetzen" hinweg
    dauerhaft waechst) bei jedem Kapitel mit mehreren Durchlaeufen fast immer
    mindestens ein Uebersprungen-Eintrag aus einem fruehen, seither sauber
    konvergierten Durchlauf an - reste_vorhanden() loeste dadurch auch dann
    aus, wenn im aktuellen Kapitelstand (und damit im Tab "Pruefen &
    Anwenden") gar nichts mehr offen war (Live-Fund 2026-09-02, "Das-Recht-
    des-Samurais": Kapitel 1/2 laengst sauber, zaehlten trotzdem mit).

    Der "letzte Durchlauf" wird primaer aus status["kapitel_letzter_
    durchlauf"] gelesen (von _automatik_lauf bei JEDEM Durchlauf aktualisiert,
    AUCH wenn dieser 0 Funde hatte) statt nur aus dem hoechsten im Protokoll
    VORKOMMENDEN Durchlauf - ein Durchlauf mit 0 Funden erzeugt naemlich
    UEBERHAUPT KEINEN protokoll_eintraege-Eintrag und waere sonst fuer diese
    Funktion unsichtbar (genau der Fall bei Kapitel 1 oben: Durchlauf 3 hatte
    0 Funde und konvergierte, ohne im Protokoll je aufzutauchen). Kapitel ohne
    Eintrag in kapitel_letzter_durchlauf (aeltere Status-Dateien) fallen auf
    den hoechsten im Protokoll vorkommenden Durchlauf zurueck; Eintraege ganz
    ohne Durchlauf-Feld werden konservativ komplett mitgezaehlt."""
    protokoll = status.get("protokoll", [])
    kapitel_letzter_durchlauf: dict[Any, int] = {}
    for kapitel_str, durchlauf in status.get("kapitel_letzter_durchlauf", {}).items():
        try:
            kapitel_letzter_durchlauf[int(kapitel_str)] = durchlauf
        except (TypeError, ValueError):
            kapitel_letzter_durchlauf[kapitel_str] = durchlauf

    # Fallback-Quelle, falls kapitel_letzter_durchlauf fuer ein Kapitel nichts
    # weiss (aeltere Status-Dateien): hoechster im Protokoll VORKOMMENDER
    # Durchlauf UEBER ALLE Arten hinweg (nicht nur "uebersprungen") - ein
    # Kapitel, das in Durchlauf 2 nur "angewendet"-Eintraege hatte, beweist
    # trotzdem, dass Durchlauf 2 stattfand und Durchlauf 1 damit ueberholt ist.
    hoechster_durchlauf: dict[Any, int | None] = {}
    for eintrag in protokoll:
        kapitel = eintrag.get("kapitel")
        durchlauf = eintrag.get("durchlauf")
        if durchlauf is None:
            hoechster_durchlauf[kapitel] = None
        else:
            bisher = hoechster_durchlauf.get(kapitel, -1)
            if bisher is not None and durchlauf > bisher:
                hoechster_durchlauf[kapitel] = durchlauf
    # kapitel_letzter_durchlauf ist die verlaesslichere Quelle, wo vorhanden -
    # ueberschreibt den rein aus dem Protokoll abgeleiteten (potenziell zu
    # alten) Wert.
    for kapitel, durchlauf in kapitel_letzter_durchlauf.items():
        hoechster_durchlauf[kapitel] = durchlauf

    return [
        eintrag for eintrag in protokoll
        if eintrag.get("art") == "uebersprungen"
        and (hoechster_durchlauf.get(eintrag.get("kapitel")) is None
             or eintrag.get("durchlauf") == hoechster_durchlauf.get(eintrag.get("kapitel")))
    ]


def reste_vorhanden(status: dict[str, Any]) -> bool:
    """True, wenn im Protokoll des letzten Laufs AKTUELL noch offene
    uebersprungene Funde (aus dem jeweils letzten Durchlauf eines Kapitels,
    siehe _aktuell_uebersprungene) oder unbekannte Woerter stehen - unabhaengig
    davon, ob das per "Pruefung abschliessen" (resten_bestaetigt) schon
    quittiert wurde. Siehe zustand_zusammenfassen() fuer die kombinierte
    Sicht, die BEIDES beruecksichtigt."""
    if _aktuell_uebersprungene(status):
        return True
    return any(
        eintrag.get("art") == "rechtschreibung" and eintrag.get("unbekannte_woerter")
        for eintrag in status.get("protokoll", [])
    )


# Ein "vorschlag" soll laut Pruefer-Persona (siehe app/data/personas/
# lektor.txt) NUR die korrigierte Fassung der zitierten "fundstelle" sein -
# kein allgemeiner Hinweis. In der Praxis rutscht dem Modell trotz dieser
# Anweisung gelegentlich ein Redaktionskommentar, ein unbeabsichtigt
# dupliziertes Textstueck oder eine woertliche Anweisung ("Ersetzen Sie...")
# als "vorschlag" durch. befunde_anwenden() prueft deshalb JEDEN Vorschlag
# vor dem Splicen gegen befunde_merge.vorschlag_verdaechtig() UND
# befunde_merge.vorschlag_dupliziert_kontext() - dieselben Pruefungen laufen
# bereits vorgelagert in app/api/pipeline.py beim Bauen der Roh-Funde (nullt
# den Vorschlag dort statt den Fund zu verwerfen), diese Pruefung hier ist
# ein zweites, unabhaengiges Sicherheitsnetz direkt vor dem eigentlichen
# Text-Splice.


def befunde_anwenden(text: str, befunde: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Wendet alle uebernehmbaren Funde auf `text` an - dieselbe Regel wie
    kannUebernommenWerden() im Frontend (befundReview.ts): ein Fund ist nur
    uebernehmbar, wenn er weder `konflikt` noch `nicht gefunden` ist. Statt
    Monacos live mitverschobenen Decorations zu nutzen, werden die
    betroffenen Funde nach `start` ABSTEIGEND sortiert und von hinten nach
    vorne eingefuegt - dadurch bleiben die vorher berechneten Offsets der
    noch nicht verarbeiteten Funde gueltig, unabhaengig von der
    Eingabe-Reihenfolge.

    Gibt den korrigierten Text und ein Protokoll zurueck, in dem JEDER Fund
    (angewendet oder uebersprungen samt Grund) auftaucht - fuer die
    Abschluss-Anzeige im Automatikmodus. Jeder Protokoll-Eintrag traegt
    zusaetzlich die `id` des zugehoerigen Eingabe-Funds (kann None sein, wenn
    `befunde` keine `id` mitbringt) - app/api/pipeline.py nutzt das, um nach
    dem Anwenden die Positionen der uebrig gebliebenen (uebersprungenen)
    Funde gegen den korrigierten Text neu zu verankern (siehe
    _kapitel_befunde_neu_verankern dort), statt sie mit inzwischen falschen
    Offsets aus befunde_NN.json stehen zu lassen."""
    anwendbar = []
    protokoll: list[dict[str, Any]] = []

    for befund in befunde:
        if befund.get("konflikt"):
            protokoll.append({
                "art": "uebersprungen", "grund": "konflikt", "id": befund.get("id"),
                "fundstelle": befund.get("fundstelle"), "vorschlag": befund.get("vorschlag"),
            })
            continue
        if not befund.get("gefunden") or befund.get("start") is None or befund.get("end") is None:
            protokoll.append({
                "art": "uebersprungen", "grund": "nicht_gefunden", "id": befund.get("id"),
                "fundstelle": befund.get("fundstelle"), "vorschlag": befund.get("vorschlag"),
            })
            continue
        if not befund.get("vorschlag"):
            protokoll.append({
                "art": "uebersprungen", "grund": "kein_vorschlag", "id": befund.get("id"),
                "fundstelle": befund.get("fundstelle"), "vorschlag": None,
            })
            continue
        if vorschlag_verdaechtig(befund.get("fundstelle") or "", befund["vorschlag"]):
            protokoll.append({
                "art": "uebersprungen", "grund": "verdaechtiger_vorschlag", "id": befund.get("id"),
                "fundstelle": befund.get("fundstelle"), "vorschlag": befund.get("vorschlag"),
            })
            continue
        if vorschlag_dupliziert_kontext(text, befund["start"], befund["end"], befund["vorschlag"]):
            protokoll.append({
                "art": "uebersprungen", "grund": "kontext_dupliziert", "id": befund.get("id"),
                "fundstelle": befund.get("fundstelle"), "vorschlag": befund.get("vorschlag"),
            })
            continue
        anwendbar.append(befund)

    # Absteigend nach start: von hinten nach vorne einfuegen, damit die
    # Offsets weiter vorne im Text fuer die naechste Iteration noch stimmen.
    anwendbar.sort(key=lambda b: b["start"], reverse=True)

    neuer_text = text
    for befund in anwendbar:
        start, end = befund["start"], befund["end"]
        neuer_text = neuer_text[:start] + befund["vorschlag"] + neuer_text[end:]
        protokoll.append({
            "art": "angewendet", "grund": None, "id": befund.get("id"),
            "fundstelle": befund.get("fundstelle"), "vorschlag": befund.get("vorschlag"),
        })

    return neuer_text, protokoll
