"""Architekten-Interview - portiert aus pre-GUI/novelle.py (cmd_architekt).

Anders als bei den anderen Rollen ist das ein echtes Mehrschritt-Gespraech:
Bei jedem Zug wird der KOMPLETTE bisherige Verlauf (als eingebetteter Text,
"Ich: ..." / "Du: ...") als eine einzelne User-Nachricht an die Rolle
'architekt' geschickt - keine strukturierte messages-Liste, sondern exakt
das Format, das die Architekt-Persona bereits aus dem CLI kennt und auf das
sie mit ihrer Ein-Frage-pro-Antwort-Regel trainiert/instruiert ist.
"""
from __future__ import annotations

import re

_ERSTE_FRAGE_MUSTER = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)

_AUSGANGSLAGE_MUSTER = re.compile(
    r"##\s*Ausgangslage\s+vor\s+Kapitel\s+eins\s*\n(.*?)(?=\n##\s|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def nur_erste_frage(antwort: str) -> str:
    """Die Architekten-Persona soll laut ihrer Anweisung nur eine Frage pro
    Nachricht stellen. Ein 8B-Modell haelt sich daran nicht zuverlaessig und
    packt gelegentlich mehrere nummerierte Fragen in eine Antwort - schneidet
    alles ab der zweiten nummerierten Frage ab, damit garantiert nur eine
    Frage angezeigt wird. Wird NICHT auf das fertige Story-Geruest angewandt
    (das hat selbst nummerierte Listen, z.B. den Kapitelplan, die nicht
    faelschlich abgeschnitten werden duerfen)."""
    treffer = list(_ERSTE_FRAGE_MUSTER.finditer(antwort))
    if len(treffer) < 2:
        return antwort
    grenze = treffer[1].start()
    return antwort[:grenze].rstrip()


def ist_geruest_antwort(antwort: str) -> bool:
    """Das fertige Geruest ist das definierte Endsignal der Architekt-
    Persona: sobald eine Antwort mit '# STORY-GERUEST' beginnt, ist das
    Gespraech inhaltlich abgeschlossen und wird nicht mehr gekuerzt."""
    return bool(re.match(r"\s*#\s*STORY-GERUEST", antwort, re.IGNORECASE))


def verlauf_zu_text(verlauf: list[str]) -> str:
    return "\n\n".join(verlauf)


def ausgangslage_erkennen(geruest: str) -> str | None:
    """Extrahiert '## Ausgangslage vor Kapitel eins' aus dem fertigen
    Geruest, falls die Architekt-Persona ihn produziert hat. Wird zu
    stand_00.md, damit Kapitel eins auf einer echten Szenerie aufbaut statt
    auf einem toten Platzhalter. None, wenn der Abschnitt fehlt - dann
    bleibt stand_00.md schlicht ungeschrieben (korrekter Normalfall)."""
    treffer = _AUSGANGSLAGE_MUSTER.search(geruest)
    if not treffer:
        return None
    inhalt = treffer.group(1).strip()
    return inhalt or None
