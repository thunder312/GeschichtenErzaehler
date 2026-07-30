import { useEffect, useRef } from "react";
import type { ProjektDetail } from "../api/types";

/** Haelt die Kapitelnummer eines Review-Tabs (Pruefen & Anwenden,
 * Rechtschreibung, Stand & Export) synchron mit dem zuletzt geschriebenen
 * Kapitel - der haeufigste Workflow ist "Kapitel schreiben, dann direkt
 * dieses Kapitel pruefen". Reagiert auch, wenn der
 * Tab schon gemountet war und WAEHREND der Sitzung ein neues Kapitel
 * dazukommt (Tabs bleiben dauerhaft gemountet, siehe App.tsx). Ueberschreibt
 * keine manuelle Eingabe, solange sich das zuletzt geschriebene Kapitel
 * nicht tatsaechlich aendert. */
export function useLetztesKapitelSync(projekt: ProjektDetail | null, setN: (n: number) => void) {
  const letzterStand = useRef<number | null>(projekt?.kapitel.at(-1) ?? null);

  useEffect(() => {
    const letztes = projekt?.kapitel.at(-1);
    if (letztes !== undefined && letztes !== letzterStand.current) {
      letzterStand.current = letztes;
      setN(letztes);
    }
  }, [projekt, setN]);
}
