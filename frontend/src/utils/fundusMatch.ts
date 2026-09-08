// Verbindet den freien "## Figuren"-Abschnitt eines Geruests (RahmenEditor.tsx)
// mit dem Personen-Fundus (FundusPage.tsx/PersonenEditor.tsx): tippt der
// Nutzer einen Figurennamen, der bereits im Fundus derselben Epoche steht,
// soll das Uebernehmen der dort hinterlegten Merkmale angeboten werden,
// statt sie erneut von Hand einzutippen.
import type { FundusFigur } from "../api/types";

/** Epoche-Namen sind in freier Wildbahn nicht konsistent geschrieben -
 * dieselbe Epoche steht z.B. in einem Projekt-".epoche"-Marker als "Burg
 * Schreckenstein" (mit Leerzeichen), im Fundus aber als "Burg-Schreckenstein"
 * (mit Bindestrich, siehe realer Vorfall 2026-08-27). Bindestriche und
 * Leerzeichen werden deshalb als gleichwertig behandelt, bevor verglichen
 * wird - ein reiner "==="-Vergleich haette hier faelschlich NIE getroffen. */
export function normalisierteEpoche(epoche: string): string {
  return epoche.trim().toLowerCase().replace(/[-\s]+/g, " ");
}

/** Pseudo-Epoche im Personen- und Orte-Fundus: eine Figur/ein Ort, der unter
 * "## Allgemein" gepflegt wird, taucht in JEDER Epoche als Vorschlag auf
 * (z.B. der Autor selbst als Figur, ein epochenuebergreifender Schauplatz).
 * Technisch nur eine weitere "## <Epoche>"-Sektion mit diesem festen Namen. */
export const ALLGEMEIN_EPOCHE = "Allgemein";

const ALLGEMEIN_NORMALISIERT = normalisierteEpoche(ALLGEMEIN_EPOCHE);

export function istAllgemeineEpoche(epoche: string | null | undefined): boolean {
  return !!epoche && normalisierteEpoche(epoche) === ALLGEMEIN_NORMALISIERT;
}

/** True, wenn ein Fundus-Eintrag mit `eintragEpoche` fuer ein Projekt der
 * Epoche `zielEpoche` angeboten werden soll - bei (Bindestrich-/Leerzeichen-
 * tolerantem) Treffer ODER wenn der Eintrag als "Allgemein" gepflegt ist. */
export function epochePasstOderAllgemein(
  eintragEpoche: string, zielEpoche: string | null | undefined,
): boolean {
  if (istAllgemeineEpoche(eintragEpoche)) return true;
  if (!zielEpoche) return false;
  return normalisierteEpoche(eintragEpoche) === normalisierteEpoche(zielEpoche);
}

/** Liefert alle Fundus-Figuren der angegebenen Epoche (gleicher Bindestrich-/
 * Leerzeichen-tolerante Abgleich wie fundusFigurFinden) PLUS aller als
 * "Allgemein" gepflegten Figuren - Grundlage fuer die Vorschlagsliste in
 * FigurenAuswahl.tsx (Mehrfachauswahl "Anwesende Figuren" im Kapitelplan).
 * Leeres Array, wenn Epoche fehlt und keine Allgemein-Figuren da sind. */
export function fundusFigurenFuerEpoche(
  fundusFiguren: FundusFigur[], epoche: string | null | undefined,
): FundusFigur[] {
  return fundusFiguren.filter((f) => epochePasstOderAllgemein(f.epoche, epoche));
}

/** Case-insensitive Namensvergleich, auf die Epoche des aktuellen Projekts
 * beschraenkt - Merkmale wie "Stand/Rolle" oder "Aussehen" sind i.d.R. nur
 * innerhalb derselben Epoche sinnvoll uebertragbar (gleiche Konvention wie
 * die "FUNDUS DIESER EPOCHE"-Vorschlaege im Architekten-Interview). Liefert
 * undefined, wenn Name leer ist oder keine passende Figur existiert. */
export function fundusFigurFinden(
  fundusFiguren: FundusFigur[], epoche: string | null | undefined, name: string,
): FundusFigur | undefined {
  const gesucht = name.trim().toLowerCase();
  if (!gesucht) return undefined;
  return fundusFiguren.find(
    (f) => epochePasstOderAllgemein(f.epoche, epoche) && f.name.trim().toLowerCase() === gesucht,
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
