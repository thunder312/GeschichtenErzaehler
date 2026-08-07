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
import time

_ERSTE_FRAGE_MUSTER = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)

_AUSGANGSLAGE_MUSTER = re.compile(
    r"##\s*Ausgangslage\s+vor\s+Kapitel\s+eins\s*\n(.*?)(?=\n##\s|\Z)",
    re.IGNORECASE | re.DOTALL,
)

_FIGUREN_MUSTER = re.compile(
    r"^##[ \t]*Figuren[ \t]*\n(.*?)(?=\n##[ \t]|\Z)",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
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


def verlauf_gekuerzt_ab(verlauf: list[str], bearbeite_ab: int) -> list[str] | None:
    """"Schritte zurueckgehen" bzw. eine fruehere Antwort bearbeiten: kuerzt
    den Verlauf auf den Stand VOR der
    eigenen Antwort an Frontend-Index `bearbeite_ab` (siehe ArchitektInterviewPage.tsx:
    Index in `nachrichten`, das den synthetischen ersten Verlauf-Eintrag und
    die noch offene letzte Frage NICHT mitzaehlt, siehe dortiger Kommentar zu
    "fortgesetzt"). Alle danach gestellten Fragen/Antworten werden verworfen,
    der Aufrufer haengt die bearbeitete Antwort selbst wieder an (per _zug()) -
    das genuegt, damit der Architekt beim naechsten Zug die naechste Frage
    zwangslaeufig neu stellt, ohne dass die Persona einen Sonderfall dafuer
    braucht (siehe Modul-Kommentar oben: jeder Zug bekommt ohnehin den
    kompletten Verlauf neu geschickt).
    None bei ungueltigem Index (ausserhalb des Bereichs, oder zeigt nicht auf
    eine eigene "Ich: "-Antwort) - der Aufrufer muss das als Fehler behandeln,
    NICHT den Verlauf trotzdem veraendern."""
    if bearbeite_ab < 0:
        return None
    ziel_index = bearbeite_ab + 1  # +1: synthetischer erster Verlauf-Eintrag
    if not (0 <= ziel_index < len(verlauf)) or not verlauf[ziel_index].startswith("Ich: "):
        return None
    return verlauf[:ziel_index]


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


def figuren_abschnitt_erkennen(geruest: str) -> str | None:
    """Extrahiert '## Figuren' aus dem fertigen Geruest (siehe app/api/
    architekt.py: fertig-Branch von ws_architekt) - Grundlage fuer den
    automatischen Personen-Fundus-Abgleich (app/core/fundus.py). Bewusst
    NUR die oberste '## Figuren'-Ueberschrift, nicht die gleichnamige
    '### Figuren'-Unterueberschrift unter '## Ausgangslage vor Kapitel eins'
    (die beschreibt Zustaende zu Geschichtenbeginn, keine Figurenstammdaten).
    None, wenn der Abschnitt fehlt."""
    treffer = _FIGUREN_MUSTER.search(geruest)
    if not treffer:
        return None
    inhalt = treffer.group(1).strip()
    return inhalt or None


def transkript_erzeugen(verlauf: list[str]) -> str:
    """Baut aus dem internen Verlauf ("Ich: ..."/"Du: ..." - die Perspektive,
    aus der die Persona angesprochen wird) ein lesbares Markdown-Protokoll
    des gesamten Architekten-Gespraechs, fuer spaetere Referenz im Projekt
    (siehe app/api/architekt.py - wird bei erfolgreichem Abschluss als
    projekt/architekten_gespraech.md gespeichert)."""
    zeilen = [
        "# Architekten-Gespräch",
        "",
        f"Erzeugt: {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
    ]
    for eintrag in verlauf:
        if eintrag.startswith("Ich: "):
            zeilen.append(f"**Nutzer:** {eintrag[len('Ich: '):]}")
        elif eintrag.startswith("Du: "):
            zeilen.append(f"**Architekt:** {eintrag[len('Du: '):]}")
        else:
            zeilen.append(eintrag)
        zeilen.append("")
    return "\n".join(zeilen).rstrip() + "\n"
