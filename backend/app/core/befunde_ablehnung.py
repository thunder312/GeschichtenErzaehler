"""Dauerhaftes Ablehnen einzelner Pruefer-Funde (Button "Ablehnen" im Tab
"Pruefen & Anwenden", parallel zu "Uebernehmen") - der Nutzer kann z.B. eine
in einer FanFic-Epoche bewusst gewuenschte Kanon-Abweichung (andere Figuren/
Orte als im Original, etwa "Deutschland statt England" bei "Harry Potter")
ein fuer alle Mal als "kein Fehler" markieren, statt bei jeder erneuten
Pruefung desselben Kapitels erneut denselben Hinweis wegklicken zu muessen.

Ein abgelehnter Fund wird ueber (Kategorie, normalisierte Fundstelle)
identifiziert - NICHT ueber seine id, die befunde_merge.py bei jedem
Pruef-Lauf pro Kapitel neu ab "b1" vergibt und die sich daher zwischen zwei
Laeufen nicht wiederverwenden laesst. Die Fundstelle selbst ist dagegen ein
deterministisches Substring des Kapiteltexts (kapiteltext[start:end]) und
bleibt exakt gleich, solange sich der Text an dieser Stelle nicht aendert -
ein stabiler Schluessel fuer "genau diese Textstelle, genau dieses
Fehlerbild, will der Nutzer nicht mehr sehen"."""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from app.core import projekt_dateien as pd

if TYPE_CHECKING:
    from app.core.befunde_merge import RoherBefund


def _normalisiert(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def lesen(projekt: Path) -> list[dict]:
    datei = pd.abgelehnte_befunde_datei(projekt)
    if not datei.exists():
        return []
    try:
        return json.loads(datei.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def hinzufuegen(projekt: Path, kategorien: list[str], fundstelle: str) -> None:
    """Merkt sich (Kategorie, Fundstelle) fuer JEDE der uebergebenen
    Kategorien einzeln vor - ein aus mehreren Pruefer-Rollen zusammen-
    gefuehrter Fund (siehe befunde_merge.py:befunde_zusammenfuehren) soll
    nur fuer die Kategorien kuenftig unterdrueckt werden, die ihn
    tatsaechlich gemeldet haben, nicht pauschal fuer die Fundstelle."""
    fundstelle_norm = _normalisiert(fundstelle)
    if not fundstelle_norm:
        return
    bestehende = lesen(projekt)
    vorhanden = {(e.get("kategorie"), e.get("fundstelle")) for e in bestehende}
    geaendert = False
    for kategorie in kategorien:
        schluessel = (kategorie, fundstelle_norm)
        if schluessel in vorhanden:
            continue
        bestehende.append({"kategorie": kategorie, "fundstelle": fundstelle_norm})
        vorhanden.add(schluessel)
        geaendert = True
    if not geaendert:
        return
    datei = pd.abgelehnte_befunde_datei(projekt)
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(json.dumps(bestehende, ensure_ascii=False, indent=2), encoding="utf-8")


# Ein per "Ablehnen" gespeicherter Fund stammt aus dem bereits ZUSAMMEN-
# GEFUEHRTEN befunde_{n}.json (siehe befunde_merge.py:befunde_zusammen
# fuehren) - dessen Fundstelle ist bei einem aus mehreren Pruefer-Rollen
# geclusterten Fund die UNION-Spanne aller beteiligten Roh-Funde, nicht
# zwingend identisch mit dem Zitat, das eine einzelne Rolle beim naechsten
# Lauf fuer sich allein (ohne den Cluster-Partner) meldet. Ein reiner
# Gleichheitsvergleich wuerde solche Faelle beim naechsten Pruef-Lauf nicht
# mehr erkennen. Da roh_befunde die Original-Zitate vor dem Merge nicht
# mehr vorliegen (nur das fertig gemergte JSON wird dauerhaft gespeichert),
# reicht ein Enthaltensein-Vergleich in beide Richtungen als Naeherung -
# mit einer Mindestlaenge, damit nicht schon ein einzelnes gemeinsames Wort
# faelschlich als Treffer zaehlt.
_MINDESTLAENGE_ENTHALTEN = 8


def ist_abgelehnt(abgelehnte: list[dict], kategorie: str, fundstelle: str) -> bool:
    fundstelle_norm = _normalisiert(fundstelle)
    if len(fundstelle_norm) < _MINDESTLAENGE_ENTHALTEN:
        return False
    for eintrag in abgelehnte:
        if eintrag.get("kategorie") != kategorie:
            continue
        eintrag_norm = eintrag.get("fundstelle") or ""
        if len(eintrag_norm) < _MINDESTLAENGE_ENTHALTEN:
            continue
        if eintrag_norm in fundstelle_norm or fundstelle_norm in eintrag_norm:
            return True
    return False


def herausfiltern(projekt: Path, roh_befunde: list["RoherBefund"]) -> list["RoherBefund"]:
    """Entfernt aus `roh_befunde` jeden Eintrag, dessen (Kategorie,
    Fundstelle) bereits abgelehnt wurde - VOR dem Zusammenfuehren zu
    Befund-Clustern (befunde_merge.py:befunde_zusammenfuehren), damit ein
    abgelehnter Fund nicht doch wieder mit einem anderen, noch offenen Fund
    an derselben Textstelle zu einem gemeinsamen Merge-Eintrag verschmilzt."""
    abgelehnte = lesen(projekt)
    if not abgelehnte:
        return roh_befunde
    return [b for b in roh_befunde if not ist_abgelehnt(abgelehnte, b.kategorie, b.fundstelle)]
