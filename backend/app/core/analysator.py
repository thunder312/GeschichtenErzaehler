"""Analysator: importiert eine bestehende Geschichte/Novelle als Rohtext und
baut daraus ein komplettes Story-Geruest (samt Kapitelplan), damit die
Geschichte als Projekt zum Neu-Schreiben verfuegbar wird (siehe ToDo.md
"groesseres Feature als neuen Haupt-Tab: Analysator"). Framework-frei wie
app/core/architekt.py/automatik.py - die eigentliche Orchestrierung
(Ollama-Aufrufe, Hintergrund-Task, Status-Polling) lebt in
app/api/analysator.py.

Ablauf:
1. vorbereiten(): der importierte Text wird OHNE KI bereinigt (Sprache
   erkennen, Fuelltext wie Disclaimer/A/N/Danksagungen entfernen, siehe
   app/core/import_bereinigung.py) und in kapitelgrosse Abschnitte zerlegt
   (Kapitelueberschriften wie "Chapter 3"/"Kapitel drei" erkennen - ihre
   Anzahl bestimmt die Kapitelzahl -, sonst Absatzweise nach Zielwortzahl
   gruppieren).
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
from dataclasses import dataclass, field
from pathlib import Path

from app.core import architekt as arch
from app.core.geruest import ordnername_aus_titel
from app.core.import_merkmale import (
    erzaehlperspektive_erkennen, explizitheit_bewerten, hoechste_stufe, jugendschutz_aus_stufe, tempus_erkennen,
)
from app.core.import_bereinigung import (
    abschnitt_saeubern, fuelltexte_entfernen, ist_fuelltext_ueberschrift, sprache_erkennen,
)
from app.core.textutil import woerter

ANALYSATOR_STATUS_DATEINAME = "analysator_status.json"

# Obergrenze fuer die Anzahl automatisch erkannter/gebildeter Kapitel - bei
# mehr wird zusammengefasst zusammengefuehrt (siehe _kapitel_zusammenfuehren_
# bis_maximum). Jedes Kapitel kostet einen eigenen, sequentiellen Ollama-
# Aufruf; bei 30 Kapiteln liegt ein kompletter Analyse-Lauf realistisch
# irgendwo zwischen 5 und 20 Minuten (abhaengig vom KI-Ziel) - ein
# vertretbarer, wenn auch spuerbarer Hintergrund-Lauf.
MAX_KAPITEL = 30

# Obergrenze, wenn die Kapitel ausdruecklich im Text stehen ("Chapter 12"):
# dann soll die Kapiteleinteilung der Vorlage folgen und nicht auf
# MAX_KAPITEL zusammengestutzt werden. Nur ein Sicherheitsnetz gegen
# Fehlerkennungen (z.B. Gedichtzeilen, die wie Ueberschriften aussehen).
MAX_KAPITEL_EXPLIZIT = 100

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


# Erkennt Kapitelueberschriften in importiertem Fremdtext. Bewusst NICHT auf
# die einheitliche eigene Kapitelplan-Syntax beschraenkt (siehe
# app/core/geruest.py:_KAPITEL_MUSTER) - importierter Fremdtext (Fanfiction,
# exportierte Word-Dokumente, ...) folgt keiner einheitlichen Konvention.
_ZAHLWOERTER = (
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    r"seventeen|eighteen|nineteen|twenty(?:[- ]\w+)?|thirty(?:[- ]\w+)?|forty|fifty|"
    r"eins|ein|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|elf|zwölf|dreizehn|vierzehn|fünfzehn|sechzehn|"
    r"siebzehn|achtzehn|neunzehn|zwanzig\w*|dreißig\w*|vierzig|fünfzig)"
)

# Stufe 1: ausdrueckliche Kapitelangaben - "Kapitel 3", "Chapter III",
# "Chapter Three", "Kapitel drei: Titel", "Teil/Part 2", "Prolog/Epilogue",
# optional als Markdown-Ueberschrift oder fett/kursiv. Roemische Zahlen nur
# in GROSSBUCHSTABEN (sonst passte "Chapter did ...").
_KAPITEL_KEYWORD_MUSTER = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?[*_]*[ \t]*(?:"
    r"(?:Kapitel|Chapter|Chap\.|Ch\.|Teil|Part)[ \t]+(?:\d+|(?-i:[IVXLCDM]+)|" + _ZAHLWOERTER + r")\b"
    r"|(?:Prolog|Prologue|Epilog|Epilogue)\b"
    r")[^\n]{0,100}$",
    re.MULTILINE | re.IGNORECASE,
)

KAPITEL_STICHWORT_MUSTER = _KAPITEL_KEYWORD_MUSTER  # oeffentlich, z.B. fuer app/core/pdf_text.py

# Stufe 2: beliebige Markdown-Ueberschriften (Ebene 1-3) - der urspruengliche
# Fallback fuer Fremdtext ohne "Kapitel"/"Chapter"-Wort.
_KAPITEL_MARKDOWN_MUSTER = re.compile(r"^[ \t]*#{1,3}[ \t]*\S.*$", re.MULTILINE)


def _kapitel_zusammenfuehren_bis_maximum(
    abschnitte: list[str], maximum: int = MAX_KAPITEL, titel: list[str] | None = None,
) -> list[str]:
    """Fasst benachbarte Abschnitte zusammen, bis hoechstens `maximum`
    uebrig sind - verschmilzt dabei bevorzugt den JEWEILS kuerzesten
    Abschnitt mit seinem kuerzeren Nachbarn, damit kein einzelner ohnehin
    schon langer Abschnitt zusaetzlich aufgeblaeht wird."""
    abschnitte = list(abschnitte)
    while len(abschnitte) > maximum:
        laengen = [woerter(a) for a in abschnitte]
        kuerzester = min(range(len(abschnitte)), key=lambda i: laengen[i])
        ziel = kuerzester + 1 if kuerzester + 1 < len(abschnitte) else kuerzester - 1
        i, j = sorted((kuerzester, ziel))
        abschnitte[i:j + 1] = ["\n\n".join(abschnitte[i:j + 1])]
        if titel is not None:
            titel[i:j + 1] = [titel[i]]  # beim Verschmelzen gilt der Titel des ersten Kapitels
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


_UEBERSCHRIFT_PRAEFIX = re.compile(
    r"^(?:Kapitel|Chapter|Chap\.|Ch\.|Teil|Part)[ \t]+(?:\d+|(?-i:[IVXLCDM]+)|" + _ZAHLWOERTER + r")\b[ \t]*[:.\-–—)]*[ \t]*",
    re.IGNORECASE,
)


def kapitel_titel_aus_ueberschrift(ueberschrift: str) -> str:
    """'Chapter Fifteen: The Final Chapter (Part 1 of 3)' -> 'The Final Chapter
    (Part 1 of 3)'; 'Chapter One' -> '' (kein Titel); 'Prologue' -> 'Prologue';
    eine sonstige Markdown-Ueberschrift ('## Der Sturm') bleibt ganz."""
    zeile = ueberschrift.strip().lstrip("#*_ \t").rstrip("*_ \t")
    rest = _UEBERSCHRIFT_PRAEFIX.sub("", zeile, count=1)
    # PDF-Artefakte: unlesbare Zeichen (U+FFFD) und das uebrig bleibende "?" davor
    rest = rest.replace("\ufffd", "")
    rest = re.sub(r"\s+\?+\)", ")", rest)
    return rest.strip(" \t:.-–—*_")


@dataclass
class Vorbereitung:
    """Ergebnis von vorbereiten(): was der Analysator tatsaechlich auswertet."""
    abschnitte: list[str]
    sprache: str  # "de" | "en" | "unbekannt"
    entfernt: list[str]  # entfernte Fuelltext-Absaetze (Disclaimer, A/N, ...)
    kapitel_quelle: str  # "stichwort" (Chapter/Kapitel) | "markdown" | "absaetze"
    verworfene_abschnitte: int  # reine Fuelltext-Kapitel ("Author's Note"), komplett verworfen
    bereinigter_text: str
    # Originaltitel je Abschnitt ("" = Kapitel hat keinen Titel), parallel zu abschnitte
    titel: list[str] = field(default_factory=list)


def _nach_ueberschriften_teilen(text: str, treffer: list[re.Match[str]]) -> tuple[list[str], list[str], int]:
    """Zerlegt `text` an den Ueberschriften-Treffern. Abschnitte, deren
    Ueberschrift selbst Fuelltext ist ("## Author's Note") oder die nach der
    Bereinigung leer sind, werden verworfen (zweiter Rueckgabewert = Anzahl)."""
    abschnitte: list[str] = []
    titel: list[str] = []
    verworfen = 0
    for i, m in enumerate(treffer):
        ende = treffer[i + 1].start() if i + 1 < len(treffer) else len(text)
        ueberschrift = m.group(0).strip().lstrip("#*_ \t").rstrip("*_ \t")
        koerper = abschnitt_saeubern(text[m.end():ende])
        if not koerper or ist_fuelltext_ueberschrift(ueberschrift):
            verworfen += 1
            continue
        abschnitte.append(koerper)
        titel.append(kapitel_titel_aus_ueberschrift(ueberschrift))
    # Text VOR der ersten erkannten Ueberschrift (z.B. ein Vorwort) wird dem
    # ersten echten Kapitel vorangestellt statt verworfen, sofern er nicht
    # nur ein paar Zeilen Titel/Widmung ist.
    vor_erster = abschnitt_saeubern(text[:treffer[0].start()])
    if vor_erster and woerter(vor_erster) >= MIN_WOERTER_PRO_ABSCHNITT and abschnitte:
        abschnitte[0] = vor_erster + "\n\n" + abschnitte[0]
    return abschnitte, titel, verworfen


def vorbereiten(text: str) -> Vorbereitung:
    """Bereitet importierten Rohtext fuer die Analyse vor, ohne KI:
    1. Sprache erkennen (Hinweis fuer die Prompts, siehe kapitel_analyse_user).
    2. Fuelltext entfernen (siehe app/core/import_bereinigung.py).
    3. Kapitel erkennen: zuerst ausdrueckliche Angaben ("Chapter 3",
       "Kapitel drei", Prolog/Epilog) - bei mindestens zwei Treffern bestimmt
       DEREN Anzahl die Kapitelzahl (bis MAX_KAPITEL_EXPLIZIT, nicht auf
       MAX_KAPITEL zusammengestutzt); sonst beliebige Markdown-Ueberschriften;
       sonst Absatz-Gruppierung nach Zielwortzahl (hoechstens MAX_KAPITEL).
    Ein einzelner Ueberschriften-Treffer gilt nicht als Muster (z.B. nur ein
    Titelblatt) und bleibt Teil des Fliesstexts."""
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return Vorbereitung([], "unbekannt", [], "absaetze", 0, "", [])

    sprache = sprache_erkennen(text)
    treffer = list(_KAPITEL_KEYWORD_MUSTER.finditer(text))
    ueberschriften_muster = _KAPITEL_KEYWORD_MUSTER if len(treffer) >= 2 else _KAPITEL_MARKDOWN_MUSTER
    bereinigt, entfernt = fuelltexte_entfernen(text, ueberschriften_muster)

    verworfen = 0
    kapitel_quelle = "absaetze"
    abschnitte: list[str] = []
    titel: list[str] = []
    for quelle, muster in (("stichwort", _KAPITEL_KEYWORD_MUSTER), ("markdown", _KAPITEL_MARKDOWN_MUSTER)):
        # Mindestens 2 Treffer noetig, um von einem echten Kapitelmuster
        # auszugehen - ein einzelner Treffer waere z.B. nur eine einleitende
        # Titelzeile am Textanfang, kein wiederkehrendes Muster.
        treffer = list(muster.finditer(bereinigt))
        if len(treffer) >= 2:
            abschnitte, titel, verworfen = _nach_ueberschriften_teilen(bereinigt, treffer)
            if abschnitte:
                kapitel_quelle = quelle
                break
    if kapitel_quelle == "absaetze":
        abschnitte = _nach_absaetzen_aufteilen(bereinigt)
        titel = [""] * len(abschnitte)
        abschnitte = _kapitel_zusammenfuehren_bis_maximum(abschnitte, MAX_KAPITEL, titel)
    else:
        abschnitte = _kapitel_zusammenfuehren_bis_maximum(abschnitte, MAX_KAPITEL_EXPLIZIT, titel)
    return Vorbereitung(abschnitte, sprache, entfernt, kapitel_quelle, verworfen, bereinigt, titel)


def text_in_kapitel_teilen(text: str) -> list[str]:
    """Nur die Abschnitte von vorbereiten() - Kurzform fuer Aufrufer/Tests, die
    keine Sprache und keine Fuelltext-Liste brauchen."""
    return vorbereiten(text).abschnitte


def kapitel_analyse_system(persona_text: str) -> str:
    return persona_text


# Zusatz fuer die Prompts, wenn der importierte Text englisch ist: der Text
# wird nicht vorab uebersetzt (zu teuer und fehleranfaellig bei langen
# Geschichten), sondern das Modell liest das Original und liefert alle
# Angaben direkt auf Deutsch - das Gerüst und damit die spaeter neu
# geschriebene Geschichte sind deutsch.
ENGLISCH_HINWEIS = (
    "HINWEIS: Der folgende Text ist auf Englisch. Lies ihn im Original, aber liefere ALLE Angaben auf "
    "Deutsch (sinngemäß übersetzt). Eigennamen von Figuren und Orten, Titel und Anreden wie Lord, Lady, "
    "Sir, Mr. bleiben unverändert; englische Redewendungen gibst du sinngemäß deutsch wieder.\n\n"
)


def _sprachhinweis(sprache: str) -> str:
    return ENGLISCH_HINWEIS if sprache == "en" else ""


def ereignis_saetze(wortzahl: int) -> int:
    """Wie ausfuehrlich das Ereignis beschrieben werden soll: 2 Saetze bei
    kurzen, bis zu 8 bei sehr langen Kapiteln (rund ein Satz je 1500 Woerter)."""
    return max(2, min(8, 2 + wortzahl // 1500))


# Obergrenze Woerter je Analyse-Aufruf: der Kontext der Rolle "analysator"
# (num_ctx 16384, siehe app/core/rollen.py) muss Persona, Anweisungen, Text UND die
# Antwort fassen. Ein 13.600-Woerter-Kapitel (ca. 18.000 Token) wurde sonst vorn
# abgeschnitten und lieferte nur Platzhalter (Vorfall 2026-10-13, Kapitel 17).
ANALYSE_MAX_WOERTER = 5000


def abschnitt_in_teile(abschnitt: str, max_woerter: int = ANALYSE_MAX_WOERTER) -> list[str]:
    """Teilt ein sehr langes Kapitel an Absatzgrenzen in gleich grosse Teile
    (je hoechstens ca. max_woerter Woerter); kurze Kapitel bleiben ein Teil."""
    gesamt = woerter(abschnitt)
    if gesamt <= max_woerter:
        return [abschnitt]
    anzahl = -(-gesamt // max_woerter)
    ziel = gesamt / anzahl
    absaetze = [a for a in re.split(r"\n\s*\n", abschnitt) if a.strip()]
    teile: list[str] = []
    aktuell: list[str] = []
    aktuelle_woerter = 0
    for absatz in absaetze:
        aktuell.append(absatz)
        aktuelle_woerter += woerter(absatz)
        if aktuelle_woerter >= ziel and len(teile) < anzahl - 1:
            teile.append("\n\n".join(aktuell))
            aktuell, aktuelle_woerter = [], 0
    if aktuell:
        teile.append("\n\n".join(aktuell))
    return teile


def analysen_zusammenfuehren(teile: list[KapitelAnalyse]) -> KapitelAnalyse:
    """Fuegt die Teil-Analysen EINES Kapitels zu einer Kapitel-Analyse zusammen,
    ohne weiteren KI-Aufruf: Titel/Vergangene Zeit vom ersten, Stand/Zustand/
    Funktion vom LETZTEN Teil (Kapitelende), Orte und Figuren ohne Dopplungen,
    Ereignisse hintereinander, Explizitheit = Maximum."""
    if len(teile) == 1:
        return teile[0]

    def eindeutig(werte: list[str], trenner: str) -> str:
        gesehen: list[str] = []
        for w in werte:
            for stueck in (s.strip() for s in w.split(trenner)):
                if stueck and stueck.lower() not in (g.lower() for g in gesehen) and "nicht ersichtlich" not in stueck:
                    gesehen.append(stueck)
        return trenner.join(gesehen) if trenner != "," else ", ".join(gesehen)

    stufen = [t.explizitheit for t in teile if t.explizitheit]
    return KapitelAnalyse(
        titel=teile[0].titel,
        ort=eindeutig([t.ort for t in teile], ",") or teile[0].ort,
        anwesende_figuren=eindeutig([t.anwesende_figuren for t in teile], ",") or teile[0].anwesende_figuren,
        ereignis=" ".join(t.ereignis.strip() for t in teile if "nicht ersichtlich" not in t.ereignis) or teile[0].ereignis,
        funktion_im_spannungsbogen=teile[-1].funktion_im_spannungsbogen,
        stand_der_liebeshandlung=teile[-1].stand_der_liebeshandlung,
        zustand_am_kapitelende=teile[-1].zustand_am_kapitelende,
        vergangene_zeit=teile[0].vergangene_zeit,
        explizitheit=hoechste_stufe(stufen) if stufen else ""
    )


def kapitel_analyse_user(
    abschnitt: str, sprache: str = "de", index: int | None = None, gesamt: int | None = None,
    originaltitel: str = "", teil: tuple[int, int] | None = None,
) -> str:
    hinweise = []
    if index is not None and gesamt is not None:
        hinweise.append(f"Dies ist Kapitel {index} von {gesamt}.")
    if teil is not None and teil[1] > 1:
        hinweise.append(
            f"Das Kapitel ist sehr lang und wird in {teil[1]} Teilen analysiert; dies ist TEIL {teil[0]} von {teil[1]}. "
            f"Beschreibe nur das, was in diesem Teil geschieht."
        )
    hinweise.append(
        f"Das Kapitel hat ca. {woerter(abschnitt)} Wörter: beschreibe das Ereignis in etwa "
        f"{ereignis_saetze(woerter(abschnitt))} Sätzen."
    )
    if originaltitel.strip():
        uebersetzen = " (bei englischem Text sinngemäß ins Deutsche übersetzt)" if sprache == "en" else ""
        hinweise.append(
            f"ORIGINALTITEL des Kapitels: \u00ab{originaltitel.strip()}\u00bb. Übernimm ihn als \"Titel:\"{uebersetzen}, "
            f"Eigennamen unverändert. Erfinde keinen neuen Titel."
        )
    else:
        hinweise.append("Das Kapitel hat keinen Originaltitel: erfinde einen kurzen, sprechenden Untertitel (max. 6 Worte).")
    return (
        "AUFGABE: KAPITEL-ANALYSE\n\n" + _sprachhinweis(sprache) + "\n".join(hinweise) + "\n\n"
        + "Analysiere den folgenden Abschnitt einer Geschichte:\n\n" + abschnitt
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
    # Zeit seit dem Ende des vorigen Kapitels ("zwei Tage später") - Pflichtfeld
    # des Kapitelplans ab Kapitel 2 (siehe app/core/geruest_ki.py:_kapitel_block).
    vergangene_zeit: str = ""
    # "keine" | "angedeutet" | "explizit" - nur intern, fuer die Jugendschutz-Stufe;
    # wird NICHT in den Kapitelplan geschrieben.
    explizitheit: str = ""


_ANALYSE_FELD_LABELS = (
    "Vergangene Zeit", "Ort", "Anwesende Figuren", "Ereignis", "Funktion im Spannungsbogen",
    "Stand der Liebeshandlung", "Zustand am Kapitelende", "Explizitheit",
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
    titel = titel_treffer.group(1).strip().strip("*_ \t\"“”„") if titel_treffer else "[aus Analyse nicht ersichtlich]"

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
        vergangene_zeit=werte.get("Vergangene Zeit", ""),
        explizitheit=_explizitheit_normalisieren(werte.get("Explizitheit", "")),
    )


SPANNUNGSBOGEN_WERTE = (
    "Exposition", "Erregendes Moment", "Steigende Handlung", "Höhepunkt/Peripetie", "Fallende Handlung", "Auflösung/Lösung",
)
_FUNKTION_STICHWORTE = (
    ("Exposition", ("exposition", "einführung", "einfuehrung", "einleitung", "introduction")),
    ("Erregendes Moment", ("erregend", "auslösend", "ausloesend", "inciting")),
    ("Höhepunkt/Peripetie", ("höhepunkt", "hoehepunkt", "peripetie", "klimax", "climax", "wendepunkt")),
    ("Fallende Handlung", ("fallend", "falling", "retardier", "nachspiel")),
    ("Auflösung/Lösung", ("auflösung", "aufloesung", "lösung", "loesung", "resolution", "abschluss", "epilog")),
    ("Steigende Handlung", ("steigend", "rising", "eskalation", "komplikation", "spannung", "verwicklung")),
)


def funktion_normalisieren(text: str) -> str:
    """Bringt die freie Angabe der KI auf einen der sechs festen Werte
    (Freytags Pyramide), wie sie die Architekt-Struktur kennt. Nicht erkennbar
    -> Text unveraendert."""
    klein = text.lower()
    for kanonisch in SPANNUNGSBOGEN_WERTE:
        if klein.strip(" .*").startswith(kanonisch.lower()):
            return kanonisch
    for kanonisch, stichworte in _FUNKTION_STICHWORTE:
        if any(s in klein for s in stichworte):
            return kanonisch
    return text


LIEBESSTUFEN = ("Begegnung", "Annäherung", "Widerstand", "Ehrliches Geständnis", "Kuss", "Körperliche Erfüllung")


def liebesstufe_normalisieren(text: str) -> str:
    """Schreibt eine mit einer Stufe der Leiter beginnende Angabe in die
    kanonische Schreibweise um (z.B. 'annaeherung (..)' -> 'Annäherung (..)');
    alles andere bleibt unveraendert."""
    # Das Modell uebernimmt manchmal den Satz aus der Anweisung woertlich
    # ("Körperliche Erfüllung - gefolgt von einem kurzen Satz in Klammern. (...)")
    text = re.sub(r"\s*[-–]\s*gefolgt von einem kurzen Satz in Klammern\.?", "", text)
    roh = text.strip()
    klein = roh.lower()
    for stufe in (*LIEBESSTUFEN, "Keine Liebeshandlung"):
        for name in {stufe.lower(), stufe.lower().replace("ä", "ae").replace("ü", "ue").replace("ö", "oe")}:
            if klein.startswith(name):
                return stufe + roh[len(name):]
    return text


def figuren_bereinigen(text: str) -> str:
    """Entfernt doppelte Figuren und Kurzformen, deren Name schon ausgeschrieben
    vorkommt ('Harry Potter, ..., Harry' -> 'Harry Potter, ...'), Reihenfolge bleibt."""
    namen = [n.strip() for n in text.split(",") if n.strip()]
    ergebnis: list[str] = []
    for i, name in enumerate(namen):
        woerter_name = re.findall(r"\w+", name.lower())
        ist_kurzform = any(
            j != i and len(woerter_name) < len(re.findall(r"\w+", anderer.lower()))
            and all(w in re.findall(r"\w+", anderer.lower()) for w in woerter_name)
            for j, anderer in enumerate(namen)
        )
        schon_da = any(name.lower() == e.lower() for e in ergebnis)
        if not ist_kurzform and not schon_da:
            ergebnis.append(name)
    return ", ".join(ergebnis) if ergebnis else text


def _explizitheit_normalisieren(text: str) -> str:
    klein = text.lower()
    if "explizit" in klein:
        return "explizit"
    if "andeut" in klein or "angedeutet" in klein:
        return "angedeutet"
    if "keine" in klein or "kein " in klein or "nein" in klein:
        return "keine"
    return ""


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
    # Sternchen/Unterstriche der KI ("*Titel*") wuerden das **fett**-Format der
    # Ueberschrift sprengen - der Kapitelplan-Editor koennte den Plan dann nicht
    # mehr in Karten zerlegen (Vorfall 2026-10-13, "Rons-Vergiftung...").
    titel = re.sub(r"[*_`]+", "", analyse.titel).strip() or "[aus Analyse nicht ersichtlich]"
    # Kapitel 1 hat keinen Vorgaenger -> leer, wie in app/core/geruest_ki.py
    # Fehlt die Angabe, bleibt das Feld leer (kein Platzhaltertext im Kapitelplan).
    vergangene = "" if index == 1 or "nicht ersichtlich" in analyse.vergangene_zeit else analyse.vergangene_zeit.strip()
    return (
        f"*   **Kapitel {zahlwort(index)}: {titel}**\n"
        f"    *   Vergangene Zeit: {vergangene}\n"
        f"    *   Ort: {analyse.ort}\n"
        f"    *   Anwesende Figuren: {figuren_bereinigen(analyse.anwesende_figuren)}\n"
        f"    *   Ereignis: {analyse.ereignis}\n"
        f"    *   Zielwortzahl: ca. {ziel} Wörter.\n"
        f"    *   Funktion im Spannungsbogen: {funktion_normalisieren(analyse.funktion_im_spannungsbogen)}\n"
        f"    *   Stand der Liebeshandlung: {liebesstufe_normalisieren(analyse.stand_der_liebeshandlung)}\n"
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


def epoche_vorschlag_user(textauszug: str, sprache: str = "de") -> str:
    return "AUFGABE: EPOCHE-VORSCHLAG\n\n" + _sprachhinweis(sprache) + "Auszug aus der Geschichte:\n\n" + textauszug


def fakten_text(fakten: dict | None) -> str:
    """Aus dem Text GEZAEHLTE Angaben als feste Vorgabe fuer die Synthese."""
    if not fakten:
        return ""
    zeilen = []
    if fakten.get("jugendschutz"):
        zeilen.append(f"Jugendschutz-Stufe: {fakten['jugendschutz']}")
    if fakten.get("perspektive"):
        zeilen.append(f"Erzählperspektive: {fakten['perspektive']}")
    if fakten.get("tempus"):
        zeilen.append(f"Tempus: {fakten['tempus']}")
    if not zeilen:
        return ""
    return (
        "## Feststehende Fakten (aus dem Gesamttext ermittelt - übernimm sie unverändert)\n"
        + "\n".join(f"- {z}" for z in zeilen) + "\n\n"
    )


def synthese_user(kapitel_analysen_text: str, textauszug: str, sprache: str = "de", fakten: dict | None = None) -> str:
    return (
        "AUFGABE: SYNTHESE\n\n" + _sprachhinweis(sprache).replace("Der folgende Text ist", "Das Original ist")
        + fakten_text(fakten)
        + "## Kapitel-Zusammenfassungen der kompletten Geschichte\n\n"
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


_RAHMEN_LABELS = (
    "Jahreszeit/Tageszeit", "Ort und Region", "Erzählperspektive", "Automatische Fortsetzung", "Jugendschutz-Stufe",
    "Autor-Modell", "Zeitangabe", "Jahreszeit", "Schauplatz", "Perspektive", "Tonlage", "Tempus", "Jahr", "Ort", "Ton",
)
_RAHMEN_FELD_VON_LABEL = {
    "zeitangabe": "zeitangabe", "jahr": "zeitangabe", "ort": "ort", "ort und region": "ort", "schauplatz": "ort",
    "jahreszeit": "jahreszeit", "jahreszeit/tageszeit": "jahreszeit", "erzählperspektive": "perspektive",
    "perspektive": "perspektive", "tempus": "tempus", "tonlage": "tonlage", "ton": "tonlage",
    "jugendschutz-stufe": "jugendschutz", "automatische fortsetzung": "fortsetzung", "autor-modell": "modell",
}
_RAHMEN_LABEL_MUSTER = re.compile(
    r"(?:(?<=^)|(?<=[\s;,*]))\**(" + "|".join(re.escape(l) for l in _RAHMEN_LABELS) + r")\**[ \t]*:[ \t]*\**",
    re.IGNORECASE | re.MULTILINE,
)
_UNBEKANNT_MUSTER = re.compile(r"unbekannt|nicht\s+(?:spezifiziert|angegeben|ersichtlich)|keine?\s+angabe|n/?a|tbd|^-+$", re.IGNORECASE)


def rahmen_felder_lesen(rahmen_block: str) -> dict[str, str]:
    """Liest die Rahmen-Angaben aus JEDER Darstellung, die die KI liefert:
    Bullet-Zeilen, Klartext-Zeilen oder EINE Zeile mit mehreren 'Label: Wert'
    getrennt durch Komma/Semikolon. Der erste nicht-leere Wert je Feld gilt."""
    treffer = list(_RAHMEN_LABEL_MUSTER.finditer(rahmen_block))
    felder: dict[str, str] = {}
    for i, m in enumerate(treffer):
        ende = treffer[i + 1].start() if i + 1 < len(treffer) else len(rahmen_block)
        wert = rahmen_block[m.end():ende].strip().strip("*;, \t\n").strip()
        feld = _RAHMEN_FELD_VON_LABEL[m.group(1).lower()]
        if wert and feld not in felder and not _UNBEKANNT_MUSTER.fullmatch(wert):
            felder[feld] = wert
    return felder


def _perspektive_fest(ki_wert: str, erkannt: str | None) -> str:
    klein = ki_wert.lower()
    ki_erste = any(s in klein for s in ("erste", "ich-", "ich ", "first", "1."))
    ki_dritte = any(s in klein for s in ("dritte", "third", "er-", "sie-", "personal", "auktorial", "allwissend", "3."))
    if erkannt == "erste Person":
        wert = ki_wert if ki_erste else "Ich-Erzähler (erste Person)"
    elif erkannt == "dritte Person":
        wert = ki_wert if ki_dritte else "Dritte Person"
    else:
        wert = ki_wert or "Dritte Person"
    return wert[:1].upper() + wert[1:]


def rahmen_aufbauen(geruest: str, fakten: dict) -> str:
    """Schreibt den Abschnitt '## Rahmen' in das kanonische Bullet-Format um (das
    der Gerüst-Editor erzeugt/liest, siehe frontend/src/utils/rahmen.ts:
    rahmenBodyAusFelder): Zeitangabe nur als vierstellige Jahreszahl oder leer,
    Perspektive/Tempus/Jugendschutz aus dem Text ermittelt, wo eindeutig.
    Ohne Rahmen-Abschnitt unveraendert."""
    treffer = _RAHMEN_ABSCHNITT_MUSTER.search(geruest)
    if not treffer:
        return geruest
    start = treffer.end()
    naechster = re.search(r"\n##\s", geruest[start:])
    ende = start + naechster.start() if naechster else len(geruest)
    felder = rahmen_felder_lesen(geruest[start:ende])

    jahr = re.search(r"\b(\d{4})\b", felder.get("zeitangabe", ""))
    ki_tempus = felder.get("tempus", "").lower()
    erkannt_tempus = fakten.get("tempus")
    if erkannt_tempus == "Präsens" or (erkannt_tempus is None and ("präsens" in ki_tempus or "gegenwart" in ki_tempus)):
        tempus = "Präsens"
    else:
        tempus = "Vergangenheitsform"
    fortsetzung = "Ein" if re.search(r"\bein\b", felder.get("fortsetzung", ""), re.IGNORECASE) else "Aus"
    jugendschutz = fakten.get("jugendschutz") or (felder.get("jugendschutz") or "Voll").split()[-1].capitalize()
    if jugendschutz not in ("Voll", "Angedeutet", "Jugendfrei"):
        jugendschutz = "Voll"

    zeilen = [
        f"*   **Zeitangabe:** {jahr.group(1) if jahr else ''}".rstrip(),
        f"*   **Ort:** {felder.get('ort', '')}".rstrip(),
    ]
    if felder.get("jahreszeit"):
        zeilen.append(f"*   **Jahreszeit:** {felder['jahreszeit']}")
    zeilen += [
        f"*   **Erzählperspektive:** {_perspektive_fest(felder.get('perspektive', ''), fakten.get('perspektive'))}",
        f"*   **Tempus:** {tempus}",
        f"*   **Tonlage:** {felder.get('tonlage', '')}".rstrip(),
        f"*   **Jugendschutz-Stufe:** Jugendschutz-Stufe: {jugendschutz}",
        "*   **Autor-Modell:** Autor-Modell: Mistral",
        f"*   **Automatische Fortsetzung:** Automatische Fortsetzung: {fortsetzung}",
    ]
    return geruest[:start] + "\n" + "\n".join(zeilen) + "\n" + geruest[ende:]


def geruest_zusammenbauen(synthese_antwort: str, kapitelplan_block: str, fakten: dict | None = None) -> str:
    """Fuegt den deterministisch gebauten Kapitelplan (siehe
    kapitelplan_block_bauen) und die deterministischen Regeln (siehe
    regeln_text_bauen) in die Synthese-Antwort ein. Der Kapitelplan kommt
    konventionsgemaess vor '## Offene Punkte' (siehe reale Beispiel-
    Geruest-Dokumente) - wird dieser Abschnitt nicht gefunden (Modell hat
    ihn ausgelassen), wird der Kapitelplan stattdessen ans Ende angehaengt."""
    synthese_antwort = _rahmen_normalisieren(synthese_antwort.strip())
    if fakten is not None:
        synthese_antwort = rahmen_aufbauen(synthese_antwort, fakten)
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


# ---------------------------------------------------------------------------
# Dauerhafte Ablage der importierten Rohtexte (Tab "Analysator", eigener
# "Analyse"-Ordner unterhalb der Projekte-Wurzel) - VOR dieser Funktion wurde
# der eingefuegte/hochgeladene Text nur im Browser-State gehalten und beim
# Verlassen der Seite bzw. nach dem Start der Analyse unwiderruflich
# verworfen; ein spaeteres erneutes Anschauen oder ein zweiter Analyse-Versuch
# mit demselben Text war nicht mehr moeglich.
# ---------------------------------------------------------------------------

ANALYSE_ORDNERNAME = "Analyse"


def analysen_ordner(projekte_wurzel: Path) -> Path:
    ordner = projekte_wurzel / ANALYSE_ORDNERNAME
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def analyse_speichern(projekte_wurzel: Path, titel: str, text: str) -> str:
    """Speichert einen importierten Rohtext dauerhaft ab - gibt den
    (kollisionsfrei gewaehlten) Dateinamen zurueck. Ueberschreibt bewusst NIE
    eine bestehende Datei (siehe Zaehler-Suffix unten), auch nicht bei
    identischem Titel - jeder Analyse-Lauf bekommt seine eigene Kopie, analog
    zu app/services.py:neuer_projekt_pfad."""
    ordner = analysen_ordner(projekte_wurzel)
    basis = ordnername_aus_titel(titel.strip() or "Import")
    name = f"{basis}.md"
    ziel = ordner / name
    zaehler = 2
    while ziel.exists():
        name = f"{basis}-{zaehler}.md"
        ziel = ordner / name
        zaehler += 1
    ziel.write_text(text, encoding="utf-8")
    return name
