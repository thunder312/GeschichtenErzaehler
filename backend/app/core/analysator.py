"""Analysator: importiert eine bestehende Geschichte/Novelle als Rohtext und
baut daraus ein komplettes Story-Geruest (samt Kapitelplan), damit die
Geschichte als Projekt zum Neu-Schreiben verfuegbar wird (siehe ToDo.md
"groesseres Feature als neuen Haupt-Tab: Analysator"). Framework-frei wie
app/core/architekt.py/automatik.py - die eigentliche Orchestrierung
(Ollama-Aufrufe, Hintergrund-Task, Status-Polling) lebt in
app/api/analysator.py.

Ablauf:
1. text_in_kapitel_teilen(): der importierte Text wird OHNE KI in
   kapitelgrosse Abschnitte zerlegt (Kapitelueberschriften erkennen, sonst
   Absatzweise nach Zielwortzahl gruppieren).
2. Je Abschnitt EIN Ollama-Aufruf (Rolle "analysator", AUFGABE:
   KAPITEL-ANALYSE) liefert Ort/Figuren/Ereignis/... - kapitel_analyse_
   parsen() liest die Antwort, kapitel_block_bauen() setzt daraus EINEN
   Kapitelplan-Eintrag im selben Bullet-Format zusammen, das auch
   frontend/src/utils/kapitelplan.ts (KapitelplanEditor) erwartet, damit das
   Ergebnis dort spaeter normal editierbar ist. Die Zielwortzahl wird NICHT
   vom Modell erfragt, sondern deterministisch aus der tatsaechlichen
   Wortzahl des Original-Abschnitts uebernommen (siehe kapitel_block_bauen).
3. EIN abschliessender Ollama-Aufruf (Rolle "analysator", AUFGABE: SYNTHESE)
   bekommt alle Kapitel-Analysen zusammen und liefert Rahmen/Titel/Figuren/
   Konflikt/Nebenstrang/Offene Punkte/Ausgangslage - OHNE Kapitelplan (der
   kommt aus Schritt 2) und OHNE Regeln (siehe regeln_text_bauen).
4. geruest_zusammenbauen() fuegt den deterministisch gebauten Kapitelplan
   und die deterministischen Regeln in die Synthese-Antwort ein - das
   Ergebnis ist ein vollstaendiges geruest.md, das ueber denselben Weg wie
   "Gerüst selbst schreiben" (app/api/projects.py:geruest_schreiben)
   gespeichert werden kann.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.core import architekt as arch
from app.core.textutil import woerter

ANALYSATOR_STATUS_DATEINAME = "analysator_status.json"

# Obergrenze fuer die Anzahl automatisch erkannter/gebildeter Kapitel - bei
# mehr wird zusammengefasst zusammengefuehrt (siehe _kapitel_zusammenfuehren_
# bis_maximum). Jedes Kapitel kostet einen eigenen, sequentiellen Ollama-
# Aufruf; bei 30 Kapiteln liegt ein kompletter Analyse-Lauf realistisch
# irgendwo zwischen 5 und 20 Minuten (abhaengig vom KI-Ziel) - ein
# vertretbarer, wenn auch spuerbarer Hintergrund-Lauf.
MAX_KAPITEL = 30

# Ziel-/Mindestwortzahl je Abschnitt fuer die Absatz-Fallback-Aufteilung
# (kein erkennbares Kapitelmuster im importierten Text) - orientiert an der
# in den Epoche-Personas ueblichen Kapitel-Zielwortzahl (siehe z.B.
# backend/app/data/epochen/Mittelalter/architekt.txt: "etwa 1.200 bis 2.000
# Wörter pro Kapitel").
ZIEL_WOERTER_PRO_ABSCHNITT = 1400
MIN_WOERTER_PRO_ABSCHNITT = 300

_ZAHLWORT_LISTE = [
    "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn",
    "elf", "zwölf", "dreizehn", "vierzehn", "fünfzehn", "sechzehn", "siebzehn", "achtzehn", "neunzehn", "zwanzig",
    "einundzwanzig", "zweiundzwanzig", "dreiundzwanzig", "vierundzwanzig", "fünfundzwanzig",
    "sechsundzwanzig", "siebenundzwanzig", "achtundzwanzig", "neunundzwanzig", "dreißig",
]


def zahlwort(n: int) -> str:
    if 1 <= n <= len(_ZAHLWORT_LISTE):
        return _ZAHLWORT_LISTE[n - 1]
    return str(n)


# Erkennt gaengige Kapitelueberschriften in importiertem Fremdtext: Markdown-
# Ueberschriften jeder Ebene ("# ", "## ", ...) ODER "Kapitel"/"Chapter"/
# "Teil"/"Part" gefolgt von einer Ziffer oder roemischen Zahl, am
# Zeilenanfang. Bewusst NICHT auf die einheitliche eigene Kapitelplan-Syntax
# beschraenkt (siehe app/core/geruest.py:_KAPITEL_MUSTER) - importierter
# Fremdtext (Fanfiction, exportierte Word-Dokumente, ...) folgt keiner
# einheitlichen Konvention.
_KAPITEL_HEADER_MUSTER = re.compile(
    r"^[ \t]*(?:"
    r"#{1,3}[ \t]*\S.*"
    r"|(?:Kapitel|Chapter|Teil|Part)[ \t]+[\dIVXLCDM]+\b.*"
    r")[ \t]*$",
    re.MULTILINE | re.IGNORECASE,
)


def _kapitel_zusammenfuehren_bis_maximum(abschnitte: list[str]) -> list[str]:
    """Fasst benachbarte Abschnitte zusammen, bis hoechstens MAX_KAPITEL
    uebrig sind - verschmilzt dabei bevorzugt den JEWEILS kuerzesten
    Abschnitt mit seinem kuerzeren Nachbarn, damit kein einzelner ohnehin
    schon langer Abschnitt zusaetzlich aufgeblaeht wird."""
    abschnitte = list(abschnitte)
    while len(abschnitte) > MAX_KAPITEL:
        laengen = [woerter(a) for a in abschnitte]
        kuerzester = min(range(len(abschnitte)), key=lambda i: laengen[i])
        ziel = kuerzester + 1 if kuerzester + 1 < len(abschnitte) else kuerzester - 1
        i, j = sorted((kuerzester, ziel))
        abschnitte[i:j + 1] = ["\n\n".join(abschnitte[i:j + 1])]
    return abschnitte


def _nach_absaetzen_aufteilen(text: str) -> list[str]:
    """Fallback ohne erkennbares Kapitelmuster: gruppiert Absaetze (getrennt
    durch Leerzeilen) zu Abschnitten von ca. ZIEL_WOERTER_PRO_ABSCHNITT
    Woertern, ohne je einen Absatz mittendrin zu zerschneiden."""
    absaetze = [a.strip() for a in re.split(r"\n\s*\n", text) if a.strip()]
    if not absaetze:
        return [text.strip()] if text.strip() else []

    abschnitte: list[str] = []
    aktuell: list[str] = []
    aktuelle_woerter = 0
    for absatz in absaetze:
        aktuell.append(absatz)
        aktuelle_woerter += woerter(absatz)
        if aktuelle_woerter >= ZIEL_WOERTER_PRO_ABSCHNITT:
            abschnitte.append("\n\n".join(aktuell))
            aktuell = []
            aktuelle_woerter = 0
    if aktuell:
        rest = "\n\n".join(aktuell)
        # Ein zu kurzer letzter Rest (z.B. nur ein Schlusssatz) wird an den
        # vorigen Abschnitt angehaengt statt ein eigenes, winziges Kapitel
        # zu bilden - es sei denn, es ist der EINZIGE Abschnitt ueberhaupt.
        if abschnitte and woerter(rest) < MIN_WOERTER_PRO_ABSCHNITT:
            abschnitte[-1] = abschnitte[-1] + "\n\n" + rest
        else:
            abschnitte.append(rest)
    return abschnitte


def text_in_kapitel_teilen(text: str) -> list[str]:
    """Zerlegt importierten Rohtext in kapitelgrosse Abschnitte - erkennbare
    Kapitelueberschriften im Text (siehe _KAPITEL_HEADER_MUSTER) haben
    Vorrang, sonst Absatzweise Gruppierung nach Zielwortzahl (siehe
    _nach_absaetzen_aufteilen). Liefert nie mehr als MAX_KAPITEL Abschnitte
    (siehe _kapitel_zusammenfuehren_bis_maximum)."""
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []

    treffer = list(_KAPITEL_HEADER_MUSTER.finditer(text))
    # Mindestens 2 Treffer noetig, um von einem echten Kapitelmuster
    # auszugehen - ein einzelner Treffer waere z.B. nur eine einleitende
    # Titelzeile am Textanfang, kein wiederkehrendes Muster.
    if len(treffer) >= 2:
        abschnitte = []
        for i, m in enumerate(treffer):
            start = m.end()
            ende = treffer[i + 1].start() if i + 1 < len(treffer) else len(text)
            koerper = text[start:ende].strip()
            if koerper:
                abschnitte.append(koerper)
        # Text VOR der ersten erkannten Ueberschrift (z.B. ein Vorwort) wird
        # dem ersten echten Kapitel vorangestellt statt verworfen, sofern er
        # nicht nur ein paar Zeilen Titel/Widmung ist.
        vor_erster = text[:treffer[0].start()].strip()
        if vor_erster and woerter(vor_erster) >= MIN_WOERTER_PRO_ABSCHNITT and abschnitte:
            abschnitte[0] = vor_erster + "\n\n" + abschnitte[0]
    else:
        abschnitte = _nach_absaetzen_aufteilen(text)

    return _kapitel_zusammenfuehren_bis_maximum(abschnitte)


def kapitel_analyse_system(persona_text: str) -> str:
    return persona_text


def kapitel_analyse_user(abschnitt: str) -> str:
    return (
        "AUFGABE: KAPITEL-ANALYSE\n\n"
        "Analysiere den folgenden Abschnitt einer Geschichte:\n\n" + abschnitt
    )


@dataclass
class KapitelAnalyse:
    titel: str
    ort: str
    anwesende_figuren: str
    ereignis: str
    funktion_im_spannungsbogen: str
    stand_der_liebeshandlung: str
    zustand_am_kapitelende: str


_ANALYSE_FELD_LABELS = (
    "Ort", "Anwesende Figuren", "Ereignis", "Funktion im Spannungsbogen",
    "Stand der Liebeshandlung", "Zustand am Kapitelende",
)
_ANALYSE_FELD_MUSTER = re.compile(
    r"^[ \t]*[*-]?[ \t]*\**[ \t]*(" + "|".join(_ANALYSE_FELD_LABELS) + r")[ \t]*:[ \t]*\**[ \t]*",
    re.MULTILINE | re.IGNORECASE,
)
_ANALYSE_TITEL_MUSTER = re.compile(r"^[ \t]*Titel[ \t]*:[ \t]*(.+)$", re.MULTILINE | re.IGNORECASE)


def kapitel_analyse_parsen(antwort: str) -> KapitelAnalyse:
    """Liest die Antwort der Rolle 'analysator' (AUFGABE: KAPITEL-ANALYSE,
    siehe app/data/personas/analysator.txt) in ein KapitelAnalyse-Objekt.
    Fehlt ein Feld (Modell haelt sich nicht an die Vorgabe), bleibt es ein
    Platzhalter statt den ganzen Import abzubrechen - der Nutzer sieht/
    korrigiert das ohnehin spaeter im (jetzt einklappbaren) Kapitelplan-
    Editor."""
    titel_treffer = _ANALYSE_TITEL_MUSTER.search(antwort)
    titel = titel_treffer.group(1).strip() if titel_treffer else "[aus Analyse nicht ersichtlich]"

    treffer = list(_ANALYSE_FELD_MUSTER.finditer(antwort))
    werte: dict[str, str] = {}
    for i, m in enumerate(treffer):
        start = m.end()
        ende = treffer[i + 1].start() if i + 1 < len(treffer) else len(antwort)
        kanonisch = next(l for l in _ANALYSE_FELD_LABELS if l.lower() == m.group(1).lower())
        werte[kanonisch] = antwort[start:ende].strip()

    platzhalter = "[aus Analyse nicht ersichtlich]"
    return KapitelAnalyse(
        titel=titel,
        ort=werte.get("Ort", platzhalter),
        anwesende_figuren=werte.get("Anwesende Figuren", platzhalter),
        ereignis=werte.get("Ereignis", platzhalter),
        funktion_im_spannungsbogen=werte.get("Funktion im Spannungsbogen", platzhalter),
        stand_der_liebeshandlung=werte.get("Stand der Liebeshandlung", platzhalter),
        zustand_am_kapitelende=werte.get("Zustand am Kapitelende", platzhalter),
    )


def _gerundete_wortzahl(n: int) -> int:
    """Rundet auf die naechsten 50 (nach oben), mindestens 100 - eine
    Zielwortzahl wie 'ca. 1.187 Wörter' wirkt unabsichtlich praezise, echte
    Kapitelplaene runden ueblicherweise (siehe reale Beispiele: '1.000',
    '1.100')."""
    return max(100, ((n + 49) // 50) * 50)


def kapitel_block_bauen(index: int, analyse: KapitelAnalyse, wortzahl_original: int) -> str:
    """Ein einzelner '## Kapitelplan'-Eintrag - Bullet-Format 1:1 wie
    frontend/src/utils/kapitelplan.ts:kapitelBlockSerialisieren(), damit das
    Ergebnis dort spaeter normal als Kapitel-Karte geparst werden kann. Die
    Zielwortzahl kommt bewusst NICHT vom Modell, sondern direkt aus der
    tatsaechlichen Wortzahl des Original-Abschnitts (siehe Modul-Docstring)."""
    ziel = _gerundete_wortzahl(wortzahl_original)
    return (
        f"*   **Kapitel {zahlwort(index)}: {analyse.titel}**\n"
        f"    *   Ort: {analyse.ort}\n"
        f"    *   Anwesende Figuren: {analyse.anwesende_figuren}\n"
        f"    *   Ereignis: {analyse.ereignis}\n"
        f"    *   Zielwortzahl: ca. {ziel} Wörter.\n"
        f"    *   Funktion im Spannungsbogen: {analyse.funktion_im_spannungsbogen}\n"
        f"    *   Stand der Liebeshandlung: {analyse.stand_der_liebeshandlung}\n"
        f"    *   Zustand am Kapitelende: {analyse.zustand_am_kapitelende}"
    )


def kapitelplan_block_bauen(eintraege: list[tuple[KapitelAnalyse, int]]) -> str:
    return "\n".join(
        kapitel_block_bauen(i, analyse, wortzahl)
        for i, (analyse, wortzahl) in enumerate(eintraege, start=1)
    )


# Trennt die reine STORY-GERUEST-Struktur (samt Platzhaltertexten) aus einer
# Architekt-Persona heraus, OHNE den "## Kapitelplan"-Abschnitt - Grundlage
# fuer den Synthese-Aufruf, der diesen Abschnitt NICHT selbst erzeugen soll
# (siehe Modul-Docstring Schritt 3). Wiederverwendet dasselbe Muster wie
# app/core/architekt.py:_grundgeruest, entfernt danach zusaetzlich den
# "## Kapitelplan"-Block.
_KAPITELPLAN_ABSCHNITT_MUSTER = re.compile(r"\n##\s*Kapitelplan\s*\n.*?(?=\n##\s|\Z)", re.IGNORECASE | re.DOTALL)


def _grundgeruest_ohne_kapitelplan(persona_text: str) -> str:
    grundgeruest = arch._grundgeruest(persona_text)  # noqa: SLF001 - bewusste Wiederverwendung im selben Package
    return _KAPITELPLAN_ABSCHNITT_MUSTER.sub("", grundgeruest)


def synthese_system(analysator_persona_text: str, epoche_architekt_persona_text: str) -> str:
    """analysator_persona_text liefert das Rollenverhalten (siehe
    app/data/personas/analysator.txt), epoche_architekt_persona_text die
    STORY-GERUEST-Struktur der Ziel-Epoche (siehe app/core/architekt.py:
    _grundgeruest) - zwei verschiedene Personas, weil der Analysator selbst
    epochenunabhaengig ist (eine einzige, geteilte persona.txt), die exakte
    Feldstruktur des Ausgabedokuments (inkl. epochenspezifischer
    Zusatzfelder, z.B. eigene Ausgangslage-Unterabschnitte) aber von der
    Ziel-Epoche des neuen Projekts kommen muss."""
    return (
        analysator_persona_text + "\n\n"
        "Die STORY-GERUEST-Struktur, die du fuer die AUFGABE: SYNTHESE "
        "ausfuellen sollst (Abschnitt '## Kapitelplan' bewusst nicht "
        "enthalten, siehe deine Anweisungen dazu):\n\n"
        + _grundgeruest_ohne_kapitelplan(epoche_architekt_persona_text)
    )


def kapitel_analysen_text_bauen(eintraege: list[tuple[KapitelAnalyse, int]]) -> str:
    """Kompakte Textform aller Kapitel-Analysen als Eingabe fuer den
    Synthese-Aufruf (siehe synthese_user) - dieselben Felder wie
    kapitel_block_bauen(), aber ohne die Zielwortzahl (fuer die Synthese
    irrelevant) und mit einer schlichten '### Kapitel N'-Ueberschrift statt
    des endgueltigen Kapitelplan-Bullet-Formats."""
    return "\n\n".join(
        f"### Kapitel {i}\n"
        f"Titel: {a.titel}\n"
        f"*   Ort: {a.ort}\n"
        f"*   Anwesende Figuren: {a.anwesende_figuren}\n"
        f"*   Ereignis: {a.ereignis}\n"
        f"*   Funktion im Spannungsbogen: {a.funktion_im_spannungsbogen}\n"
        f"*   Stand der Liebeshandlung: {a.stand_der_liebeshandlung}\n"
        f"*   Zustand am Kapitelende: {a.zustand_am_kapitelende}"
        for i, (a, _wortzahl) in enumerate(eintraege, start=1)
    )


def textauszug_bauen(text: str, woerter_anfang: int = 400, woerter_ende: int = 250) -> str:
    """Kurzer Anfangs-/Endausschnitt des Originaltexts fuer den Synthese-
    Aufruf (siehe app/data/personas/analysator.txt: 'für Ton und Sprache') -
    bewusst nicht der ganze Text (der steckt bereits verdichtet in den
    Kapitel-Analysen), nur genug fuer einen Eindruck von Stil und Sprache."""
    woerter_liste = text.split()
    if len(woerter_liste) <= woerter_anfang + woerter_ende:
        return text.strip()
    anfang = " ".join(woerter_liste[:woerter_anfang])
    ende = " ".join(woerter_liste[-woerter_ende:])
    return anfang + "\n\n[...]\n\n" + ende


def epoche_vorschlag_system(persona_text: str) -> str:
    return persona_text


def epoche_vorschlag_user(textauszug: str) -> str:
    return "AUFGABE: EPOCHE-VORSCHLAG\n\nAuszug aus der Geschichte:\n\n" + textauszug


def synthese_user(kapitel_analysen_text: str, textauszug: str) -> str:
    return (
        "AUFGABE: SYNTHESE\n\n"
        "## Kapitel-Zusammenfassungen der kompletten Geschichte\n\n"
        + kapitel_analysen_text
        + "\n\n## Auszug aus dem Originaltext (für Ton und Sprache, NICHT wörtlich übernehmen)\n\n"
        + textauszug
    )


# Deterministischer Baustein fuer den Regeln-Abschnitt (siehe Modul-
# Docstring Schritt 4) - inhaltlich identisch zu den drei Literal-Marker-
# Reminder-Regeln aus frontend/src/utils/geruestVorlage.ts (Feature
# "Gerüst selbst schreiben"), damit beide Wege zu einem Geruest denselben
# Mindeststandard an maschinenlesbaren Pflichtangaben absichern.
def regeln_text_bauen() -> str:
    return (
        "## Regeln\n"
        "Keine Prosa, keine Beispielsätze, keine Dialoge. Nur Struktur in Stichpunkten.\n"
        "Das Jahr MUSS vierstellig im Gerüst stehen.\n"
        "Die Jugendschutz-Stufe MUSS wörtlich \"Jugendschutz-Stufe: Voll\" oder "
        "\"Jugendschutz-Stufe: Angedeutet\" oder \"Jugendschutz-Stufe: Jugendfrei\" lauten.\n"
        "Ist unter \"## Anrede-Konventionen\" eine feste Anredeform zwischen zwei Figuren "
        "festgelegt, gilt jede Abweichung davon in einem Kapitel als Kontinuitätsfehler.\n"
        "Das LETZTE Kapitel im Kapitelplan MUSS die vollständige Auflösung des "
        "Kernkonflikts (und eines evtl. Nebenstrangs) enthalten, kein offener Cliffhanger.\n"
    )


_RAHMEN_ABSCHNITT_MUSTER = re.compile(r"##\s*Rahmen\s*\n", re.IGNORECASE)
_JUGENDSCHUTZ_LITERAL_MUSTER = re.compile(r"Jugendschutz-Stufe\s*[:\-]", re.IGNORECASE)
_JUGENDSCHUTZ_STICHWORT_MUSTER = re.compile(r"\b(Jugendfrei|Angedeutet|Voll)\b", re.IGNORECASE)
_FORTSETZUNG_LITERAL_MUSTER = re.compile(r"Automatische Fortsetzung\s*[:\-]", re.IGNORECASE)
_FORTSETZUNG_STICHWORT_MUSTER = re.compile(r"\bAutomatische Fortsetzung\b[^\n]{0,20}\b(Ein|Aus)\b", re.IGNORECASE)


def _rahmen_normalisieren(geruest: str) -> str:
    """Sicherheitsnetz gegen ein reales, beim Live-Test beobachtetes
    Fehlerbild: die Synthese-Antwort uebernimmt manchmal das Rahmen-Format
    der Epoche-Persona woertlich (eine einzige, mit Kommas getrennte
    Aufzaehlung, z.B. "..., Jugendfrei, Automatische Fortsetzung (Ein)")
    STATT der fuer geruest.py:jugendschutz_stufe_erkennen()/
    automatische_fortsetzung_aktiviert() erforderlichen eigenen, woertlichen
    Zeilen ("Jugendschutz-Stufe: Jugendfrei"). Ohne dieses Sicherheitsnetz
    faellt eine z.B. als "Jugendfrei" erkannte Geschichte beim Parsen
    stillschweigend auf den score-seitigen Default "voll" zurueck - der
    genaue GEGENTEIL-Fall einer harmlosen Geschichte, die faelschlich als
    voll explizit markiert wird. Die Prompt-Anweisung in
    app/data/personas/analysator.txt deckt den Regelfall ab, dies hier ist
    die zweite, unabhaengige Verteidigungslinie direkt vor dem Speichern -
    analog zum vorschlag_verdaechtig()-Sicherheitsnetz in
    befunde_merge.py/automatik.py."""
    rahmen_treffer = _RAHMEN_ABSCHNITT_MUSTER.search(geruest)
    if not rahmen_treffer:
        return geruest
    rahmen_start = rahmen_treffer.end()
    naechster_abschnitt = re.search(r"\n##\s", geruest[rahmen_start:])
    rahmen_ende = rahmen_start + naechster_abschnitt.start() if naechster_abschnitt else len(geruest)
    rahmen_block = geruest[rahmen_start:rahmen_ende]

    einfuegungen = []
    if not _JUGENDSCHUTZ_LITERAL_MUSTER.search(rahmen_block):
        stichwort = _JUGENDSCHUTZ_STICHWORT_MUSTER.search(rahmen_block)
        wert = stichwort.group(1).capitalize() if stichwort else "Voll"
        einfuegungen.append(f"Jugendschutz-Stufe: {wert}")
    if not _FORTSETZUNG_LITERAL_MUSTER.search(rahmen_block):
        stichwort = _FORTSETZUNG_STICHWORT_MUSTER.search(rahmen_block)
        wert = stichwort.group(1).capitalize() if stichwort else "Aus"
        einfuegungen.append(f"Automatische Fortsetzung: {wert}")

    if not einfuegungen:
        return geruest
    ergaenzung = "\n".join(einfuegungen) + "\n"
    return geruest[:rahmen_start] + ergaenzung + geruest[rahmen_start:]


_OFFENE_PUNKTE_MUSTER = re.compile(r"\n##\s*Offene Punkte\b", re.IGNORECASE)


def geruest_zusammenbauen(synthese_antwort: str, kapitelplan_block: str) -> str:
    """Fuegt den deterministisch gebauten Kapitelplan (siehe
    kapitelplan_block_bauen) und die deterministischen Regeln (siehe
    regeln_text_bauen) in die Synthese-Antwort ein. Der Kapitelplan kommt
    konventionsgemaess vor '## Offene Punkte' (siehe reale Beispiel-
    Geruest-Dokumente) - wird dieser Abschnitt nicht gefunden (Modell hat
    ihn ausgelassen), wird der Kapitelplan stattdessen ans Ende angehaengt."""
    synthese_antwort = _rahmen_normalisieren(synthese_antwort.strip())
    kapitelplan_abschnitt = f"\n\n## Kapitelplan\n{kapitelplan_block}\n"

    treffer = _OFFENE_PUNKTE_MUSTER.search(synthese_antwort)
    if treffer:
        einfuege_stelle = treffer.start()
        geruest = synthese_antwort[:einfuege_stelle] + kapitelplan_abschnitt + synthese_antwort[einfuege_stelle:]
    else:
        geruest = synthese_antwort + kapitelplan_abschnitt

    return geruest.strip() + "\n\n" + regeln_text_bauen()


# --- Status-Datei fuer den Hintergrund-Lauf (siehe app/api/analysator.py) -
# gleiches JSON-Datei-Muster wie app/core/automatik.py:status_lesen/
# status_schreiben, bewusst als eigene, einfachere Struktur statt
# Wiederverwendung: ein Analysator-Lauf hat keine Durchlaeufe/Protokoll-
# Eintraege/Reste-Bestaetigung, nur einen linearen Fortschritt durch die
# erkannten Kapitel.


def status_datei(projekt_root: Path) -> Path:
    return projekt_root / "projekt" / ANALYSATOR_STATUS_DATEINAME


def status_lesen(projekt_root: Path) -> dict:
    pfad = status_datei(projekt_root)
    if not pfad.exists():
        return {
            "laeuft": False, "phase": None, "aktuelles_kapitel": None,
            "gesamt_kapitel": None, "log": [], "abgeschlossen": False, "fehler": None,
        }
    return json.loads(pfad.read_text(encoding="utf-8"))


def status_schreiben(projekt_root: Path, status: dict) -> None:
    pfad = status_datei(projekt_root)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def verwaiste_laeufe_zuruecksetzen(projects_root: Path) -> int:
    """Setzt jeden analysator_status.json unterhalb von projects_root mit
    laeuft=true auf laeuft=false (mit Fehlermeldung) zurueck - EINMALIG beim
    Backend-Start aufgerufen (siehe app/main.py), analog zu
    app/core/automatik.py:verwaiste_laeufe_zuruecksetzen und aus demselben
    Grund: ein Hintergrund-Task, der beim Prozessende (Deploy, Absturz,
    manueller Neustart) mitten in einer Analyse unterbrochen wird, bekommt
    NIE die Chance, sein eigenes "laeuft = False" zu schreiben - ohne dieses
    Zuruecksetzen bliebe der Analysator-Tab fuer das betroffene Projekt fuer
    immer auf "laeuft" haengen, ohne dass je wieder ein neuer Statuseintrag
    kaeme. Anders als beim Automatikmodus gibt es hier kein "Fortsetzen" -
    der Nutzer muss den Import einfach neu anstossen."""
    zurueckgesetzt = 0
    for pfad in projects_root.rglob(ANALYSATOR_STATUS_DATEINAME):
        try:
            status = json.loads(pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not status.get("laeuft"):
            continue
        status["laeuft"] = False
        status["fehler"] = (
            "Der Analyse-Lauf wurde durch einen Backend-Neustart unterbrochen (z.B. Deploy, Absturz "
            "oder Server-Neustart) - bitte den Import erneut starten."
        )
        try:
            pfad.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            continue
        zurueckgesetzt += 1
    return zurueckgesetzt
