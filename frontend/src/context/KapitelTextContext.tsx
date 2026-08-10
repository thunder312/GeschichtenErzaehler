import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

interface KapitelEintrag {
  text: string;
}

interface KapitelTextApi {
  /** Letzter je Projekt+Kapitel bekanntgegebener Speicherstand (Schluessel
   * `${ordner}::${kapitel}`) - siehe veroeffentlichen(). */
  stand: Record<string, KapitelEintrag>;
  /** Von PruefenAnwendenPage/RechtschreibungPage nach erfolgreichem Speichern
   * eines Kapitels aufgerufen. Beide Tabs bleiben beim Tab-Wechsel dauerhaft
   * gemountet (siehe App.tsx) und cachen den Kapiteltext unabhaengig
   * voneinander - ohne diese Veroeffentlichung wuerde eine im jeweils
   * anderen Tab gespeicherte Aenderung dort erst nach manuellem "Neu laden"
   * sichtbar. */
  veroeffentlichen: (ordner: string, kapitel: number, text: string) => void;
}

const KapitelTextContext = createContext<KapitelTextApi | null>(null);

function schluessel(ordner: string, kapitel: number) {
  return `${ordner}::${kapitel}`;
}

export function KapitelTextProvider({ children }: { children: ReactNode }) {
  const [stand, setStand] = useState<Record<string, KapitelEintrag>>({});

  const veroeffentlichen = useCallback((ordner: string, kapitel: number, text: string) => {
    const key = schluessel(ordner, kapitel);
    setStand((bisher) => (bisher[key]?.text === text ? bisher : { ...bisher, [key]: { text } }));
  }, []);

  const value = useMemo(() => ({ stand, veroeffentlichen }), [stand, veroeffentlichen]);

  return <KapitelTextContext.Provider value={value}>{children}</KapitelTextContext.Provider>;
}

export function useKapitelText(): KapitelTextApi {
  const ctx = useContext(KapitelTextContext);
  if (!ctx) throw new Error("useKapitelText() muss innerhalb von <KapitelTextProvider> verwendet werden.");
  return ctx;
}

export { schluessel as kapitelTextSchluessel };
