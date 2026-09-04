"""Verlauf der Titelbild-Versuche EINES Projekts (siehe ToDo.md) - protokolliert
jeden KI-generierten oder hochgeladenen Cover-Versuch mit Zeitstempel und
Prompt, damit der Nutzer zwischen mehreren Versuchen vor- und zurueckspringen
kann, statt einen frueheren, eigentlich besseren Versuch unwiderruflich durch
einen neuen zu ueberschreiben.

Reine Funktionen (kein I/O), analog zu app/core/fundus.py - die eigentliche
cover_log.json sowie die Bild-Kopien je Eintrag werden vom Aufrufer
(app/api/pipeline.py) ueber app/core/projekt_dateien.py gelesen/geschrieben.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CoverLogEintrag:
    id: str
    zeitpunkt: str  # ISO 8601, lokale Zeitzone (siehe jetzt_iso())
    herkunft: str  # "generiert" | "hochgeladen"
    prompt_deutsch: str = ""
    prompt_englisch: str = ""
    kommentar: str = ""


def neue_id() -> str:
    return uuid.uuid4().hex[:12]


def jetzt_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def leeres_log() -> tuple[list[CoverLogEintrag], None]:
    return [], None


def log_parsen(text: str) -> tuple[list[CoverLogEintrag], str | None]:
    """Liest cover_log.json - liefert (Eintraege in Speicherreihenfolge,
    aktive_id). Fehlt die Datei (leerer Text) oder ist sie beschaedigt, wird
    defensiv ein leeres Log geliefert statt eine Exception zu werfen - ein
    kaputtes Log soll das Anzeigen/Weiter-Generieren des Titelbilds nicht
    blockieren."""
    if not text.strip():
        return leeres_log()
    try:
        daten = json.loads(text)
    except json.JSONDecodeError:
        return leeres_log()

    eintraege = [
        CoverLogEintrag(
            id=e["id"],
            zeitpunkt=e.get("zeitpunkt", ""),
            herkunft=e.get("herkunft", "generiert"),
            prompt_deutsch=e.get("prompt_deutsch", ""),
            prompt_englisch=e.get("prompt_englisch", ""),
            kommentar=e.get("kommentar", ""),
        )
        for e in daten.get("eintraege", [])
        if "id" in e
    ]
    aktive_id = daten.get("aktive_id")
    return eintraege, aktive_id


def log_serialisieren(eintraege: list[CoverLogEintrag], aktive_id: str | None) -> str:
    daten = {
        "eintraege": [
            {
                "id": e.id,
                "zeitpunkt": e.zeitpunkt,
                "herkunft": e.herkunft,
                "prompt_deutsch": e.prompt_deutsch,
                "prompt_englisch": e.prompt_englisch,
                "kommentar": e.kommentar,
            }
            for e in eintraege
        ],
        "aktive_id": aktive_id,
    }
    return json.dumps(daten, ensure_ascii=False, indent=2)
