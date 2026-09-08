"""Einmalige Nachruestung des Konvergenz-Markers (automatik_geprueft.json) fuer
Projekte, deren Automatik-Lauf ABGESCHLOSSEN wurde, BEVOR es diesen Marker gab
(eingefuehrt 2026-09-02, Commit "Automatikmodus: alte Kapitel nach Geruest-
Erweiterung nicht mehr neu pruefen").

Ohne diese Nachruestung prueft Phase 2 bei einer laengst fertigen, im Geruest
nur um Kapitel ergaenzten Geschichte die alten Kapitel erneut (siehe
app/api/pipeline.py, Phase-2-Regel (b)). Der Marker wird aus dem AKTUELLEN
Kapiteltext gebildet - identisch zu dem, was automatik.geprueft_markieren()
direkt nach jedem Kapitel geschrieben haette.

Nur Projekte mit automatik_status.json -> abgeschlossen == True und noch OHNE
automatik_geprueft.json werden angefasst. Gestoppte/fehlgeschlagene Laeufe
bleiben unberuehrt (die brauchen echte Phase 2). Standardmaessig Trockenlauf;
mit  --apply  wird geschrieben.

Aufruf auf dem Server:
    cd /var/www/geschichten/backend
    ./.venv/bin/python3 scripts/automatik_marker_backfill.py           # zeigt nur
    ./.venv/bin/python3 scripts/automatik_marker_backfill.py --apply   # schreibt
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.config import get_settings                       # noqa: E402
from app.core import automatik                            # noqa: E402
from app.core import projekt_dateien as pd                # noqa: E402
from app.services import projekte_wurzel_unskopiert       # noqa: E402


def _projekt_ordner(wurzel: Path) -> list[Path]:
    ergebnis: list[Path] = []
    if not wurzel.is_dir():
        return ergebnis
    for benutzer_dir in sorted(p for p in wurzel.iterdir() if p.is_dir()):
        for eintrag in sorted(p for p in benutzer_dir.iterdir() if p.is_dir()):
            if (eintrag / "projekt").is_dir():
                ergebnis.append(eintrag)
                continue
            for unter in sorted(p for p in eintrag.iterdir() if p.is_dir()):
                if (unter / "projekt").is_dir():
                    ergebnis.append(unter)
    return ergebnis


def main() -> None:
    apply = "--apply" in sys.argv
    wurzel = projekte_wurzel_unskopiert(get_settings())
    print(f"Projekte-Wurzel: {wurzel}")
    print(f"Modus: {'SCHREIBEN' if apply else 'Trockenlauf (nur Anzeige)'}\n")

    angefasst = 0
    for projekt_root in _projekt_ordner(wurzel):
        projekt = projekt_root / "projekt"
        rel = projekt_root.relative_to(wurzel)
        status = automatik.status_lesen(projekt_root)

        if not status.get("gestartet_am"):
            continue  # nie Automatik benutzt
        if (projekt / automatik.AUTOMATIK_GEPRUEFT_DATEINAME).exists():
            continue  # Marker schon vorhanden - nichts zu tun
        if not status.get("abgeschlossen"):
            print(f"[uebersprungen] {rel}  (letzter Lauf nicht abgeschlossen: "
                  f"{automatik.zustand_zusammenfassen(status)})")
            continue

        kapitel = pd.vorhandene_kapitel(projekt)
        if not kapitel:
            continue

        nummern = [pd.kapitelnummer_aus_dateiname(p) for p in kapitel]
        print(f"[backfill]      {rel}  -> {len(nummern)} Kapitel "
              f"({', '.join(str(n) for n in nummern)})")
        if apply:
            for p, n in zip(kapitel, nummern):
                automatik.geprueft_markieren(projekt_root, n, pd.lies(p))
        angefasst += 1

    print(f"\n{angefasst} Projekt(e) {'nachgeruestet' if apply else 'waeren betroffen'}.")
    if not apply and angefasst:
        print("Zum tatsaechlichen Schreiben erneut mit  --apply  aufrufen.")


if __name__ == "__main__":
    main()
