"""Bereinigung importierter Fremdtexte fuer den Analysator (siehe
app/core/analysator.py:vorbereiten): Spracherkennung und Entfernen von
Fuelltext, der NICHT zur Geschichte gehoert (Disclaimer, A/N, Autoren-
anmerkungen, Danksagungen, Fanfiction-Kopfzeilen wie "Rating:"/"Summary:").

Rein deterministisch, kein KI-Aufruf: die Muster sind bewusst konservativ -
lieber ein Fuelltext-Absatz bleibt stehen (der Analysator-Prompt ignoriert
ihn ohnehin weitgehend), als dass echter Geschichtentext verloren geht.
Entfernt wird immer ein GANZER Absatz (durch Leerzeilen getrennt), nie ein
Satz mittendrin; mehrere aufeinanderfolgende Anmerkungs-Absaetze muessen
jeweils selbst mit einem Marker beginnen."""
from __future__ import annotations

import re

from app.core.textutil import woerter

# --- Spracherkennung --------------------------------------------------------

# Nur Woerter, die in der JEWEILS anderen Sprache nicht (oder kaum) vorkommen
# - "die", "was", "in", "war", "an" etc. sind absichtlich nicht dabei.
_EN_WOERTER = frozenset(
    "the and of he she her his that with you had have not but said they it for as are him them "
    "from this there their would could what when would about into your were been".split()
)
_DE_WOERTER = frozenset(
    "der und nicht ist ich er das mit ein eine auf den dem zu von es auch wie aber wenn hatte sich "
    "sie ihr ihm ihn sein seine einen einem dass noch nur schon wurde".split()
)


def sprache_erkennen(text: str) -> str:
    """"en", "de" oder "unbekannt" - Stoppwort-Zaehlung ueber die ersten 4000
    Woerter (reicht fuer ein sicheres Urteil und bleibt auch bei langen
    Texten schnell)."""
    tokens = re.findall(r"[a-zäöüß']+", text.lower())[:4000]
    en = sum(1 for t in tokens if t in _EN_WOERTER)
    de = sum(1 for t in tokens if t in _DE_WOERTER)
    if en + de < 15:
        return "unbekannt"
    if en >= de * 1.5:
        return "en"
    if de >= en * 1.5:
        return "de"
    return "unbekannt"


# --- Fuelltext --------------------------------------------------------------

# Dekorationszeichen, die Marker einrahmen koennen: "**A/N:**", "[A/N ...]",
# "(Disclaimer: ...)", "~ Author's Note ~", "> Note".
_DEKO = r"[\s\*_>\[\(#~\-=]*"

# Eindeutige Marker: gelten unabhaengig von der Absatzlaenge.
_STARK = re.compile(
    _DEKO + r"(?:"
    r"A\s*/\s*N\b|A\.N\.|AN\s*:"
    r"|Author'?s?[’']?\s+(?:Notes?|Post-?scripts?)\b|Authors?\s+(?:Notes?|Post-?scripts?)\b"
    r"|Note\s+(?:from|by)\s+the\s+author|Note\s+to\s+readers?"
    r"|Disclaimers?\b|Warnings?\s*:|(?:Trigger|Content)\s+Warnings?\b"
    r"|Beta(?:d|\s+read)?\s+by\b|Acknowledg(?:e)?ments?\b|Dedication\b"
    r"|Danksagung(?:en)?\b|Autoren?-?\s*(?:anmerkung|notiz|nachricht|vorwort)\w*"
    r"|Anmerkung(?:en)?\s+(?:des|der|vom|von)\s+Auto\w+|Vorbemerkung\b|Nachbemerkung\b|Nachwort\b"
    r"|Widmung\b|Gewidmet\b|Haftungsausschluss\b|Rechtliche[rn]?\s+Hinweis|Content[- ]Hinweis"
    r")",
    re.IGNORECASE,
)

# Schwache Marker: nur bei kurzen Absaetzen (Danke-/Reviewbitten-Zeilen),
# damit ein Satz der Geschichte wie "Thanks to the storm, ..." nicht fliegt.
_SCHWACH = re.compile(
    _DEKO + r"(?:"
    r"Thanks?\s+(?:so\s+much\s+)?(?:for|to)\b|Thank\s+you\s+(?:so\s+much\s+)?(?:for|to|all)\b"
    r"|I\s+(?:do\s*n['’]?t|do\s+not)\s+own\b|(?:All\s+)?(?:characters|rights)\b.{0,50}\b(?:belong|owned)\b"
    r"|(?:Please\s+|Pls\s+)(?:read\s*(?:and|&)\s*)?review\b|(?:Read\s*(?:and|&)\s*)?Review\s*!"
    r"|Reviews?\s+(?:are|=)\b|To\s+be\s+continued\b|Fortsetzung\s+folgt\b"
    r"|Danke\s+(?:an|für|fürs)\b|Vielen\s+Dank\b|Über\s+(?:Kommentare|Reviews)\b|Ich\s+freue\s+mich\s+über\b"
    r"|Mir\s+gehört\s+nichts\b|Die\s+Figuren\s+gehören\b|Alle\s+Rechte\b"
    r")",
    re.IGNORECASE,
)
SCHWACH_MAX_WOERTER = 70

# Kopfzeilen von Fanfiction-Seiten ("Title:", "Rating:", "Summary:", ...) -
# nur in den ersten Absaetzen des Textes.
_KOPF_LABEL = re.compile(
    r"^[\s\*_]*(?:Title|Titel|Author|Autor(?:in)?|Rating|Pairing|Paarung|Summary|Zusammenfassung|Inhaltsangabe|"
    r"Genre|Characters?|Charaktere|Status|Fandom|Words|Wörter|Category|Kategorie|Language|Sprache|"
    r"Published|Updated|Tags?|Series|Serie|Betas?)[\s\*_]*:",
    re.IGNORECASE,
)
KOPF_ABSAETZE = 5

# Abschnitts-Trenner (Szenenwechsel/Dekoration) - bleiben mitten im Text als
# Szenenwechsel stehen, werden aber am Anfang/Ende eines Abschnitts entfernt.
_TRENNER = re.compile(r"^[\s\*\-_=~#•·.]{3,}$")


def ist_fuelltext_ueberschrift(text: str) -> bool:
    """Fuer Kapitelueberschriften wie '## Author's Note' oder 'Acknowledgements'."""
    return bool(_STARK.match(text.strip()))


def _ist_fuelltext_absatz(absatz: str) -> bool:
    if _STARK.match(absatz):
        return True
    return bool(_SCHWACH.match(absatz)) and woerter(absatz) <= SCHWACH_MAX_WOERTER


def abschnitt_saeubern(text: str) -> str:
    """Entfernt Trenner-Absaetze ('***', '---') am Anfang und Ende."""
    absaetze = [a for a in re.split(r"\n\s*\n", text.strip()) if a.strip()]
    while absaetze and _TRENNER.match(absaetze[0].strip()):
        absaetze.pop(0)
    while absaetze and _TRENNER.match(absaetze[-1].strip()):
        absaetze.pop()
    return "\n\n".join(absaetze)


KOPF_ZEILEN = 12  # im Zeilenmodus ist jede Zeile ein Absatz, der Kopfblock entsprechend laenger

_SATZENDE = re.compile(r"[.!?…\"”’»)*_]\s*$")


def _zeilenweise(text: str) -> bool:
    """True, wenn der Text 'ein Absatz pro Zeile' ist (typisch fuer aus PDF/
    Webseite kopierte Geschichten: kaum Leerzeilen, aber fast jede Zeile endet
    mit Satzzeichen) - dann ist jede Zeile eine Einheit. Bei hart umbrochenem
    Text (Zeilen enden mitten im Satz) bleibt der Leerzeilen-Block die Einheit."""
    zeilen = [z for z in text.split("\n") if z.strip()]
    if len(zeilen) < 5:
        return False
    return sum(1 for z in zeilen if _SATZENDE.search(z)) / len(zeilen) >= 0.65


def _einheiten(text: str) -> list[str]:
    bloecke = [a.strip() for a in re.split(r"\n\s*\n", text) if a.strip()]
    if not _zeilenweise(text):
        return bloecke
    return [z.strip() for b in bloecke for z in b.split("\n") if z.strip()]


def fuelltexte_entfernen(text: str, ueberschriften: re.Pattern[str] | None = None) -> tuple[str, list[str]]:
    """Gibt (bereinigter Text, entfernte Absaetze) zurueck. Mit
    `ueberschriften` (Kapitelueberschriften-Muster) werden Ueberschrifts-
    zeilen vorher als eigene Absaetze isoliert, damit eine direkt darunter
    stehende Anmerkung ('Chapter 3\\nA/N: ...') nicht an der Ueberschrift
    klebt und mit ihr verschwindet bzw. bleibt."""
    text = text.replace("\r\n", "\n")
    if ueberschriften is not None:
        text = ueberschriften.sub(lambda m: "\n\n" + m.group(0).strip() + "\n\n", text)
    absaetze = _einheiten(text)
    behalten: list[str] = []
    entfernt: list[str] = []
    kopf_grenze = KOPF_ZEILEN if len(absaetze) > 0 and _zeilenweise(text) else KOPF_ABSAETZE
    for i, absatz in enumerate(absaetze):
        # Ueberschriften bleiben stehen: eine Fuelltext-UEBERSCHRIFT ("## Author's
        # Note") verwirft spaeter den GANZEN Abschnitt samt Text darunter
        # (siehe analysator._nach_ueberschriften_teilen), nicht nur die Zeile.
        if ueberschriften is not None and "\n" not in absatz and ueberschriften.fullmatch(absatz):
            behalten.append(absatz)
            continue
        ist_kopf = i < kopf_grenze and bool(_KOPF_LABEL.match(absatz))
        if ist_kopf or _ist_fuelltext_absatz(absatz):
            entfernt.append(absatz)
        else:
            behalten.append(absatz)
    return "\n\n".join(behalten), entfernt
