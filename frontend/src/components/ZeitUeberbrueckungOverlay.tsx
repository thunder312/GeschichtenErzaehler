import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { WissenEintrag } from "../api/types";
import { useAktivitaet } from "../context/AktivitaetContext";

const START_VERZOEGERUNG_MS = 20_000;
const WECHSEL_INTERVALL_MS = 20_000;

function naechsterZufallsEintrag(liste: WissenEintrag[], bisheriger: WissenEintrag | null): WissenEintrag | null {
  if (liste.length === 0) return null;
  if (liste.length === 1) return liste[0];
  let kandidat: WissenEintrag;
  do {
    kandidat = liste[Math.floor(Math.random() * liste.length)];
  } while (kandidat === bisheriger);
  return kandidat;
}

/** Zeigt waehrend laengerer KI-Wartezeiten (siehe AktivitaetContext) nach
 * 20 Sekunden ein zentrales Overlay mit unnuetzem Buch-/Autoren-Wissen, das
 * alle 20 Sekunden wechselt - gibt dem Nutzer etwas zu lesen, statt
 * untaetig auf eine fertige Antwort zu warten. Schliesst sich automatisch,
 * sobald die Aktivitaet endet. */
export function ZeitUeberbrueckungOverlay() {
  const { aktivitaet } = useAktivitaet();
  const [wissen, setWissen] = useState<WissenEintrag[]>([]);
  const [sichtbar, setSichtbar] = useState(false);
  const [eintrag, setEintrag] = useState<WissenEintrag | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api.unnuetzesWissen().then(setWissen).catch(() => setWissen([]));
  }, []);

  useEffect(() => {
    function aufraeumen() {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (intervalRef.current) clearInterval(intervalRef.current);
      timerRef.current = null;
      intervalRef.current = null;
    }

    if (!aktivitaet || wissen.length === 0) {
      aufraeumen();
      setSichtbar(false);
      return aufraeumen;
    }

    aufraeumen();
    timerRef.current = setTimeout(() => {
      setEintrag((bisher) => naechsterZufallsEintrag(wissen, bisher));
      setSichtbar(true);
      intervalRef.current = setInterval(() => {
        setEintrag((bisher) => naechsterZufallsEintrag(wissen, bisher));
      }, WECHSEL_INTERVALL_MS);
    }, START_VERZOEGERUNG_MS);

    return aufraeumen;
  }, [aktivitaet, wissen]);

  if (!sichtbar || !eintrag) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="relative mx-auto max-w-md rounded-2xl border border-border bg-surface p-6 shadow-2xl shadow-black/50">
        <button
          onClick={() => setSichtbar(false)}
          className="absolute right-3 top-3 text-text-muted hover:text-text"
          aria-label="Schließen"
        >
          ✕
        </button>
        <div className="mb-1 flex items-center gap-2 text-xs italic text-text-muted">
          <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-accent" aria-hidden="true" />
          {aktivitaet?.text ?? "Die KI arbeitet..."}
        </div>
        <div className="mb-2 text-xs font-medium uppercase tracking-wider text-accent-light">
          Unnützes Wissen · {eintrag.kategorie}
        </div>
        <h3 className="font-heading mb-2 text-lg font-semibold text-text">
          {eintrag.thema}: {eintrag.kuriositaet}
        </h3>
        <p className="text-sm leading-relaxed text-text-muted">{eintrag.hintergrund}</p>
      </div>
    </div>
  );
}
