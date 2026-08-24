// Strukturierter Editor NUR fuer den Teil von geruest.md VOR "## Kapitelplan"
// (siehe utils/kapitelplan.ts fuer den Kapitelplan-Teil selbst und
// GeruestPage.tsx fuer die Einbindung). Bisher war dieser komplette Block
// ("## Rahmen", "## Titel", "## Unerhörte Begebenheit", "## Figuren",
// "## Konflikt", "## Nebenstrang") EIN einziges Freitext-Markdown-Feld -
// gerade beim erstmaligen Ausfuellen ueber "Gerüst selbst schreiben" (ohne
// Architekten-Interview) war unklar, was wo einzutragen ist (siehe ToDo.md).
//
// Strategie wie in kapitelplan.ts: jede "## "-Ueberschrift wird ein eigenes,
// klar beschriftetes Feld statt eines gemeinsamen Textblocks. "## Rahmen" und
// "## Figuren" bekommen zusaetzlich eine feinere Aufschluesselung in
// Einzelfelder bzw. Personen-Karten - beides NUR "best effort": erkennt der
// Parser eine Zeile/einen Abschnitt nicht sicher, landet der Rohtext
// unveraendert in einem Auffangfeld ("Weitere Angaben" bzw. Rohtext-Fallback)
// statt verworfen zu werden. Backend-seitig aendert sich nichts (siehe
// backend/app/core/geruest.py) - die hier erzeugten Bullet-Zeilen folgen
// exakt dem Format, das die dortigen Regexe ohnehin schon lesen.

export interface Abschnitt {
  heading: string;
  body: string;
}

export interface VorStruktur {
  praeambel: string;
  abschnitte: Abschnitt[];
}

/** Zerlegt den "vor"-Teil (siehe kapitelplanAusGeruestExtrahieren) in eine
 * Praeambel (typischerweise nur "# STORY-GERUEST") und eine geordnete Liste
 * von "## "-Abschnitten. Rein strukturell, verwirft nichts - jeder Bestand an
 * Text taucht entweder in praeambel oder in genau einem Abschnitt wieder auf.
 * Absichtlich NUR einfache "## " (zwei Rauten), keine "### "-Unterueberschriften -
 * "## Ausgangslage vor Kapitel eins" im "nach"-Teil nutzt "### Figuren"/
 * "### Zeit"/... als Unterpunkte, die hier nicht relevant sind (der "nach"-
 * Teil bleibt bewusst weiterhin Freitext, siehe GeruestPage.tsx). */
export function vorAbschnitteZerlegen(vorRoh: string): VorStruktur {
  const vor = vorRoh.replace(/\r\n/g, "\n");
  const muster = /^##[ \t]+(.+?)[ \t]*$/gm;
  const treffer = [...vor.matchAll(muster)];
  if (treffer.length === 0) {
    return { praeambel: vor.trim(), abschnitte: [] };
  }
  const praeambel = vor.slice(0, treffer[0].index ?? 0).trim();
  const abschnitte: Abschnitt[] = treffer.map((m, i) => {
    const start = (m.index ?? 0) + m[0].length;
    const ende = i + 1 < treffer.length ? (treffer[i + 1].index ?? vor.length) : vor.length;
    return { heading: m[1].trim(), body: vor.slice(start, ende).trim() };
  });
  return { praeambel, abschnitte };
}

/** Gegenstueck zu vorAbschnitteZerlegen(). */
export function vorAusAbschnittenZusammenbauen(struktur: VorStruktur): string {
  const teile = [struktur.praeambel.trim()];
  for (const a of struktur.abschnitte) {
    teile.push(`## ${a.heading}\n${a.body.trim()}`);
  }
  return teile.filter((t) => t.length > 0).join("\n\n");
}

interface RohBullet {
  label: string;
  wert: string;
}

// Erfasst "* Label: Wert", "*   **Label:** Wert" und Mischformen (0-2
// optionale "*" vor UND nach dem Label, wie schon in kapitelplan.ts
// FELD_LABEL_MUSTER) - EIN Label pro Zeile. Eine Folgezeile OHNE eigenen
// Bullet-Marker wird als Fortsetzung des vorherigen Werts behandelt (siehe
// bulletZeilenParsen unten), deckt also auch mehrzeilige Werte ab (z.B. eine
// laengere Tonlage-Beschreibung).
const BULLET_ZEILE_MUSTER = /^[ \t]*[*-][ \t]*\*{0,2}[ \t]*([^:*\n]+?)[ \t]*\*{0,2}[ \t]*:[ \t]*\*{0,2}[ \t]*(.*)$/;

function bulletZeilenParsen(body: string): RohBullet[] {
  const bullets: RohBullet[] = [];
  for (const zeile of body.split("\n")) {
    const m = zeile.match(BULLET_ZEILE_MUSTER);
    if (m) {
      bullets.push({ label: m[1].trim(), wert: m[2].replace(/\*+[ \t]*$/, "").trim() });
    } else if (bullets.length > 0 && zeile.trim()) {
      const letzter = bullets[bullets.length - 1];
      letzter.wert = `${letzter.wert} ${zeile.trim()}`.trim();
    }
  }
  return bullets;
}

// Reale, vom Architekten-Interview erzeugte "## Rahmen"-Abschnitte stehen oft
// NICHT als Bullet-Liste, sondern als EIN einzeiliger, kommagetrennter Satz:
// "Jahr: 1250, Ort: ..., Jahreszeit: ..., Erzaehlperspektive: ..., ...". Ohne
// diese zweite Erkennung faende bulletZeilenParsen() oben ueberhaupt keine
// Bullets, und der komplette Rahmen wuerde beim Serialisieren zurueck nach
// geruest.md STILLSCHWEIGEND VERWORFEN (Vorfall beim Testen dieses Editors an
// "Eine unerwartete Begegnung", 2026-08-24 - die reale Rahmen-Zeile bestand
// exakt aus diesem Format). Nur EIN naiver Split reicht nicht (ein Wert wie
// "Ort: Bath, Brighton" enthaelt selbst ein Komma) - matcht deshalb wie
// alleFelderExtrahieren() in kapitelplan.ts ALLE Label-Startpositionen
// gleichzeitig und nimmt den Text dazwischen als Wert, statt naiv bei jedem
// Komma zu trennen.
const KOMMA_LABEL_MUSTER = /(?:^|,)\s*([A-ZÄÖÜ][A-Za-zäöüÄÖÜß\-/ ]{1,30}?):\s*/g;

function kommaGetrennteBulletsParsen(body: string): RohBullet[] {
  const einzeiler = body.replace(/\s*\n\s*/g, " ").trim();
  const treffer = [...einzeiler.matchAll(KOMMA_LABEL_MUSTER)];
  // Bei nur einem Treffer ist die Erkennung zu unsicher (koennte z.B. ein
  // einzelner Doppelpunkt in einem Fliesstext-Satz sein) - dann lieber gar
  // nicht strukturiert parsen, siehe Aufrufer (rahmenFelderAusBody: faellt
  // auf den kompletten Rohtext in "weitereAngaben" zurueck).
  if (treffer.length < 2) return [];
  return treffer.map((m, i) => {
    const start = (m.index ?? 0) + m[0].length;
    const ende = i + 1 < treffer.length ? (treffer[i + 1].index ?? einzeiler.length) : einzeiler.length;
    return { label: m[1].trim(), wert: einzeiler.slice(start, ende).trim() };
  });
}

function vereinfacht(s: string): string {
  return s
    .toLowerCase()
    .replace(/ä/g, "a")
    .replace(/ö/g, "o")
    .replace(/ü/g, "u")
    .replace(/ß/g, "ss")
    .trim();
}

// Bekannte Rahmen-Feld-Label inkl. gaengiger Varianten, wie sie in echten,
// vom Architekten generierten Gerüsten vorkommen koennen (siehe
// backend/app/core/epoche.py:architekt_vorlage - die Rahmen-Vorgabe dort ist
// eine freie Beschreibung, keine feste Bullet-Vorlage, die KI formuliert die
// tatsaechlichen Labels frei). Ein Bullet, dessen Label hier NICHT auftaucht,
// landet unveraendert in "weitereAngaben" statt verworfen zu werden.
type RahmenTextFeld = "zeitangabe" | "ort" | "jahreszeit" | "erzaehlperspektive" | "tempus" | "tonlage";

const RAHMEN_LABEL_ALIASE: Record<string, RahmenTextFeld | undefined> = {
  zeitangabe: "zeitangabe",
  jahr: "zeitangabe",
  ort: "ort",
  "ort und region": "ort",
  schauplatz: "ort",
  jahreszeit: "jahreszeit",
  erzahlperspektive: "erzaehlperspektive",
  perspektive: "erzaehlperspektive",
  tempus: "tempus",
  tonlage: "tonlage",
  ton: "tonlage",
};

export interface RahmenFelder {
  zeitangabe: string;
  ort: string;
  jahreszeit: string;
  erzaehlperspektive: string;
  tempus: string;
  tonlage: string;
  jugendschutzStufe: "voll" | "angedeutet" | "jugendfrei";
  automatischeFortsetzung: "ein" | "aus";
  weitereAngaben: string;
}

export function leereRahmenFelder(): RahmenFelder {
  return {
    zeitangabe: "",
    ort: "",
    jahreszeit: "",
    erzaehlperspektive: "Dritte Person",
    tempus: "Vergangenheitsform",
    tonlage: "",
    jugendschutzStufe: "voll",
    automatischeFortsetzung: "aus",
    weitereAngaben: "",
  };
}

// Die Vorlage (siehe utils/geruestVorlage.ts:leeresGeruestSkelett) schreibt
// den Wert dieser drei Bullets bewusst mit wiederholtem Label ("Jugendschutz-
// Stufe: Jugendschutz-Stufe: Voll"), damit backend/app/core/geruest.py das
// Feld auch dann noch per Volltextsuche findet, wenn das Markdown-Bett davor
// (Bullet-Marker, Fettdruck) unterschiedlich ausfaellt. bulletZeilenParsen()
// oben schneidet nur das ERSTE (fettgedruckte) Label ab, der Wert traegt das
// Label deshalb oft noch ein zweites Mal wörtlich in sich - vor der
// eigentlichen Auswertung entfernen, sonst scheitert z.B. ein startsWith()
// an der wiederholten Kopie.
function entferneWiederholtesLabel(wert: string, label: string): string {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const muster = new RegExp(`^(?:${escaped}\\s*[:\\-]?\\s*)+`, "i");
  return wert.replace(muster, "").trim();
}

/** Wie backend/app/core/geruest.py:jugendschutz_stufe_erkennen() - dieselbe
 * Substring-Logik, damit Anzeige und spaetere serverseitige Auswertung nie
 * auseinanderlaufen. */
function jugendschutzAusRohwert(wertRoh: string): RahmenFelder["jugendschutzStufe"] | null {
  const w = entferneWiederholtesLabel(wertRoh, "Jugendschutz-Stufe").toLowerCase();
  if (w.includes("jugendfrei")) return "jugendfrei";
  if (w.includes("angedeutet") || w.includes("romantisch")) return "angedeutet";
  if (w.includes("voll")) return "voll";
  return null;
}

/** Wie backend/app/core/geruest.py:automatische_fortsetzung_aktiviert(). */
function fortsetzungAusRohwert(wertRoh: string): RahmenFelder["automatischeFortsetzung"] | null {
  const w = entferneWiederholtesLabel(wertRoh, "Automatische Fortsetzung").toLowerCase();
  if (w.startsWith("ein")) return "ein";
  if (w.startsWith("aus")) return "aus";
  return null;
}

/** Zerlegt den Body von "## Rahmen" in Einzelfelder. Nie ein Totalausfall wie
 * bei kapitelplanAusGeruestExtrahieren() - jedes Feld hat einen Default (siehe
 * leereRahmenFelder), nicht erkannte Bullets (z.B. "Autor-Modell", oder eine
 * epochenspezifische Zusatzangabe) sammeln sich unveraendert in
 * "weitereAngaben", damit beim Speichern nichts verloren geht. Erkennt weder
 * bulletZeilenParsen() noch die Komma-Variante (kommaGetrennteBulletsParsen())
 * AUCH NUR EINEN Bullet (z.B. echter Fliesstext ohne jede Label:Wert-Struktur),
 * landet der komplette Body unveraendert in "weitereAngaben" statt
 * stillschweigend zu verschwinden. */
export function rahmenFelderAusBody(body: string): RahmenFelder {
  const felder = leereRahmenFelder();
  const unbekannt: string[] = [];
  let jugendschutzGefunden = false;
  let fortsetzungGefunden = false;

  const bulletsGefunden = bulletZeilenParsen(body);
  const bullets = bulletsGefunden.length > 0 ? bulletsGefunden : kommaGetrennteBulletsParsen(body);
  if (bullets.length === 0) {
    if (body.trim()) felder.weitereAngaben = body.trim();
    return felder;
  }

  for (const bullet of bullets) {
    const ziel = RAHMEN_LABEL_ALIASE[vereinfacht(bullet.label)];
    if (vereinfacht(bullet.label) === "jugendschutz-stufe" || vereinfacht(bullet.label).includes("jugendschutz")) {
      const stufe = jugendschutzAusRohwert(bullet.wert);
      if (stufe) {
        felder.jugendschutzStufe = stufe;
        jugendschutzGefunden = true;
        continue;
      }
    }
    if (vereinfacht(bullet.label).includes("automatische fortsetzung")) {
      const fortsetzung = fortsetzungAusRohwert(bullet.wert);
      if (fortsetzung) {
        felder.automatischeFortsetzung = fortsetzung;
        fortsetzungGefunden = true;
        continue;
      }
    }
    if (vereinfacht(bullet.label).includes("autor-modell") || vereinfacht(bullet.label) === "autor modell") {
      // Seit dem Wegfall von Hermes3/Qwen3 gibt es nur noch Mistral (siehe
      // Memory "Autor-Modell nur noch Mistral") - der Bullet wird beim
      // Serialisieren ohnehin immer fest neu geschrieben, ein evtl.
      // abweichender Altwert wird bewusst NICHT in "weitereAngaben"
      // aufgehoben.
      continue;
    }
    if (ziel) {
      felder[ziel] = bullet.wert;
      continue;
    }
    unbekannt.push(`${bullet.label}: ${bullet.wert}`);
  }

  // Auch bei GEFUNDENEM, aber nicht auswertbarem Rohwert (z.B. "Jugendschutz-
  // Stufe: TBD") den Rohwert sichtbar behalten statt ihn stillschweigend
  // durch den Default zu ersetzen.
  if (!jugendschutzGefunden) {
    const roh = bullets.find((b) => vereinfacht(b.label).includes("jugendschutz"));
    if (roh && roh.wert) unbekannt.push(`Jugendschutz-Stufe: ${roh.wert}`);
  }
  if (!fortsetzungGefunden) {
    const roh = bullets.find((b) => vereinfacht(b.label).includes("automatische fortsetzung"));
    if (roh && roh.wert) unbekannt.push(`Automatische Fortsetzung: ${roh.wert}`);
  }

  felder.weitereAngaben = unbekannt.join("\n");
  return felder;
}

export function rahmenBodyAusFelder(felder: RahmenFelder): string {
  const stufeText = { voll: "Voll", angedeutet: "Angedeutet", jugendfrei: "Jugendfrei" }[felder.jugendschutzStufe];
  const fortsetzungText = { ein: "Ein", aus: "Aus" }[felder.automatischeFortsetzung];
  const zeilen = [
    `*   **Zeitangabe:** ${felder.zeitangabe.trim()}`,
    `*   **Ort:** ${felder.ort.trim()}`,
  ];
  if (felder.jahreszeit.trim()) zeilen.push(`*   **Jahreszeit:** ${felder.jahreszeit.trim()}`);
  zeilen.push(
    `*   **Erzählperspektive:** ${felder.erzaehlperspektive.trim()}`,
    `*   **Tempus:** ${felder.tempus.trim()}`,
    `*   **Tonlage:** ${felder.tonlage.trim()}`,
    `*   **Jugendschutz-Stufe:** Jugendschutz-Stufe: ${stufeText}`,
    `*   **Autor-Modell:** Autor-Modell: Mistral`,
    `*   **Automatische Fortsetzung:** Automatische Fortsetzung: ${fortsetzungText}`,
  );
  if (felder.weitereAngaben.trim()) {
    zeilen.push(...felder.weitereAngaben.trim().split("\n").map((z) => `*   ${z.trim()}`));
  }
  return zeilen.join("\n");
}

export interface FigurEintrag {
  name: string;
  details: string;
}

export function leereFigur(): FigurEintrag {
  return { name: "", details: "" };
}

/** null = Body sieht nicht wie eine Bullet-Liste "* **Name:** ..." aus (z.B.
 * ein alter, frei formulierter Fliesstext-Absatz) - der Aufrufer (RahmenEditor)
 * faellt dann auf ein einzelnes Rohtext-Feld fuer den gesamten Figuren-
 * Abschnitt zurueck, analog zur "warnung" in kapitelplan.ts. Ein leerer Body
 * liefert bewusst [] (kein Fallback), damit ueber "+ Figur" trotzdem gleich
 * strukturiert begonnen werden kann. */
export function figurenAusBody(body: string): FigurEintrag[] | null {
  if (!body.trim()) return [];
  const bullets = bulletZeilenParsen(body);
  if (bullets.length === 0) return null;
  return bullets.map((b) => ({ name: b.label, details: b.wert }));
}

export function figurenBodyAusEintraegen(figuren: FigurEintrag[]): string {
  return figuren.map((f) => `*   **${f.name.trim()}:** ${f.details.trim()}`).join("\n");
}

/** Ein einzelner "## "-Abschnitt aus dem "vor"-Teil, in der Form, die der
 * RahmenEditor tatsaechlich bearbeitet: "## Rahmen" bekommt Einzelfelder,
 * "## Figuren" wird - wenn erkennbar - zu Personen-Karten, jeder andere
 * Abschnitt (Titel, Unerhörte Begebenheit, Konflikt, Nebenstrang, sowie jede
 * epochenspezifische Zusatzueberschrift) bleibt ein einzelnes, klar
 * beschriftetes Freitextfeld ("roh"). */
export type VorAbschnittBearbeitet =
  | { heading: string; art: "rahmen"; felder: RahmenFelder }
  | { heading: string; art: "figuren"; figuren: FigurEintrag[] }
  | { heading: string; art: "roh"; text: string };

function abschnittZuBearbeitet(a: Abschnitt): VorAbschnittBearbeitet {
  const h = vereinfacht(a.heading);
  if (h === "rahmen") return { heading: a.heading, art: "rahmen", felder: rahmenFelderAusBody(a.body) };
  if (h === "figuren") {
    const figuren = figurenAusBody(a.body);
    if (figuren !== null) return { heading: a.heading, art: "figuren", figuren };
  }
  return { heading: a.heading, art: "roh", text: a.body };
}

function abschnittZuRoh(a: VorAbschnittBearbeitet): Abschnitt {
  if (a.art === "rahmen") return { heading: a.heading, body: rahmenBodyAusFelder(a.felder) };
  if (a.art === "figuren") return { heading: a.heading, body: figurenBodyAusEintraegen(a.figuren) };
  return { heading: a.heading, body: a.text };
}

/** Liefert null fuer "abschnitte", wenn im "vor"-Text ueberhaupt keine
 * "## "-Ueberschrift gefunden wurde (z.B. ein von Hand komplett geleertes
 * oder sehr altes, abweichend formatiertes Gerüst) - der Aufrufer
 * (GeruestPage) faellt dann auf den alten rohen Markdown-Editor fuer den
 * gesamten Block zurueck, statt ein irrefuehrend leeres Formular zu zeigen. */
export function vorZuBearbeitet(vorRoh: string): { praeambel: string; abschnitte: VorAbschnittBearbeitet[] | null } {
  const { praeambel, abschnitte } = vorAbschnitteZerlegen(vorRoh);
  if (abschnitte.length === 0) return { praeambel, abschnitte: null };
  return { praeambel, abschnitte: abschnitte.map(abschnittZuBearbeitet) };
}

export function bearbeitetZuVor(praeambel: string, abschnitte: VorAbschnittBearbeitet[]): string {
  return vorAusAbschnittenZusammenbauen({ praeambel, abschnitte: abschnitte.map(abschnittZuRoh) });
}
