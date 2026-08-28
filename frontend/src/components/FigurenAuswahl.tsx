import { useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { FundusFigur } from "../api/types";
import { fundusFigurenFuerEpoche } from "../utils/fundusMatch";

interface FigurenAuswahlProps {
  /** Kommagetrennter Freitext, wie ihn das Geruest-Format erwartet (siehe
   * utils/kapitelplan.ts: KapitelEintrag.anwesendeFiguren, z.B.
   * "Ottokar, Stephan, Daniel") - bleibt bewusst ein simpler String statt
   * eines eigenen Array-Felds, damit Parsen/Serialisieren des Kapitelplans
   * unveraendert bleibt. */
  value: string;
  onChange: (value: string) => void;
  fundusFiguren?: FundusFigur[];
  epoche?: string | null;
  className?: string;
}

function namenAusWert(value: string): string[] {
  return value.split(",").map((n) => n.trim()).filter(Boolean);
}

/** Mehrfachauswahl fuer "Anwesende Figuren" im Kapitelplan (KapitelplanEditor.tsx):
 * Chips fuer bereits gewaehlte Namen, ein Textfeld mit Fundus-gespeisten
 * Vorschlaegen (nur Figuren derselben Epoche, siehe fundusFigurenFuerEpoche),
 * UND freie Texteingabe fuer Figuren, die (noch) nicht im Fundus stehen -
 * der Nutzer bleibt fuer neue/einmalige Nebenfiguren kreativ frei, siehe
 * ToDo-Wunsch "zusaetzlich freie Namen eingeben, da darf der Schreiber
 * kreativ sein". Speichert weiterhin nur den kommagetrennten String, kein
 * eigenes Datenformat. */
export function FigurenAuswahl({
  value, onChange, fundusFiguren = [], epoche, className = "",
}: FigurenAuswahlProps) {
  const [eingabe, setEingabe] = useState("");
  const [fokussiert, setFokussiert] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const ausgewaehlt = namenAusWert(value);
  const ausgewaehltKlein = useMemo(
    () => new Set(ausgewaehlt.map((n) => n.toLowerCase())),
    [ausgewaehlt],
  );

  const fundusOptionen = useMemo(
    () => fundusFigurenFuerEpoche(fundusFiguren, epoche),
    [fundusFiguren, epoche],
  );

  const vorschlaege = useMemo(() => {
    const suchtext = eingabe.trim().toLowerCase();
    return fundusOptionen
      .filter((f) => !ausgewaehltKlein.has(f.name.trim().toLowerCase()))
      .filter((f) => !suchtext || f.name.toLowerCase().includes(suchtext))
      .slice(0, 8);
  }, [fundusOptionen, eingabe, ausgewaehltKlein]);

  function hinzufuegen(name: string) {
    const bereinigt = name.trim();
    if (bereinigt && !ausgewaehltKlein.has(bereinigt.toLowerCase())) {
      onChange([...ausgewaehlt, bereinigt].join(", "));
    }
    setEingabe("");
    inputRef.current?.focus();
  }

  function entfernen(name: string) {
    onChange(ausgewaehlt.filter((n) => n !== name).join(", "));
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      if (eingabe.trim()) hinzufuegen(eingabe);
    } else if (e.key === "Backspace" && !eingabe && ausgewaehlt.length > 0) {
      entfernen(ausgewaehlt[ausgewaehlt.length - 1]);
    }
  }

  const zeigeVorschlaege = fokussiert && vorschlaege.length > 0;

  return (
    <div className={`relative ${className}`}>
      <div
        onClick={() => inputRef.current?.focus()}
        className="flex min-h-[2.5rem] flex-wrap items-center gap-1.5 rounded-lg border border-border bg-bg px-2 py-1.5 focus-within:border-accent"
      >
        {ausgewaehlt.map((name) => (
          <span
            key={name}
            className="flex items-center gap-1 rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-medium text-accent-light"
          >
            {name}
            <button
              type="button"
              onClick={() => entfernen(name)}
              className="text-accent-light/70 hover:text-accent-light"
              aria-label={`${name} entfernen`}
            >
              ✕
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          value={eingabe}
          onChange={(e) => setEingabe(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => setFokussiert(true)}
          // Verzoegerung noetig, damit ein Klick auf einen Vorschlag (siehe
          // onMouseDown/preventDefault dort) VOR dem Blur noch ankommt.
          onBlur={() => setTimeout(() => setFokussiert(false), 120)}
          placeholder={ausgewaehlt.length === 0 ? "Name eingeben oder aus Fundus wählen..." : ""}
          className="min-w-[8rem] flex-1 bg-transparent py-0.5 text-sm text-text outline-none placeholder:text-text-muted/70"
        />
      </div>
      {zeigeVorschlaege && (
        <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-lg border border-border bg-surface shadow-lg">
          {vorschlaege.map((f) => (
            <button
              key={f.name}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => hinzufuegen(f.name)}
              className="block w-full px-3 py-1.5 text-left text-sm text-text hover:bg-surface-hover"
            >
              📋 {f.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
