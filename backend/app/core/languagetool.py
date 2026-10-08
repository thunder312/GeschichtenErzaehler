"""Deterministischer Grammatik-Pruefer ueber einen (optionalen) LanguageTool-
HTTP-Server - ergaenzt den LLM-Lektor um Faelle, die ein Regelwerk zuverlaessiger
trifft als gemma4: falsche Artikel/Adjektivendungen im Nominalgruppen-Verbund
("einen kühlen Gemisch") und Altschreibung ("bewußt").

Bewusst NUR eine schmale Whitelist an Regeln (siehe _REGELN). Ein Live-Test auf
einem echten Projekt zeigte: die uebrigen Kategorien sind fuer Prosa mit
Eigenbegriffen unbrauchbar (GERMAN_SPELLER_RULE flaggt "Commander"/"Tricorder",
Auslassungspunkte- und Gross-/Kleinschreibungs-Regeln flaggen Kapitelueber-
schriften und Dialoge). Subjekt-Verb-Numerus ("kehrte Daniel und Larissa")
und "als ob" + Indikativ erkennt LanguageTool ohne n-Gramm-Daten nicht.

Ist `languagetool_url` leer oder der Server nicht erreichbar, liefert
grammatik_befunde() eine leere Liste - die Pruefung laeuft dann wie bisher."""

from __future__ import annotations

import logging

import httpx

from app.core.befunde_merge import RoherBefund

logger = logging.getLogger(__name__)

# Regel-ID -> Beschreibung im Fund.
_REGELN = {
    "DE_AGREEMENT": "Artikel, Adjektiv und Nomen stimmen nicht überein (Kongruenz).",
    "DE_AGREEMENT2": "Artikel, Adjektiv und Nomen stimmen nicht überein (Kongruenz).",
    "OLD_SPELLING_RULE": "Veraltete Rechtschreibung (laut aktueller Duden-Schreibung).",
}


async def grammatik_befunde(kapiteltext: str, url: str, timeout: float = 30.0) -> list[RoherBefund]:
    if not url or not kapiteltext.strip():
        return []
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            antwort = await client.post(
                url.rstrip("/") + "/v2/check",
                data={"language": "de-DE", "text": kapiteltext, "enabledOnly": "false"},
            )
            antwort.raise_for_status()
            treffer = antwort.json().get("matches", [])
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("LanguageTool nicht erreichbar oder unlesbare Antwort (%s) - uebersprungen.", e)
        return []

    ergebnis: list[RoherBefund] = []
    gesehen: set[tuple[int, int]] = set()
    for m in treffer:
        beschreibung = _REGELN.get(m.get("rule", {}).get("id", ""))
        if not beschreibung:
            continue
        start, laenge = m["offset"], m["length"]
        if (start, laenge) in gesehen:
            continue
        gesehen.add((start, laenge))
        fundstelle = kapiteltext[start:start + laenge]
        ersetzungen = [r["value"] for r in m.get("replacements", []) if r.get("value")]
        if not ersetzungen:
            continue
        # Nur ein EINDEUTIGER Vorschlag ist direkt uebernehmbar (und wird im
        # Automatikmodus auch ungeprueft angewendet). Bei mehreren Varianten
        # ("die Frau" / "der Frau") entscheidet der Nutzer - ohne Vorschlag
        # taucht der Fund im Tab "Prüfen & Anwenden" nur als Hinweis auf.
        if len(ersetzungen) == 1:
            vorschlag = ersetzungen[0]
        else:
            vorschlag = None
            beschreibung += " Mögliche Korrekturen: " + " / ".join(ersetzungen[:4])
        ergebnis.append(RoherBefund(
            kategorie="lektorat", fundstelle=fundstelle, beschreibung=beschreibung,
            sicherheit="hoch", vorschlag=vorschlag, start=start, end=start + laenge,
        ))
    return ergebnis
