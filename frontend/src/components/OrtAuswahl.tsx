import { useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { Ort } from "../api/types";

interface OrtAuswahlProps {
  /** Freitext, wie ihn das Geruest-Format erwartet (KapitelEintrag.ort) -
   * bleibt bewusst ein simpler String statt einer Referenz auf einen
   * Fundus-Eintrag, damit Parsen/Serialisieren des Kapitelplans unveraendert
   * bleibt und auch ein (noch) nicht im Fundus gepflegter Ort eingetragen
   * werden kann. */
  value: string;
  onChange: (value: string) => void;
  orte?: Ort[];
  epoche?: string | null;
  className?: string;
}

/** Einzelwert-Pendant zu FigurenAuswahl.tsx fuer das Feld "Ort" im
 * Kapitelplan (KapitelplanEditor.tsx): Textfeld mit Dropdown-Vorschlaegen aus
 * dem Orte-Fundus (nur Orte derselben Epoche), UND weiterhin freie
 * Texteingabe fuer Orte, die (noch) nicht im Fundus stehen - anders als bei
 * Figuren gibt es hier keine Mehrfachauswahl (ein Kapitel spielt an genau
 * einem Ort), deshalb kein Chip-Array, sondern ein einzelner String. */
export function OrtAuswahl({ value, onChange, orte = [], epoche, className = "" }: OrtAuswahlProps) {
  const [fokussiert, setFokussiert] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const orteOptionen = useMemo(
    () => orte.filter((o) => !epoche || o.epoche === epoche),
    [orte, epoche],
  );

  const vorschlaege = useMemo(() => {
    const suchtext = value.trim().toLowerCase();
    return orteOptionen
      .filter((o) => !suchtext || o.name.toLowerCase().includes(suchtext))
      .slice(0, 8);
  }, [orteOptionen, value]);

  function auswaehlen(name: string) {
    onChange(name);
    setFokussiert(false);
    inputRef.current?.blur();
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      setFokussiert(false);
      inputRef.current?.blur();
    }
  }

  const zeigeVorschlaege = fokussiert && vorschlaege.length > 0;

  return (
    <div className="relative">
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        onFocus={() => setFokussiert(true)}
        // Verzoegerung noetig, damit ein Klick auf einen Vorschlag (siehe
        // onMouseDown/preventDefault dort) VOR dem Blur noch ankommt.
        onBlur={() => setTimeout(() => setFokussiert(false), 120)}
        placeholder="Ort eingeben oder aus Fundus wählen..."
        className={`w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text outline-none transition-colors focus:border-accent ${className}`}
      />
      {zeigeVorschlaege && (
        <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-lg border border-border bg-surface shadow-lg">
          {vorschlaege.map((o) => (
            <button
              key={o.name}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => auswaehlen(o.name)}
              title={o.beschreibung}
              className="block w-full px-3 py-1.5 text-left text-sm text-text hover:bg-surface-hover"
            >
              📍 {o.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
