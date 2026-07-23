import { useState } from "react";
import { api } from "../api/client";
import type { ProjektDetail, SSHZiel } from "../api/types";
import { Badge, Button, Card, Input, Label, Select } from "../components/ui";

interface StandExportPageProps {
  ordner: string;
  projekt: ProjektDetail | null;
  sshZiele: SSHZiel[];
  onGeaendert: () => void;
}

export function StandExportPage({ ordner, projekt, sshZiele, onGeaendert }: StandExportPageProps) {
  const [n, setN] = useState(projekt?.kapitel.at(-1) ?? 1);
  const [sshZielId, setSshZielId] = useState("");
  const [standText, setStandText] = useState<string | null>(null);
  const [autoExport, setAutoExport] = useState(false);
  const [ladenStand, setLadenStand] = useState(false);

  const [von, setVon] = useState<number | undefined>(undefined);
  const [bis, setBis] = useState<number | undefined>(undefined);
  const [gesamtText, setGesamtText] = useState<string | null>(null);
  const [ladenExport, setLadenExport] = useState(false);

  const [fehler, setFehler] = useState<string | null>(null);

  async function standErzeugen() {
    setLadenStand(true);
    setFehler(null);
    try {
      const antwort = await api.standErzeugen(ordner, n, sshZielId || null);
      setStandText(antwort.stand);
      setAutoExport(antwort.auto_export);
      onGeaendert();
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLadenStand(false);
    }
  }

  async function exportieren() {
    setLadenExport(true);
    setFehler(null);
    try {
      const antwort = await api.exportieren(ordner);
      setGesamtText(antwort.gesamt);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLadenExport(false);
    }
  }

  async function zusammenfassen() {
    setLadenExport(true);
    setFehler(null);
    try {
      const antwort = await api.zusammenfassen(ordner, von, bis);
      setGesamtText(antwort.inhalt ?? antwort.gesamt ?? null);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLadenExport(false);
    }
  }

  return (
    <div className="space-y-6 p-6">
      <Card>
        <h2 className="mb-3 text-sm font-semibold text-neutral-700 dark:text-neutral-200">
          Zustand nach Kapitel festhalten (Chronist)
        </h2>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <Label>Kapitelnummer</Label>
            <Input type="number" min={1} value={n} onChange={(e) => setN(Number(e.target.value))} className="w-28" />
          </div>
          <div>
            <Label>KI über SSH-Ziel (optional)</Label>
            <Select value={sshZielId} onChange={(e) => setSshZielId(e.target.value)} className="w-56">
              <option value="">Lokal / Standard-Ollama</option>
              {sshZiele.map((z) => (
                <option key={z.id} value={z.id}>
                  {z.name} ({z.host})
                </option>
              ))}
            </Select>
          </div>
          <Button onClick={standErzeugen} disabled={ladenStand}>
            {ladenStand ? "Erzeugt..." : "Stand erzeugen"}
          </Button>
        </div>
        {fehler && <p className="mt-2 text-sm text-red-600">{fehler}</p>}
        {standText && (
          <div className="mt-4">
            {autoExport && (
              <div className="mb-2">
                <Badge tone="green">
                  Letztes geplantes Kapitel erreicht - alle Kapitel wurden automatisch zu gesamt.md
                  zusammengefügt.
                </Badge>
              </div>
            )}
            <pre className="max-h-[360px] overflow-auto whitespace-pre-wrap rounded-md bg-neutral-50 p-3 text-sm dark:bg-neutral-950">
              {standText}
            </pre>
          </div>
        )}
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-neutral-700 dark:text-neutral-200">
          Export / Zwischenstand
        </h2>
        <div className="flex flex-wrap items-end gap-4">
          <Button onClick={exportieren} variant="secondary" disabled={ladenExport}>
            Alle Kapitel -&gt; gesamt.md
          </Button>
          <div>
            <Label>von Kapitel</Label>
            <Input type="number" min={1} className="w-24" value={von ?? ""} onChange={(e) => setVon(e.target.value ? Number(e.target.value) : undefined)} />
          </div>
          <div>
            <Label>bis Kapitel</Label>
            <Input type="number" min={1} className="w-24" value={bis ?? ""} onChange={(e) => setBis(e.target.value ? Number(e.target.value) : undefined)} />
          </div>
          <Button onClick={zusammenfassen} variant="secondary" disabled={ladenExport}>
            Zwischenstand zusammenfassen
          </Button>
        </div>
        {gesamtText && (
          <pre className="mt-4 max-h-[420px] overflow-auto whitespace-pre-wrap rounded-md bg-neutral-50 p-3 text-sm dark:bg-neutral-950">
            {gesamtText}
          </pre>
        )}
      </Card>
    </div>
  );
}
