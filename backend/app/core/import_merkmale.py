"""Deterministische Textmerkmale fuer den Analysator: Erzaehlperspektive,
Zeitform (Tempus) und Explizitheit (Jugendschutz-Stufe) einer importierten
Geschichte. Reine Zaehlung, kein KI-Aufruf - die KI schaetzt diese Dinge aus
Zusammenfassungen oder kurzen Auszuegen, hier steht der ganze Text
zur Verfuegung. Ergebnisse werden nur uebernommen, wenn sie eindeutig sind;
sonst bleibt die Angabe der KI stehen (siehe app/core/analysator.py:
rahmen_fakten_anwenden).

Alle Woerterlisten gelten fuer Deutsch UND Englisch (Fremdtext ist oft
englisch, siehe app/core/import_bereinigung.py:sprache_erkennen). Gezaehlt
wird ausserhalb woertlicher Rede, wo es um die Erzaehlstimme geht."""
from __future__ import annotations

import re

from app.core.textutil import woerter

# --- Woertliche Rede entfernen ---------------------------------------------

_REDE_GERADE = re.compile(r"\"[^\"\n]{0,600}\"")
_REDE_TYPO = re.compile(r"[“„»][^”“«\n]{0,600}[”“«]")


def ohne_woertliche_rede(text: str) -> str:
    return _REDE_TYPO.sub(" ", _REDE_GERADE.sub(" ", text))


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-zäöüß’']+", text.lower())


# --- Erzaehlperspektive ----------------------------------------------------

_ICH = frozenset(
    "i i'm i've i'd i'll me my mine myself ich mir mich mein meine meinen meinem meiner meines".split()
)
_ER_SIE = frozenset(
    "he she him her his hers himself herself he's she's he'd she'd he'll she'll "
    "er ihn ihm sein seine seinen seinem seiner ihr ihre ihren ihrem ihrer".split()
)


def erzaehlperspektive_erkennen(text: str) -> str | None:
    """"erste Person", "dritte Person" oder None (gemischt/unklar). Zaehlt
    Pronomen nur im Erzaehltext (ohne woertliche Rede)."""
    tokens = _tokens(ohne_woertliche_rede(text))
    ich = sum(1 for t in tokens if t in _ICH)
    dritte = sum(1 for t in tokens if t in _ER_SIE)
    if ich + dritte < 40:
        return None
    anteil_ich = ich / (ich + dritte)
    if anteil_ich >= 0.6:
        return "erste Person"
    if anteil_ich <= 0.12:
        return "dritte Person"
    return None


# --- Tempus ----------------------------------------------------------------

_VERGANGENHEIT = frozenset(
    "was were had did said asked replied thought knew felt saw looked turned walked "
    "war waren hatte hatten sagte fragte antwortete dachte wusste fuehlte fühlte sah blickte ging kam stand "
    "nahm gab ließ liess lief".split()
)
_GEGENWART = frozenset(
    "is are has does says asks replies thinks knows feels sees looks turns walks "
    "ist sind hat sagt fragt antwortet denkt weiß weiss fühlt fuehlt sieht blickt geht kommt steht "
    "nimmt gibt lässt laesst läuft".split()
)


def tempus_erkennen(text: str) -> str | None:
    """"Präteritum", "Präsens" oder None. Zaehlt typische Verbformen im
    Erzaehltext (ohne woertliche Rede), Vergangenheits- gegen Gegenwartsform."""
    tokens = _tokens(ohne_woertliche_rede(text))
    v = sum(1 for t in tokens if t in _VERGANGENHEIT)
    g = sum(1 for t in tokens if t in _GEGENWART)
    if v + g < 30:
        return None
    anteil = v / (v + g)
    if anteil >= 0.75:
        return "Präteritum"
    if anteil <= 0.25:
        return "Präsens"
    return None


# --- Explizitheit ----------------------------------------------------------

_STARK = re.compile(
    r"\b(?:cock|dick|pussy|clit(?:oris)?|cunt|erections?|orgasm\w*|cum(?:ming|s)?|fuck\w*|blowjobs?|"
    r"ejaculat\w*|penetrat\w*|vagina|penis|nipples?|hard-on|schwanz|pimmel|fotze|muschi|klitoris|erektion\w*|"
    r"orgasmus|orgasmen|fick\w*|sperma|ejakul\w*|brustwarze\w*)\b",
    re.IGNORECASE,
)
_SCHWACH = re.compile(
    r"\b(?:naked|nude|moan\w*|aroused|arousal|kiss\w*|caress\w*|thighs?|breasts?|lust\w*|desire|"
    r"nackt\w*|stöhn\w*|erregt\w*|erregung|küss\w*|kuss|streichel\w*|verlangen|begehren|busen|brüste|schenkel)\b",
    re.IGNORECASE,
)

STUFEN = ("keine", "angedeutet", "explizit")
# Jugendschutz-Stufe laut Gerüst-Rahmen (siehe app/core/geruest.py:jugendschutz_stufe_erkennen)
_STUFE_ZU_JUGENDSCHUTZ = {"keine": "Jugendfrei", "angedeutet": "Angedeutet", "explizit": "Voll"}


def explizitheit_bewerten(text: str) -> str:
    """"keine" | "angedeutet" | "explizit" - Woerterlisten-Heuristik fuer EIN
    Kapitel: viele eindeutige Begriffe (absolut oder je 1000 Woerter) =
    explizit, vereinzelte eindeutige oder viele zaertliche Begriffe =
    angedeutet."""
    anzahl_woerter = max(woerter(text), 1)
    stark = len(_STARK.findall(text))
    schwach = len(_SCHWACH.findall(text))
    if stark >= 4 or stark / anzahl_woerter * 1000 >= 1.5:
        return "explizit"
    if stark >= 1 or schwach >= 6:
        return "angedeutet"
    return "keine"


def hoechste_stufe(stufen: list[str]) -> str:
    gueltig = [s for s in stufen if s in STUFEN]
    return max(gueltig, key=STUFEN.index) if gueltig else "keine"


def jugendschutz_aus_stufe(stufe: str) -> str:
    return _STUFE_ZU_JUGENDSCHUTZ.get(stufe, "Voll")
