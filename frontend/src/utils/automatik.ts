import type { AutomatikProtokollEintrag } from "../api/types";

/** Dieselbe Regel wie app/core/automatik.py:reste_vorhanden() - fuer die
 * Sichtbarkeit des "Prüfung abschließen"-Buttons (nur zeigen, wenn es
 * ueberhaupt etwas zu bestaetigen gibt). */
export function hatReste(protokoll: AutomatikProtokollEintrag[]): boolean {
  return protokoll.some(
    (eintrag) => eintrag.art === "uebersprungen" || (eintrag.art === "rechtschreibung" && !!eintrag.unbekannte_woerter?.length),
  );
}
