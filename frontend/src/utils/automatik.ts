import type { AutomatikProtokollEintrag } from "../api/types";

/** Dieselbe Regel wie app/core/automatik.py:_aktuell_uebersprungene() -
 * reduziert "uebersprungen"-Eintraege auf den jeweils letzten Durchlauf pro
 * Kapitel, damit ein laengst durch einen spaeteren Durchlauf ueberholter
 * Zwischenstand (z.B. Durchlauf 1/2 eines Kapitels, das in Durchlauf 3
 * sauber konvergierte) nicht mehr als aktuell offen zaehlt. */
function aktuellUebersprungene(protokoll: AutomatikProtokollEintrag[]): AutomatikProtokollEintrag[] {
  const hoechsterDurchlauf = new Map<number | undefined, number | null>();
  for (const eintrag of protokoll) {
    if (eintrag.art !== "uebersprungen") continue;
    if (eintrag.durchlauf == null) {
      hoechsterDurchlauf.set(eintrag.kapitel, null);
      continue;
    }
    const bisher = hoechsterDurchlauf.get(eintrag.kapitel);
    if (bisher !== null && (bisher === undefined || eintrag.durchlauf > bisher)) {
      hoechsterDurchlauf.set(eintrag.kapitel, eintrag.durchlauf);
    }
  }
  return protokoll.filter((eintrag) => {
    if (eintrag.art !== "uebersprungen") return false;
    const hoechster = hoechsterDurchlauf.get(eintrag.kapitel);
    return hoechster == null || eintrag.durchlauf === hoechster;
  });
}

/** Dieselbe Regel wie app/core/automatik.py:reste_vorhanden() - fuer die
 * Sichtbarkeit des "Prüfung abschließen"-Buttons (nur zeigen, wenn es
 * ueberhaupt etwas zu bestaetigen gibt). */
export function hatReste(protokoll: AutomatikProtokollEintrag[]): boolean {
  if (aktuellUebersprungene(protokoll).length > 0) return true;
  return protokoll.some((eintrag) => eintrag.art === "rechtschreibung" && !!eintrag.unbekannte_woerter?.length);
}

export interface ResteZusammenfassung {
  angewendet: number;
  gesamt: number;
  uebersprungenNachGrund: Record<string, number>;
  unbekannteWoerter: number;
}

/** Fasst das Protokoll zu Zahlen zusammen - Grundlage fuer eine auf einen
 * Blick lesbare Zeile wie "27 von 69 Funden übersprungen", statt dass die
 * einzige Moeglichkeit, das zu erfahren, das Durchzaehlen der (per Default
 * eingeklappten) Rohliste ist. Vorfall "Das-Echo-der-Verpflichtung-Ein-
 * Geheimnis-in-Winterbottom-Hall" (2026-08-10): 27 von 69 Funden wurden
 * automatisch übersprungen, bevor der Nutzer das je bemerkte. */
export function resteZusammenfassen(protokoll: AutomatikProtokollEintrag[]): ResteZusammenfassung {
  const ergebnis: ResteZusammenfassung = {
    angewendet: 0, gesamt: 0, uebersprungenNachGrund: {}, unbekannteWoerter: 0,
  };
  for (const eintrag of protokoll) {
    if (eintrag.art === "angewendet") {
      ergebnis.angewendet += 1;
      ergebnis.gesamt += 1;
    } else if (eintrag.art === "uebersprungen") {
      const grund = eintrag.grund ?? "unbekannt";
      ergebnis.uebersprungenNachGrund[grund] = (ergebnis.uebersprungenNachGrund[grund] ?? 0) + 1;
      ergebnis.gesamt += 1;
    } else if (eintrag.art === "rechtschreibung") {
      ergebnis.unbekannteWoerter += eintrag.unbekannte_woerter?.length ?? 0;
    }
  }
  return ergebnis;
}
