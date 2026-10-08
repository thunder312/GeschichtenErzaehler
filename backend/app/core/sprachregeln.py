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


# "Spezies" hat im Singular und Plural dieselbe Form, deshalb ist der Numerus
# aus dem Wort selbst nicht erkennbar. Eindeutig unstimmig wirkt aber das
# Muster "Diese Spezies ... sie sind": Der Satz beginnt wie ein Singular und
# faellt mit "sie" + Plural-Verb in den Plural. Ob Singular oder Plural gemeint
# ist, kann nur der Nutzer entscheiden - deshalb ein Fund OHNE Vorschlag.
_PLURAL_VERBEN = (
    "sind|waren|haben|hatten|können|konnten|müssen|mussten|werden|wurden|wollen|wollten|"
    "sollen|sollten|scheinen|schienen|wirken|wirkten"
)
_SPEZIES_NUMERUS_MUSTER = re.compile(
    rf"(?:\b(?:Diese|Jene|Die|Eine|Jede)\s+)?\bSpezies(?:\s*(?:\.\.\.|…|[,;:–—-])\s*|\s+)(?:sie|Sie)\s+(?:{_PLURAL_VERBEN})\b"
)


def spezies_numerus_roh_befunde(text: str) -> list[RoherBefund]:
    return [
        RoherBefund(
            kategorie="lektorat", fundstelle=m.group(0),
            beschreibung=(
                '"Spezies" steht erst im Singular, dann folgt "sie" + Plural-Verb. '
                'Entweder durchgehend Singular ("sie ist …") oder Plural mit eindeutigem '
                'Bezugswort ("Diese Wesen … sie sind …") verwenden.'
            ),
            sicherheit="mittel", vorschlag=None, start=m.start(), end=m.end(),
        )
        for m in _SPEZIES_NUMERUS_MUSTER.finditer(text)
    ]


# "als ob" / "als wenn" verlangen den Konjunktiv. Eindeutig erkennbar ist der
# Fehler nur bei Verben, deren Indikativ-Praeteritum vom Konjunktiv II
# abweicht (sah/saehe, war/waere). Schwache Verben (suchte, wollte, sollte)
# sind in beiden Modi gleich und werden NICHT gemeldet. Geprueft wird nur das
# erste passende Verb im selben Teilsatz (bis Komma/Satzende/Nebensatz-
# Einleiter), damit ein korrektes "als ob er wuesste, dass die Antwort Ja war"
# nicht wegen des Verbs im "dass"-Satz auffaellt.
_KONJUNKTIV_II = {
    "war": "wäre", "hatte": "hätte", "wurde": "würde", "wusste": "wüsste",
    "konnte": "könnte", "musste": "müsste", "durfte": "dürfte",
    "sah": "sähe", "kam": "käme", "ging": "ginge", "stand": "stünde", "lag": "läge",
    "gab": "gäbe", "fand": "fände", "nahm": "nähme", "trat": "träte", "blieb": "bliebe",
    "zog": "zöge", "trug": "trüge", "hielt": "hielte", "lief": "liefe", "fuhr": "führe",
    "saß": "säße", "fiel": "fiele", "sprach": "spräche", "hob": "höbe", "bot": "böte",
    "schlug": "schlüge", "trank": "tränke", "ließ": "ließe", "schien": "schiene",
    "begann": "begänne", "erschien": "erschiene", "schwieg": "schwiege", "stieg": "stiege",
    "verlor": "verlöre", "verstand": "verstünde", "wuchs": "wüchse",
}
# Bereits korrekte Konjunktiv-II-Formen im Teilsatz: dann nichts melden.
_KONJUNKTIV_FORMEN = set(_KONJUNKTIV_II.values()) | {"wollte", "sollte"}
_ALS_OB_MUSTER = re.compile(r"\b[Aa]ls (?:ob|wenn)\b")
_TEILSATZ_ENDE = {
    "dass", "weil", "obwohl", "wenn", "als", "während", "damit", "sodass", "bevor",
    "nachdem", "ob", "sobald", "bis", "was", "wo", "wie",
}
_WORT = re.compile(r"[\wäöüÄÖÜß]+|[,.!?;:–—\n“”„\"]")


def als_ob_roh_befunde(text: str) -> list[RoherBefund]:
    ergebnis: list[RoherBefund] = []
    for m in _ALS_OB_MUSTER.finditer(text):
        worte = list(_WORT.finditer(text, m.end(), min(len(text), m.end() + 200)))
        teilsatz = []
        for w in worte:
            if not re.match(r"[\wäöüÄÖÜß]", w.group(0)) or w.group(0).lower() in _TEILSATZ_ENDE:
                break
            teilsatz.append(w)
        if any(w.group(0) in _KONJUNKTIV_FORMEN for w in teilsatz):
            continue
        for w in teilsatz:
            ind = w.group(0)
            if ind in _KONJUNKTIV_II:
                ergebnis.append(RoherBefund(
                    kategorie="lektorat", fundstelle=ind,
                    beschreibung='Nach "als ob"/"als wenn" steht der Konjunktiv II.',
                    sicherheit="hoch", vorschlag=_KONJUNKTIV_II[ind], start=w.start(), end=w.end(),
                ))
                break
    return ergebnis
