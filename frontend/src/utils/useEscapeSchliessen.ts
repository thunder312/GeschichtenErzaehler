import { useEffect } from "react";

/** Escape schliesst ein Overlay/Dialog - wie Klick auf den Hintergrund. */
export function useEscapeSchliessen(schliessen: () => void, aktiv = true) {
  useEffect(() => {
    if (!aktiv) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") schliessen();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [schliessen, aktiv]);
}
