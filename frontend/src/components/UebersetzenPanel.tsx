import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { FuelltextVorschau, UebersetzenStatus } from "../api/types";
import { blobHerunterladen } from "../utils/download";
import { Button, Textarea } from "./ui";

interface UebersetzenPanelProps {
  /** Der aktuell im Analysator geöffnete Text. */
  text: string;
  /** Name des geöffneten Dokuments (bestimmt Format und Namen der _de-Datei). */
  dateiname: string;
  sshZielId: string | null;
  /** Übersetzung ins Textfeld übernehmen. */
  onUebernehmen: (text: string) => void;
}

const SPRACHE_TEXT: Record<string, string> = {
  en: "Englisch erkannt",
  de: "Der Text scheint bereits Deutsch zu sein",
  unbekannt: "Sprache nicht sicher erkannt",
};

/** "Ins Deutsche übersetzen" für das im Analysator geöffnete Dokument
 * (siehe backend/app/core/uebersetzer.py). Fragt vor dem Start, ob Fülltext
 * (Disclaimer, A/N, ...) gleich entfernt werden soll, zeigt den Fortschritt
 * kapitelweise, bietet Zwischenstände zum Lesen/Speichern (fertige Kapitel) und
 * ein Fortsetzen nach Abbruch. Gespeichert wird im selben Format als
 * "<name>_de.<endung>". */
export function UebersetzenPanel({ text, dateiname, sshZielId, onUebernehmen }: UebersetzenPanelProps) {
  const [status, setStatus] = useState<UebersetzenStatus | null>(null);
  const [vorschau, setVorschau] = useState<FuelltextVorschau | null>(null);
  const [vorschauLaedt, setVorschauLaedt] = useState(false);
  const [entfernen, setEntfernen] = useState(true);
  const [wirdGestartet, setWirdGestartet] = useState(false);
  const [wirdGespeichert, setWirdGespeichert] = useState(false);
  const [lesetext, setLesetext] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const laeuftRef = useRef(false);

  // Beim Öffnen des Tabs einmal den Stand laden (eine Übersetzung kann noch laufen
  // oder fertig sein), danach nur pollen, solange eine läuft. Bewusst langes
  // Intervall: häufiges Polling bremst den laufenden KI-Aufruf über den SSH-Tunnel.
  useEffect(() => {
    let abgebrochen = false;
    const laden = () =>
      api
        .uebersetzenStatus()
        .then((s) => {
          if (abgebrochen) return;
          setStatus(s);
          laeuftRef.current = s.laeuft;
        })
        .catch(() => {});
    laden();
    const intervall = setInterval(() => {
      if (laeuftRef.current) laden();
    }, 10000);
    return () => {
      abgebrochen = true;
      clearInterval(intervall);
    };
  }, []);

  async function dialogOeffnen() {
    setFehler(null);
    setVorschauLaedt(true);
    try {
      const v = await api.fuelltextVorschau(text);
      setEntfernen(v.fuelltext_absaetze > 0);
      setVorschau(v);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setVorschauLaedt(false);
    }
  }

  async function starten(fortsetzen = false) {
    setWirdGestartet(true);
    setFehler(null);
    try {
      await api.uebersetzenStarten(
        text, dateiname, entfernen && (vorschau?.fuelltext_absaetze ?? 0) > 0, sshZielId, fortsetzen,
      );
      setVorschau(null);
      laeuftRef.current = true;
      setStatus(await api.uebersetzenStatus());
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setWirdGestartet(false);
    }
  }

  async function stoppen() {
    await api.uebersetzenStoppen().catch(() => {});
    setStatus(await api.uebersetzenStatus());
  }

  /** zwischenstand = nur die vollständig übersetzten Kapitel (auch während des Laufs). */
  async function speichern(zwischenstand: boolean) {
    if (!status?.dateiname) return;
    setWirdGespeichert(true);
    setFehler(null);
    try {
      const name = zwischenstand ? status.dateiname.replace(/(\.[^.]+)$/, "_Zwischenstand$1") : status.dateiname;
      if (status.dateiname.toLowerCase().endsWith(".pdf")) {
        blobHerunterladen(name, await api.uebersetzenPdf(zwischenstand));
      } else {
        const ergebnis = await api.uebersetzenErgebnis(zwischenstand);
        blobHerunterladen(name, new Blob([ergebnis], { type: "text/plain;charset=utf-8" }));
      }
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setWirdGespeichert(false);
    }
  }

  async function lesen() {
    setFehler(null);
    try {
      setLesetext(await api.uebersetzenErgebnis(true));
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    }
  }

  async function uebernehmen() {
    try {
      onUebernehmen(await api.uebersetzenErgebnis(false));
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    }
  }

  const laeuft = status?.laeuft ?? false;
  const hatErgebnis = !!status && !status.laeuft && status.ergebnis_woerter > 0;
  const prozent =
    status && status.woerter_gesamt > 0 ? Math.min(100, Math.round((status.woerter_fertig / status.woerter_gesamt) * 100)) : 0;
  const zielName = status?.dateiname ?? "";
  // Fortsetzen nur für dieselbe, unterbrochene Übersetzung dieses Dokuments
  const kannFortsetzen =
    !!status && !status.laeuft && !status.abgeschlossen && status.ergebnis_woerter > 0 &&
    status.dateiname === dateiNameVorschau(dateiname);
  const hatFertigeKapitel = (status?.kapitel_fertig ?? 0) > 0;

  const zwischenstandKnoepfe = hatFertigeKapitel && status && (
    <>
      <Button variant="secondary" onClick={lesen}>
        📖 Zwischenstand lesen ({status.kapitel_fertig} {status.kapitel_fertig === 1 ? "Kapitel" : "Kapitel"})
      </Button>
      <Button variant="secondary" onClick={() => speichern(true)} disabled={wirdGespeichert}>
        💾 Zwischenstand speichern
      </Button>
    </>
  );

  return (
    <div className="mt-2 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="secondary"
          onClick={dialogOeffnen}
          disabled={!text.trim() || laeuft || vorschauLaedt}
          title="Das geöffnete Dokument ins Deutsche übersetzen und als _de-Datei speichern"
        >
          {vorschauLaedt ? "Prüfe Text…" : "🇩🇪 Ins Deutsche übersetzen"}
        </Button>
        {!laeuft && !hatErgebnis && (
          <span className="text-xs text-text-muted">Speichert danach als „{dateiNameVorschau(dateiname)}“.</span>
        )}
      </div>

      {laeuft && status && (
        <div className="space-y-2 rounded-lg border border-border bg-bg p-3">
          <p className="text-sm text-text">
            Übersetze{status.fortgesetzt ? " (fortgesetzt)" : ""} · Kapitel{" "}
            <strong>
              {Math.min(status.kapitel_fertig + 1, Math.max(status.kapitel_gesamt, 1))}
            </strong>{" "}
            von {status.kapitel_gesamt} · {prozent} %{" "}
            <span className="text-text-muted">
              ({status.kapitel_fertig} {status.kapitel_fertig === 1 ? "Kapitel" : "Kapitel"} fertig)
            </span>
          </p>
          <div className="h-2 w-full overflow-hidden rounded-full bg-surface-hover">
            <div className="h-full bg-accent" style={{ width: `${prozent}%` }} />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="danger" onClick={stoppen} disabled={status.stop_angefordert}>
              {status.stop_angefordert ? "Wird nach dem Schritt gestoppt…" : "Stoppen"}
            </Button>
            {zwischenstandKnoepfe}
          </div>
          <p className="text-xs text-text-muted">
            Jedes fertige Kapitel liegt zusätzlich als eigene Datei unter Analyse/Uebersetzungen/. Nach „Stoppen“ kannst
            du mit „Fortsetzen“ genau dort weitermachen.
          </p>
        </div>
      )}

      {hatErgebnis && status && (
        <div className="space-y-2 rounded-lg border border-border bg-bg p-3">
          <p className="text-sm text-text">
            {status.abgeschlossen
              ? `Übersetzung fertig (${status.ergebnis_woerter} Wörter).`
              : status.gestoppt
                ? `Übersetzung gestoppt - bisher ${status.ergebnis_woerter} Wörter, ${status.kapitel_fertig} von ${status.kapitel_gesamt} Kapiteln fertig.`
                : `Übersetzung unterbrochen - bisher ${status.ergebnis_woerter} Wörter, ${status.kapitel_fertig} von ${status.kapitel_gesamt} Kapiteln fertig.`}
            {status.fuelltext_entfernt > 0 && (
              <span className="text-text-muted"> {status.fuelltext_entfernt} Fülltext-Absätze entfernt.</span>
            )}
          </p>
          {status.fehler && <p className="text-sm text-red-400">Fehler: {status.fehler}</p>}
          <div className="flex flex-wrap gap-2">
            {kannFortsetzen && (
              <Button onClick={() => starten(true)} disabled={wirdGestartet}>
                {wirdGestartet ? "Startet…" : "▶ Fortsetzen"}
              </Button>
            )}
            <Button onClick={() => speichern(false)} disabled={wirdGespeichert} variant={kannFortsetzen ? "secondary" : "primary"}>
              {wirdGespeichert ? "Speichere…" : `💾 Als ${zielName} speichern${status.abgeschlossen ? "" : " (bisher)"}`}
            </Button>
            {status.abgeschlossen && (
              <Button variant="secondary" onClick={uebernehmen}>
                Ins Textfeld übernehmen
              </Button>
            )}
            {!status.abgeschlossen && zwischenstandKnoepfe}
          </div>
          {kannFortsetzen && (
            <p className="text-xs text-text-muted">
              „Fortsetzen“ übersetzt nur den Rest, die fertigen Kapitel bleiben unverändert. Das Dokument im Textfeld
              muss dasselbe sein.
            </p>
          )}
        </div>
      )}

      {!laeuft && status?.fehler && !hatErgebnis && (
        <p className="text-sm text-red-400">Übersetzung fehlgeschlagen: {status.fehler}</p>
      )}
      {fehler && <p className="text-sm text-red-400">{fehler}</p>}

      {lesetext !== null && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
          onClick={() => setLesetext(null)}
        >
          <div
            className="relative mx-auto flex max-h-[90vh] w-full max-w-3xl flex-col rounded-2xl border border-border bg-surface p-5 shadow-2xl shadow-black/50"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-2 flex items-center justify-between gap-3">
              <h3 className="font-heading text-lg font-semibold text-text">
                Zwischenstand - {status?.kapitel_fertig ?? 0} fertige Kapitel
              </h3>
              <Button variant="secondary" onClick={() => setLesetext(null)}>
                Schließen
              </Button>
            </div>
            <Textarea readOnly rows={24} value={lesetext} className="flex-1 text-sm" />
          </div>
        </div>
      )}

      {vorschau && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
          onClick={() => setVorschau(null)}
        >
          <div
            className="relative mx-auto w-full max-w-lg rounded-2xl border border-border bg-surface p-6 shadow-2xl shadow-black/50"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="font-heading mb-2 text-lg font-semibold text-text">Ins Deutsche übersetzen</h3>
            <div className="mb-4 space-y-1 text-sm text-text-muted">
              <p>
                {SPRACHE_TEXT[vorschau.sprache] ?? SPRACHE_TEXT.unbekannt} · {vorschau.woerter} Wörter · ca.{" "}
                {vorschau.abschnitte} Schritte
              </p>
              <p>
                Dauer grob {vorschau.geschaetzte_minuten} Minuten, je nach KI-Ziel (Kapitel für Kapitel, mit
                Fortschrittsanzeige, Zwischenständen und „Stoppen“/„Fortsetzen“). Gespeichert wird als „
                {dateiNameVorschau(dateiname)}“.
              </p>
              {vorschau.sprache === "de" && (
                <p className="text-amber-300">
                  Hinweis: Der Text wirkt bereits deutsch - eine Übersetzung ist vermutlich nicht nötig.
                </p>
              )}
            </div>

            {vorschau.fuelltext_absaetze > 0 ? (
              <div className="mb-5 rounded-lg border border-border bg-bg p-3">
                <label className="flex items-start gap-2 text-sm text-text">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={entfernen}
                    onChange={(e) => setEntfernen(e.target.checked)}
                  />
                  <span>
                    Fülltext vorher entfernen ({vorschau.fuelltext_absaetze} Absätze: Disclaimer, A/N,
                    Danksagungen …)
                  </span>
                </label>
                <ul className="mt-2 space-y-0.5 text-xs text-text-muted">
                  {vorschau.beispiele.map((b, i) => (
                    <li key={i} className="truncate">
                      „{b}“
                    </li>
                  ))}
                  {vorschau.fuelltext_absaetze > vorschau.beispiele.length && (
                    <li>… und {vorschau.fuelltext_absaetze - vorschau.beispiele.length} weitere</li>
                  )}
                </ul>
              </div>
            ) : (
              <p className="mb-5 text-sm text-text-muted">Es wurde kein Fülltext (Disclaimer, A/N …) gefunden.</p>
            )}

            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setVorschau(null)} disabled={wirdGestartet}>
                Abbrechen
              </Button>
              <Button onClick={() => starten(false)} disabled={wirdGestartet}>
                {wirdGestartet ? "Startet…" : "Übersetzen"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** Spiegel von backend/app/core/uebersetzer.py:dateiname_de (nur zur Anzeige und zum Abgleich). */
function dateiNameVorschau(dateiname: string): string {
  const m = dateiname.match(/^(.*?)(\.(?:txt|md|pdf))?$/i);
  const basis = (m?.[1] ?? dateiname).replace(/_de$/i, "").replace(/[\\/:*?"<>|]+/g, "-").trim() || "Uebersetzung";
  return `${basis}_de${(m?.[2] ?? ".txt").toLowerCase()}`;
}
