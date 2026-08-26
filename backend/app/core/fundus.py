"""Personen-Fundus: sammelt Figuren aus abgeschlossenen Geschichten pro
Benutzer, getrennt nach Epoche, damit der Architekt sie bei neuen
Geschichten vorschlagen kann statt jedes Mal neue Figuren zu erfinden
(siehe ToDo.md).

Reine Funktionen (kein I/O), analog zu app/core/geruest.py. Die Datei
fundus.md selbst wird von den Aufrufern (app/api/fundus.py,
app/api/architekt.py) ueber app/core/projekt_dateien.py gelesen/geschrieben.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_VORLAGE = '''<!--
FUNDUS-VORLAGE — bitte diesen Kommentarblock nicht löschen.

Neue Figur manuell anlegen: unter der passenden "## <Epoche>"-Überschrift
einen Block in genau diesem Format einfügen:

### Vollständiger Name
- Alter: 27
- Stand/Rolle: Verarmte Baronesse
- Eigenschaften: schlagfertig, misstraut Fremden, spielt heimlich Karten
- Geschichten: Der Markt von Rothenfeld

Die "Geschichten:"-Zeile wird automatisch ergänzt, sobald diese Figur in
einer weiteren Geschichte vorkommt. Die anderen Zeilen darfst du jederzeit
von Hand nachbessern - sie werden beim automatischen Zusammenführen NICHT
überschrieben, nur die Geschichten-Liste wächst. Eine neue Epoche bekommt
automatisch eine eigene "## <Epoche>"-Überschrift bei der ersten Figur.
-->
'''

_EPOCHE_ABSCHNITT_MUSTER = r"^##[ \t]+{}[ \t]*\n(.*?)(?=\n##[ \t]|\Z)"
_FIGUR_BLOCK_MUSTER = r"^###[ \t]+.+?\n(?:(?!^###[ \t]|^##[ \t]).*\n?)*"
_GESCHICHTEN_ZEILE_MUSTER = re.compile(r"^-\s*Geschichten:\s*(.*)$", re.IGNORECASE | re.MULTILINE)


def leere_vorlage() -> str:
    """Inhalt einer noch nicht existierenden fundus.md - nur der erklaerende
    Kopfkommentar, keine Epochen-Abschnitte."""
    return _VORLAGE


def epoche_abschnitt_erkennen(fundus_text: str, epoche: str) -> str | None:
    """Extrahiert den Textblock unter '## <epoche>' bis zur naechsten
    '## '-Ueberschrift oder Textende. None, wenn die Epoche (noch) keinen
    eigenen Abschnitt hat."""
    muster = re.compile(_EPOCHE_ABSCHNITT_MUSTER.format(re.escape(epoche)), re.MULTILINE | re.DOTALL)
    treffer = muster.search(fundus_text)
    if not treffer:
        return None
    inhalt = treffer.group(1).strip()
    return inhalt or None


@dataclass
class FigurEintrag:
    name: str
    alter: str = ""
    stand: str = ""
    eigenschaften: str = ""
    geschichten: list[str] = field(default_factory=list)


# JEDE Epoche-Vorlage schreibt fuer den "## Figuren"-Abschnitt dieselbe
# Satzstruktur vor: "Je Figur: Name, Alter, Stand, Ziel, größte Angst,
# Geheimnis, Entwicklungsbogen in einem Satz" (siehe z.B.
# app/data/epochen/Wilhelminisches Preußen/architekt.txt). Deutsche
# Grossschreibung ALLER Substantive macht diese wiederkehrenden Feld-
# Bezeichner fuer ein schwaches lokales Modell (Rolle "fundus_pfleger",
# siehe app/core/rollen.py) leicht mit einem Eigennamen verwechselbar, wenn
# sie - wie von der Vorlage selbst erzeugt - unmittelbar nach einem Punkt
# vor einem Doppelpunkt stehen (".. Ziel: ... größte Angst: ... Geheimnis:
# ... Entwicklungsbogen: ..."). Realer Vorfall (2026-08, "Dunkle-
# Geheimnisse-im-Gutshaus"): der fundus_pfleger trug "Ziel"/"Geheimnis" als
# eigene Figuren in den Fundus ein - Eigenschaften der echten Figuren
# wurden so faelschlich zu neuen Personen. Deterministischer Filter statt
# alleinigem Prompt-Vertrauen, analog zu app/core/befunde_merge.py.
_KEIN_FIGURENNAME = {
    "ziel", "geheimnis", "geheimnisse", "angst", "ängste", "aengste",
    "größte angst", "groesste angst", "entwicklungsbogen", "eigenschaften",
    "konflikt", "stand", "rolle", "stand/rolle", "alter",
    "charakterzug", "charakterzüge", "charakterzuege",
}


def ist_plausibler_figurenname(name: str) -> bool:
    """False fuer einen von der Fundus-Pfleger-Rolle gemeldeten 'name', der
    tatsaechlich einer der wiederkehrenden Feld-Bezeichner aus der Figuren-
    Vorlage ist (siehe _KEIN_FIGURENNAME oben), statt eines echten
    Figurennamens."""
    return name.strip().lower() not in _KEIN_FIGURENNAME


def figur_block_erzeugen(figur: FigurEintrag, story_titel: str) -> str:
    """Baut einen neuen '### Name'-Block, wie er von Hand oder beim
    automatischen Zusammenfuehren einer bisher unbekannten Figur angelegt
    wird."""
    zeilen = [f"### {figur.name}"]
    if figur.alter.strip():
        zeilen.append(f"- Alter: {figur.alter.strip()}")
    if figur.stand.strip():
        zeilen.append(f"- Stand/Rolle: {figur.stand.strip()}")
    if figur.eigenschaften.strip():
        zeilen.append(f"- Eigenschaften: {figur.eigenschaften.strip()}")
    zeilen.append(f"- Geschichten: {story_titel.strip()}")
    return "\n".join(zeilen) + "\n"


def _figur_bloecke_mit_namen(abschnitt_text: str) -> list[tuple[str, str]]:
    """Liefert (Name, kompletter Block-Text) fuer jeden '### Name'-Block
    innerhalb eines Epoche-Abschnitts, in Ursprungsreihenfolge."""
    ergebnis: list[tuple[str, str]] = []
    for treffer in re.finditer(_FIGUR_BLOCK_MUSTER, abschnitt_text, re.MULTILINE):
        block = treffer.group(0)
        kopf = block.splitlines()[0]
        name = kopf.lstrip("#").strip()
        ergebnis.append((name, block))
    return ergebnis


def _geschichten_ergaenzen(block: str, story_titel: str) -> str:
    """Haengt story_titel an die 'Geschichten:'-Zeile eines bestehenden
    Blocks an (dedupe), ohne andere Zeilen anzufassen. Fehlt die Zeile ganz
    (z.B. weil der Nutzer sie von Hand geloescht hat), wird sie am
    Blockende neu angefuegt statt den Block unveraendert zu lassen -
    defensiv, aber ohne Datenverlust."""
    treffer = _GESCHICHTEN_ZEILE_MUSTER.search(block)
    if not treffer:
        block_ohne_zeilenumbruch = block.rstrip("\n")
        return block_ohne_zeilenumbruch + f"\n- Geschichten: {story_titel.strip()}\n"

    vorhandene = [g.strip() for g in treffer.group(1).split(",") if g.strip()]
    if story_titel.strip() and story_titel.strip() not in vorhandene:
        vorhandene.append(story_titel.strip())
    neue_zeile = f"- Geschichten: {', '.join(vorhandene)}"
    return block[:treffer.start()] + neue_zeile + block[treffer.end():]


def figuren_zusammenfuehren(
    fundus_text: str, epoche: str, story_titel: str, figuren: list[FigurEintrag],
) -> str:
    """Fuegt figuren in die '## <epoche>'-Sektion von fundus_text ein.
    Bereits vorhandene Figuren (case-insensitiver Namensabgleich innerhalb
    derselben Epoche) bekommen nur die Geschichte an ihre 'Geschichten:'-
    Zeile angehaengt (dedupe) - alle anderen von Hand gepflegten Felder
    bleiben unangetastet. Neue Figuren werden als frischer '### Name'-Block
    ans Ende der Sektion angehaengt. Findet sich die Epoche-Ueberschrift noch
    nicht, wird sie neu angelegt.

    Defensiv: laesst sich die Blockstruktur einer vermeintlich vorhandenen
    Figur nicht sauber wiederfinden, wird ein neuer Block angehaengt statt
    eine Exception zu werfen oder Daten zu verlieren."""
    if not figuren:
        return fundus_text

    if not fundus_text.strip():
        fundus_text = leere_vorlage()

    muster = re.compile(_EPOCHE_ABSCHNITT_MUSTER.format(re.escape(epoche)), re.MULTILINE | re.DOTALL)
    treffer = muster.search(fundus_text)

    if treffer:
        abschnitt = treffer.group(1)
        vorhandene_bloecke = _figur_bloecke_mit_namen(abschnitt)
    else:
        abschnitt = "\n"
        vorhandene_bloecke = []

    namen_lower = {name.lower(): block for name, block in vorhandene_bloecke}
    neue_bloecke: list[str] = []

    for figur in figuren:
        key = figur.name.strip().lower()
        alter_block = namen_lower.get(key)
        if alter_block is not None:
            aktualisiert = _geschichten_ergaenzen(alter_block, story_titel)
            abschnitt = abschnitt.replace(alter_block, aktualisiert, 1)
            namen_lower[key] = aktualisiert
        else:
            neuer_block = figur_block_erzeugen(figur, story_titel)
            neue_bloecke.append(neuer_block)
            namen_lower[key] = neuer_block

    if neue_bloecke:
        abschnitt = abschnitt.rstrip("\n") + "\n\n" + "\n".join(neue_bloecke)
        abschnitt = abschnitt.rstrip("\n") + "\n"

    if treffer:
        return fundus_text[:treffer.start(1)] + abschnitt + fundus_text[treffer.end(1):]

    ergaenzung = f"\n## {epoche}\n\n" + abschnitt.strip() + "\n"
    return fundus_text.rstrip("\n") + "\n" + ergaenzung
