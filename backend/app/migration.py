"""Einmalige Layout-Migration beim Uebergang zu Benutzer-Accounts (siehe
ToDo.md Deployment): bestehende Projekte lagen bisher direkt unter der
Speicherort-Wurzel, liegen ab jetzt aber pro Benutzer in einem eigenen
Unterordner (siehe app/services.py:projekte_wurzel). Zusaetzlich zieht
diese Migration bestehende gesamt.md-Exporte aus dem projekt/-
Arbeitsdateien-Unterordner eine Ebene hoeher in den Story-Root um (siehe
app/api/pipeline.py:_export_ausfuehren fuer den neuen Schreibort).

Wird bei jedem Start aufgerufen (siehe app/main.py), ist aber idempotent:
sobald der Ziel-Benutzerordner einmal existiert bzw. gesamt.md schon am
neuen Ort liegt, passiert bei folgenden Starts nichts mehr.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.config import Settings
from app.services import projekte_wurzel_unskopiert

logger = logging.getLogger(__name__)


def layout_migrieren(settings: Settings) -> None:
    wurzel = projekte_wurzel_unskopiert(settings)
    ziel_ordner = wurzel / settings.default_username

    if not ziel_ordner.exists():
        gefunden = [eintrag for eintrag in sorted(wurzel.iterdir()) if eintrag.is_dir()]
        if gefunden:
            ziel_ordner.mkdir(parents=True, exist_ok=True)
            for eintrag in gefunden:
                ziel = ziel_ordner / eintrag.name
                logger.info("Layout-Migration: verschiebe %s nach %s", eintrag, ziel)
                shutil.move(str(eintrag), str(ziel))

    _gesamt_md_umziehen(ziel_ordner)
    _gesamt_md_umbenennen(ziel_ordner)


def _gesamt_md_umziehen(benutzer_ordner: Path) -> None:
    """gesamt.md lag frueher im projekt/-Arbeitsdateien-Unterordner, landet
    jetzt im Story-Root direkt darueber - fuer weniger technisch versierte
    Nutzer verstaendlicher (projekt/ = reine Arbeitsdateien)."""
    if not benutzer_ordner.is_dir():
        return
    for alte_datei in benutzer_ordner.rglob("projekt/gesamt.md"):
        neue_datei = alte_datei.parent.parent / "gesamt.md"
        if not neue_datei.exists():
            logger.info("Layout-Migration: verschiebe %s nach %s", alte_datei, neue_datei)
            shutil.move(str(alte_datei), str(neue_datei))


def _gesamt_md_umbenennen(benutzer_ordner: Path) -> None:
    """gesamt.md hiess frueher immer woertlich so, unabhaengig vom
    Story-Titel. Export/PDF nutzen inzwischen den tatsaechlichen Titel
    (=Ordnername) als Dateiname (siehe app/api/pipeline.py:
    _export_ausfuehren) - bereits vorhandene gesamt.md-Dateien einmalig
    entsprechend umbenennen, damit auch alte Exporte konsistent heissen."""
    if not benutzer_ordner.is_dir():
        return
    for projekt_unterordner in benutzer_ordner.rglob("projekt"):
        story_root = projekt_unterordner.parent
        alte_datei = story_root / "gesamt.md"
        neue_datei = story_root / f"{story_root.name}.md"
        if alte_datei.exists() and not neue_datei.exists():
            logger.info("Layout-Migration: benenne %s um zu %s", alte_datei, neue_datei)
            alte_datei.rename(neue_datei)
