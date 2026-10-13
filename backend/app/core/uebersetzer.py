"""Uebersetzer: bringt ein im Analysator geoeffnetes Dokument ins Deutsche
(Absatz fuer Absatz, Format bleibt erhalten) und speichert es als "<name>_de".
Framework-frei wie app/core/analysator.py - die Orchestrierung (Ollama-Aufrufe,
Hintergrund-Task, Status-Polling) lebt in app/api/analysator.py.

Ablauf: optional Fuelltext entfernen (app/core/import_bereinigung.py), den Text
in Abschnitte von rund CHUNK_WOERTER Woertern teilen (nie mitten im Absatz),
je Abschnitt EIN Ollama-Aufruf mit der Rolle "analysator". Stimmt die Zahl der
Absaetze in der Antwort nicht mit dem Original ueberein (das Modell hat etwas
zusammengefasst oder geteilt), wird dieser Abschnitt absatzweise wiederholt -
so geht nichts verloren und das Format bleibt stabil. Das Ergebnis wird nach
JEDEM Abschnitt gespeichert, ein Abbruch behaelt die bisherige Uebersetzung."""
from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Any

from app.core.analysator import analysen_ordner
from app.core.textutil import woerter

CHUNK_WOERTER = 900
ERGEBNIS_ORDNERNAME = "Uebersetzungen"
STATUS_DATEINAME = "status.json"
# Grobe Erfahrung: ein Abschnitt braucht mit Mistral-Small rund 2-3 Minuten
MINUTEN_JE_ABSCHNITT = 3

SYSTEM = (
    "Du bist ein professioneller Literaturübersetzer (Englisch nach Deutsch). Übersetze den Text vollständig, "
    "originalgetreu und stilistisch passend in natürliches, gut lesbares Deutsch.\n\n"
    "Regeln:\n"
    "- Gib NUR die Übersetzung aus: keine Einleitung, keine Anmerkung, keine Erklärung, keine Code-Blöcke.\n"
    "- Behalte die Absätze exakt bei: genau so viele Absätze (durch Leerzeilen getrennt) wie im Original. "
    "Fasse nichts zusammen, lass nichts weg, füge nichts hinzu, teile oder verbinde keine Absätze.\n"
    "- Behalte Markdown-Auszeichnungen (#, **, *, ---) und die Zeilenstruktur unverändert.\n"
    "- Eigennamen von Personen, Orten, Zaubersprüchen und erfundenen Begriffen bleiben unverändert. Anreden wie "
    "Lord, Lady, Sir, Mr., Mrs. bleiben stehen.\n"
    "- Kapitelüberschriften übersetzt du in die deutsche Form: \"Chapter Three\" wird \"Kapitel drei\", "
    "\"Chapter 3: The Storm\" wird \"Kapitel 3: Der Sturm\"; sie bleiben eine eigene Zeile.\n"
    "- Wörtliche Rede setzt du in deutsche Anführungszeichen („…“).\n"
    "- Inhalt, Ton und Deutlichkeit des Originals bleiben unverändert: nichts abschwächen, nichts weglassen, "
    "nichts kommentieren.\n"
    "- Ist ein Absatz bereits deutsch, gib ihn unverändert aus."
)


def abschnitte_bilden(text: str, max_woerter: int = CHUNK_WOERTER) -> list[list[str]]:
    """Teilt den Text in Abschnitte aus ganzen Absaetzen (Absatz = durch
    Leerzeile getrennt, sonst eine Zeile). Jeder Abschnitt ist eine Liste von
    Absaetzen, zusammen rund max_woerter Woerter (ein einzelner laengerer
    Absatz bildet einen eigenen Abschnitt)."""
    text = text.replace("\r\n", "\n").strip()
    trenner = "\n\n" if "\n\n" in text else "\n"
    absaetze = [a.strip() for a in text.split(trenner) if a.strip()]
    abschnitte: list[list[str]] = []
    aktuell: list[str] = []
    aktuelle_woerter = 0
    for absatz in absaetze:
        anzahl = woerter(absatz)
        if aktuell and aktuelle_woerter + anzahl > max_woerter:
            abschnitte.append(aktuell)
            aktuell, aktuelle_woerter = [], 0
        aktuell.append(absatz)
        aktuelle_woerter += anzahl
    if aktuell:
        abschnitte.append(aktuell)
    return abschnitte


def trenner_fuer(text: str) -> str:
    """Absatztrenner des Originals - damit der Ausgabetext dasselbe Format hat."""
    return "\n\n" if "\n\n" in text.replace("\r\n", "\n") else "\n"


def user_text(absaetze: list[str]) -> str:
    return "Übersetze den folgenden Text ins Deutsche:\n\n" + "\n\n".join(absaetze)


_CODEBLOCK = re.compile(r"^```[a-z]*\s*\n?|\n?```\s*$", re.IGNORECASE)
_VORSPANN = re.compile(r"^(?:Hier ist die Übersetzung|Übersetzung|Translation)\s*:?\s*\n+", re.IGNORECASE)


def antwort_bereinigen(antwort: str) -> str:
    """Entfernt Code-Zaeune und einen Vorspann ('Hier ist die Übersetzung:')."""
    text = _CODEBLOCK.sub("", antwort.strip()).strip()
    return _VORSPANN.sub("", text).strip()


def absaetze_der_antwort(antwort: str) -> list[str]:
    return [a.strip() for a in re.split(r"\n\s*\n", antwort) if a.strip()]


def dateiname_de(dateiname: str) -> str:
    """'Geschichte.pdf' -> 'Geschichte_de.pdf', 'Notiz' -> 'Notiz_de.txt'."""
    pfad = Path(dateiname)
    endung = pfad.suffix.lower() if pfad.suffix.lower() in (".txt", ".md", ".pdf") else ".txt"
    basis = re.sub(r"_de$", "", pfad.stem if pfad.suffix else pfad.name)
    basis = re.sub(r"[\\/:*?\"<>|]+", "-", basis).strip(" .") or "Uebersetzung"
    return f"{basis}_de{endung}"


# --- Status/Ergebnis (eine Uebersetzung je Benutzer) -----------------------

def ordner(projekte_wurzel: Path) -> Path:
    o = analysen_ordner(projekte_wurzel) / ERGEBNIS_ORDNERNAME
    o.mkdir(parents=True, exist_ok=True)
    return o


def _status_datei(projekte_wurzel: Path) -> Path:
    return ordner(projekte_wurzel) / STATUS_DATEINAME


LEERER_STATUS: dict[str, Any] = {
    "laeuft": False, "abgeschlossen": False, "gestoppt": False, "stop_angefordert": False,
    "aktuell": 0, "gesamt": 0, "log": [], "fehler": None, "dateiname": None,
    "ergebnis_woerter": 0, "fuelltext_entfernt": 0,
}


def status_lesen(projekte_wurzel: Path) -> dict[str, Any]:
    pfad = _status_datei(projekte_wurzel)
    if not pfad.exists():
        return dict(LEERER_STATUS, log=[])
    try:
        return {**LEERER_STATUS, **json.loads(pfad.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(LEERER_STATUS, log=[])


def status_schreiben(projekte_wurzel: Path, status: dict[str, Any], behalte_stop: bool = True) -> None:
    """Ein per Stop-Endpunkt gesetztes stop_angefordert darf von einem
    laufenden Schreibvorgang nicht ueberschrieben werden (siehe
    app/api/pipeline.py:_automatik_status_schreiben) - deshalb ODER mit dem
    Stand der Datei."""
    pfad = _status_datei(projekte_wurzel)
    if behalte_stop and pfad.exists():
        try:
            status["stop_angefordert"] = bool(
                status.get("stop_angefordert") or json.loads(pfad.read_text(encoding="utf-8")).get("stop_angefordert")
            )
        except (OSError, ValueError):
            pass
    pfad.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def ergebnis_pfad(projekte_wurzel: Path, dateiname: str) -> Path:
    return ordner(projekte_wurzel) / Path(dateiname).name


def verwaiste_laeufe_zuruecksetzen(projects_root: Path) -> int:
    """Nach einem Backend-Neustart kann kein Uebersetzungs-Lauf mehr aktiv sein
    (analog app/core/automatik.py:verwaiste_laeufe_zuruecksetzen)."""
    zurueck = 0
    for pfad in projects_root.rglob(f"{ERGEBNIS_ORDNERNAME}/{STATUS_DATEINAME}"):
        try:
            status = json.loads(pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if status.get("laeuft"):
            status["laeuft"] = False
            status["gestoppt"] = True
            status["log"] = list(status.get("log", [])) + ["Durch einen Backend-Neustart unterbrochen."]
            pfad.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
            zurueck += 1
    return zurueck


# --- PDF ------------------------------------------------------------------

_FETT = re.compile(r"\*\*(.+?)\*\*")
_KURSIV = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_UEBERSCHRIFT = re.compile(r"^(?:#{1,6}\s*)?\**\s*(Kapitel\s+\S+.*|Prolog\b.*|Epilog\b.*)\**\s*$", re.IGNORECASE)


def text_pdf_erzeugen(titel: str, text: str) -> bytes:
    """Einfaches, gut lesbares A4-PDF aus dem Uebersetzungstext (Schrift DejaVu
    Serif, damit Umlaute und Sonderzeichen stimmen - siehe app/core/pdf_export.py)."""
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    from app.core import pdf_export  # registriert die DejaVu-Schriften beim Import

    normal = ParagraphStyle("txt", fontName=pdf_export._SCHRIFT_NORMAL, fontSize=10.5, leading=15,  # noqa: SLF001
                            alignment=TA_JUSTIFY, spaceAfter=7)
    kopf = ParagraphStyle("kopf", parent=normal, fontName=pdf_export._SCHRIFT_FETT, fontSize=15, leading=20,  # noqa: SLF001
                          alignment=TA_CENTER, spaceBefore=18, spaceAfter=12)
    puffer = io.BytesIO()
    doc = SimpleDocTemplate(puffer, pagesize=A4, leftMargin=2.4 * cm, rightMargin=2.4 * cm,
                            topMargin=2.2 * cm, bottomMargin=2.2 * cm, title=titel)
    inhalt: list = []
    for absatz in absaetze_der_antwort(text.replace("\r\n", "\n")) if "\n\n" in text else [a for a in text.split("\n") if a.strip()]:
        ueberschrift = _UEBERSCHRIFT.match(absatz.strip())
        roh = pdf_export._escape(absatz.strip().lstrip("#").strip() if ueberschrift else absatz.strip())  # noqa: SLF001
        roh = _FETT.sub(r"<b>\1</b>", roh)
        roh = _KURSIV.sub(r"<i>\1</i>", roh).replace("\n", "<br/>")
        inhalt.append(Paragraph(roh, kopf if ueberschrift else normal))
    if not inhalt:
        inhalt = [Spacer(1, 1)]
    doc.build(inhalt)
    return puffer.getvalue()
