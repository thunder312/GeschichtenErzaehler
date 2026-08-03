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

import json
from pathlib import Path
from typing import Any

AUTOMATIK_STATUS_DATEINAME = "automatik_status.json"
AUTOMATIK_VERLAUF_DATEINAME = "automatik_verlauf.json"


def _automatik_status_datei(projekt_root: Path) -> Path:
    return projekt_root / "projekt" / AUTOMATIK_STATUS_DATEINAME


def _automatik_verlauf_datei(projekt_root: Path) -> Path:
    return projekt_root / "projekt" / AUTOMATIK_VERLAUF_DATEINAME


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
        }
    status = json.loads(pfad.read_text(encoding="utf-8"))
    status.setdefault("aktueller_durchlauf", None)
    status.setdefault("resten_bestaetigt", False)
    # Erst mit den 502/503-Retries (siehe app/api/pipeline.py:
    # _automatik_mit_retry) eingefuehrt - setdefault fuer Status-Dateien
    # aelterer, noch laufender/pausierter Automatik-Laeufe.
    status.setdefault("fehler_schritt", None)
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


def reste_vorhanden(status: dict[str, Any]) -> bool:
    """True, wenn das Protokoll des letzten Laufs uebersprungene Funde
    (Konflikt/nicht gefunden) oder unbekannte Woerter enthaelt - unabhaengig
    davon, ob das per "Pruefung abschliessen" (resten_bestaetigt) schon
    quittiert wurde. Siehe zustand_zusammenfassen() fuer die kombinierte
    Sicht, die BEIDES beruecksichtigt."""
    return any(
        eintrag.get("art") == "uebersprungen"
        or (eintrag.get("art") == "rechtschreibung" and eintrag.get("unbekannte_woerter"))
        for eintrag in status.get("protokoll", [])
    )


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
    Abschluss-Anzeige im Automatikmodus."""
    anwendbar = []
    protokoll: list[dict[str, Any]] = []

    for befund in befunde:
        if befund.get("konflikt"):
            protokoll.append({
                "art": "uebersprungen", "grund": "konflikt",
                "fundstelle": befund.get("fundstelle"), "vorschlag": befund.get("vorschlag"),
            })
            continue
        if not befund.get("gefunden") or befund.get("start") is None or befund.get("end") is None:
            protokoll.append({
                "art": "uebersprungen", "grund": "nicht_gefunden",
                "fundstelle": befund.get("fundstelle"), "vorschlag": befund.get("vorschlag"),
            })
            continue
        if not befund.get("vorschlag"):
            protokoll.append({
                "art": "uebersprungen", "grund": "kein_vorschlag",
                "fundstelle": befund.get("fundstelle"), "vorschlag": None,
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
            "art": "angewendet", "grund": None,
            "fundstelle": befund.get("fundstelle"), "vorschlag": befund.get("vorschlag"),
        })

    return neuer_text, protokoll
