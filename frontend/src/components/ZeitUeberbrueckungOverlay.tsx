import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { WissenEintrag } from "../api/types";
import { useAktivitaet } from "../context/AktivitaetContext";

const START_VERZOEGERUNG_MS = 20_000;
const WECHSEL_INTERVALL_MS = 20_000;

/** Zeigt waehrend laengerer KI-Wartezeiten (siehe AktivitaetContext) nach
 * 20 Sekunden ein zentrales Overlay mit unnuetzem Buch-/Autoren-Wissen, das
 * alle 20 Sekunden wechselt - gibt dem Nutzer etwas zu lesen, statt
 * untaetig auf eine fertige Antwort zu warten. Schliesst sich automatisch,
 * sobald die Aktivitaet endet.
 *
 * Die Reihenfolge kommt vom Server (/api/unnuetzeswissen/naechstes,
 * siehe app/db.py:wissen_status_*) - eine EINMAL gemischte Reihenfolge
 * aller Eintraege statt reinem Math.random() pro Anzeige, damit jeder
 * Eintrag garantiert einmal drankommt, bevor sich etwas wiederholt (purer
 * Zufall wirkt bei kurzfristigen Wiederholungen leicht wie ein Bug, obwohl
 * das bei echtem Zufall statistisch normal waere). */
export function ZeitUeberbrueckungOverlay() {
  const { aktivitaet } = useAktivitaet();
  const [sichtbar, setSichtbar] = useState(false);
  const [eintrag, setEintrag] = useState<WissenEintrag | null>(null);
  const [position, setPosition] = useState<number | null>(null);
  const [gesamt, setGesamt] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const naechstesLaden = useCallback(() => {
    api
      .unnuetzesWissenNaechstes()
      .then((antwort) => {
        setEintrag(antwort.eintrag);
        setPosition(antwort.position);
        setGesamt(antwort.gesamt);
      })
      .catch(() => {});
  }, []);

  const starteWechselIntervall = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(naechstesLaden, WECHSEL_INTERVALL_MS);
  }, [naechstesLaden]);

  // Manuelles Weiterblaettern setzt das Auto-Wechsel-Intervall zurueck,
  // damit nicht kurz nach einem bewussten Klick schon der naechste
  // automatische Wechsel folgt.
  const weiterblaettern = useCallback(() => {
    naechstesLaden();
    starteWechselIntervall();
  }, [naechstesLaden, starteWechselIntervall]);

  useEffect(() => {
    function aufraeumen() {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (intervalRef.current) clearInterval(intervalRef.current);
      timerRef.current = null;
      intervalRef.current = null;
    }

    if (!aktivitaet) {
      aufraeumen();
      setSichtbar(false);
      return aufraeumen;
    }

    aufraeumen();
    timerRef.current = setTimeout(() => {
      naechstesLaden();
      setSichtbar(true);
      starteWechselIntervall();
    }, START_VERZOEGERUNG_MS);

    return aufraeumen;
  }, [aktivitaet, naechstesLaden, starteWechselIntervall]);

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
        <div className="mb-2 flex items-center justify-between gap-2 text-xs font-medium uppercase tracking-wider text-accent-light">
          <span>Unnützes Wissen · {eintrag.kategorie}</span>
          {position != null && gesamt != null && (
            <span className="text-text-muted">{position} / {gesamt}</span>
          )}
        </div>
        <h3 className="font-heading mb-2 text-lg font-semibold text-text">
          {eintrag.thema}: {eintrag.kuriositaet}
        </h3>
        <p className="mb-4 text-sm leading-relaxed text-text-muted">{eintrag.hintergrund}</p>
        <button
          onClick={weiterblaettern}
          className="text-xs font-medium text-accent-light hover:text-accent"
        >
          Nächster Fakt →
        </button>
      </div>
    </div>
  );
}
