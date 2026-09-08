import { useMemo } from "react";
import type { EpocheKurz } from "../api/types";
import { ALLGEMEIN_EPOCHE, istAllgemeineEpoche, normalisierteEpoche } from "../utils/fundusMatch";
import { Select } from "./ui";

interface EpocheSelectProps {
  /** Gespeicherter Wert: der stabile Ordner-/Identifier-Name einer Epoche
   * (EpocheKurz.name) oder die Pseudo-Epoche "Allgemein". */
  value: string;
  onChange: (value: string) => void;
  epochen: EpocheKurz[];
  /** Text der leeren Startoption. */
  platzhalter?: string;
  className?: string;
}

/** Dropdown "Epoche" fuer den Personen-/Orte-Fundus: alle bestehenden Epochen
 * (Anzeige = anzeigename, Wert = stabiler name) plus eine feste Option
 * "Allgemein" - damit lassen sich Figuren/Orte anlegen, die in JEDER Epoche
 * als Vorschlag auftauchen (siehe utils/fundusMatch.ts:ALLGEMEIN_EPOCHE).
 * Ein bereits gespeicherter Wert, der zu keiner aktuellen Epoche passt (z.B.
 * frueher frei getippt, Epoche inzwischen umbenannt), bleibt als eigene
 * Option erhalten, statt stillschweigend zu verschwinden. */
export function EpocheSelect({
  value, onChange, epochen, platzhalter = "– Epoche wählen –", className = "",
}: EpocheSelectProps) {
  const unbekannterWert = useMemo(() => {
    if (!value || istAllgemeineEpoche(value)) return null;
    const bekannt = epochen.some((e) => normalisierteEpoche(e.name) === normalisierteEpoche(value));
    return bekannt ? null : value;
  }, [value, epochen]);

  return (
    <Select className={className} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{platzhalter}</option>
      {epochen.map((e) => (
        <option key={e.name} value={e.name}>
          {e.anzeigename}
        </option>
      ))}
      <option value={ALLGEMEIN_EPOCHE}>Allgemein (alle Epochen)</option>
      {unbekannterWert && <option value={unbekannterWert}>{unbekannterWert} (unbekannt)</option>}
    </Select>
  );
}
