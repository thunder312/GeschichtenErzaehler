"""Orte-Fundus: benutzerweite, nach Epoche gegliederte Sammlung wieder-
verwendbarer Schauplaetze mit Beschreibung - kann beim Ausfuellen des
Kapitelplans (Feld "Ort", siehe frontend/src/components/KapitelplanEditor.tsx)
ausgewaehlt werden, analog zum Personen-Fundus (siehe app/core/fundus.py).

Reine Funktionen (kein I/O), analog zu app/core/fundus.py. Anders als dort
gibt es hier KEINE automatische Extraktion/Zusammenfuehrung aus abgeschlossenen
Geschichten - Orte werden ausschliesslich manuell gepflegt (siehe
app/api/orte.py), das Datenmodell ist deshalb bewusst schlanker (nur ein
Feld "Beschreibung" statt der acht Felder einer Figur)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.fundus import feldwert_einzeilig

_VORLAGE = '''<!--
ORTE-VORLAGE — bitte diesen Kommentarblock nicht löschen.

Neuen Ort manuell anlegen: unter der passenden "## <Epoche>"-Überschrift
einen Block in genau diesem Format einfügen:

### Marktplatz von Rothenfeld
- Beschreibung: Belebter Platz im Herzen der Stadt, umgeben von
  Fachwerkhäusern und Marktständen, an Markttagen laut und voller Menschen.

Eine neue Epoche bekommt automatisch eine eigene "## <Epoche>"-Überschrift
beim ersten Ort.
-->
'''

_ERSTE_EPOCHE_MUSTER = re.compile(r"^##[ \t]", re.MULTILINE)
_ORT_BLOCK_MUSTER = r"^###[ \t]+.+?\n(?:(?!^###[ \t]|^##[ \t]).*\n?)*"
_BESCHREIBUNG_ZEILE_MUSTER = re.compile(r"^-\s*Beschreibung:\s*(.*)$", re.IGNORECASE | re.MULTILINE)


def leere_vorlage() -> str:
    return _VORLAGE


def kopf_kommentar_extrahieren(orte_text: str) -> str:
    """Siehe app/core/fundus.py:kopf_kommentar_extrahieren - identische Logik,
    hier separat gehalten, da beide Fundus-Arten unabhaengige Dateien/Formate
    sind."""
    treffer = _ERSTE_EPOCHE_MUSTER.search(orte_text)
    if not treffer:
        return orte_text if orte_text.strip() else leere_vorlage()
    return orte_text[: treffer.start()]


@dataclass
class Ort:
    epoche: str
    name: str
    beschreibung: str


def ort_block_erzeugen(ort: Ort) -> str:
    return f"### {ort.name}\n- Beschreibung: {feldwert_einzeilig(ort.beschreibung)}\n"


def _ort_bloecke_mit_namen(abschnitt_text: str) -> list[tuple[str, str]]:
    ergebnis: list[tuple[str, str]] = []
    for treffer in re.finditer(_ORT_BLOCK_MUSTER, abschnitt_text, re.MULTILINE):
        block = treffer.group(0)
        kopf = block.splitlines()[0]
        name = kopf.lstrip("#").strip()
        ergebnis.append((name, block))
    return ergebnis


def orte_parsen(orte_text: str) -> list[Ort]:
    """Zerlegt die gesamte orte.md (ohne den einleitenden Kopf-Kommentar) in
    eine flache, geordnete Liste aller Orte ueber alle Epochen hinweg - siehe
    app/core/fundus.py:fundus_parsen fuer dasselbe Muster bei Figuren."""
    treffer = _ERSTE_EPOCHE_MUSTER.search(orte_text)
    if not treffer:
        return []
    rumpf = orte_text[treffer.start():]

    ergebnis: list[Ort] = []
    epochen_treffer = list(re.finditer(r"^##[ \t]+(.+?)[ \t]*$", rumpf, re.MULTILINE))
    for i, epoche_treffer in enumerate(epochen_treffer):
        epoche = epoche_treffer.group(1).strip()
        ende = epochen_treffer[i + 1].start() if i + 1 < len(epochen_treffer) else len(rumpf)
        abschnitt = rumpf[epoche_treffer.end():ende]
        for name, block in _ort_bloecke_mit_namen(abschnitt):
            treffer_beschreibung = _BESCHREIBUNG_ZEILE_MUSTER.search(block)
            beschreibung = treffer_beschreibung.group(1).strip() if treffer_beschreibung else ""
            ergebnis.append(Ort(epoche=epoche, name=name, beschreibung=beschreibung))
    return ergebnis


def orte_serialisieren(orte: list[Ort]) -> str:
    """Baut eine komplette orte.md aus einer flachen Orte-Liste neu auf - ohne
    den Kopf-Kommentar (der bleibt beim Aufrufer erhalten, siehe
    app/api/orte.py). Epochen erscheinen in der Reihenfolge ihres ERSTEN
    Auftretens, Orte innerhalb einer Epoche in Listenreihenfolge."""
    epochen: dict[str, list[Ort]] = {}
    for ort in orte:
        epochen.setdefault(ort.epoche, []).append(ort)

    abschnitte = []
    for epoche, orte_in_epoche in epochen.items():
        bloecke = [ort_block_erzeugen(ort) for ort in orte_in_epoche]
        abschnitte.append(f"## {epoche}\n\n" + "\n".join(bloecke))
    return "\n".join(abschnitte).rstrip("\n") + "\n"
