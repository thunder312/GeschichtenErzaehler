// Von PruefenAnwendenPage und RechtschreibungPage geteilt - beide bauen aus
// den einzelnen Kapiteltexten denselben "## Kapitel N"-getrennten
// Editor-Text zusammen. Eine gemeinsame Stelle stellt sicher, dass beide
// Tabs exakt dasselbe Format und dieselben Positionen erwarten (wichtig fuer
// den Cross-Tab-Sync ueber KapitelTextContext, siehe dort).

export interface Spanne {
  start: number;
  end: number;
}

const KAPITEL_MARKER_MUSTER = /^## Kapitel (\d+)\s*$/gm;

export const kapitelUeberschrift = (n: number) => `## Kapitel ${n}`;

/** Teilt den kombinierten Text anhand der "## Kapitel N"-Ueberschriften
 * wieder in einzelne Kapitel auf - Gegenstueck zu kapitelTextZusammenbauen(). */
export function splitteNachKapitel(text: string): Map<number, string> {
  const treffer = [...text.matchAll(KAPITEL_MARKER_MUSTER)];
  const ergebnis = new Map<number, string>();
  for (let i = 0; i < treffer.length; i++) {
    const n = Number(treffer[i][1]);
    const startInhalt = treffer[i].index! + treffer[i][0].length;
    const endeInhalt = i + 1 < treffer.length ? treffer[i + 1].index! : text.length;
    ergebnis.set(n, text.slice(startInhalt, endeInhalt).trim());
  }
  return ergebnis;
}

/** Anker-Offset (Beginn der "## Kapitel N"-Ueberschrift) je Kapitel im
 * kombinierten Text, aufsteigend nach Offset sortiert - Grundlage fuer die
 * "ein Kapitel vor/zurueck"-Navigation in PruefenAnwendenPage und
 * RechtschreibungPage. `spannen[n].start` zeigt auf den Kapitel-INHALT (nach
 * der Ueberschrift), deshalb Laenge von "## Kapitel N" + "\n\n" abziehen. */
export function kapitelAnkerOffsets(
  kapitelNummern: number[],
  spannen: Record<number, Spanne>,
): { n: number; offset: number }[] {
  return kapitelNummern
    .filter((n) => spannen[n])
    .map((n) => ({ n, offset: Math.max(0, spannen[n].start - (kapitelUeberschrift(n).length + 2)) }))
    .sort((a, b) => a.offset - b.offset);
}

/** Ziel-Offset fuer "ein Kapitel vor/zurueck". Bezugspunkt ist die weiteste
 * Leseposition: das Maximum aus oberster sichtbarer Zeile und Cursor. Nach
 * einem Sprung sitzt der Cursor exakt auf der Ueberschrift (waehrend
 * revealLineNearTop() noch ein paar Zeilen Kontext darueber stehen laesst) -
 * ohne den Cursor-Anteil wuerde "Weiter" deshalb dauerhaft am selben Kapitel
 * kleben. null = in dieser Richtung kein Kapitel mehr. */
export function nachbarKapitelOffset(
  anker: { n: number; offset: number }[],
  sichtbarerOffset: number,
  cursorOffset: number,
  richtung: -1 | 1,
): number | null {
  if (anker.length === 0) return null;
  const TOLERANZ = 16;
  const bezug = Math.max(sichtbarerOffset, cursorOffset);
  // Aktuelles Kapitel = letzter Anker, der noch auf/vor der Bezugsposition
  // liegt; von da aus genau ein Schritt weiter.
  let aktIndex = 0;
  for (let i = 0; i < anker.length; i++) {
    if (anker[i].offset <= bezug + TOLERANZ) aktIndex = i;
  }
  const zielIndex = aktIndex + richtung;
  if (zielIndex < 0 || zielIndex >= anker.length) return null;
  return anker[zielIndex].offset;
}

/** Baut aus einer geordneten Liste von Kapitelnummern und einer
 * Text-je-Kapitel-Funktion den kombinierten Editor-Text plus die
 * Zeichen-Spannen jedes Kapitels darin. `textFuer` liefert `undefined`
 * zurueck, um ein Kapitel (noch) auszulassen (z.B. noch nicht geladen). */
export function kapitelTextZusammenbauen(
  kapitelNummern: number[],
  textFuer: (n: number) => string | undefined,
): { text: string; spannen: Record<number, Spanne> } {
  let text = "";
  const spannen: Record<number, Spanne> = {};
  for (const n of kapitelNummern) {
    const inhalt = textFuer(n);
    if (inhalt === undefined) continue;
    if (text) text += "\n\n";
    text += `${kapitelUeberschrift(n)}\n\n`;
    const start = text.length;
    text += inhalt;
    spannen[n] = { start, end: text.length };
  }
  return { text, spannen };
}
