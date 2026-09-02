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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas import Befund

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


def befunde_neu_verankern(text: str, befunde: list["Befund"]) -> list["Befund"]:
    """Sucht fuer JEDEN uebergebenen Fund per finde_fundstelle() seine
    (ggf. verschobene) Position im gegebenen `text` neu - fuer Faelle, in
    denen `text` inzwischen an einer FRUEHEREN Stelle veraendert wurde (z.B.
    ein anderer Fund im selben Kapitel wurde uebernommen und hat den Text
    verschoben), sodass der urspruenglich gespeicherte start/end nicht mehr
    stimmt, das Zitat selbst (`fundstelle`) aber unveraendert ist. Wird
    NICHT gefunden, wird der Fund auf `gefunden=False`/start=end=None
    gesetzt statt verworfen - das Frontend zeigt ihn dann weiterhin in der
    Liste, nur ohne Editor-Decoration (siehe befundReview.ts).

    Gemeinsam genutzt von app/api/pipeline.py (Automatikmodus, nach jedem
    Anwenden von Korrekturen) und app/api/projects.py (Mobil-Ansicht, nach
    dem serverseitigen Uebernehmen EINES einzelnen Funds) - siehe
    app/api/pipeline.py:_kapitel_befunde_neu_verankern fuer den Vorfall
    (2026-09-02), der diese Funktion noetig machte: ohne Neuverankerung
    verschwinden noch offene Funde nach dem Uebernehmen anderer Funde
    unsichtbar aus "Pruefen & Anwenden" (Anker-Check haelt sie faelschlich
    fuer "verwaist")."""
    neu = []
    for befund in befunde:
        stelle = finde_fundstelle(text, befund.fundstelle)
        neu.append(befund.model_copy(update={
            "start": stelle[0] if stelle else None,
            "end": stelle[1] if stelle else None,
            "gefunden": stelle is not None,
        }))
    return neu
