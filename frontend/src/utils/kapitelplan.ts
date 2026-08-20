// Parst/serialisiert NUR den "## Kapitelplan"-Abschnitt von geruest.md in
// strukturierte Kapitel-Bloecke (siehe KapitelplanEditor.tsx). Der Rest des
// Gerüsts (Rahmen, Figuren, Konflikt, Nebenstrang, Ausgangslage, Regeln)
// bleibt bewusst Freitext, siehe ToDo.md "Gerüst-Editor mit Struktur-Zwang" -
// diese Felder unterscheiden sich je Epoche (auch frei vom User erfundene,
// z.B. "Kaigyū" statt "Stand"), das Kapitelplan-Schema unten ist dagegen in
// ALLEN Epochen identisch (siehe backend/app/core/epoche.py und
// backend/app/data/epochen/*/architekt.txt, Abschnitt "## Kapitelplan").
//
// Backend-Pendant/Gegenstueck: backend/app/core/geruest.py (kapitelplan_erkennen,
// kapitel_block_erkennen, kapitelplan_pruefen) - bleibt als serverseitige
// Absicherung bestehen, falls dieser Client-Parser je an Formaten scheitert,
// die er nicht kennt (z.B. ein sehr alt handgepflegtes Geruest).

export interface KapitelEintrag {
  titel: string;
  ort: string;
  anwesendeFiguren: string;
  ereignis: string;
  zielwortzahl: number | null;
  funktionImSpannungsbogen: string;
  standDerLiebeshandlung: string;
  zustandAmKapitelende: string;
}

export interface KapitelplanFehler {
  index: number;
  feld: keyof KapitelEintrag;
  meldung: string;
}

export interface GeruestMitKapitelplan {
  vor: string;
  kapitel: KapitelEintrag[];
  nach: string;
}

const ZAHLWORT_LISTE = [
  "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn",
  "elf", "zwölf", "dreizehn", "vierzehn", "fünfzehn", "sechzehn", "siebzehn", "achtzehn", "neunzehn", "zwanzig",
];

function zahlwort(n: number): string {
  return ZAHLWORT_LISTE[n - 1] ?? String(n);
}

export function leeresKapitel(): KapitelEintrag {
  return {
    titel: "",
    ort: "",
    anwesendeFiguren: "",
    ereignis: "",
    zielwortzahl: null,
    funktionImSpannungsbogen: "",
    standDerLiebeshandlung: "",
    zustandAmKapitelende: "",
  };
}

// Erfasst NUR die fettgedruckte Kapitel-Ueberschrift am Zeilenanfang
// ("*   **Kapitel eins: Titel**"), bewusst enger als das Backend-Pendant
// (das jedes "Kapitel N" im ganzen Text matcht) - verhindert, dass ein
// Fliesstext-Verweis wie "...wie in Kapitel drei..." innerhalb eines
// Ereignis-Felds faelschlich als neuer Kapitel-Block erkannt wird.
const KAPITEL_HEADING_MUSTER = /^[ \t]*[*-][ \t]*\*\*[ \t]*Kapitel[ \t]+(\d+|[a-zA-ZäöüÄÖÜß]+)[ \t]*:[ \t]*([^\n*]*?)\*\*/gim;

function feldExtrahieren(block: string, label: string): string {
  const muster = new RegExp(`^[ \\t]*[*-][ \\t]*${label}[ \\t]*:[ \\t]*(.+)$`, "im");
  const treffer = block.match(muster);
  return treffer ? treffer[1].trim() : "";
}

function zielwortzahlExtrahieren(block: string): number | null {
  const zeile = feldExtrahieren(block, "Zielwortzahl");
  if (!zeile) return null;
  const treffer = [...zeile.matchAll(/([\d][\d.,]*)[ \t]*W(?:oe|ö)rter/gi)];
  if (treffer.length === 0) return null;
  // Bei einer Spanne ("1800–2200 Wörter") wie im Backend die LETZTE (obere)
  // Zahl vor "Wörter" verwenden.
  const zahlText = treffer[treffer.length - 1][1].replace(/[.,]/g, "");
  const zahl = Number(zahlText);
  return Number.isFinite(zahl) && zahl > 0 ? zahl : null;
}

function kapitelBloeckeParsen(body: string): KapitelEintrag[] {
  const treffer = [...body.matchAll(KAPITEL_HEADING_MUSTER)];
  return treffer.map((m, i) => {
    const start = (m.index ?? 0) + m[0].length;
    const ende = i + 1 < treffer.length ? (treffer[i + 1].index ?? body.length) : body.length;
    const block = body.slice(start, ende);
    return {
      titel: (m[2] ?? "").trim(),
      ort: feldExtrahieren(block, "Ort"),
      anwesendeFiguren: feldExtrahieren(block, "Anwesende Figuren"),
      ereignis: feldExtrahieren(block, "Ereignis"),
      zielwortzahl: zielwortzahlExtrahieren(block),
      funktionImSpannungsbogen: feldExtrahieren(block, "Funktion im Spannungsbogen"),
      standDerLiebeshandlung: feldExtrahieren(block, "Stand der Liebeshandlung"),
      zustandAmKapitelende: feldExtrahieren(block, "Zustand am Kapitelende"),
    };
  });
}

/** Trennt ein komplettes geruest.md in "vor" (alles bis vor "## Kapitelplan"),
 * die strukturiert geparsten Kapitel-Bloecke, und "nach" (alles ab der
 * naechsten "## "-Ueberschrift danach). Kein "## Kapitelplan" gefunden -
 * z.B. ein brandneues, noch leeres Geruest -> der komplette Text landet in
 * "vor", kapitel bleibt leer (kein Fehler, siehe kapitelplan_pruefen()
 * backend-seitig: ein fehlender Abschnitt ist kein Strukturfehler). */
export function kapitelplanAusGeruestExtrahieren(geruest: string): GeruestMitKapitelplan {
  const headingMatch = geruest.match(/##[ \t]*Kapitelplan[ \t]*\n/i);
  if (!headingMatch || headingMatch.index === undefined) {
    return { vor: geruest, kapitel: [], nach: "" };
  }
  const vorEnde = headingMatch.index;
  const bodyStart = headingMatch.index + headingMatch[0].length;
  const rest = geruest.slice(bodyStart);
  const nextHeadingMatch = rest.match(/\n##[ \t]/);
  const bodyEnde = nextHeadingMatch && nextHeadingMatch.index !== undefined ? nextHeadingMatch.index : rest.length;

  return {
    vor: geruest.slice(0, vorEnde).replace(/[ \t\n]+$/, ""),
    kapitel: kapitelBloeckeParsen(rest.slice(0, bodyEnde)),
    nach: rest.slice(bodyEnde).replace(/^[ \t\n]+/, ""),
  };
}

function kapitelBlockSerialisieren(kapitel: KapitelEintrag, index: number): string {
  const zielwortzahlZeile = kapitel.zielwortzahl != null && kapitel.zielwortzahl > 0
    ? `ca. ${kapitel.zielwortzahl} Wörter.`
    : "";
  return [
    `*   **Kapitel ${zahlwort(index + 1)}: ${kapitel.titel.trim()}**`,
    `    *   Ort: ${kapitel.ort.trim()}`,
    `    *   Anwesende Figuren: ${kapitel.anwesendeFiguren.trim()}`,
    `    *   Ereignis: ${kapitel.ereignis.trim()}`,
    `    *   Zielwortzahl: ${zielwortzahlZeile}`,
    `    *   Funktion im Spannungsbogen: ${kapitel.funktionImSpannungsbogen.trim()}`,
    `    *   Stand der Liebeshandlung: ${kapitel.standDerLiebeshandlung.trim()}`,
    `    *   Zustand am Kapitelende: ${kapitel.zustandAmKapitelende.trim()}`,
  ].join("\n");
}

/** Gegenstueck zu kapitelplanAusGeruestExtrahieren() - baut aus den drei
 * Teilen wieder ein komplettes geruest.md. Ohne Kapitel wird der
 * "## Kapitelplan"-Abschnitt komplett weggelassen statt einen leeren Rumpf
 * zu hinterlassen. */
export function geruestAusKapitelplanZusammenbauen(vor: string, kapitel: KapitelEintrag[], nach: string): string {
  const vorGetrimmt = vor.replace(/[ \t\n]+$/, "");
  const nachGetrimmt = nach.replace(/^[ \t\n]+/, "");
  const teile = [vorGetrimmt];
  if (kapitel.length > 0) {
    teile.push(`## Kapitelplan\n${kapitel.map(kapitelBlockSerialisieren).join("\n")}`);
  }
  teile.push(nachGetrimmt);
  return teile.filter((t) => t.length > 0).join("\n\n");
}

const PFLICHTFELDER: { feld: keyof KapitelEintrag; label: string }[] = [
  { feld: "titel", label: "Titel" },
  { feld: "ort", label: "Ort" },
  { feld: "anwesendeFiguren", label: "Anwesende Figuren" },
  { feld: "ereignis", label: "Ereignis" },
  { feld: "funktionImSpannungsbogen", label: "Funktion im Spannungsbogen" },
  { feld: "standDerLiebeshandlung", label: "Stand der Liebeshandlung" },
  { feld: "zustandAmKapitelende", label: "Zustand am Kapitelende" },
];

/** Client-seitige Pflichtfeld-Pruefung - der eigentliche Kern von Schritt 2:
 * ein Kapitel ohne Zielwortzahl (oder ohne eines der anderen Felder) laesst
 * sich damit gar nicht erst absenden, statt erst beim Speichern serverseitig
 * abgelehnt zu werden (siehe backend/app/core/geruest.py:
 * kapitelplan_pruefen, das als zweite Verteidigungslinie unveraendert
 * bestehen bleibt - z.B. falls dieser Parser an einem alten, handgepflegten
 * Geruest scheitert). */
export function kapitelPflichtfelderPruefen(kapitel: KapitelEintrag[]): KapitelplanFehler[] {
  const fehler: KapitelplanFehler[] = [];
  kapitel.forEach((k, index) => {
    for (const { feld, label } of PFLICHTFELDER) {
      if (!(k[feld] as string).trim()) {
        fehler.push({ index, feld, meldung: `Kapitel ${index + 1}: ${label} fehlt.` });
      }
    }
    if (k.zielwortzahl == null || k.zielwortzahl <= 0) {
      fehler.push({ index, feld: "zielwortzahl", meldung: `Kapitel ${index + 1}: Zielwortzahl fehlt.` });
    }
  });
  return fehler;
}
