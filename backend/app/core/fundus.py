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
einen Block in genau diesem Format einfügen - JEDES Feld wird immer
aufgeführt, auch wenn nichts dazu bekannt ist (dann einfach leer lassen,
z.B. "- Aussehen: "):

### Vollständiger Name
- Alter: 27
- Stand/Rolle: Verarmte Baronesse
- Eigenschaften: schlagfertig, misstraut Fremden, spielt heimlich Karten
- Aussehen: schmale Gestalt, rotblondes Haar, trägt geflickte, einst feine Kleider
- Ziel: eine eigene Existenz ohne die Gunst ihrer Verwandten aufbauen
- Angst: als Bettlerin zu enden und den Familiennamen zu beschämen
- Geheimnis: spielt heimlich um Geld, um ihre Schulden zu tilgen
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


_ERSTE_EPOCHE_MUSTER = re.compile(r"^##[ \t]", re.MULTILINE)


def kopf_kommentar_extrahieren(fundus_text: str) -> str:
    """Liefert den einleitenden Kommentarblock (alles vor der ersten
    '## <Epoche>'-Ueberschrift) unveraendert - wird beim Zusammenbauen mit
    fundus_serialisieren() vorangestellt, da diese Funktion selbst keinen
    Kopf erzeugt (siehe app/api/fundus.py). Faellt auf leere_vorlage()
    zurueck, wenn der Text (noch) keine Epoche enthaelt. ^ in MULTILINE
    matcht bewusst auch Zeile 1 (Text OHNE Kopf-Kommentar, faengt direkt mit
    '## Epoche' an - z.B. in Tests) - eine reine '\\n## '-Suche wuerde
    diesen Fall verfehlen, weil vor Zeile 1 kein Zeilenumbruch steht."""
    treffer = _ERSTE_EPOCHE_MUSTER.search(fundus_text)
    if not treffer:
        return fundus_text if fundus_text.strip() else leere_vorlage()
    return fundus_text[: treffer.start()]


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
    aussehen: str = ""
    ziel: str = ""
    angst: str = ""
    geheimnis: str = ""
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
    "aussehen", "konflikt", "stand", "rolle", "stand/rolle", "alter",
    "charakterzug", "charakterzüge", "charakterzuege",
}


def ist_plausibler_figurenname(name: str) -> bool:
    """False fuer einen von der Fundus-Pfleger-Rolle gemeldeten 'name', der
    tatsaechlich einer der wiederkehrenden Feld-Bezeichner aus der Figuren-
    Vorlage ist (siehe _KEIN_FIGURENNAME oben), statt eines echten
    Figurennamens."""
    return name.strip().lower() not in _KEIN_FIGURENNAME


def feldwert_einzeilig(wert: str) -> str:
    """Kollabiert Zeilenumbrueche/mehrfache Leerzeichen in EINEN Leerraum -
    das fundus.md-Format ist strikt eine Zeile pro Feld ('- Label: Wert',
    siehe _VORLAGE/_FELD_ZEILE_MUSTER); fundus_parsen() erkennt eine
    Fortsetzungszeile OHNE fuehrendes '- ' nicht als Teil des Werts und
    ueberspringt sie stillschweigend. Ein direkt (ohne dieses Kollabieren)
    gespeicherter mehrzeiliger Wert wirkt daher beim naechsten Laden
    abgeschnitten - realer Vorfall (2026-08-27): ein mehrere Absaetze langer
    "Aussehen"-Text verlor beim naechsten Speichern alles ab dem zweiten
    Absatz, weil er zwischenzeitlich unveraendert (roh mehrzeilig) in die
    Datei geschrieben, beim Wiedereinlesen aber nur bis zum ersten
    Zeilenumbruch erfasst wurde. Wird sowohl beim Schreiben eines neuen
    Blocks (figur_block_erzeugen) als auch beim Serialisieren bestehender
    Figuren (fundus_serialisieren) angewandt, damit KEIN Schreibweg einen
    mehrzeiligen Wert je in die Datei durchlaesst."""
    return " ".join(wert.split())


def figur_block_erzeugen(figur: FigurEintrag, story_titel: str) -> str:
    """Baut einen neuen '### Name'-Block, wie er von Hand oder beim
    automatischen Zusammenfuehren einer bisher unbekannten Figur angelegt
    wird. JEDES Feld wird immer als eigene Zeile ausgegeben, auch wenn dazu
    nichts bekannt ist (dann bleibt der Wert leer) - so hat jeder Block
    dieselbe, vorhersehbare Feld-Reihenfolge und laesst sich beim Lesen
    leicht ergaenzen (Nutzer-Vorgabe 2026-08, siehe fundus.md-Vorlage
    oben)."""
    zeilen = [
        f"### {figur.name}",
        f"- Alter: {feldwert_einzeilig(figur.alter)}",
        f"- Stand/Rolle: {feldwert_einzeilig(figur.stand)}",
        f"- Eigenschaften: {feldwert_einzeilig(figur.eigenschaften)}",
        f"- Aussehen: {feldwert_einzeilig(figur.aussehen)}",
        f"- Ziel: {feldwert_einzeilig(figur.ziel)}",
        f"- Angst: {feldwert_einzeilig(figur.angst)}",
        f"- Geheimnis: {feldwert_einzeilig(figur.geheimnis)}",
        f"- Geschichten: {story_titel.strip()}",
    ]
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


STANDARD_FELDER = ["Alter", "Stand/Rolle", "Eigenschaften", "Aussehen", "Ziel", "Angst", "Geheimnis"]
# "Geschichten" bewusst NICHT hier drin - es steht in jedem Block als feste
# Sonderposition ganz am Ende (siehe figur_block_erzeugen), unabhaengig
# davon, welche sonstigen (Standard- oder Custom-)Felder dazwischenstehen.

_FELD_ZEILE_MUSTER = re.compile(r"^-[ \t]*([^:\n]+?)[ \t]*:[ \t]*(.*)$")


@dataclass
class Figur:
    """Eine Figur als strukturierte (Feldname -> Wert)-Abbildung statt
    Roh-Markdown - Grundlage fuer den strukturierten Personen-Editor (siehe
    app/api/fundus.py). `felder` ist insertion-ordered (Python-dict), die
    Reihenfolge entspricht der im Markdown-Block; 'Geschichten' ist ein
    normaler Schluessel darin, keine Sonderbehandlung noetig, solange neue
    Felder ueber feld_setzen() ergaenzt werden."""
    epoche: str
    name: str
    felder: dict[str, str]


def feld_setzen(felder: dict[str, str], name: str, wert: str) -> None:
    """Setzt felder[name] = wert - ist der Schluessel neu, wird er direkt
    VOR 'Geschichten' eingefuegt (statt einfach ans Ende), damit
    'Geschichten' beim Serialisieren weiterhin die letzte Zeile jedes
    Blocks bleibt, wie es die Standard-Vorlage vorgibt."""
    if name in felder:
        felder[name] = wert
        return
    geschichten = felder.pop("Geschichten", None)
    felder[name] = wert
    if geschichten is not None:
        felder["Geschichten"] = geschichten


def fundus_parsen(fundus_text: str) -> list[Figur]:
    """Zerlegt die gesamte fundus.md (ohne den einleitenden Kopf-Kommentar)
    in eine flache, geordnete Liste aller Figuren ueber alle Epochen hinweg.
    Rein lesend - Grundlage fuer den strukturierten Personen-Editor, der
    GET /api/fundus/figuren liefert. Toleriert unbekannte/eigene Feldzeilen
    (alles im Muster '- Label: Wert' wird als Feld uebernommen); Zeilen, die
    diesem Muster nicht entsprechen (z.B. Reste alter freier Fliesstext-
    Eintraege), werden stillschweigend uebersprungen statt einen Fehler zu
    werfen."""
    treffer = _ERSTE_EPOCHE_MUSTER.search(fundus_text)
    if not treffer:
        return []
    rumpf = fundus_text[treffer.start():]

    ergebnis: list[Figur] = []
    epochen_treffer = list(re.finditer(r"^##[ \t]+(.+?)[ \t]*$", rumpf, re.MULTILINE))
    for i, epoche_treffer in enumerate(epochen_treffer):
        epoche = epoche_treffer.group(1).strip()
        ende = epochen_treffer[i + 1].start() if i + 1 < len(epochen_treffer) else len(rumpf)
        abschnitt = rumpf[epoche_treffer.end():ende]
        for name, block in _figur_bloecke_mit_namen(abschnitt):
            felder: dict[str, str] = {}
            for zeile in block.splitlines()[1:]:
                feld_treffer = _FELD_ZEILE_MUSTER.match(zeile)
                if not feld_treffer:
                    continue
                feld_name = feld_treffer.group(1).strip()
                wert = feld_treffer.group(2).strip()
                if feld_name in felder and felder[feld_name]:
                    felder[feld_name] = f"{felder[feld_name]} {wert}".strip()
                else:
                    felder[feld_name] = wert
            ergebnis.append(Figur(epoche=epoche, name=name, felder=felder))
    return ergebnis


def fundus_serialisieren(figuren: list[Figur]) -> str:
    """Baut eine komplette fundus.md aus einer flachen Figuren-Liste neu auf
    - Inverse von fundus_parsen(), OHNE den Kopf-Kommentar (der bleibt beim
    Aufrufer erhalten, siehe app/api/fundus.py). Epochen erscheinen in der
    Reihenfolge ihres ERSTEN Auftretens in `figuren`, Figuren innerhalb
    einer Epoche in der Reihenfolge, in der sie in der Liste stehen. Jede
    Figur listet NUR die Felder auf, die in ihrem eigenen `felder`-Dict
    stehen (siehe feld_setzen fuer die Merge-Regel
    "nur diese Person" vs. "alle Personen" beim Hinzufuegen eines neuen
    Feldes) - anders als figur_block_erzeugen() erzwingt diese Funktion
    KEINE einheitliche Acht-Felder-Struktur, damit Custom-Felder gezielt
    auf einzelne Figuren beschraenkt bleiben koennen."""
    epochen: dict[str, list[Figur]] = {}
    for figur in figuren:
        epochen.setdefault(figur.epoche, []).append(figur)

    abschnitte = []
    for epoche, figuren_in_epoche in epochen.items():
        bloecke = []
        for figur in figuren_in_epoche:
            zeilen = [f"### {figur.name}"]
            zeilen += [f"- {name}: {feldwert_einzeilig(wert)}" for name, wert in figur.felder.items()]
            bloecke.append("\n".join(zeilen) + "\n")
        abschnitte.append(f"## {epoche}\n\n" + "\n".join(bloecke))
    return "\n".join(abschnitte).rstrip("\n") + "\n"


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
