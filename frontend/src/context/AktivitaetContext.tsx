import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

interface AktivitaetState {
  text: string;
  seit: number;
}

interface AktivitaetApi {
  aktivitaet: AktivitaetState | null;
  starten: (text: string) => void;
  beenden: () => void;
}

const AktivitaetContext = createContext<AktivitaetApi | null>(null);

/** Globaler Status "was macht die KI gerade" - unabhaengig vom aktiven Tab
 * sichtbar (siehe StatusFooter), damit ein laengerer Ollama-Aufruf (v.a.
 * Pruefen: zwei sequentielle LLM-Anfragen ohne Zwischenstreaming) nicht wie
 * ein abgestuerzter Tab wirkt. */
export function AktivitaetProvider({ children }: { children: ReactNode }) {
  const [aktivitaet, setAktivitaet] = useState<AktivitaetState | null>(null);

  const starten = useCallback((text: string) => {
    setAktivitaet({ text, seit: Date.now() });
  }, []);

  const beenden = useCallback(() => {
    setAktivitaet(null);
  }, []);

  const value = useMemo(() => ({ aktivitaet, starten, beenden }), [aktivitaet, starten, beenden]);

  return <AktivitaetContext.Provider value={value}>{children}</AktivitaetContext.Provider>;
}

export function useAktivitaet(): AktivitaetApi {
  const ctx = useContext(AktivitaetContext);
  if (!ctx) throw new Error("useAktivitaet() muss innerhalb von <AktivitaetProvider> verwendet werden.");
  return ctx;
}
