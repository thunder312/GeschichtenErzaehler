"""Text aus einer PDF-Datei lesen (Analysator: "Datei laden" akzeptiert auch
.pdf). pypdf liefert den Text zeilenweise so, wie er im PDF umbrochen ist -
Absatzgrenzen gehen dabei verloren. rekonstruieren() baut daraus wieder
Absaetze (getrennt durch Leerzeilen), damit app/core/analysator.py:vorbereiten
(Fuelltext, Kapitelueberschriften, Absatz-Gruppierung) damit arbeiten kann.

Reine Text-PDFs. Gescannte PDFs (nur Bilder) enthalten keinen Text - das ist
ein Fehler mit klarer Meldung, kein OCR."""
from __future__ import annotations

import io
import re
from collections import Counter
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_BYTES = 30 * 1024 * 1024
MAX_SEITEN = 1500


class PdfFehler(Exception):
    pass


@dataclass
class PdfText:
    text: str
    seiten: int


_LIGATUREN = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "­": "", "\x00": ""}
_SEITENZAHL = re.compile(r"^\s*(?:[-–—]?\s*\d{1,4}\s*[-–—]?|(?:page|seite)\s+\d+(?:\s+(?:of|von)\s+\d+)?)\s*$", re.IGNORECASE)
_SATZENDE = re.compile(r"[.!?…\"”’»)]\s*$")


def _zeilen_normalisieren(seite: str) -> list[str]:
    for alt, neu in _LIGATUREN.items():
        seite = seite.replace(alt, neu)
    zeilen = [re.sub(r"[ \t ]+", " ", z).strip() for z in seite.replace("\r\n", "\n").split("\n")]
    return zeilen


def _kopf_fusszeilen_entfernen(seiten: list[list[str]]) -> list[list[str]]:
    """Entfernt reine Seitenzahlen und Zeilen, die (Ziffern ignoriert) auf
    mindestens 40 % der Seiten (min. 4 Seiten) wiederkehren, z.B. laufende
    Kopf-/Fusszeilen."""
    if not seiten:
        return seiten
    zaehler: Counter[str] = Counter()
    for zeilen in seiten:
        belegt = {re.sub(r"\d+", "#", z) for z in zeilen[:3] + zeilen[-3:] if z and len(z) <= 90}
        zaehler.update(belegt)
    schwelle = max(4, int(len(seiten) * 0.4))
    wiederkehrend = {z for z, n in zaehler.items() if n >= schwelle and len(seiten) >= 4}
    ergebnis = []
    for zeilen in seiten:
        ergebnis.append([
            z for z in zeilen
            if not _SEITENZAHL.match(z) and re.sub(r"\d+", "#", z) not in wiederkehrend
        ])
    return ergebnis


def rekonstruieren(zeilen: list[str], ueberschrift: re.Pattern[str] | None = None) -> str:
    """Fasst umbrochene Zeilen wieder zu Absaetzen zusammen. Eine Zeile gehoert
    zur naechsten, wenn die naechste klein beginnt ODER die Zeile fast die volle
    Textbreite hat (90. Perzentil der Zeilenlaengen); eine deutlich kuerzere Zeile
    beendet den Absatz. Leerzeilen im PDF-Text und Kapitelueberschriften
    (`ueberschrift`) beenden den Absatz immer."""
    laengen = sorted(len(z) for z in zeilen if z)
    if not laengen:
        return ""
    breit = laengen[int(len(laengen) * 0.9)] or 1
    absaetze: list[str] = []
    aktuell: list[str] = []

    def abschliessen() -> None:
        if aktuell:
            absaetze.append(" ".join(aktuell))
            aktuell.clear()

    vorige = ""
    for z in zeilen:
        if not z:
            abschliessen()
            vorige = ""
            continue
        if ueberschrift is not None and ueberschrift.fullmatch(z):
            abschliessen()
            absaetze.append(z)
            vorige = ""
            continue
        if aktuell:
            fortsetzung = z[0].islower() or z[0].isdigit() or len(vorige) >= 0.85 * breit
            if not fortsetzung:
                abschliessen()
        if aktuell and aktuell[-1].endswith("-") and z[:1].islower():
            aktuell[-1] = aktuell[-1] + z  # Silbentrennung am Zeilenende
        else:
            aktuell.append(z)
        vorige = z
    abschliessen()
    return "\n\n".join(absaetze)


def pdf_text_extrahieren(daten: bytes, ueberschrift: re.Pattern[str] | None = None) -> PdfText:
    if len(daten) > MAX_BYTES:
        raise PdfFehler(f"Die PDF-Datei ist zu groß (mehr als {MAX_BYTES // (1024 * 1024)} MB).")
    try:
        leser = PdfReader(io.BytesIO(daten))
        if leser.is_encrypted and not leser.decrypt(""):
            raise PdfFehler("Die PDF-Datei ist passwortgeschützt.")
        if len(leser.pages) > MAX_SEITEN:
            raise PdfFehler(f"Die PDF-Datei hat zu viele Seiten (mehr als {MAX_SEITEN}).")
        seiten = [_zeilen_normalisieren(s.extract_text() or "") for s in leser.pages]
    except PdfFehler:
        raise
    except (PdfReadError, ValueError, KeyError, OSError, NotImplementedError) as e:
        raise PdfFehler(f"Die PDF-Datei konnte nicht gelesen werden: {e}") from e

    zeilen = [z for s in _kopf_fusszeilen_entfernen(seiten) for z in s]
    text = rekonstruieren(zeilen, ueberschrift)
    if len(text.split()) < 30:
        raise PdfFehler(
            "In der PDF-Datei wurde (fast) kein Text gefunden - vermutlich ein Scan aus Bildern. "
            "Texterkennung (OCR) wird nicht unterstützt."
        )
    return PdfText(text=text, seiten=len(seiten))
