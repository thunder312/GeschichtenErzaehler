import { useEffect, useState } from "react";
import { useAktivitaet } from "../context/AktivitaetContext";

/** Feste Fussleiste: zeigt an, welche KI-Anfrage gerade laeuft, inklusive
 * hochzaehlender Sekunden - gibt Sicherheit, dass die Anwendung nicht
 * abgestuerzt ist, waehrend z.B. das Pruefen eines Kapitels ohne
 * Zwischen-Feedback vom Backend wartet. */
export function StatusFooter() {
  const { aktivitaet } = useAktivitaet();
  const [jetzt, setJetzt] = useState(Date.now());

  useEffect(() => {
    if (!aktivitaet) return;
    setJetzt(Date.now());
    const intervall = setInterval(() => setJetzt(Date.now()), 1000);
    return () => clearInterval(intervall);
  }, [aktivitaet]);

  const sekunden = aktivitaet ? Math.max(0, Math.round((jetzt - aktivitaet.seit) / 1000)) : 0;

  return (
    <footer className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface px-4 py-2 text-sm sm:px-6">
      {aktivitaet ? (
        <div className="flex items-center gap-2 text-accent-light">
          <span className="inline-block h-2 w-2 shrink-0 animate-pulse rounded-full bg-accent" aria-hidden="true" />
          <span>{aktivitaet.text}</span>
          <span className="text-text-muted">({sekunden}s)</span>
        </div>
      ) : (
        <div className="flex items-center gap-2 text-text-muted">
          <span className="inline-block h-2 w-2 shrink-0 rounded-full bg-text-muted/40" aria-hidden="true" />
          <span>Bereit.</span>
        </div>
      )}
    </footer>
  );
}
