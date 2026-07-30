"""Fuehrt die Funde der beiden PARALLEL laufenden Pruefer-Rollen
("anachronismus"/"stimmigkeit" aus der Rolle "anachronismus", "kontinuitaet"
aus der gleichnamigen Rolle) deterministisch zusammen - ohne weiteren
KI-Aufruf, wie vom Nutzer gewuenscht. Zwei Funde, deren Fundstellen im
Kapiteltext ueberlappen, werden zu EINEM Eintrag mit mehreren Kategorie-Tags
zusammengefuehrt; stimmen ihre Vorschlaege nicht ueberein, wird der Eintrag
als Konflikt markiert statt einen der beiden Vorschlaege zu bevorzugen.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RoherBefund:
    kategorie: str  # "anachronismus" | "stimmigkeit" | "kontinuitaet"
    fundstelle: str
    beschreibung: str
    sicherheit: str | None  # nur bei anachronismus/stimmigkeit gesetzt
    vorschlag: str | None
    start: int | None
    end: int | None


_SICHERHEIT_RANG = {"hoch": 2, "mittel": 1, "gering": 0}


def _normalisiert(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def _hoechste_sicherheit(werte: list[str | None]) -> str | None:
    vorhandene = [w for w in werte if w]
    if not vorhandene:
        return None
    return max(vorhandene, key=lambda w: _SICHERHEIT_RANG.get(w, -1))


def befunde_zusammenfuehren(kapiteltext: str, roh_befunde: list[RoherBefund]) -> list[dict]:
    gefunden = sorted(
        (b for b in roh_befunde if b.start is not None), key=lambda b: b.start,
    )
    nicht_gefunden = [b for b in roh_befunde if b.start is None]

    cluster: list[list[RoherBefund]] = []
    aktuelles_ende = -1
    for befund in gefunden:
        if cluster and befund.start < aktuelles_ende:
            cluster[-1].append(befund)
            aktuelles_ende = max(aktuelles_ende, befund.end)
        else:
            cluster.append([befund])
            aktuelles_ende = befund.end

    ergebnisse: list[dict] = []
    zaehler = 0

    for gruppe in cluster:
        zaehler += 1
        start = min(b.start for b in gruppe)
        end = max(b.end for b in gruppe)
        kategorien: list[str] = []
        for b in gruppe:
            if b.kategorie not in kategorien:
                kategorien.append(b.kategorie)

        vorschlaege = [(b.kategorie, b.vorschlag) for b in gruppe if b.vorschlag]
        distinct = {_normalisiert(v) for _, v in vorschlaege}
        konflikt = len(distinct) > 1
        vorschlag = None if konflikt else (vorschlaege[0][1] if vorschlaege else None)
        konflikt_vorschlaege = (
            [{"quelle": q, "text": v} for q, v in vorschlaege] if konflikt else None
        )

        ergebnisse.append({
            "id": f"b{zaehler}",
            "kategorien": kategorien,
            "fundstelle": kapiteltext[start:end],
            "beschreibungen": [{"quelle": b.kategorie, "text": b.beschreibung} for b in gruppe],
            "sicherheit": _hoechste_sicherheit([b.sicherheit for b in gruppe]),
            "vorschlag": vorschlag,
            "konflikt": konflikt,
            "konflikt_vorschlaege": konflikt_vorschlaege,
            "gefunden": True,
            "start": start,
            "end": end,
        })

    for b in nicht_gefunden:
        zaehler += 1
        ergebnisse.append({
            "id": f"b{zaehler}",
            "kategorien": [b.kategorie],
            "fundstelle": b.fundstelle,
            "beschreibungen": [{"quelle": b.kategorie, "text": b.beschreibung}],
            "sicherheit": b.sicherheit,
            "vorschlag": b.vorschlag,
            "konflikt": False,
            "konflikt_vorschlaege": None,
            "gefunden": False,
            "start": None,
            "end": None,
        })

    return ergebnisse
