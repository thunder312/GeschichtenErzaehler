import { useState } from "react";
import { api } from "../api/client";
import type { HostStatus } from "../api/types";
import { Button } from "./ui";

function gb(mb: number): string {
  return `${(mb / 1024).toFixed(1)} GB`;
}

function Balken({ anteil, warnung }: { anteil: number; warnung: boolean }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-surface-hover">
      <div
        className={`h-full ${warnung ? "bg-amber-400" : "bg-accent"}`}
        style={{ width: `${Math.min(100, Math.max(0, anteil * 100))}%` }}
      />
    </div>
  );
}

/** Host-Speicher-/Container-Übersicht (Feature "KI- und Speicherkontrolle").
 * Wird an zwei Stellen genutzt:
 * - beim Schreibstart ("Container herunterfahren?" - beide Buttons schreiben weiter)
 * - als reine Statusanzeige im Tab „KI-Ziele" (nur `status`, keine Buttons).
 */
export function HostStatusPanel({ status }: { status: HostStatus }) {
  if (!status.verfuegbar) {
    return (
      <p className="text-xs text-text-muted">
        Für dieses KI-Ziel ist keine Speicher-/Container-Steuerung konfiguriert.
      </p>
    );
  }
  const ram = status.ram;
  const swap = status.swap;
  return (
    <div className="space-y-3 text-xs">
      <div>
        <div className="mb-1 flex justify-between text-text-muted">
          <span>RAM</span>
          <span>
            {gb(ram.used_mb)} / {gb(ram.total_mb)} belegt · {gb(ram.available_mb)} frei
          </span>
        </div>
        <Balken anteil={ram.total_mb ? ram.used_mb / ram.total_mb : 0} warnung={ram.available_mb < 6144} />
      </div>
      {swap.total_mb > 0 && (
        <div>
          <div className="mb-1 flex justify-between text-text-muted">
            <span>Swap</span>
            <span>
              {gb(swap.used_mb)} / {gb(swap.total_mb)}
            </span>
          </div>
          <Balken anteil={swap.used_mb / swap.total_mb} warnung={swap.used_mb > 200} />
        </div>
      )}
      <div>
        <span className="text-text-muted">Bild-Container:</span>{" "}
        {status.containers.length === 0
          ? "keine"
          : status.containers
              .map((c) => `${c.name} ${c.running ? "läuft" : "aus"}`)
              .join(" · ")}
      </div>
      {status.ollama.length > 0 && (
        <div>
          <span className="text-text-muted">Ollama geladen:</span>{" "}
          {status.ollama.map((m) => m.name).join(", ")}
        </div>
      )}
    </div>
  );
}

interface DialogProps {
  status: HostStatus;
  wirdAusgefuehrt?: boolean;
  /** Container herunterfahren und weiterschreiben. */
  onHerunterfahren: () => void;
  /** So lassen und trotzdem weiterschreiben. */
  onWeiter: () => void;
}

/** Nach einem Automatik-Lauf, der Container heruntergefahren hat: Angebot,
 * sie wieder zu starten (Nutzer-Entscheidung: "fragen"). Session-lokal
 * ausblendbar - der Status auf der Platte behält die Liste. */
export function SpeicherkontrolleWiederhochBanner({
  container,
  zielId,
}: {
  container: string[];
  zielId: string | null;
}) {
  const [weg, setWeg] = useState(false);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  if (weg || container.length === 0) return null;

  async function hochfahren() {
    if (!zielId) {
      setFehler("Kein KI-Ziel ausgewählt.");
      return;
    }
    setLaeuft(true);
    setFehler(null);
    try {
      for (const name of container) await api.hostContainer(zielId, name, "start");
      setWeg(true);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLaeuft(false);
    }
  }

  return (
    <div className="rounded-xl border border-amber-400/40 bg-amber-400/10 p-3 text-sm">
      <p className="text-text">
        Für den Lauf wurden <b>{container.join(", ")}</b> heruntergefahren. Wieder starten?
      </p>
      {fehler && <p className="mt-1 text-xs text-red-400">{fehler}</p>}
      <div className="mt-2 flex gap-2">
        <Button onClick={hochfahren} disabled={laeuft}>
          {laeuft ? "Startet…" : "Wieder hochfahren"}
        </Button>
        <Button variant="secondary" onClick={() => setWeg(true)} disabled={laeuft}>
          Aus lassen
        </Button>
      </div>
    </div>
  );
}

export function SpeicherkontrolleDialog({ status, wirdAusgefuehrt, onHerunterfahren, onWeiter }: DialogProps) {
  const laufende = status.containers.filter((c) => c.running).map((c) => c.name);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="relative mx-auto max-w-md rounded-2xl border border-border bg-surface p-6 shadow-2xl shadow-black/50">
        <h3 className="font-heading mb-2 text-lg font-semibold text-text">
          Bild-KI vor dem Schreiben herunterfahren?
        </h3>
        <p className="mb-3 text-sm text-text-muted">
          Auf dem KI-Host {laufende.length > 0 ? <>laufen <b>{laufende.join(", ")}</b> im Leerlauf</> : "läuft eine Bild-KI im Leerlauf"} und
          belegen Speicher, den der Autor beim Schreiben braucht. Herunterfahren bringt spürbar mehr
          Tempo; du kannst sie später (oder für ein Titelbild) wieder starten.
        </p>
        <div className="mb-5 rounded-xl border border-border bg-surface-hover/40 p-3">
          <HostStatusPanel status={status} />
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="secondary" onClick={onWeiter} disabled={wirdAusgefuehrt}>
            So lassen
          </Button>
          <Button onClick={onHerunterfahren} disabled={wirdAusgefuehrt}>
            {wirdAusgefuehrt ? "Fährt herunter…" : "Herunterfahren & schreiben"}
          </Button>
        </div>
      </div>
    </div>
  );
}
