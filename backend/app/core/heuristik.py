"""Automatische Sicherheitsnetze - portiert aus pre-GUI/novelle.py.

Im CLI schreiben diese Funktionen direkt auf stderr (warn()/info()). Fuer
die GUI geben sie stattdessen strukturierte Findings zurueck, die die
API/das Frontend frei darstellen koennen (Toast, Badge, Liste im Merge-
Editor, ...). Die Erkennungslogik (Regex, Schwellwerte) ist bewusst
wortgleich zum Original, damit sich CLI und GUI bei gleichem Text identisch
verhalten (siehe doc/Schnittstellen-Uebersicht.md Abschnitt 5.6-5.11).
"""
from __future__ import annotations

import difflib
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from app.core.textutil import woerter

ExecFn = Callable[[list[str], str], tuple[int, str, str]]


@dataclass
class Finding:
    code: str
    meldung: str
    schwere: str = "warnung"  # "warnung" | "info"


# ---------------------------------------------------------------------------
# Sprachdrift
# ---------------------------------------------------------------------------

ENGLISCHE_SIGNALWOERTER = re.compile(
    r"\b(the|and|was|were|with|his|her|that|this|they|their|had|from|"
    r"which|would|could|should|what|when|where|because|you|your)\b",
    re.IGNORECASE,
)


def sprachdrift_pruefen(text: str, schwelle: float = 0.03) -> list[Finding]:
    gesamt = woerter(text)
    if gesamt == 0:
        return []
    treffer = len(ENGLISCHE_SIGNALWOERTER.findall(text))
    anteil = treffer / gesamt
    if anteil > schwelle:
        return [Finding(
            "sprachdrift",
            f"Möglicher Sprachdrift ins Englische - {treffer} typisch "
            f"englische Wörter auf {gesamt} Wörter gesamt ({anteil:.0%}). "
            f"Bei echtem Drift: betroffenen Abschnitt verwerfen und neu "
            f"erzeugen lassen, nicht nur übersetzen.",
        )]
    return []


# Dieselbe Wortliste wie ENGLISCHE_SIGNALWOERTER, aber OHNE "was"/"her" -
# beides sind auch gueltige, haeufige deutsche Woerter (was = what, her =
# hierher), die bei einer satzweisen Pruefung ohne die Verduennung durch
# die Prozent-Schwelle von sprachdrift_pruefen() zu vielen Fehlalarmen
# fuehren wuerden.
_ENGLISCHE_WOERTER_EINDEUTIG = re.compile(
    r"\b(the|and|were|with|his|that|this|they|their|had|from|"
    r"which|would|could|should|what|when|where|because|you|your)\b",
    re.IGNORECASE,
)


def sprachdrift_lokal_pruefen(text: str) -> list[Finding]:
    """Ergaenzt sprachdrift_pruefen() um eine satzweise Pruefung: ein
    einzelner englischer Satzfetzen mitten in einem sonst vollstaendig
    deutschen, mehrere tausend Woerter langen Kapitel faellt bei der
    Prozent-Schwelle unter den Tisch, weil er im Vergleich zur
    Kapitellaenge verschwindend gering ist (beobachtet: "Diesmal because
    of love." blieb in einem sonst deutschen Kapitel unbemerkt stehen).
    Prueft deshalb JEDEN Satz einzeln gegen eine auf eindeutig englische
    Woerter verengte Liste, statt ueber das ganze Kapitel zu mitteln."""
    saetze = re.split(r"(?<=[.!?])\s+", text)
    findings = []
    for satz in saetze:
        treffer = sorted(set(m.lower() for m in _ENGLISCHE_WOERTER_EINDEUTIG.findall(satz)))
        if not treffer:
            continue
        ausschnitt = satz.strip()
        if len(ausschnitt) > 140:
            ausschnitt = ausschnitt[:137] + "…"
        findings.append(Finding(
            "sprachdrift_lokal",
            f"Möglicher englischer Satzfetzen mitten im deutschen Text "
            f"({', '.join(treffer)}): „{ausschnitt}“",
        ))
    return findings


# ---------------------------------------------------------------------------
# Ich-Perspektive-Drift
# ---------------------------------------------------------------------------

_ICH_PRONOMEN_MUSTER = re.compile(
    r"\b(ich|mein|meine|meinen|meiner|meinem|meines|mir|mich)\b", re.IGNORECASE)


def _ohne_dialog(text: str) -> str:
    ohne = re.sub(r'„[^"“]*["“]', ' ', text)
    return re.sub(r'"[^"]*"', ' ', ohne)


def erzaehlperspektive_pruefen(text: str, geruest: str, schwellwert: int = 2) -> list[Finding]:
    """Nur relevant, wenn das Geruest explizit 'Dritte Person' vorschreibt."""
    if not re.search(r"Dritte Person", geruest, re.IGNORECASE):
        return []
    treffer = _ICH_PRONOMEN_MUSTER.findall(_ohne_dialog(text))
    if len(treffer) >= schwellwert:
        gefundene_woerter = ", ".join(sorted(set(w.lower() for w in treffer)))
        return [Finding(
            "ich_perspektive",
            f"Geruest schreibt dritte Person vor, aber außerhalb wörtlicher "
            f"Rede tauchen {len(treffer)} Ich-Perspektive-Wörter auf "
            f"({gefundene_woerter}). Vermutlich mitten im Text in die "
            f"Ich-Perspektive gerutscht - Abschnitt eher neu schreiben lassen "
            f"als von Hand umformulieren.",
        )]
    return []


# ---------------------------------------------------------------------------
# Anredeform (Sie/du)
# ---------------------------------------------------------------------------

_FORMELL_ANREDE_MUSTER = re.compile(r"\b(Sie|Ihnen)\b")
_INFORMELL_ANREDE_MUSTER = re.compile(r"\b(du|dich|dir|dein\w*)\b")


def anredeform_pruefen(text: str) -> list[Finding]:
    dialogzeilen = re.findall(r'„([^"“]*)["“]', text)
    dialogzeilen += re.findall(r'"([^"]*)"', text)
    dialogtext = " ".join(dialogzeilen)
    foermlich = _FORMELL_ANREDE_MUSTER.findall(dialogtext)
    informell = _INFORMELL_ANREDE_MUSTER.findall(dialogtext)
    if foermlich and informell:
        return [Finding(
            "anredeform",
            f"Sowohl förmliche Anrede (Sie/Ihnen, {len(foermlich)}x) als "
            f"auch informelle Anrede (du/dich/dir/dein, {len(informell)}x) "
            f"in wörtlicher Rede gefunden. Prüfen, ob der Wechsel "
            f"beabsichtigt ist (z.B. wachsende Vertrautheit) oder ein "
            f"unbegründeter Ausrutscher.",
        )]
    return []


# ---------------------------------------------------------------------------
# Ausweichformulierungen / Explizitheit
# ---------------------------------------------------------------------------

AUSWEICH_MUSTER = [
    "sprache des samens", "sprache der liebe",
    "blumenkelch", "blumen der liebe",
    "grenzen erkundet", "grenzen erkunden",
    "verloren ineinander", "eins wurden", "eins werden",
    "neue welt", "neuer morgen brach",
    "wie die götter es vorgeschrieben",
]


def ausweichformulierungen_pruefen(text: str) -> list[Finding]:
    treffer = [m for m in AUSWEICH_MUSTER if m in text.lower()]
    if treffer:
        return [Finding(
            "ausweichformulierung",
            f"Mögliche Ausweichformulierung(en) gefunden: {', '.join(treffer)}. "
            f"Deutet auf ein Fade-to-black statt einer ausgeführten Szene hin - "
            f"Kapitel lesen, nicht nur auf die Wortzahl verlassen.",
        )]
    return []


EXPLIZIT_SIGNALWOERTER = [
    "oralsex", "analsex", "cunnilingus", "fellatio", "fingering",
    "penetration", "ejakulation", "orgasmus", "erektion",
    "klitoris", "vagina", "penis", "eichel", "sperma",
    "geschlechtsteil", "schwanz", "muschi",
    "drang in sie ein", "drang tief in sie", "stiess in sie",
    "leckte zwischen ihren beinen", "saugte an ihrer klitoris",
]


def explizitheit_pruefen(text: str, stufe: str) -> list[Finding]:
    """Nur relevant, wenn stufe != 'voll'."""
    if stufe == "voll":
        return []
    text_klein = text.lower()
    treffer = [w for w in EXPLIZIT_SIGNALWOERTER
               if re.search(r"\b" + re.escape(w) + r"\b", text_klein)]
    if treffer:
        return [Finding(
            "explizitheit",
            f"Jugendschutz-Stufe ist '{stufe}', aber folgende eindeutig "
            f"explizite Begriffe wurden gefunden: {', '.join(treffer)}. "
            f"Kapitel unbedingt gegenlesen.",
        )]
    return []


# ---------------------------------------------------------------------------
# Kapitel-Neustart / vorzeitiges Kapitelende / Meta-Zeilen (bei Fortsetzung)
# ---------------------------------------------------------------------------

META_ZEILEN_MUSTER = re.compile(
    r"^\s*(-{2,}|#{2,}|\*{2,})\s*$"
    r"|^\s*\[?(wortzahl|word count|gedankenerhebung)\b.*$"
    r"|^\s*\d+\s*w(oe|ö)rter\s*\.?\s*(halte dich .*|halt dich .*|bitte .*)?$"
    r"|^\s*hier ist (die|der|das) (fortgesetzte|fortsetzung|weitere).*$"
    r"|^\s*(fortsetzung|hier folgt die fortsetzung)\s*:?\s*$"
    r"|^\s*kapitel\s+\S+\s+(endet|ist zu ende|ist beendet|ist fertig)\b.*$"
    r"|^\s*(ende|schluss|fortsetzung folgt)\s+(des|von)\s+kapitel\b.*$"
    r"|^\s*dies ist die fortsetzung (des|von) kapitel.*$",
    re.IGNORECASE,
)


def meta_zeilen_entfernen(text: str) -> str:
    zeilen = [z for z in text.split("\n") if not META_ZEILEN_MUSTER.match(z)]
    return "\n".join(zeilen).strip()


_FUEHRENDE_MARKDOWN_UEBERSCHRIFT_MUSTER = re.compile(
    r"^\s*#{1,6}[ \t]*\*{0,2}[ \t]*(Kapitel\s+\S+.*?)[ \t]*\*{0,2}[ \t]*\n+", re.IGNORECASE,
)

# Reine Klartext-Kapitelueberschrift (ohne fuehrende Markdown-Raute) - fuer
# die Frage, ob nach einer entfernten Markdown-Ueberschrift ueberhaupt noch
# eine echte Ueberschrift dasteht.
_KAPITEL_UEBERSCHRIFT_KLARTEXT_MUSTER = re.compile(
    r"^\s*\*{0,2}Kapitel\s+\S+\s*[:\-–—]", re.IGNORECASE,
)


def fuehrende_markdown_ueberschrift_entfernen(text: str) -> tuple[str, list[Finding]]:
    """Manche Modelle (z.B. Mistral) schreiben die Kapitelueberschrift als
    Markdown-Ueberschrift ("### Kapitel eins: Rechtlose Magd") statt als
    reinen Text ("Kapitel eins: Rechtlose Magd", wie die Persona es
    verlangt). Zwei Faelle:

    - Dahinter steht bereits die richtige Klartext-Ueberschrift: die
      Markdown-Zeile ist ein reines Duplikat und wird ersatzlos entfernt.
    - Es gibt NUR die Markdown-Ueberschrift: dann wird lediglich die
      Markdown-Auszeichnung (Raute, Sternchen) abgestreift und die Zeile als
      Klartext-Ueberschrift behalten - sonst stuende das Kapitel voellig ohne
      Ueberschrift da (fruehere Version loeschte hier die einzige
      Ueberschrift, wodurch die rohe "### Kapitel eins: ..."-Zeile ueber
      kapitelueberschrift_sicherstellen() als doppelte Klartext-Zeile wieder
      auftauchte und dann im PDF-/Gesamt-Export als Absatz landete)."""
    entfernt: list[str] = []
    rest = text
    while True:
        treffer = _FUEHRENDE_MARKDOWN_UEBERSCHRIFT_MUSTER.match(rest)
        if not treffer:
            break
        entfernt.append(treffer.group(1).strip().strip("*").strip())
        rest = rest[treffer.end():]

    if not entfernt:
        return text, []

    if _KAPITEL_UEBERSCHRIFT_KLARTEXT_MUSTER.match(rest):
        neuer_text = rest
        meldung = (
            "Zusätzliche Markdown-Kapitelüberschrift vor der eigentlichen "
            "Überschrift automatisch entfernt."
        )
    else:
        ueberschrift = entfernt[-1]
        neuer_text = f"{ueberschrift}\n\n{rest}" if rest.strip() else ueberschrift
        meldung = (
            f"Die Kapitelüberschrift stand nur als Markdown-Überschrift da "
            f"('{ueberschrift}') - Markdown-Auszeichnung automatisch entfernt."
        )
    return neuer_text, [Finding("markdown_ueberschrift", meldung, schwere="info")]


_KAPITEL_UEBERSCHRIFT_VORHANDEN_MUSTER = re.compile(
    r"^\s*(?:#{1,6}[ \t]*)?\*{0,2}Kapitel\s+\S+\s*[:\-–—]", re.IGNORECASE,
)

# Holt die komplette "Kapitel <Zahlwort>: <Titel>"-Zeile aus dem
# Kapitelplan-Block (siehe geruest.py:kapitel_block_erkennen) - bewusst
# derselbe locker gefasste Titel-Rest wie beim Vorhanden-Check oben (bis zum
# naechsten "*", nicht bis zum Zeilenende), da der Kapitelplan-Titel selbst
# als "*   **Kapitel eins: Titel**" mit schliessenden Sternchen endet.
_KAPITELPLAN_UEBERSCHRIFT_MUSTER = re.compile(
    r"Kapitel\s+(?:\d{1,2}|[a-zA-ZäöüÄÖÜß]+)\s*:\s*[^\n*]+", re.IGNORECASE,
)


def kapitelueberschrift_sicherstellen(text: str, kapitel_block: str | None) -> tuple[str, list[Finding]]:
    """Ergaenzt die laut Autor-Formatregeln vorgeschriebene Kapitelueberschrift
    ("Kapitel eins: Sprechender Untertitel"), falls das Modell sie komplett
    ausgelassen hat - beobachteter Vorfall (Hermines-Grenzen, 2026-08-24):
    Kapitel 1 bis 3 einer Geschichte begannen direkt mit Fliesstext ohne jede
    Ueberschrift, Kapitel 4 hatte dagegen eine (wenn auch abweichend in
    Markdown-Fettdruck statt reinem Text). Ohne Ueberschrift zeigt "Pruefen &
    Anwenden" fuer das betroffene Kapitel nur den generischen "## Kapitel N"-
    Platzhalter ohne erkennbaren Titel (siehe frontend/src/utils/
    kapitelKombiniert.ts), und die Gliederung geht verloren.

    Erkennt auch eine bereits vorhandene, nur abweichend formatierte
    Ueberschrift (z.B. mit Markdown-Fettdruck) und fasst sie NICHT an - nur
    eine wirklich fehlende Ueberschrift wird ergaenzt. `kapitel_block` ist
    der Kapitelplan-Textblock dieses Kapitels (kapitel_block_erkennen()) -
    fehlt er (kein Kapitelplan-Eintrag gefunden), wird nichts eingefuegt, um
    keine falsche oder leere Ueberschrift zu erzeugen."""
    if not kapitel_block or _KAPITEL_UEBERSCHRIFT_VORHANDEN_MUSTER.match(text):
        return text, []
    treffer = _KAPITELPLAN_UEBERSCHRIFT_MUSTER.search(kapitel_block)
    if not treffer:
        return text, []
    ueberschrift = treffer.group(0).strip()
    finding = Finding(
        "kapitelueberschrift_fehlt",
        f"Der Text begann ohne die vorgeschriebene Kapitelüberschrift - "
        f"'{ueberschrift}' aus dem Kapitelplan automatisch ergänzt.",
        schwere="info",
    )
    return f"{ueberschrift}\n\n{text}", [finding]


_KAPITEL_UEBERSCHRIFT_MUSTER = re.compile(r"^\s*Kapitel\s+\S+\s*:", re.IGNORECASE | re.MULTILINE)


def kapitel_neustart_abschneiden(text: str) -> tuple[str, list[Finding]]:
    """Eine zweite Kapitelueberschrift im selben Kapiteltext kommt in einer
    echten, korrekten Fortsetzung nie vor - zuverlaessiges Stopp-Signal
    dafuer, dass das Modell neu angefangen statt fortgesetzt hat."""
    treffer = list(_KAPITEL_UEBERSCHRIFT_MUSTER.finditer(text))
    if len(treffer) <= 1:
        return text, []
    grenze = treffer[1].start()
    finding = Finding(
        "kapitel_neustart",
        "Die Kapitelüberschrift wurde ein zweites Mal gefunden - das Modell "
        "hat vermutlich neu angefangen statt fortzusetzen. Text ab der "
        "zweiten Überschrift automatisch abgeschnitten.",
    )
    return text[:grenze].rstrip(), [finding]


_KAPITEL_ENDE_ERKLAERUNG_MUSTER = re.compile(
    r"(das kapitel (endete|endet|ist zu ende|erreichte seinen abschluss)|"
    r"und damit (endete|hatte) (das )?kapitel)",
    re.IGNORECASE,
)


def vorzeitige_kapitelende_abschneiden(text: str, mindest_rest: int = 50) -> tuple[str, list[Finding]]:
    treffer = _KAPITEL_ENDE_ERKLAERUNG_MUSTER.search(text)
    if not treffer:
        return text, []
    satzende = text.find(".", treffer.end())
    grenze = satzende + 1 if satzende != -1 else treffer.end()
    rest = text[grenze:].strip()
    if woerter(rest) < mindest_rest:
        return text, []
    finding = Finding(
        "vorzeitiges_kapitelende",
        f"Der Text erklärt sich mitten drin selbst für beendet "
        f"(Fundstelle: '{treffer.group(0)}'), schreibt danach aber noch "
        f"{woerter(rest)} Wörter weiter - vermutlich eine ungeplante neue "
        f"Szene nach einer Fortsetzung. Text ab dieser Stelle automatisch "
        f"abgeschnitten.",
    )
    return text[:grenze].rstrip(), [finding]


def fuehrende_duplikate_entfernen(bisheriger_text: str, fortsetzung: str,
                                   max_fenster: int = 4) -> tuple[str, list[Finding]]:
    """Prueft, ob die ERSTEN k Absaetze der Fortsetzung mit den LETZTEN k
    Absaetzen des bisherigen Texts uebereinstimmen, fuer absteigende
    Fenstergroessen, und entfernt den groessten gefundenen Treffer."""
    bisherige = [a for a in bisheriger_text.split("\n\n") if a.strip()]
    neue = [a for a in fortsetzung.split("\n\n") if a.strip()]

    fenster_max = min(max_fenster, len(bisherige), len(neue))
    for k in range(fenster_max, 0, -1):
        alte_fenster = bisherige[-k:]
        neue_fenster = neue[:k]
        aehnlichkeiten = [
            difflib.SequenceMatcher(None, a.strip(), b.strip()).ratio()
            for a, b in zip(alte_fenster, neue_fenster)
        ]
        if min(aehnlichkeiten) > 0.75:
            finding = Finding(
                "fuehrende_duplikate",
                f"{k} wiederholte(r) Absatz/Absätze aus der Fortsetzung "
                f"entfernt (Modell hat trotz Anweisung dupliziert).",
                schwere="info",
            )
            return "\n\n".join(neue[k:]), [finding]

    return fortsetzung, []


def interne_wiederholung_abschneiden(text: str, min_fenster: int = 2, max_fenster: int = 10,
                                      mindest_wiederholungen: int = 3) -> tuple[str, list[Finding]]:
    """Erkennt einen Absatzblock, den das Modell INNERHALB EINES generierten
    Texts mehrfach hintereinander (fast) identisch wiederholt hat - eine
    haengengebliebene Generierungsschleife, anders als
    fuehrende_duplikate_entfernen() (Ueberlappung zwischen ZWEI
    Fortsetzungs-Aufrufen). Schneidet nach der ERSTEN Kopie des Blocks ab."""
    absaetze = [a for a in text.split("\n\n") if a.strip()]
    n = len(absaetze)
    for k in range(min_fenster, min(max_fenster, n // mindest_wiederholungen) + 1):
        for i in range(0, n - k * mindest_wiederholungen + 1):
            basis = absaetze[i:i + k]
            wiederholungen = 1
            j = i + k
            while j + k <= n:
                kandidat = absaetze[j:j + k]
                aehnlichkeiten = [
                    difflib.SequenceMatcher(None, a.strip(), b.strip()).ratio()
                    for a, b in zip(basis, kandidat)
                ]
                if min(aehnlichkeiten) > 0.8:
                    wiederholungen += 1
                    j += k
                else:
                    break
            if wiederholungen >= mindest_wiederholungen:
                gekuerzt = "\n\n".join(absaetze[:i + k])
                finding = Finding(
                    "interne_wiederholung",
                    f"Modell hat einen Textblock ({k} Absatz/Absätze) {wiederholungen}x "
                    f"hintereinander wiederholt (hängengebliebene Generierung) - "
                    f"Text nach der ersten Kopie automatisch abgeschnitten.",
                )
                return gekuerzt, [finding]
    return text, []


def wiederholten_absatzblock_ausschneiden(text: str, min_fenster: int = 2, max_fenster: int = 10,
                                           max_luecke_faktor: int = 3) -> tuple[str, list[Finding]]:
    """Erkennt einen groesseren Absatzblock (>= min_fenster Absaetze), den das
    Modell an einer SPAETEREN, NICHT unmittelbar angrenzenden Stelle im
    selben Kapitel noch einmal (fast) wortgleich erzaehlt hat - z.B. weil es
    eine Szene neu aufgerollt statt fortgesetzt hat (realer Vorfall: Kapitel
    4 von "Das-Echo-der-Verpflichtung-Ein-Geheimnis-in-Winterbottom-Hall" -
    ein 5-Absatz-Dialogblock kehrte nach 4 andersformulierten, aber
    inhaltlich redundanten Zwischenabsaetzen fast wortgleich zurueck).
    interne_wiederholung_abschneiden() findet solche Faelle NICHT: sie
    vergleicht nur den unmittelbar naechsten Block (j = i + k), die anders
    formulierten Zwischenabsaetze reissen die Kette dort sofort ab.
    Deshalb hier eine begrenzte Vorschau (max_luecke_faktor * Fenstergroesse)
    statt strikter Adjazenz. Bei einem so grossen Block ist bereits EINE
    Wiederholung (zwei Kopien) ein zuverlaessiges Signal - anders als bei
    interne_wiederholung_abschneiden(), wo ein einzelner kurzer Absatz auch
    ein bewusst gesetzter Stil-Refrain sein kann (siehe dortige Tests).
    min_fenster=2 (statt urspruenglich 3) schliesst eine beobachtete Luecke:
    ein KURZER, nur 2-Absatz-Dialogschnipsel (z.B. eine wiederholte
    Reaktions-/Antwort-Zeile), der spaeter im Kapitel noch einmal auftaucht,
    fiel bei min_fenster=3 durchs Raster, weil weder diese Funktion (Block zu
    kurz) noch interne_wiederholung_abschneiden() (nicht 3x unmittelbar
    hintereinander) ihn erfasste. Ein einzelner, isolierter 1-Absatz-Refrain
    bleibt weiterhin bewusst unangetastet (siehe
    test_wiederholten_absatzblock_ausschneiden_ignoriert_kurzen_refrain).
    Schneidet NUR den Bereich zwischen dem Ende der ersten und dem Ende der
    zweiten Kopie heraus (statt wie interne_wiederholung_abschneiden() den
    gesamten Rest des Texts zu verwerfen): nach einer solchen Neuaufrollung
    schreibt das Modell oft trotzdem echte neue Handlung weiter, anders als
    bei der haengengebliebenen Endlosschleife bis zum Generierungsende, die
    interne_wiederholung_abschneiden() behandelt.
    Prueft absteigend nach Fenstergroesse (groesster Block zuerst), damit ein
    gefundener Treffer den vollen redundanten Bereich abdeckt statt nur ein
    kleineres Teilstueck davon (jede Teilmenge eines passenden Blocks passt
    zwangslaeufig ebenfalls)."""
    absaetze = [a for a in text.split("\n\n") if a.strip()]
    n = len(absaetze)
    for k in range(min(max_fenster, n // 2), min_fenster - 1, -1):
        max_luecke = k * max_luecke_faktor
        for i in range(0, n - k + 1):
            basis = absaetze[i:i + k]
            ende_suche = min(i + k + max_luecke, n - k)
            for j in range(i + k, ende_suche + 1):
                kandidat = absaetze[j:j + k]
                aehnlichkeiten = [
                    difflib.SequenceMatcher(None, a.strip(), b.strip()).ratio()
                    for a, b in zip(basis, kandidat)
                ]
                if min(aehnlichkeiten) > 0.8:
                    rest = absaetze[:i + k] + absaetze[j + k:]
                    gekuerzt = "\n\n".join(rest)
                    finding = Finding(
                        "wiederholter_absatzblock",
                        f"Modell hat einen Absatzblock ({k} Absatz/Absätze) an einer "
                        f"späteren Stelle im Kapitel noch einmal fast wortgleich "
                        f"erzählt - wiederholten Mittelteil automatisch entfernt.",
                    )
                    return gekuerzt, [finding]
    return text, []


def alle_nachbearbeitungs_checks(text: str, geruest: str, stufe: str) -> list[Finding]:
    """Buendelt alle rein lesenden Pruefungen (keine Textveraenderung), wie
    sie novelle.py am Ende von cmd_schreiben/cmd_lektorieren aufruft."""
    findings: list[Finding] = []
    findings += sprachdrift_pruefen(text)
    findings += sprachdrift_lokal_pruefen(text)
    findings += erzaehlperspektive_pruefen(text, geruest)
    findings += anredeform_pruefen(text)
    findings += ausweichformulierungen_pruefen(text)
    findings += explizitheit_pruefen(text, stufe)
    return findings


# ---------------------------------------------------------------------------
# Rechtschreibpruefung via hunspell (externe Systemabhaengigkeit, Linux-only)
# ---------------------------------------------------------------------------

def _lokal_ausfuehren(cmd: list[str], stdin_text: str) -> tuple[int, str, str]:
    ergebnis = subprocess.run(
        cmd, input=stdin_text, capture_output=True, text=True, timeout=30,
        env={**os.environ, "LC_ALL": "C.UTF-8"},
    )
    return ergebnis.returncode, ergebnis.stdout, ergebnis.stderr


def hunspell_unbekannte_woerter(text: str, exec_fn: ExecFn | None = None) -> list[str] | None:
    """Liefert None bei Fehler/nicht verfuegbar (unterscheidet sich bewusst
    von einer leeren Liste = sauber geprueft). Auf Windows-Entwicklungs-
    rechnern ist hunspell lokal i.d.R. nicht vorhanden - exec_fn kann dann
    ssh_manager.exec_command uebergeben werden, um den Aufruf auf dem
    konfigurierten Linux-Zielserver auszufuehren (siehe app/core/ssh_manager.py)."""
    ausfuehren = exec_fn or _lokal_ausfuehren
    try:
        code, stdout, stderr = ausfuehren(["hunspell", "-d", "de_DE", "-l"], text)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None

    if code != 0 and not stdout:
        return None

    unbekannt = sorted(set(
        w.strip().strip(".,;:!?…") for w in stdout.splitlines()
    ))
    return [w for w in unbekannt if len(w) > 2]


def wort_position_finden(text: str, wort: str) -> tuple[int, int] | None:
    """Zeichen-Offsets (start, end) der ERSTEN Fundstelle von `wort` als
    eigenes Wort in `text`, oder None. Fuer den Sprung-zur-Stelle-Klick im
    Frontend (siehe RechtschreibWort.start/end) - im Unterschied zu
    fundstellen.finde_fundstelle() genuegt hier ein simpler Wortgrenzen-
    Abgleich, da hunspell-Woerter (anders als LLM-Zitate) immer exakt
    denselben Text widerspiegeln, gegen den geprueft wurde."""
    treffer = re.search(r"\b" + re.escape(wort) + r"\b", text)
    return (treffer.start(), treffer.end()) if treffer else None


def satz_mit_wort_finden(text: str, wort: str, max_laenge: int = 220) -> str | None:
    """Fuer die interaktive Rechtschreib-Durchsicht: Satz mit Kontext um den
    Fund herum, gekuerzt auf max_laenge Zeichen."""
    saetze = re.split(r"(?<=[.!?])\s+", text)
    muster = re.compile(r"\b" + re.escape(wort) + r"\b")
    for satz in saetze:
        treffer = muster.search(satz)
        if treffer:
            satz = satz.strip()
            if len(satz) > max_laenge:
                pos = treffer.start()
                start = max(0, pos - max_laenge // 2)
                ende = min(len(satz), pos + max_laenge // 2)
                satz = (("..." if start > 0 else "") + satz[start:ende]
                        + ("..." if ende < len(satz) else ""))
            return satz
    return None
