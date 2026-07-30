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


def alle_nachbearbeitungs_checks(text: str, geruest: str, stufe: str) -> list[Finding]:
    """Buendelt alle rein lesenden Pruefungen (keine Textveraenderung), wie
    sie novelle.py am Ende von cmd_schreiben/cmd_lektorieren aufruft."""
    findings: list[Finding] = []
    findings += sprachdrift_pruefen(text)
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
