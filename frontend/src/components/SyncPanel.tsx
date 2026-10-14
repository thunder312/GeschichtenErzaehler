import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import type { SyncInfo, SyncStatus, SyncZeile } from "../api/types";
import { CollapsibleCard } from "./CollapsibleCard";
import { ConfirmDialog } from "./ConfirmDialog";
import { Badge, Button } from "./ui";

interface SyncPanelProps {
  /** Nach jeder Übertragung/Bereinigung: Projektliste der App neu laden. */
  onProjekteGeaendert: () => void;
  /** Wird ein lokal geöffnetes Projekt entfernt, muss die App es loslassen. */
  onProjektEntfernt: (ordner: string) => void;
}

const STATUS_ANZEIGE: Record<SyncStatus, { text: string; ton: "neutral" | "green" | "amber" | "blue" }> = {
  nur_lokal: { text: "nur auf dem PC", ton: "blue" },
  nur_server: { text: "nur auf dem Server", ton: "blue" },
  gleich: { text: "✓ identisch", ton: "green" },
  lokal_neuer: { text: "⬆ PC ist neuer", ton: "amber" },
  server_neuer: { text: "⬇ Server ist neuer", ton: "amber" },
  abweichend: { text: "⚠ beide geändert", ton: "amber" },
};

function zeitText(ts: number): string {
  return new Date(ts * 1000).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
}

function Seite({ info }: { info: SyncInfo | null }) {
  if (!info) return <span className="text-text-muted">–</span>;
  return (
    <span>
      {info.anzahl_kapitel} Kap.
      <span className="block text-xs text-text-muted">{zeitText(info.geaendert_ts)}</span>
    </span>
  );
}

type Rueckfrage = { zeile: SyncZeile; richtung: "hoch" | "runter"; nachricht: string };

/** Vergleichsliste zwischen diesem PC und der eingetragenen Gegenstelle
 * (Server). Erscheint nur, wenn unter Einstellungen eine Gegenstelle
 * hinterlegt ist. Jede Übertragung läuft von diesem PC aus. */
export function SyncPanel({ onProjekteGeaendert, onProjektEntfernt }: SyncPanelProps) {
  const [konfiguriert, setKonfiguriert] = useState<boolean | null>(null);

  useEffect(() => {
    api.syncPartner().then((p) => setKonfiguriert(p.konfiguriert), () => setKonfiguriert(false));
  }, []);

  if (!konfiguriert) return null;

  return (
    <div className="md:col-span-2">
      <CollapsibleCard title="🔄 Abgleich mit Server" defaultOffen={false}>
        <SyncInhalt onProjekteGeaendert={onProjekteGeaendert} onProjektEntfernt={onProjektEntfernt} />
      </CollapsibleCard>
    </div>
  );
}

function SyncInhalt({ onProjekteGeaendert, onProjektEntfernt }: SyncPanelProps) {
  const [zeilen, setZeilen] = useState<SyncZeile[] | null>(null);
  const [laedt, setLaedt] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [hinweis, setHinweis] = useState<string | null>(null);
  const [beschaeftigt, setBeschaeftigt] = useState<string | null>(null);
  const [rueckfrage, setRueckfrage] = useState<Rueckfrage | null>(null);
  const [entfernenFrage, setEntfernenFrage] = useState<SyncZeile | null>(null);

  const laden = useCallback(async () => {
    setLaedt(true);
    setFehler(null);
    try {
      setZeilen((await api.syncVergleich()).zeilen);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLaedt(false);
    }
  }, []);

  useEffect(() => {
    void laden();
  }, [laden]);

  async function uebertragen(zeile: SyncZeile, richtung: "hoch" | "runter", force = false) {
    const ordner = richtung === "hoch" ? zeile.lokal?.ordner : zeile.server?.ordner;
    if (!ordner) return;
    setBeschaeftigt(zeile.name);
    setHinweis(null);
    setFehler(null);
    try {
      const antwort =
        richtung === "hoch" ? await api.syncHochladen(ordner, force) : await api.syncHerunterladen(ordner, force);
      setHinweis(`${zeile.titel ?? zeile.name}: ${antwort.nachricht}`);
      onProjekteGeaendert();
      await laden();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && (e.detail as { art?: string })?.art === "ueberschreiben") {
        setRueckfrage({ zeile, richtung, nachricht: e.message });
      } else {
        setFehler(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setBeschaeftigt(null);
    }
  }

  async function lokalAufraeumen(zeile: SyncZeile) {
    if (!zeile.lokal) return;
    setBeschaeftigt(zeile.name);
    setHinweis(null);
    setFehler(null);
    try {
      const ordner = zeile.lokal.ordner;
      await api.syncLokalAufraeumen(ordner, zeile.status === "lokal_neuer");
      setHinweis(`${zeile.titel ?? zeile.name}: lokale Projektdateien entfernt.`);
      onProjektEntfernt(ordner);
      onProjekteGeaendert();
      await laden();
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setBeschaeftigt(null);
    }
  }

  return (
    <div className="p-4">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <Button variant="secondary" onClick={() => void laden()} disabled={laedt}>
          {laedt ? "Vergleiche..." : "🔃 Neu vergleichen"}
        </Button>
        <p className="text-xs text-text-muted">
          Der Vergleich merkt sich, welcher Stand zuletzt auf beiden Seiten identisch war. Ein älterer Stand
          überschreibt einen neueren nur nach ausdrücklicher Bestätigung (es wird eine Sicherung angelegt).
        </p>
      </div>

      {fehler && <p className="mb-3 text-sm text-red-400">{fehler}</p>}
      {hinweis && !fehler && <p className="mb-3 text-sm text-accent-light">{hinweis}</p>}

      {zeilen && zeilen.length === 0 && <p className="text-sm text-text-muted">Keine Projekte gefunden.</p>}

      {zeilen && zeilen.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wider text-text-muted">
                <th className="py-2 pr-3 font-medium">Projekt</th>
                <th className="py-2 pr-3 font-medium">Dieser PC</th>
                <th className="py-2 pr-3 font-medium">Server</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 font-medium">Aktion</th>
              </tr>
            </thead>
            <tbody>
              {zeilen.map((z) => {
                const busy = beschaeftigt === z.name;
                const status = STATUS_ANZEIGE[z.status];
                return (
                  <tr key={(z.lokal ?? z.server)!.projekt_id + z.name} className="border-b border-border/50 align-top">
                    <td className="py-2 pr-3">
                      <span className="font-medium text-text">{z.titel ?? z.name}</span>
                      <span className="block text-xs text-text-muted">{z.epoche ?? "ohne Epoche"}</span>
                    </td>
                    <td className="py-2 pr-3">
                      <Seite info={z.lokal} />
                    </td>
                    <td className="py-2 pr-3">
                      <Seite info={z.server} />
                    </td>
                    <td className="py-2 pr-3">
                      <Badge tone={status.ton}>{status.text}</Badge>
                      {z.unsicher && (
                        <span className="mt-1 block text-xs text-amber-300">
                          noch nie abgeglichen – nur nach Änderungszeit geschätzt
                        </span>
                      )}
                      {z.aufraeumen_vorgemerkt && (
                        <span className="mt-1 block text-xs text-text-muted">
                          🧹 Prüfung am Server abgeschlossen – lokale Kopie kann weg
                        </span>
                      )}
                    </td>
                    <td className="py-2">
                      <div className="flex flex-wrap gap-2">
                        {z.lokal && z.status !== "gleich" && (
                          <Button variant="secondary" onClick={() => void uebertragen(z, "hoch")} disabled={busy}>
                            ⬆ Zum Server
                          </Button>
                        )}
                        {z.server && z.status !== "gleich" && (
                          <Button variant="secondary" onClick={() => void uebertragen(z, "runter")} disabled={busy}>
                            ⬇ Auf den PC
                          </Button>
                        )}
                        {z.lokal && z.server && (
                          <Button variant="secondary" onClick={() => setEntfernenFrage(z)} disabled={busy}>
                            🧹 Lokal entfernen
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {entfernenFrage && (
        <ConfirmDialog
          titel="Lokale Projektdateien entfernen?"
          beschreibung={
            `Der Projektordner von "${entfernenFrage.titel ?? entfernenFrage.name}" wird auf diesem PC gelöscht ` +
            `(exportierte PDFs daneben bleiben). Das geht nur, wenn der Server alle lokalen Änderungen schon ` +
            `hat` +
            (entfernenFrage.status === "lokal_neuer" ? " – der neuere lokale Stand wird vorher hochgeladen." : ".")
          }
          bestaetigenText="Lokal entfernen"
          onBestaetigen={() => {
            const z = entfernenFrage;
            setEntfernenFrage(null);
            void lokalAufraeumen(z);
          }}
          onAbbrechen={() => setEntfernenFrage(null)}
        />
      )}

      {rueckfrage && (
        <ConfirmDialog
          titel="Neuere Version überschreiben?"
          beschreibung={rueckfrage.nachricht}
          bestaetigenText="Trotzdem überschreiben"
          wirdAusgefuehrt={beschaeftigt === rueckfrage.zeile.name}
          onBestaetigen={() => {
            const r = rueckfrage;
            setRueckfrage(null);
            void uebertragen(r.zeile, r.richtung, true);
          }}
          onAbbrechen={() => setRueckfrage(null)}
        />
      )}
    </div>
  );
}
