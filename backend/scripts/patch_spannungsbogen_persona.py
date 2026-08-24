#!/usr/bin/env python3
"""Idempotente Migration: fuegt die Erklaerung der sechs "Funktion im
Spannungsbogen"-Kategorien (Freytags Pyramide - siehe
app/core/epoche.py:autor_vorlage/architekt_vorlage, wo dieselben Texte seit
2026-08-24 in JEDE neu erzeugte Persona einfliessen) nachtraeglich in jede
architekt.txt/autor.txt unterhalb von <root> ein, die das noch nicht hat.

Funktioniert fuer BEIDE moeglichen Wurzeln unveraendert, weil sie einfach
rekursiv nach Dateien mit dem Namen "architekt.txt"/"autor.txt" sucht:
  - Epochen-Bibliothek:        backend/app/data           (epochen/*/*.txt + personas/*.txt)
  - Bereits angelegte Geschichten: backend/instance/projects  (*/*/personas/*.txt)

Bereits gepatchte Dateien (Erkennung: der Anker-Satz/die Ueberschrift ist
schon vorhanden) werden unveraendert uebersprungen - das Skript kann also
gefahrlos mehrfach laufen, auch nachdem ein Teil der Dateien schon von Hand
oder in einem frueheren Lauf aktualisiert wurde.

Aufruf (Dry-Run per Default, zeigt nur was sich aendern WUERDE):
    python3 patch_spannungsbogen_persona.py <root>
Tatsaechlich schreiben:
    python3 patch_spannungsbogen_persona.py <root> --apply
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

AUTOR_ANCHOR = "Du stellst KEINE Fragen. Das Interview ist bereits geführt, das Geruest liegt vor.\n"
AUTOR_MARKER = "## Funktion im Spannungsbogen"
AUTOR_INSERT = """
## Funktion im Spannungsbogen
Das Feld "Funktion im Spannungsbogen" im Kapitelplan sagt dir, welche
dramaturgische Aufgabe dieses eine Kapitel in der Gesamtgeschichte hat
(Freytags Pyramide). Du kennst die sechs möglichen Werte und schreibst das
Kapitel entsprechend:
- Exposition: Figuren, Ort und Ausgangslage werden eingeführt, die Spannung
  beginnt erst leicht zu steigen.
- Erregendes Moment: Das Ereignis, das die eigentliche Handlung auslöst,
  tritt jetzt ein.
- Steigende Handlung: Der Konflikt verschärft sich, Hindernisse und Einsätze
  wachsen, die Spannung steigt spürbar.
- Höhepunkt/Peripetie: Die entscheidende Konfrontation, Entscheidung oder
  Wendung mit der größten Spannung der gesamten Geschichte.
- Fallende Handlung: Die unmittelbaren Folgen des Höhepunkts zeigen sich,
  eventuell noch ein letzter Rückschlag, die Spannung nimmt sichtbar ab.
- Auflösung/Lösung: Der Kernkonflikt (und ein eventueller Nebenstrang) lösen
  sich endgültig auf, kein neuer offener Spannungsbogen am Ende.
Steht im Geruest ein anderer, frei formulierter Wert in diesem Feld,
orientierst du dich sinngemäß an der nächstliegenden dieser sechs Funktionen.
"""

ARCHITEKT_MARKER = 'Funktion im Spannungsbogen: immer einer der sechs Werte "Exposition"'
ARCHITEKT_ANKER_MUSTER = re.compile(
    r"## Kapitelplan\n.*?Funktion im Spannungsbogen,.*?\n\n", re.DOTALL,
)
ARCHITEKT_INSERT_SENTENCE = (
    '\nFunktion im Spannungsbogen: immer einer der sechs Werte "Exposition",\n'
    '"Erregendes Moment", "Steigende Handlung", "Höhepunkt/Peripetie", "Fallende\n'
    'Handlung" oder "Auflösung/Lösung" (Freytags Pyramide), passend zur\n'
    'dramaturgischen Aufgabe des jeweiligen Kapitels in der Gesamtgeschichte.'
)


def patch_autor(path: Path, apply: bool) -> str:
    text = path.read_text(encoding="utf-8")
    if AUTOR_MARKER in text:
        return "übersprungen (bereits vorhanden)"
    if AUTOR_ANCHOR not in text:
        return "ÜBERSPRUNGEN (Anker-Satz nicht gefunden, evtl. stark abweichend formuliert)"
    if apply:
        neu = text.replace(AUTOR_ANCHOR, AUTOR_ANCHOR + AUTOR_INSERT, 1)
        path.write_text(neu, encoding="utf-8", newline="\n")
        return "geändert"
    return "würde ändern"


def patch_architekt(path: Path, apply: bool) -> str:
    text = path.read_text(encoding="utf-8")
    if ARCHITEKT_MARKER in text:
        return "übersprungen (bereits vorhanden)"
    m = ARCHITEKT_ANKER_MUSTER.search(text)
    if not m:
        return "ÜBERSPRUNGEN (Kapitelplan-Absatz nicht im erwarteten Format gefunden)"
    if apply:
        para_end = text.rfind("\n\n", m.start(), m.end())
        neu = text[:para_end] + ARCHITEKT_INSERT_SENTENCE + text[para_end:]
        path.write_text(neu, encoding="utf-8", newline="\n")
        return "geändert"
    return "würde ändern"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="Wurzelverzeichnis, wird rekursiv durchsucht")
    ap.add_argument("--apply", action="store_true", help="Tatsächlich schreiben statt nur Dry-Run")
    args = ap.parse_args()

    if not args.root.is_dir():
        raise SystemExit(f"Kein Verzeichnis: {args.root}")

    ergebnisse: list[tuple[Path, str]] = []
    for p in sorted(args.root.rglob("autor.txt")):
        ergebnisse.append((p, patch_autor(p, args.apply)))
    for p in sorted(args.root.rglob("architekt.txt")):
        ergebnisse.append((p, patch_architekt(p, args.apply)))

    for p, status in ergebnisse:
        print(f"{status:55s} {p}")

    betroffen = sum(1 for _, s in ergebnisse if s in ("geändert", "würde ändern"))
    uebersprungen_warnung = sum(1 for _, s in ergebnisse if s.startswith("ÜBERSPRUNGEN"))
    print(f"\n{betroffen} von {len(ergebnisse)} Dateien betroffen.")
    if uebersprungen_warnung:
        print(f"{uebersprungen_warnung} Datei(en) mit ÜBERSPRUNGEN-Warnung - bitte von Hand prüfen.")
    if not args.apply and betroffen:
        print("Dry-Run - zum tatsächlichen Schreiben mit --apply erneut aufrufen.")


if __name__ == "__main__":
    main()
