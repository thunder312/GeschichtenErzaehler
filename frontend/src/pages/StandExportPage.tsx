import { useState } from "react";
import { api } from "../api/client";
import type { ProjektDetail } from "../api/types";
import { Badge, Button, Card, CardTitle, Input, Label } from "../components/ui";
import { alsDateiHerunterladen } from "../utils/download";

interface StandExportPageProps {
  ordner: string;
  projekt: ProjektDetail | null;
  sshZielId: string;
  onGeaendert: () => void;
}

export function StandExportPage({
  ordner,
  projekt,
  sshZielId,
  onGeaendert,
}: StandExportPageProps) {
  const [n, setN] = useState(projekt?.kapitel.at(-1) ?? 1);
  const [standText, setStandText] = useState<string | null>(null);
  const [autoExport, setAutoExport] = useState(false);
  const [ladenStand, setLadenStand] = useState(false);

  const [von, setVon] = useState<number | undefined>(undefined);
  const [bis, setBis] = useState<number | undefined>(undefined);
  const [gesamtText, setGesamtText] = useState<string | null>(null);
  const [gesamtDateiname, setGesamtDateiname] = useState("gesamt.md");
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
      setGesamtDateiname("gesamt.md");
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
      setGesamtDateiname(`zwischenstand_${von ?? "start"}-${bis ?? "ende"}.md`);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLadenExport(false);
    }
  }

  return (
    <div className="space-y-6 p-6">
      <Card>
        <CardTitle>📦 Zustand nach Kapitel festhalten (Chronist)</CardTitle>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <Label>Kapitelnummer</Label>
            <Input type="number" min={1} value={n} onChange={(e) => setN(Number(e.target.value))} className="w-28" />
          </div>
          <Button onClick={standErzeugen} disabled={ladenStand}>
            {ladenStand ? "Erzeugt..." : "Stand erzeugen"}
          </Button>
        </div>
        {fehler && <p className="mt-2 text-sm text-red-400">{fehler}</p>}
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
            <div className="mb-1 flex justify-end">
              <button
                onClick={() => alsDateiHerunterladen(`stand_${String(n).padStart(2, "0")}.md`, standText)}
                className="text-xs text-accent-light hover:underline"
              >
                ⬇️ Herunterladen
              </button>
            </div>
            <pre className="max-h-[360px] overflow-auto whitespace-pre-wrap rounded-lg bg-bg p-3 text-sm text-text">
              {standText}
            </pre>
          </div>
        )}
      </Card>

      <Card>
        <CardTitle>🗂️ Export / Zwischenstand</CardTitle>
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
          <div className="mt-4">
            <div className="mb-1 flex justify-end">
              <button
                onClick={() => alsDateiHerunterladen(gesamtDateiname, gesamtText)}
                className="text-xs text-accent-light hover:underline"
              >
                ⬇️ Herunterladen
              </button>
            </div>
            <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap rounded-lg bg-bg p-3 text-sm text-text">
              {gesamtText}
            </pre>
          </div>
        )}
      </Card>
    </div>
  );
}
