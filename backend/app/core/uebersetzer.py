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

import hashlib
import io
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.analysator import KAPITEL_STICHWORT_MUSTER, analysen_ordner
from app.core.import_bereinigung import fuelltexte_entfernen
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


def ueberschrift_normalisieren(text: str) -> str:
    """Glaettet eine uebersetzte Kapitelueberschrift ohne KI: entfernt Markdown-Zusaetze,
    die das Modell von sich aus ergaenzt ('# Kapitel eins', '**Kapitel drei**'), schreibt
    das Zahlwort klein ('Kapitel Acht' -> 'Kapitel acht') und entfernt PDF-Artefakte aus
    der Quelle ('(2 von 3 ¾?)' -> '(2 von 3)')."""
    zeile = text.strip().lstrip("#*_ \t").rstrip("*_ \t").replace("�", "")
    zeile = re.sub(r"\s*¾?\?+\s*\)", ")", zeile)
    return re.sub(
        r"^(Kapitel|Teil)\s+([A-Za-zÄÖÜäöüß]+)",
        lambda m: f"{m.group(1).capitalize()} {m.group(2).lower()}",
        zeile, count=1, flags=re.IGNORECASE,
    )


def absaetze_der_antwort(antwort: str) -> list[str]:
    return [a.strip() for a in re.split(r"\n\s*\n", antwort) if a.strip()]


def dateiname_de(dateiname: str) -> str:
    """'Geschichte.pdf' -> 'Geschichte_de.pdf', 'Notiz' -> 'Notiz_de.txt'."""
    pfad = Path(dateiname)
    endung = pfad.suffix.lower() if pfad.suffix.lower() in (".txt", ".md", ".pdf") else ".txt"
    basis = re.sub(r"_de$", "", pfad.stem if pfad.suffix else pfad.name)
    basis = re.sub(r"[\\/:*?\"<>|]+", "-", basis).strip(" .") or "Uebersetzung"
    return f"{basis}_de{endung}"


# --- Planung: Kapitel, Zwischenstaende, Fortsetzen ----------------------------

BLOCK_WOERTER = 3000  # Zwischenstands-Block, wenn der Text keine Kapitel hat
_TRENNER_ZEILE = re.compile(r"^[\s\*\-_=~#•·.]{3,}$")


def einheiten_bilden(text: str) -> tuple[list[str], str]:
    """(Absaetze, Absatztrenner des Originals). Eine 'Einheit' ist ein Absatz
    (durch Leerzeile getrennt, sonst eine Zeile); jede Einheit wird zu genau
    EINER uebersetzten Einheit - darauf beruht das Fortsetzen."""
    text = text.replace("\r\n", "\n").strip()
    trenner = trenner_fuer(text)
    return [a.strip() for a in text.split(trenner) if a.strip()], trenner


def quell_hash(einheiten: list[str]) -> str:
    return hashlib.sha1("\n".join(einheiten).encode("utf-8")).hexdigest()


@dataclass
class Kapitel:
    titel: str
    start: int  # Index der ersten Einheit
    ende: int  # Index NACH der letzten Einheit


def kapitel_einteilen(einheiten: list[str]) -> list[Kapitel]:
    """Kapitel anhand der Ueberschriften ('Chapter 3', 'Kapitel drei', Prolog ...),
    mindestens zwei. Ohne Kapitel entstehen Bloecke von rund BLOCK_WOERTER Woertern,
    bevorzugt an einem Szenentrenner ('***', '---'), sonst an einer Absatzgrenze -
    damit es auch dann sinnvolle Zwischenstaende gibt."""
    if not einheiten:
        return []
    kopf = [i for i, e in enumerate(einheiten) if "\n" not in e and KAPITEL_STICHWORT_MUSTER.fullmatch(e)]
    if len(kopf) >= 2:
        grenzen = kopf if kopf[0] == 0 else [0] + kopf
        return [
            Kapitel(einheiten[start][:80] if start in kopf else "Vorspann", start,
                    grenzen[n + 1] if n + 1 < len(grenzen) else len(einheiten))
            for n, start in enumerate(grenzen)
        ]
    bloecke: list[Kapitel] = []
    start = 0
    summe = 0
    for i, e in enumerate(einheiten):
        summe += woerter(e)
        if (_TRENNER_ZEILE.match(e) and summe >= 0.7 * BLOCK_WOERTER) or summe >= 1.3 * BLOCK_WOERTER:
            bloecke.append(Kapitel(f"Teil {len(bloecke) + 1}", start, i + 1))
            start, summe = i + 1, 0
    if start < len(einheiten):
        if bloecke and summe < 0.3 * BLOCK_WOERTER:
            bloecke[-1].ende = len(einheiten)  # kleiner Rest haengt am letzten Block
        else:
            bloecke.append(Kapitel(f"Teil {len(bloecke) + 1}", start, len(einheiten)))
    return bloecke


@dataclass
class Schritt:
    kapitel: int  # Index in der Kapitelliste
    absaetze: list[str]
    ende: int  # Index NACH der letzten Einheit dieses Schritts
    kapitel_ende: bool  # letzter Schritt seines Kapitels


def plan_bauen(einheiten: list[str], kapitel: list[Kapitel], bereits_fertig: int = 0,
               max_woerter: int = CHUNK_WOERTER) -> list[Schritt]:
    """Uebersetzungs-Schritte (je ein KI-Aufruf), die nie ueber eine Kapitelgrenze
    gehen. bereits_fertig = Zahl der schon uebersetzten Einheiten (Fortsetzen):
    deren Schritte entfallen, der Rest wird neu in Schritte geteilt."""
    schritte: list[Schritt] = []
    for k, kap in enumerate(kapitel):
        lo = max(kap.start, bereits_fertig)
        if lo >= kap.ende:
            continue
        aktuell: list[str] = []
        aktuelle_woerter = 0
        position = lo
        for i in range(lo, kap.ende):
            anzahl = woerter(einheiten[i])
            if aktuell and aktuelle_woerter + anzahl > max_woerter:
                schritte.append(Schritt(k, aktuell, position, False))
                aktuell, aktuelle_woerter = [], 0
            aktuell.append(einheiten[i])
            aktuelle_woerter += anzahl
            position = i + 1
        if aktuell:
            schritte.append(Schritt(k, aktuell, position, True))
    return schritte


def fertige_kapitel(kapitel: list[Kapitel], einheiten_fertig: int) -> tuple[int, int]:
    """(Zahl vollstaendig uebersetzter Kapitel, Einheiten am Ende des letzten davon)."""
    fertig = [k for k in kapitel if k.ende <= einheiten_fertig]
    return len(fertig), (fertig[-1].ende if fertig else 0)


def kapitel_datei_schreiben(projekte_wurzel: Path, ziel_name: str, nummer: int, text: str) -> None:
    """Legt jedes fertige Kapitel zusaetzlich als eigene Datei ab:
    Uebersetzungen/<name>_de_Kapitel/Kapitel_01.txt - zum Zwischendurch-Lesen,
    lokal direkt im Dateisystem."""
    basis = Path(ziel_name).stem
    ziel = ordner(projekte_wurzel) / f"{basis}_Kapitel"
    ziel.mkdir(parents=True, exist_ok=True)
    (ziel / f"Kapitel_{nummer:02d}.txt").write_text(text + "\n", encoding="utf-8")


def ergebnis_text(projekte_wurzel: Path, status: dict[str, Any], nur_fertige_kapitel: bool = False) -> str:
    """Der bisher uebersetzte Text; mit nur_fertige_kapitel nur bis zum Ende des
    letzten vollstaendig uebersetzten Kapitels (Zwischenstand zum Lesen)."""
    name = status.get("dateiname")
    if not name:
        raise FileNotFoundError("Es gibt noch keine Übersetzung.")
    text_datei = name[:-4] + ".txt" if name.endswith(".pdf") else name
    pfad = ergebnis_pfad(projekte_wurzel, text_datei)
    if not pfad.is_file():
        raise FileNotFoundError("Das Ergebnis der Übersetzung wurde nicht gefunden.")
    text = pfad.read_text(encoding="utf-8")
    if not nur_fertige_kapitel:
        return text
    trenner = status.get("trenner") or trenner_fuer(text)
    einheiten = [a for a in text.split(trenner) if a.strip()][: int(status.get("zwischenstand_einheiten") or 0)]
    if not einheiten:
        raise FileNotFoundError("Es ist noch kein Kapitel vollständig übersetzt.")
    return trenner.join(einheiten) + "\n"


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
    # Kapitelweise Zwischenstaende und Fortsetzen
    "kapitel_gesamt": 0, "kapitel_fertig": 0, "zwischenstand_einheiten": 0,
    "woerter_gesamt": 0, "woerter_fertig": 0,
    "fuelltext_entfernen": False, "quell_hash": None, "trenner": "\n\n", "fortgesetzt": False,
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
    job_speichern(projekte_wurzel, status)


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
    # Auch die Job-Eintraege (jobs/<fingerabdruck>.json): sonst bliebe ein verwaister Lauf dort
    # fuer immer "laeuft" und ließe sich nie fortsetzen.
    for pfad in projects_root.rglob(f"{ERGEBNIS_ORDNERNAME}/{JOBS_ORDNERNAME}/*.json"):
        try:
            job = json.loads(pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if job.get("laeuft"):
            job["laeuft"] = False
            job["gestoppt"] = True
            job["log"] = list(job.get("log", [])) + ["Durch einen Backend-Neustart unterbrochen."]
            pfad.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    return zurueck


# --- Jobs nach Textinhalt (Fortsetzen unabhaengig vom Dateinamen) -------------------

JOBS_ORDNERNAME = "jobs"


def _job_datei(projekte_wurzel: Path, quell_hash_wert: str) -> Path:
    jobs = ordner(projekte_wurzel) / JOBS_ORDNERNAME
    jobs.mkdir(parents=True, exist_ok=True)
    return jobs / f"{quell_hash_wert[:16]}.json"


def job_speichern(projekte_wurzel: Path, status: dict[str, Any]) -> None:
    """Haelt den Stand jeder Uebersetzung zusaetzlich unter dem Fingerabdruck des
    ORIGINALTEXTES fest (status.json beschreibt nur die zuletzt gestartete). So laesst
    sich eine unterbrochene Uebersetzung wiederfinden, egal unter welchem Namen oder
    aus welcher Quelle (Datei, gespeicherter Rohtext, eingefuegt) der Text geoeffnet wird."""
    if status.get("quell_hash"):
        _job_datei(projekte_wurzel, status["quell_hash"]).write_text(
            json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8",
        )


def job_lesen(projekte_wurzel: Path, quell_hash_wert: str) -> dict[str, Any] | None:
    pfad = _job_datei(projekte_wurzel, quell_hash_wert)
    if not pfad.is_file():
        return None
    try:
        return {**LEERER_STATUS, **json.loads(pfad.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return None


def fortsetzbaren_job_finden(projekte_wurzel: Path, text: str) -> dict[str, Any] | None:
    """Unterbrochene (nicht fertige, nicht laufende) Uebersetzung GENAU dieses Textes -
    mit und ohne Fuelltext-Entfernung geprueft, passend zur Einstellung des Jobs."""
    for entfernen in (True, False):
        pruef = fuelltexte_entfernen(text, KAPITEL_STICHWORT_MUSTER)[0] if entfernen else text
        einheiten, _trenner = einheiten_bilden(pruef)
        if not einheiten:
            continue
        job = job_lesen(projekte_wurzel, quell_hash(einheiten))
        if (job and not job["abgeschlossen"] and not job["laeuft"] and job["ergebnis_woerter"] > 0
                and bool(job.get("fuelltext_entfernen")) == entfernen and job.get("dateiname")):
            name = job["dateiname"]
            if ergebnis_pfad(projekte_wurzel, name[:-4] + ".txt" if name.endswith(".pdf") else name).is_file():
                return job
    return None


def alten_job_registrieren(projekte_wurzel: Path, text: str, fuelltext_entfernen: bool) -> bool:
    """Einmalige Uebernahme eines Standes der ERSTEN Version (kein quell_hash): ordnet die
    zuletzt gestartete, nicht fertige Uebersetzung dem uebergebenen Text zu, damit sie sich
    ueber den Inhalt fortsetzen laesst. Der Aufrufer muss sicher sein, dass der Text zu dieser
    Uebersetzung gehoert (die Ergebnisdatei wird nur gezaehlt, nicht verglichen)."""
    status = status_lesen(projekte_wurzel)
    if status["abgeschlossen"] or status["laeuft"] or status.get("quell_hash") or not status.get("dateiname"):
        return False
    pruef = fuelltexte_entfernen(text, KAPITEL_STICHWORT_MUSTER)[0] if fuelltext_entfernen else text
    einheiten, trenner = einheiten_bilden(pruef)
    if not einheiten:
        return False
    status.update(quell_hash=quell_hash(einheiten), fuelltext_entfernen=fuelltext_entfernen, trenner=trenner,
                  gestoppt=True, stop_angefordert=False)
    status_schreiben(projekte_wurzel, status, behalte_stop=False)
    return True


def ergebnis_sichern(projekte_wurzel: Path, text_datei: str) -> str | None:
    """Beginnt eine Uebersetzung neu, obwohl die Ergebnisdatei schon Inhalt hat: die alte
    Datei wird NICHT ueberschrieben, sondern als '<name>.vorher-<zeit>' beiseite gelegt."""
    pfad = ergebnis_pfad(projekte_wurzel, text_datei)
    if not pfad.is_file() or pfad.stat().st_size == 0:
        return None
    ziel = pfad.with_name(f"{pfad.stem}.vorher-{time.strftime('%Y%m%d-%H%M%S')}{pfad.suffix}")
    pfad.rename(ziel)
    return ziel.name


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
