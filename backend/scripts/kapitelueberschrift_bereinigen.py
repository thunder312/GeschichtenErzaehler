#!/usr/bin/env python3
"""Einmalige Bereinigung: entfernt aus bereits gespeicherten kapitel_NN.md
die doppelte bzw. rein als Markdown gesetzte Kapitelüberschrift.

Hintergrund (Commit 081a8ab, 2026-08-24 bis zum Fix): die beiden
Überschrift-Heuristiken in app/api/pipeline.py:_kapitel_schreiben_kern liefen
in falscher Reihenfolge. Eine reine Markdown-Überschrift des Modells
("### Kapitel eins: Rechtlose Magd") galt als "fehlt", das Sicherheitsnetz
kapitelueberschrift_sicherstellen() stellte eine zweite Klartext-Zeile davor,
und die rohe ###-Zeile blieb liegen:

    Kapitel eins: Rechtlose Magd
    ### Kapitel eins: Rechtlose Magd
    Die Sonne stand hoch ...

Im PDF- und Gesamttext-Export landete die zweite Zeile als gewöhnlicher
Absatz direkt unter der römisch nummerierten Kapitelüberschrift.

Der Code-Fix (heuristik.py / pdf_export.py) sorgt dafür, dass neue Kapitel
sauber entstehen UND der PDF-Export bestehende Dateien richtig rendert.
Dieses Skript räumt zusätzlich die GESPEICHERTEN Dateien auf, damit auch der
`<Projekt>.md`-Gesamttext-Export und der Editor im Tab "Prüfen & Anwenden"
sie sauber zeigen.

Geändert wird eine Kapiteldatei nur, wenn am Textanfang (nach einer
eventuellen Titelseite) entweder
  - mehrere Kapitelüberschrift-Zeilen direkt hintereinander stehen, ODER
  - genau eine, aber als Markdown-Überschrift ("#"-Präfix).
Eine einzelne Überschrift in Klartext oder **Fettdruck** bleibt unangetastet
(so schreibt sie die Persona bzw. das Sicherheitsnetz für Kapitel 1).

Der eigentliche Prosatext wird NIE angefasst. Die alte Fassung wird wie bei
jedem App-Schreibvorgang als "<name>.<zeitstempel>.bak" gesichert.

Aufruf (Dry-Run, zeigt nur was sich ändern WÜRDE):
    .venv/bin/python3 scripts/kapitelueberschrift_bereinigen.py <projekte-wurzel>
Tatsächlich schreiben (inkl. Neuaufbau der vorhandenen <Projekt>.md-Exporte):
    .venv/bin/python3 scripts/kapitelueberschrift_bereinigen.py <projekte-wurzel> --apply
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import projekt_dateien as pd  # noqa: E402

# "Kapitel <Zahl/Zahlwort> : <Titel>" - optional mit fuehrender Markdown-Raute
# und/oder umschliessenden Sternchen.
_UEBERSCHRIFT_RE = re.compile(
    r"^(?:#{1,6}[ \t]*)?\*{0,2}[ \t]*Kapitel\s+\S+\s*[:\-–—]", re.IGNORECASE
)
_IST_MARKDOWN_RE = re.compile(r"^#{1,6}\s")
# Titelseiten-Zeilen (nur Kapitel 1): "# Titel" und "*Untertitel*".
_TITELSEITE_ITALIC_RE = re.compile(r"^\*[^*].*\*$")


def _ist_ueberschrift(zeile: str) -> bool:
    return bool(_UEBERSCHRIFT_RE.match(zeile))


def _ist_markdown_ueberschrift(zeile: str) -> bool:
    return bool(_IST_MARKDOWN_RE.match(zeile))


def _klartext(zeile: str) -> str:
    """'### Kapitel eins: Rechtlose Magd ###' / '**Kapitel eins: X**'
    -> 'Kapitel eins: Rechtlose Magd'."""
    z = zeile.strip()
    z = z.lstrip("#").strip()
    z = z.strip("*").strip()
    return z


def bereinige(text: str) -> tuple[str, str] | None:
    """Gibt (neuer_text, beschreibung) zurück, oder None wenn nichts zu tun
    ist."""
    zeilen = text.split("\n")
    n = len(zeilen)

    # 1. Titelseite (# Titel / *Untertitel*) + fuehrende Leerzeilen ueberspringen.
    i = 0
    while i < n:
        z = zeilen[i].strip()
        if not z:
            i += 1
            continue
        if z.startswith("# ") or _TITELSEITE_ITALIC_RE.match(z):
            i += 1
            continue
        break

    kopf_ende = i

    # 2. Lauf aus aufeinanderfolgenden Ueberschrift-Zeilen einsammeln
    #    (Leerzeilen dazwischen erlaubt).
    ueberschriften: list[str] = []
    letzte_ueberschrift_idx = -1
    while i < n:
        z = zeilen[i].strip()
        if not z:
            i += 1
            continue
        if _ist_ueberschrift(z):
            ueberschriften.append(z)
            letzte_ueberschrift_idx = i
            i += 1
            continue
        break

    if not ueberschriften:
        return None

    mehrfach = len(ueberschriften) >= 2
    markdown_einzeln = len(ueberschriften) == 1 and _ist_markdown_ueberschrift(ueberschriften[0])
    if not (mehrfach or markdown_einzeln):
        return None

    # Kanonische Ueberschrift: bevorzugt die erste NICHT-Markdown-Variante,
    # sonst die erste - immer in Klartext.
    kanonisch = next(
        (_klartext(u) for u in ueberschriften if not _ist_markdown_ueberschrift(u)),
        _klartext(ueberschriften[0]),
    )

    prefix = "\n".join(zeilen[:kopf_ende]).rstrip("\n")
    body_zeilen = zeilen[letzte_ueberschrift_idx + 1:]
    while body_zeilen and not body_zeilen[0].strip():
        body_zeilen.pop(0)
    while body_zeilen and not body_zeilen[-1].strip():
        body_zeilen.pop()
    body = "\n".join(body_zeilen)

    teile = [t for t in (prefix, kanonisch, body) if t]
    neu = "\n\n".join(teile)
    if text.endswith("\n"):
        neu += "\n"

    if neu == text:
        return None

    if mehrfach:
        beschreibung = f"{len(ueberschriften)} Überschriftszeilen -> 1 ('{kanonisch}')"
    else:
        beschreibung = f"Markdown-Überschrift -> Klartext ('{kanonisch}')"
    return neu, beschreibung


def _story_root(kapitel_datei: Path) -> Path:
    # .../<story>/projekt/kapitel_NN.md  ->  .../<story>
    return kapitel_datei.parent.parent


def _export_neu_aufbauen(story_root: Path, apply: bool) -> str | None:
    """Baut <Projekt>.md aus den (jetzt bereinigten) Kapiteln neu - aber nur,
    wenn die Datei schon existiert (kein neuer Export, wo vorher keiner war).
    Identisch zu app/api/pipeline.py:_export_ausfuehren."""
    ziel = story_root / f"{story_root.name}.md"
    if not ziel.exists():
        return None
    kapitel = pd.vorhandene_kapitel(story_root / "projekt")
    if not kapitel:
        return None
    ganz = "\n\n".join(pd.lies(p) for p in kapitel)
    if ganz.strip() + "\n" == ziel.read_text(encoding="utf-8").strip() + "\n":
        return None
    if apply:
        sicherung = ziel.with_suffix(ziel.suffix + f".{int(time.time())}.bak")
        ziel.rename(sicherung)
        ziel.write_text(ganz + "\n", encoding="utf-8")
        return f"neu aufgebaut (Sicherung: {sicherung.name})"
    return "würde neu aufgebaut"


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("root", type=Path, help="Projekte-Wurzel, wird rekursiv durchsucht")
    ap.add_argument("--apply", action="store_true", help="Tatsächlich schreiben statt nur Dry-Run")
    args = ap.parse_args()

    if not args.root.is_dir():
        raise SystemExit(f"Kein Verzeichnis: {args.root}")

    geaendert = 0
    betroffene_storys: set[Path] = set()
    for kap in sorted(args.root.rglob("kapitel_*.md")):
        if ".bak" in kap.name:
            continue
        try:
            text = kap.read_text(encoding="utf-8")
        except OSError as e:
            print(f"FEHLER beim Lesen: {kap} ({e})")
            continue
        ergebnis = bereinige(text)
        if ergebnis is None:
            continue
        neu, beschreibung = ergebnis
        geaendert += 1
        betroffene_storys.add(_story_root(kap))
        if args.apply:
            sicherung = kap.with_suffix(kap.suffix + f".{int(time.time())}.bak")
            kap.rename(sicherung)
            kap.write_text(neu, encoding="utf-8")
            print(f"geändert   {kap}  [{beschreibung}]  (Sicherung: {sicherung.name})")
        else:
            print(f"würde ändern   {kap}  [{beschreibung}]")

    export_meldungen = []
    for story_root in sorted(betroffene_storys):
        meldung = _export_neu_aufbauen(story_root, args.apply)
        if meldung:
            export_meldungen.append(f"  {story_root.name}.md: {meldung}")

    print()
    print(f"{geaendert} Kapiteldatei(en) betroffen, {len(betroffene_storys)} Geschichte(n).")
    if export_meldungen:
        print("Gesamttext-Exporte:")
        print("\n".join(export_meldungen))
    if not args.apply and geaendert:
        print("\nDry-Run - zum tatsächlichen Schreiben mit --apply erneut aufrufen.")


if __name__ == "__main__":
    main()
