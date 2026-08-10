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
