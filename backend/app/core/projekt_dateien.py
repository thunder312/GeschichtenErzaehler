"""Dateizugriff auf Projektordner - portiert aus pre-GUI/novelle.py.

Haelt den Ordnervertrag aus doc/Schnittstellen-Uebersicht.md Abschnitt 1
exakt ein, damit ein mit der GUI erzeugter Projektordner unveraendert mit
der bestehenden novelle.py weiterbearbeitet werden koennte (und umgekehrt).

Unterschied zum CLI: Dort ist der Projektordner das aktuelle Arbeits-
verzeichnis (PROJEKT = Path(cwd)/"projekt"). Die GUI verwaltet mehrere
Projekte parallel, deshalb nehmen alle Funktionen hier den Projektordner
explizit als Parameter entgegen statt ihn aus einer globalen Konstante zu
lesen.
"""
from __future__ import annotations

import logging
import re
import shutil
import time
from pathlib import Path

from app.core import geruest as _geruest
from app.core.textutil import woerter

logger = logging.getLogger(__name__)

EPOCHE_PERSONA_DATEIEN = ("architekt.txt", "autor.txt", "pruefer_anachronismus.txt")
GEMEINSAME_PERSONA_DATEIEN = (
    "chronist.txt", "pruefer_kontinuitaet.txt", "lektor.txt", "pruefer_satzbau.txt",
)


class DateiFehlt(Exception):
    pass


def kapitel_datei(projekt: Path, n: int) -> Path:
    return projekt / f"kapitel_{n:02d}.md"


def stand_datei(projekt: Path, n: int) -> Path:
    return projekt / f"stand_{n:02d}.md"


def befunde_datei(projekt: Path, n: int) -> Path:
    return projekt / f"befunde_{n:02d}.json"


def geruest_datei(projekt: Path) -> Path:
    return projekt / "geruest.md"


def verbotsliste_datei(projekt: Path) -> Path:
    return projekt / "verbotsliste.md"


def architekt_verlauf_datei(projekt: Path) -> Path:
    """Zwischenspeicher fuer ein unterbrochenes Architekten-Gespraech (siehe
    app/api/architekt.py) - existiert nur, waehrend das Interview noch
    laeuft, und wird bei Abschluss oder explizitem Abbruch wieder
    geloescht."""
    return projekt / "architekt_verlauf.json"


def lies(pfad: Path, pflicht: bool = True, ersatz: str = "") -> str:
    if not pfad.exists():
        if pflicht:
            raise DateiFehlt(f"Datei fehlt: {pfad}")
        return ersatz
    return pfad.read_text(encoding="utf-8").strip()


def schreib(pfad: Path, text: str, force: bool = False) -> tuple[Path, str | None]:
    """Schreibt die Datei, sichert eine vorhandene Fassung als .bak (ausser
    force=True). Gibt (Pfad, Name_der_Sicherung_oder_None) zurueck."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    sicherung_name = None
    if pfad.exists() and not force:
        sicherung = pfad.with_suffix(pfad.suffix + f".{int(time.time())}.bak")
        pfad.rename(sicherung)
        sicherung_name = sicherung.name
    pfad.write_text(text + "\n", encoding="utf-8")
    return pfad, sicherung_name


def kapitelnummer_aus_dateiname(pfad: Path) -> int:
    treffer = re.search(r"kapitel_(\d+)\.md$", pfad.name)
    return int(treffer.group(1)) if treffer else -1


def vorhandene_kapitel(projekt: Path) -> list[Path]:
    return sorted(projekt.glob("kapitel_*.md"), key=kapitelnummer_aus_dateiname)


def persona_lesen(projekt: Path, name: str) -> str:
    return lies(projekt / "personas" / f"{name}.txt")


def projekt_anlegen(ziel: Path, epoche_ordner: Path, gemeinsame_personas_ordner: Path,
                     epoche_name: str) -> None:
    """Legt personas/ + projekt/ in ziel an, analog zu novelle.py's
    _projekt_befuellen(). ziel muss bereits existieren oder wird erzeugt."""
    ziel.mkdir(parents=True, exist_ok=True)
    personas_ziel = ziel / "personas"
    personas_ziel.mkdir(exist_ok=True)
    (ziel / "projekt").mkdir(exist_ok=True)

    for datei in EPOCHE_PERSONA_DATEIEN:
        quelle = epoche_ordner / datei
        if quelle.exists():
            shutil.copy(quelle, personas_ziel / datei)
    for datei in GEMEINSAME_PERSONA_DATEIEN:
        quelle = gemeinsame_personas_ordner / datei
        if quelle.exists():
            shutil.copy(quelle, personas_ziel / datei)

    verbotsliste_quelle = epoche_ordner / "verbotsliste.md"
    if verbotsliste_quelle.exists():
        shutil.copy(verbotsliste_quelle, ziel / "projekt" / "verbotsliste.md")

    (ziel / ".epoche").write_text(epoche_name, encoding="utf-8")


def epoche_von_projekt(ziel: Path) -> str | None:
    marker = ziel / ".epoche"
    return marker.read_text(encoding="utf-8").strip() if marker.exists() else None


def woerter_im_kapitel(projekt: Path, n: int) -> int:
    text = lies(kapitel_datei(projekt, n), pflicht=False, ersatz="")
    return woerter(text)


def _freier_pfad(wurzel: Path, name: str) -> Path:
    """Findet einen im Ordner `wurzel` noch freien Namen, ausgehend von
    `name` - haengt bei Kollision -2, -3, ... an (z.B. wenn bereits ein
    Projekt mit demselben aus dem Titel abgeleiteten Namen existiert)."""
    ziel = wurzel / name
    zaehler = 2
    while ziel.exists():
        ziel = wurzel / f"{name}-{zaehler}"
        zaehler += 1
    return ziel


def projektordner_umbenennen(projekt_root: Path, geruest_text: str) -> str | None:
    """Versucht, den Projektordner nach dem im Geruest gewaehlten Titel
    umzubenennen - portiert aus novelle.py's
    _projektordner_nach_titel_umbenennen(). Nur direkt nach dem
    Architekten-Gespraech sinnvoll, solange noch kein Kapitel existiert.
    Gibt den neuen Ordnernamen zurueck, falls umbenannt wurde, sonst None
    (kein Fehler - best effort, wie im Original)."""
    if vorhandene_kapitel(projekt_root / "projekt"):
        return None

    titel = _geruest.titel_erkennen(geruest_text)
    if not titel:
        return None

    neuer_name = _geruest.ordnername_aus_titel(titel)
    if projekt_root.name == neuer_name:
        return None

    neuer_pfad = _freier_pfad(projekt_root.parent, neuer_name)

    # Direkt nach dem Schreiben von geruest.md (siehe Aufrufer) haelt ein
    # Sync-Tool (Dropbox) oder der Windows-Suchindex/Virenscanner die Datei
    # manchmal fuer einen kurzen Moment noch offen - Windows verweigert dann
    # das Umbenennen des Elternordners mit PermissionError(13), obwohl der
    # Zustand Millisekunden spaeter schon wieder frei ist. Mit kurzen,
    # steigenden Wartezeiten erneut versuchen, bevor endgueltig aufgegeben
    # wird (insgesamt ca. 3s), statt beim ersten Versuch schon klein
    # beizugeben.
    letzter_fehler: OSError | None = None
    for wartezeit in (0, 0.1, 0.2, 0.4, 0.8, 1.6):
        if wartezeit:
            time.sleep(wartezeit)
        try:
            projekt_root.rename(neuer_pfad)
            return neuer_pfad.name
        except OSError as e:
            letzter_fehler = e

    logger.warning(
        "Projektordner-Umbenennung fehlgeschlagen nach mehreren Versuchen: %s -> %s (%r)",
        projekt_root, neuer_pfad, letzter_fehler,
    )
    return None
