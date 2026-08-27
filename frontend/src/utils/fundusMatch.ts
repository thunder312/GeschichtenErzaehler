// Verbindet den freien "## Figuren"-Abschnitt eines Geruests (RahmenEditor.tsx)
// mit dem Personen-Fundus (FundusPage.tsx/PersonenEditor.tsx): tippt der
// Nutzer einen Figurennamen, der bereits im Fundus derselben Epoche steht,
// soll das Uebernehmen der dort hinterlegten Merkmale angeboten werden,
// statt sie erneut von Hand einzutippen.
import type { FundusFigur } from "../api/types";

/** Case-insensitive Namensvergleich, auf die Epoche des aktuellen Projekts
 * beschraenkt - Merkmale wie "Stand/Rolle" oder "Aussehen" sind i.d.R. nur
 * innerhalb derselben Epoche sinnvoll uebertragbar (gleiche Konvention wie
 * die "FUNDUS DIESER EPOCHE"-Vorschlaege im Architekten-Interview). Liefert
 * undefined, wenn Name leer ist oder keine passende Figur existiert. */
export function fundusFigurFinden(
  fundusFiguren: FundusFigur[], epoche: string | null | undefined, name: string,
): FundusFigur | undefined {
  const gesucht = name.trim().toLowerCase();
  if (!gesucht || !epoche) return undefined;
  return fundusFiguren.find(
    (f) => f.epoche === epoche && f.name.trim().toLowerCase() === gesucht,
  );
}

/** Baut aus den Fundus-Feldern einer Figur den "Details"-Freitext, wie ihn
 * das Geruest-Figuren-Format erwartet (siehe utils/rahmen.ts:FigurEintrag,
 * Vorbild-Beispiel in der Architekten-Persona: "34 Jahre; Spionin im Dienst
 * der Krone; kühl und berechnend, ..."): nur die WERTE der Standard- und
 * Zusatzfelder, durch "; " getrennt, ohne die Feld-Label und ohne die
 * "Geschichten"-Liste (die gehoert nicht zur Charakterbeschreibung). Leere
 * Felder werden uebersprungen statt als leeres Segment mitgezogen zu werden. */
export function fundusFelderZuDetails(felder: Record<string, string>): string {
  return Object.entries(felder)
    .filter(([name, wert]) => name !== "Geschichten" && wert.trim())
    .map(([, wert]) => wert.trim())
    .join("; ");
}
