"""Findet die vom Pruefer zitierte "Fundstelle" als echten Zeichen-Bereich im
Kapiteltext - notwendig, damit das Frontend den Fund direkt im editierbaren
Text farbig markieren kann (siehe BefundEditor.tsx) und damit
befunde_merge.py ueberlappende Funde ueberhaupt erkennen kann.

Ein LLM zitiert nicht immer zeichengenau: unterschiedliche Anfuehrungszeichen,
kollabierter Whitespace oder eine leichte Umformulierung sind haeufig. Daher
drei Stufen, von exakt zu tolerant, und ein expliziter "nicht gefunden"-Fall
statt eines geratenen Bereichs.
"""
from __future__ import annotations

import difflib
import re

# Gerade und typografische Anfuehrungszeichen/Apostrophe sollen als
# gleichwertig gelten, weil das LLM beim Zitieren oft die eine durch die
# andere Form ersetzt.
_ANFUEHRUNGSZEICHEN = {
    '"': '["„“”]',
    "'": "['‘’‚]",
    "„": '["„“”]',
    "“": '["„“”]',
    "”": '["„“”]',
}

_FUZZY_SCHWELLE = 0.6


def _tolerantes_muster(zitat: str) -> re.Pattern[str]:
    teile: list[str] = []
    for zeichen in zitat:
        if zeichen.isspace():
            if not teile or teile[-1] != r"\s+":
                teile.append(r"\s+")
        elif zeichen in _ANFUEHRUNGSZEICHEN:
            teile.append(_ANFUEHRUNGSZEICHEN[zeichen])
        else:
            teile.append(re.escape(zeichen))
    return re.compile("".join(teile))


def finde_fundstelle(text: str, zitat: str) -> tuple[int, int] | None:
    """Liefert (start, end) als Zeichen-Offsets in `text`, oder None, wenn
    sich das Zitat auch tolerant/fuzzy nicht zuordnen laesst."""
    zitat = zitat.strip()
    if not zitat:
        return None

    # 1) Exakter Substring-Treffer.
    pos = text.find(zitat)
    if pos != -1:
        return pos, pos + len(zitat)

    # 2) Tolerantes Muster: Whitespace kollabiert, Anfuehrungszeichen als
    #    Zeichenklasse - deckt die haeufigsten woertlichen Abweichungen ab,
    #    ohne auf eine reine Aehnlichkeits-Heuristik zurueckfallen zu muessen.
    treffer = _tolerantes_muster(zitat).search(text)
    if treffer:
        return treffer.start(), treffer.end()

    # 3) Satzweiser Fuzzy-Abgleich fuer freier umformulierte Zitate: den Satz
    #    mit der hoechsten Aehnlichkeit zum Zitat suchen, ab einer
    #    Mindest-Aehnlichkeit dessen Bereich zurueckgeben.
    bester_bereich: tuple[int, int] | None = None
    beste_note = 0.0
    for satz_treffer in re.finditer(r"[^.!?\n]+[.!?]?", text):
        satz = satz_treffer.group()
        if not satz.strip():
            continue
        note = difflib.SequenceMatcher(None, satz, zitat).ratio()
        if note > beste_note:
            beste_note = note
            bester_bereich = (satz_treffer.start(), satz_treffer.end())

    if bester_bereich and beste_note >= _FUZZY_SCHWELLE:
        return bester_bereich

    return None
