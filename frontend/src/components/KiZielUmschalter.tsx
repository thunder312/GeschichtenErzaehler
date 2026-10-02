import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { SSHZiel } from "../api/types";

type Erreichbarkeit = "pruefe" | "ja" | "nein";

interface KiZielUmschalterProps {
  ziele: SSHZiel[];
  value: string;
  onChange: (zielId: string) => void;
}

/** Umschalter im Kopfbereich zwischen den KI-Zielen, z.B. "Athene" (langsam,
 * laeuft immer - fuer Automatik ueber Nacht) und "PC" (schnell per GPU, muss
 * aber eingeschaltet sein). Jeder Knopf zeigt per Punkt, ob das Ziel gerade
 * erreichbar ist - geprueft einmal beim Laden und erneut beim Anklicken,
 * bewusst ohne Polling (siehe /erreichbar in backend/app/api/ssh_targets.py).
 * Ein bereits laufender Automatik-Lauf behaelt sein beim Start gewaehltes
 * Ziel; der Umschalter wirkt nur auf neu gestartete Aufrufe. */
export function KiZielUmschalter({ ziele, value, onChange }: KiZielUmschalterProps) {
  const [status, setStatus] = useState<Record<string, { e: Erreichbarkeit; meldung: string }>>({});

  function pruefen(id: string) {
    setStatus((s) => ({ ...s, [id]: { e: "pruefe", meldung: "Prüfe Erreichbarkeit…" } }));
    api
      .sshZielErreichbar(id)
      .then((r) => setStatus((s) => ({ ...s, [id]: { e: r.erfolgreich ? "ja" : "nein", meldung: r.meldung } })))
      .catch((err) => setStatus((s) => ({ ...s, [id]: { e: "nein", meldung: String(err) } })));
  }

  // Stabiler String-Schluessel statt der Array-Referenz als Effekt-Abhaengigkeit,
  // sonst wuerde jedes Neuladen der Ziel-Liste alle Checks erneut ausloesen.
  const zielSchluessel = ziele.map((z) => z.id).join(",");
  useEffect(() => {
    zielSchluessel.split(",").filter(Boolean).forEach(pruefen);
  }, [zielSchluessel]);

  if (ziele.length === 0) return null;

  return (
    <div role="radiogroup" aria-label="KI-Ziel" className="flex flex-wrap gap-1 rounded-lg border border-border bg-bg p-1">
      {ziele.map((z) => {
        const aktiv = z.id === value;
        const st = status[z.id];
        const punkt =
          st?.e === "ja" ? "bg-emerald-400" : st?.e === "nein" ? "bg-red-400" : "bg-text-muted animate-pulse";
        return (
          <button
            key={z.id}
            role="radio"
            aria-checked={aktiv}
            onClick={() => {
              onChange(z.id);
              pruefen(z.id);
            }}
            title={`${z.host}\n${st?.meldung ?? ""}`}
            className={`flex items-center gap-2 rounded-md px-3 py-1 text-sm transition-colors ${
              aktiv ? "bg-accent-soft text-accent-light shadow-inner" : "text-text-muted hover:bg-surface-hover hover:text-text"
            }`}
          >
            <span aria-hidden="true" className={`h-2 w-2 shrink-0 rounded-full ${punkt}`} />
            {z.name}
          </button>
        );
      })}
    </div>
  );
}
