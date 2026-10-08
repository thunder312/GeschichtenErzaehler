"""Deterministische Sprachregeln fuer genau die Fehler, die der LLM-Lektor auf
einem echten Projekt (Star-Trek "Echo der Ursprünge") trotz Abschnitts-Aufrufen
und think reproduzierbar uebersah - Live-Test gegen Athene, 2026-10-08:

- Numerus: "kehrte Daniel und Larissa ... zurück" (zwei Subjekte, Verb Singular)
- Altschreibung / bekannte Tippfehler: "bewußt", "zerissen", "daß"

Beides sind Regeln mit sehr wenigen Fehlalarmen, deshalb ohne KI-Aufruf und
mit direkt uebernehmbarem Vorschlag. Alles andere (Spezies-Singular/Plural,
Kasus) bleibt beim LLM-Lektor."""

from __future__ import annotations

import re

from app.core.befunde_merge import RoherBefund

# Altschreibung bzw. haeufige Tippfehler -> korrekte Form. Nur Woerter, bei denen
# die alte Form KEIN gueltiges deutsches Wort ist (kein "Fluß"->"Fluss"-Risiko bei
# Eigennamen, deshalb ganze Woerter statt ss/ß-Ersetzung im Wortinneren).
_ALTSCHREIBUNG = {
    "bewußt": "bewusst", "Bewußtsein": "Bewusstsein", "bewußtlos": "bewusstlos",
    "daß": "dass", "muß": "muss", "mußte": "musste", "mußten": "mussten",
    "wußte": "wusste", "wußten": "wussten", "läßt": "lässt", "laß": "lass",
    "Schluß": "Schluss", "Kuß": "Kuss", "Haß": "Hass", "naß": "nass",
    "Fluß": "Fluss", "Genuß": "Genuss", "Einfluß": "Einfluss", "bißchen": "bisschen",
    "zerissen": "zerrissen",
}

_ALT_MUSTER = re.compile(
    r"(?<![\wäöüÄÖÜß])(" + "|".join(sorted(map(re.escape, _ALTSCHREIBUNG), key=len, reverse=True)) + r")(?![\wäöüÄÖÜß])"
)

# Singular-Praeterita, die bei zwei Subjekten in den Plural muessen. Schwache
# Verben (-te) werden per Endung erkannt, starke per Liste.
_STARK_SG = {
    "ging", "kam", "stand", "lag", "saß", "trat", "blieb", "sah", "fand", "nahm",
    "lief", "fuhr", "hielt", "zog", "schlich", "trug", "gab", "sprach", "war",
}
_SCHWACH_SG = re.compile(r"^[a-zäöüß]{2,}te$")

_NEBENSATZ_EINLEITER = r"(?:Nachdem|Als|Während|Sobald|Bevor|Wenn|Weil|Obwohl|Seitdem)"
_PRAEPOSITIONEN = {
    "mit", "bei", "von", "zu", "für", "an", "auf", "über", "unter", "neben", "zwischen", "vor",
    "hinter", "ohne", "gegen", "um", "nach", "aus", "durch", "und", "sowie", "oder", "als", "wie",
}


def _plural_von(verb: str) -> str:
    return verb + ("n" if verb.endswith("e") else "en")


def _ist_singular_praeteritum(wort: str) -> bool:
    return wort in _STARK_SG or bool(_SCHWACH_SG.match(wort))


def numerus_roh_befunde(text: str, namen: set[str]) -> list[RoherBefund]:
    """"Name und Name" + Verb im Singular. Zwei Muster:
    A) "Daniel und Larissa kehrte ..." (Namen direkt vor dem Verb, nicht nach
       Praeposition/Konjunktion - sonst waeren sie Objekt).
    B) "Nachdem ..., kehrte Daniel und Larissa ..." (Verb direkt vor den Namen,
       nur nach Komma in einem Satz mit Nebensatz-Einleiter)."""
    if len(namen) < 2:
        return []
    n = "(?:" + "|".join(sorted(map(re.escape, namen), key=len, reverse=True)) + ")"
    wort = r"[a-zäöüß]+"
    ergebnis: list[RoherBefund] = []
    gesehen: set[tuple[int, int]] = set()

    def melden(start: int, ende: int, fundstelle: str, vorschlag: str) -> None:
        if (start, ende) in gesehen:
            return
        gesehen.add((start, ende))
        ergebnis.append(RoherBefund(
            kategorie="lektorat", fundstelle=fundstelle,
            beschreibung="Zwei Subjekte verlangen das Verb im Plural.",
            sicherheit="hoch", vorschlag=vorschlag, start=start, end=ende,
        ))

    for m in re.finditer(rf"(?<![\wäöüÄÖÜß])({n} und {n}) ({wort})(?![\wäöüß])", text):
        verb = m.group(2)
        davor = re.findall(r"[\wäöüÄÖÜß]+", text[max(0, m.start() - 20):m.start()])
        if davor and davor[-1].lower() in _PRAEPOSITIONEN:
            continue
        if _ist_singular_praeteritum(verb):
            melden(m.start(), m.end(), m.group(0), f"{m.group(1)} {_plural_von(verb)}")

    for m in re.finditer(rf", ({wort}) ({n} und {n})(?![\wäöüß])", text):
        verb = m.group(1)
        satzanfang = max(text.rfind(". ", 0, m.start()), text.rfind("\n", 0, m.start())) + 1
        if not re.search(rf"\b{_NEBENSATZ_EINLEITER}\b", text[satzanfang:m.start()]):
            continue
        if _ist_singular_praeteritum(verb):
            melden(m.start() + 2, m.end(), m.group(0)[2:], f"{_plural_von(verb)} {m.group(2)}")
    return ergebnis


def altschreibung_roh_befunde(text: str) -> list[RoherBefund]:
    ergebnis: list[RoherBefund] = []
    for m in _ALT_MUSTER.finditer(text):
        falsch = m.group(1)
        ergebnis.append(RoherBefund(
            kategorie="lektorat", fundstelle=falsch,
            beschreibung="Veraltete Schreibung bzw. Tippfehler.",
            sicherheit="hoch", vorschlag=_ALTSCHREIBUNG[falsch], start=m.start(), end=m.end(),
        ))
    return ergebnis
