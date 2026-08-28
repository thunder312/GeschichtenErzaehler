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
  // Wie viel erzaehlte Zeit seit dem Ende des vorigen Kapitels vergangen ist
  // (z.B. "drei Tage spaeter, ein neuer Abend") - bewusst optional (siehe
  // PFLICHTFELDER unten): bleibt es leer, waehlt der Autor laut Persona-
  // Vorgabe (backend/app/core/epoche.py:autor_vorlage) selbst den kuerzesten
  // noch logisch plausiblen Zeitsprung. Bei Kapitel 1 ohne Bedeutung (siehe
  // "Ausgangslage vor Kapitel eins" fuer den Startzeitpunkt), deshalb blendet
  // KapitelplanEditor.tsx das Feld dort aus.
  vergangeneZeit: string;
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
  // Gesetzt, wenn ein vorhandener, NICHT-leerer "## Kapitelplan"-Abschnitt
  // nicht sicher in Kapitel-Karten zerlegt werden konnte (siehe
  // kapitelBloeckeParsen) - der Rohtext landet dann unangetastet in "nach",
  // "kapitel" bleibt leer. Unterscheidet "wirklich noch kein Kapitelplan"
  // von "einer ist da, nur nicht strukturiert erkannt" - ohne diese
  // Unterscheidung wuerde ein Klick auf "+ Kapitel" den vorhandenen
  // Kapitelplan NICHT ersetzen (er bleibt ja in "nach" erhalten), aber der
  // Nutzer koennte faelschlich denken, das Projekt haette noch gar keinen.
  warnung: string | null;
}

const ZAHLWORT_LISTE = [
  "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn",
  "elf", "zwölf", "dreizehn", "vierzehn", "fünfzehn", "sechzehn", "siebzehn", "achtzehn", "neunzehn", "zwanzig",
];

function zahlwort(n: number): string {
  return ZAHLWORT_LISTE[n - 1] ?? String(n);
}

// Vorbelegter Zielwortzahl-Mittelwert fuer ein neu angelegtes Kapitel (siehe
// KapitelplanEditor.tsx "+ Kapitel" und GeruestPage.tsx: automatisches erstes
// Kapitel bei einem noch leeren Gerüst). Recherche zu gaengigen Kapitellaengen
// bei Kurzgeschichten/Novellen (1-6 Kapitel) ergibt uebereinstimmend ca.
// 1.000 bis 2.000 Woerter pro Kapitel - deckt sich mit den in dieser App
// selbst schon verwendeten Richtwerten aus dem Architekten-Interview (siehe
// backend/app/core/epoche.py: "Kurz" 2 Kapitel a ca. 1.250 Woerter, "Mittel"
// 4 Kapitel a ca. 1.250 Woerter, "Erzaehlung" 6 Kapitel a ca. 1.580 Woerter).
// 1.500 liegt als flacher Mittelwert innerhalb all dieser Spannen und ist nur
// ein Vorschlag - der Nutzer kann ihn jederzeit ueberschreiben.
export const ZIELWORTZAHL_VORSCHLAG = 1500;

// Gaengige Kategorien fuer "Funktion im Spannungsbogen" bei (Kurz-)Geschichten
// und Novellen, nach Freytags Pyramide (Exposition, steigende Handlung,
// Hoehepunkt/Peripetie, fallende Handlung, Ausgang/Loesung), ergaenzt um das
// "erregende Moment" als eigenen, in der Praxis oft vom Rest der Exposition
// getrennten Auftakt. Dieselben sechs Werte kennt auch die Autor-Persona
// (siehe backend/app/core/epoche.py:autor_vorlage, "## Funktion im
// Spannungsbogen") - Architekt und Autor sollen dieselbe, konsistente
// Kategorisierung verwenden wie das Dropdown hier.
export const FUNKTION_IM_SPANNUNGSBOGEN_OPTIONEN = [
  "Exposition",
  "Erregendes Moment",
  "Steigende Handlung",
  "Höhepunkt/Peripetie",
  "Fallende Handlung",
  "Auflösung/Lösung",
] as const;

export function leeresKapitel(zielwortzahl: number | null = ZIELWORTZAHL_VORSCHLAG): KapitelEintrag {
  return {
    titel: "",
    vergangeneZeit: "",
    ort: "",
    anwesendeFiguren: "",
    ereignis: "",
    zielwortzahl,
    funktionImSpannungsbogen: "",
    standDerLiebeshandlung: "",
    zustandAmKapitelende: "",
  };
}

// Erfasst die fettgedruckte Kapitel-Ueberschrift am Zeilenanfang, mit ODER
// ohne vorangestellten Bullet-Marker ("*   **Kapitel eins: Titel**" ODER
// "**Kapitel 1: Titel**" - beide Formen kommen in echten Projekten vor, der
// Architekt haelt sich nicht immer an dieselbe Bullet-Konvention). Bewusst
// trotzdem enger als das Backend-Pendant (das jedes "Kapitel N" im ganzen
// Text matcht, auch ohne Fett-Markierung) - verhindert, dass ein Fliesstext-
// Verweis wie "...wie in Kapitel drei..." innerhalb eines Ereignis-Felds
// faelschlich als neuer Kapitel-Block erkannt wird. Siehe
// kapitelBloeckeParsen() unten fuer die Gegenprobe, die diese Enge wieder
// absichert: bemerkt sie moegliche Kapitel-Ueberschriften, die HIER nicht
// matchen, wird gar nicht erst strukturiert geparst (kein Datenverlust).
const KAPITEL_HEADING_MUSTER = /^[ \t]*(?:[*-][ \t]*)?\*\*[ \t]*Kapitel[ \t]+(\d+|[a-zA-ZäöüÄÖÜß]+)[ \t]*:[ \t]*([^\n*]*?)\*\*/gim;

// Lockere Gegenprobe OHNE Fett-/Bullet-Zwang, aehnlich dem Backend-Muster
// in geruest.py (_KAPITEL_MUSTER) - dient NUR als Bauchgefuehl-Test in
// kapitelBloeckeParsen(), niemals zum eigentlichen Parsen.
const KAPITEL_ERWAEHNUNG_MUSTER = /Kapitel[ \t]+(\d+|[a-zA-ZäöüÄÖÜß]+)[ \t]*:/gi;

// Die 7 bekannten Feld-Labels je Kapitel-Block, absichtlich als EIN Muster
// statt sieben Einzelsuchen - siehe alleFelderExtrahieren() unten fuer den
// Grund (Mehrzeilen-Werte brauchen die Position ALLER Labels gleichzeitig,
// um zu wissen, wo ein Wert endet).
const FELD_LABELS: readonly string[] = [
  "Vergangene Zeit", "Ort", "Anwesende Figuren", "Ereignis", "Zielwortzahl",
  "Funktion im Spannungsbogen", "Stand der Liebeshandlung", "Zustand am Kapitelende",
];

// Sowohl "*   Ort: ..." als auch "*   **Ort:** ..." (Label komplett
// fettgedruckt inkl. Doppelpunkt) kommen in echten Projekten vor - die 0-2
// optionalen "*" vor UND nach dem Label decken beide Formen ab. Keines der
// Labels enthaelt Regex-Sonderzeichen, deshalb ohne Escaping direkt in die
// Alternation uebernommen.
const FELD_LABEL_MUSTER = new RegExp(
  `^[ \\t]*[*-]?[ \\t]*\\*{0,2}[ \\t]*(${FELD_LABELS.join("|")})[ \\t]*:[ \\t]*\\*{0,2}[ \\t]*`,
  "gim",
);

/** Extrahiert ALLE 7 Felder auf einmal aus einem Kapitel-Block, jeweils als
 * Wert von "nach dem Label" bis "kurz vor das naechste gefundene Label"
 * (oder Blockende) - MEHRZEILIG, nicht nur die erste Zeile. Noetig, weil
 * z.B. ein Ereignis-Feld oft mehrere Saetze/Absaetze mit eigenen
 * Zeilenumbruechen enthaelt (die Textarea im Editor erlaubt das explizit).
 * Eine reine "ein Label = eine Zeile"-Extraktion (fruehere Fassung) hat
 * hier still Text verschluckt: nur die erste Zeile eines mehrzeiligen
 * Ereignis-Felds kam beim naechsten Laden/Speichern noch an, der Rest fiel
 * unbemerkt weg (Vorfall Kapitel 7 "Die Fischerhütte" in
 * a-Blut-und-Ahornlaub-Die-Ehre-des-Verbotenen, 2026-08-21). */
function alleFelderExtrahieren(block: string): Record<string, string> {
  const treffer = [...block.matchAll(FELD_LABEL_MUSTER)];
  const ergebnis: Record<string, string> = {};
  treffer.forEach((m, i) => {
    const start = (m.index ?? 0) + m[0].length;
    const ende = i + 1 < treffer.length ? (treffer[i + 1].index ?? block.length) : block.length;
    const wert = block.slice(start, ende).replace(/\*+[ \t\n]*$/, "").trim();
    // m[1] behaelt die im Text tatsaechlich vorkommende Schreibweise (die
    // Suche ist "i"-case-insensitive) - auf die kanonische Form aus
    // FELD_LABELS zurueckfuehren, damit der Objekt-Key immer gleich heisst.
    const kanonisch = FELD_LABELS.find((l) => l.toLowerCase() === m[1].toLowerCase());
    if (kanonisch) ergebnis[kanonisch] = wert;
  });
  return ergebnis;
}

function zielwortzahlExtrahieren(wert: string | undefined): number | null {
  if (!wert) return null;
  const treffer = [...wert.matchAll(/([\d][\d.,]*)[ \t]*W(?:oe|ö)rter/gi)];
  if (treffer.length === 0) return null;
  // Bei einer Spanne ("1800–2200 Wörter") wie im Backend die LETZTE (obere)
  // Zahl vor "Wörter" verwenden.
  const zahlText = treffer[treffer.length - 1][1].replace(/[.,]/g, "");
  const zahl = Number(zahlText);
  return Number.isFinite(zahl) && zahl > 0 ? zahl : null;
}

/** null = "nicht sicher genug geparst" (siehe Gegenprobe unten), NIE ein
 * Grund, den Rohtext zu verwerfen - der Aufrufer (kapitelplanAusGeruest
 * Extrahieren) faellt in diesem Fall auf Freitext zurueck. */
function kapitelBloeckeParsen(body: string): KapitelEintrag[] | null {
  const treffer = [...body.matchAll(KAPITEL_HEADING_MUSTER)];
  const erwaehnungen = [...body.matchAll(KAPITEL_ERWAEHNUNG_MUSTER)];
  // Findet die lockere Gegenprobe MEHR "Kapitel N:"-Stellen als der
  // strenge Parser oben Ueberschriften erkannt hat, gibt es vermutlich
  // Kapitel in einem Format, das hier nicht erkannt wird - lieber gar
  // nicht strukturiert anzeigen als welche zu verschlucken (Vorfall:
  // Bayern-zur-Zeit-Koenig-Ludwigs-II/Das-Vergehen-des-Adels-..., 2026-08-20 -
  // alle 6 Kapitel nutzten "**Kapitel 1: ...**" OHNE Bullet-Praefix und
  // waeren mit dem alten, zu strengen Muster komplett verlorengegangen).
  if (treffer.length === 0 || treffer.length < erwaehnungen.length) {
    return null;
  }
  return treffer.map((m, i) => {
    const start = (m.index ?? 0) + m[0].length;
    const ende = i + 1 < treffer.length ? (treffer[i + 1].index ?? body.length) : body.length;
    const felder = alleFelderExtrahieren(body.slice(start, ende));
    return {
      titel: (m[2] ?? "").trim(),
      vergangeneZeit: felder["Vergangene Zeit"] ?? "",
      ort: felder["Ort"] ?? "",
      anwesendeFiguren: felder["Anwesende Figuren"] ?? "",
      ereignis: felder["Ereignis"] ?? "",
      zielwortzahl: zielwortzahlExtrahieren(felder["Zielwortzahl"]),
      funktionImSpannungsbogen: felder["Funktion im Spannungsbogen"] ?? "",
      standDerLiebeshandlung: felder["Stand der Liebeshandlung"] ?? "",
      zustandAmKapitelende: felder["Zustand am Kapitelende"] ?? "",
    };
  });
}

/** Trennt ein komplettes geruest.md in "vor" (alles bis vor "## Kapitelplan"),
 * die strukturiert geparsten Kapitel-Bloecke, und "nach" (alles ab der
 * naechsten "## "-Ueberschrift danach). Kein "## Kapitelplan" gefunden -
 * z.B. ein brandneues, noch leeres Geruest -> der komplette Text landet in
 * "vor", kapitel bleibt leer (kein Fehler, siehe kapitelplan_pruefen()
 * backend-seitig: ein fehlender Abschnitt ist kein Strukturfehler).
 *
 * Ein VORHANDENER, nicht-leerer Kapitelplan, der sich nicht sicher in
 * Kapitel-Karten zerlegen laesst, wird NIE verworfen: er bleibt als Rohtext
 * unangetastet in "nach" (samt "## Kapitelplan"-Ueberschrift), "kapitel"
 * bleibt leer, und "warnung" erklaert dem Aufrufer warum - siehe
 * kapitelBloeckeParsen() oben. */
export function kapitelplanAusGeruestExtrahieren(geruestRoh: string): GeruestMitKapitelplan {
  // Manche Projekte (z.B. waehrend lokaler Windows-Entwicklung gespeichert)
  // haben CRLF-Zeilenenden statt LF - ALLE Regexe hier verankern auf "\n",
  // ein liegen gebliebenes "\r" davor liesse jedes Muster stillschweigend
  // scheitern (Vorfall Eine-unerwartete-Begegnung, 2026-08-20: "##
  // Kapitelplan\r\n" wurde dadurch gar nicht erst als Abschnitt erkannt,
  // der GESAMTE Text inkl. sechs fertig geschriebener Kapitel landete
  // undifferenziert in "vor" - ohne Datenverlust, aber ohne Warnung).
  const geruest = geruestRoh.replace(/\r\n/g, "\n");
  const headingMatch = geruest.match(/##[ \t]*Kapitelplan[ \t]*\n/i);
  if (!headingMatch || headingMatch.index === undefined) {
    return { vor: geruest, kapitel: [], nach: "", warnung: null };
  }
  const vorEnde = headingMatch.index;
  const bodyStart = headingMatch.index + headingMatch[0].length;
  const rest = geruest.slice(bodyStart);
  const nextHeadingMatch = rest.match(/\n##[ \t]/);
  const bodyEnde = nextHeadingMatch && nextHeadingMatch.index !== undefined ? nextHeadingMatch.index : rest.length;
  const body = rest.slice(0, bodyEnde);
  const nach = rest.slice(bodyEnde).replace(/^[ \t\n]+/, "");
  const vor = geruest.slice(0, vorEnde).replace(/[ \t\n]+$/, "");

  const kapitel = kapitelBloeckeParsen(body);
  if (kapitel === null && body.trim()) {
    return {
      vor,
      kapitel: [],
      nach: [`## Kapitelplan\n${body.trim()}`, nach].filter((t) => t.length > 0).join("\n\n"),
      warnung:
        "Der vorhandene Kapitelplan konnte nicht in einzelne Kapitel-Karten zerlegt werden (unbekanntes " +
        "Format) - er steht unverändert weiter unten als Freitext und wurde NICHT gelöscht. Bitte dort " +
        "weiterbearbeiten, statt über \"+ Kapitel\" einen zweiten, separaten Kapitelplan anzulegen.",
    };
  }
  return { vor, kapitel: kapitel ?? [], nach, warnung: null };
}

function kapitelBlockSerialisieren(kapitel: KapitelEintrag, index: number): string {
  const zielwortzahlZeile = kapitel.zielwortzahl != null && kapitel.zielwortzahl > 0
    ? `ca. ${kapitel.zielwortzahl} Wörter.`
    : "";
  return [
    `*   **Kapitel ${zahlwort(index + 1)}: ${kapitel.titel.trim()}**`,
    `    *   Vergangene Zeit: ${kapitel.vergangeneZeit.trim()}`,
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
