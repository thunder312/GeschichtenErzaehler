"""Laedt das "unnuetzes Wissen" (Buch-/Autoren-Kuriositaeten) aus der
Pipe-getrennten Datei docs/unnützesWissen.csv - fuer das Zeit-
Ueberbrueckungs-Overlay im Frontend (siehe app/api/wissen.py). Reine
Parse-Funktion, kein Datenbankzugriff hier (siehe app/db.py fuer die
Persistenz)."""
from __future__ import annotations

import csv
import io
from pathlib import Path


def _text_lesen(pfad: Path) -> str:
    rohdaten = pfad.read_bytes()
    try:
        return rohdaten.decode("utf-8")
    except UnicodeDecodeError:
        # In diesem Windows-Setup wurde die Datei schon mal mit
        # Editoren gespeichert, die standardmaessig cp1252 statt UTF-8
        # verwenden - Umlaute wuerden sonst durch "?"/Mojibake ersetzt.
        return rohdaten.decode("cp1252")


def csv_einlesen(pfad: Path) -> list[dict[str, str]]:
    if not pfad.exists():
        return []
    with io.StringIO(_text_lesen(pfad)) as datei:
        reader = csv.DictReader(datei, delimiter="|")
        return [
            {
                "kategorie": (zeile.get("Kategorie") or "").strip(),
                "thema": (zeile.get("Thema") or "").strip(),
                "kuriositaet": (zeile.get("Kuriositaet") or "").strip(),
                "hintergrund": (zeile.get("Hintergrund") or "").strip(),
                "quelle": (zeile.get("Quelle") or "").strip(),
            }
            for zeile in reader
            if zeile.get("Kategorie") and zeile.get("Kuriositaet")
        ]
