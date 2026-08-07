"""Fuehrt die Funde der beiden PARALLEL laufenden Pruefer-Rollen
("anachronismus"/"stimmigkeit" aus der Rolle "anachronismus", "kontinuitaet"
aus der gleichnamigen Rolle) deterministisch zusammen - ohne weiteren
KI-Aufruf, wie vom Nutzer gewuenscht. Zwei Funde, deren Fundstellen im
Kapiteltext ueberlappen, werden zu EINEM Eintrag mit mehreren Kategorie-Tags
zusammengefuehrt; stimmen ihre Vorschlaege nicht ueberein, wird der Eintrag
als Konflikt markiert statt einen der beiden Vorschlaege zu bevorzugen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Bereits einmal ("Die-Schwerkraft-der-Erinnerung.md"-Vorfall) UND ein
# zweites Mal ("Schatten-ueber-Luxor...md") bewaehrter Filter gegen zwei
# verwandte, aber verschiedene Fehlerbilder eines Pruefer-"vorschlag": ein
# liegen gebliebener
# Redaktionskommentar/dupliziertes Textfragment (viel laenger als die
# fundstelle - Laengen-Heuristik) ODER eine woertliche Anweisung ANS SCHREIB-
# BZW. PRUEF-TEAM statt direkt einsetzbarem Ersatztext (Muster-Heuristik,
# siehe _ANWEISUNGS_MUSTER unten) - z.B. "Ersetzen Sie 'Luxor' durch...".
# Der zweite Vorfall zeigte, dass die reine Laengen-Heuristik allein NICHT
# reicht: ist die fundstelle selbst schon ein laengerer Satz, passt eine
# ganze Anweisung locker unter die 3x-Grenze und wird trotzdem woertlich in
# den Kapiteltext gespleisst.
_VORSCHLAG_MAX_ABSOLUT = 80
_VORSCHLAG_MAX_VERHAELTNIS = 3

# Formulierungen, die (fast) nie in echter Erzaehlprosa vorkommen, aber
# typisch fuer eine an den Menschen/das Modell gerichtete Anweisung sind -
# sowohl foermliches ("Ersetzen Sie") als auch informelles Imperativ-Register
# ("Fuege ... ein"), sowie die "muss/sollte ... werden"-Passiv-Auflage-Form.
_ANWEISUNGS_MUSTER = re.compile(
    r"\b("
    r"ersetzen sie|w[äa]hlen sie|erg[äa]nzen sie|f[üu]gen sie|beschreiben sie|"
    r"formulieren sie|streichen sie|[äa]ndern sie|geben sie an|"
    r"f[üu]ge(?:n)?\s+\S+.{0,20}\bein\b|"
    r"w[äa]hle(?:n)?\s+ein(?:e[nrs]?)?\b|"
    r"muss(?:te|ten)?\s+.{0,60}\bkorrigiert werden\b|"
    r"sollte(?:n)?\s+.{0,60}\bwerden\b|"
    r"\bbitte\s+(?:eine?|der|die|das)\b"
    r")",
    re.IGNORECASE,
)


def vorschlag_verdaechtig(fundstelle: str, vorschlag: str) -> bool:
    """True, wenn `vorschlag` eher nach einem liegen gebliebenen
    Redaktionskommentar, einem duplizierten Textfragment oder einer
    Anweisung ans Schreib-/Pruef-Team aussieht als nach einer echten,
    direkt einsetzbaren Korrektur von `fundstelle`. Bewusst KEIN
    Wortueberlapp-Check: kurze Kasus-/Genus-Korrekturen (z.B. "kein" ->
    "keine") aendern gerade die Funktionswoerter und teilen sich oft nur ein
    einziges Inhaltswort mit der fundstelle - ein Aehnlichkeits-Check wuerde
    genau diese legitimen Faelle blockieren."""
    if len(vorschlag) > max(_VORSCHLAG_MAX_ABSOLUT, len(fundstelle) * _VORSCHLAG_MAX_VERHAELTNIS):
        return True
    return bool(_ANWEISUNGS_MUSTER.search(vorschlag))


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
