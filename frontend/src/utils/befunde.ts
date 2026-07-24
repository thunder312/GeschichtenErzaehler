// Die Befunde-Berichte werden serverseitig deterministisch mit den
// Ueberschriften "## Anachronismen" und "## Kontinuitaet und Logik"
// zusammengebaut (siehe backend/app/api/pipeline.py, _pruefe_kapitel) -
// das Aufteilen anhand dieser Marker ist daher zuverlaessig moeglich, auch
// wenn der Inhalt darunter frei formulierter LLM-Text ist.
const ANACHRONISMEN_MARKER = /^##\s*Anachronismen\s*$/im;
const KONTINUITAET_MARKER = /^##\s*Kontinuit[aä]t(?:en)? und Logik\s*$/im;

export interface BefundeAbschnitte {
  header: string;
  anachronismen: string;
  kontinuitaet: string;
  erkannt: boolean;
}

function trennlinieAbschneiden(text: string): string {
  return text.replace(/-{3,}\s*$/, "").trim();
}

export function befundeAufteilen(text: string): BefundeAbschnitte {
  const aMatch = ANACHRONISMEN_MARKER.exec(text);
  const kMatch = KONTINUITAET_MARKER.exec(text);

  if (!aMatch || !kMatch) {
    return { header: "", anachronismen: text, kontinuitaet: "", erkannt: false };
  }

  const header = trennlinieAbschneiden(text.slice(0, aMatch.index));
  const anachronismen = trennlinieAbschneiden(text.slice(aMatch.index + aMatch[0].length, kMatch.index));
  const kontinuitaet = text.slice(kMatch.index + kMatch[0].length).trim();

  return { header, anachronismen, kontinuitaet, erkannt: true };
}