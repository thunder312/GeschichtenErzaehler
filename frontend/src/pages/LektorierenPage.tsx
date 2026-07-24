import { useState } from "react";
import { api } from "../api/client";
import type { AnwendenAntwort, ProjektDetail } from "../api/types";
import { MergeEditor } from "../components/MergeEditor";
import { Button, Card, Input, Label } from "../components/ui";
import { useAktivitaet } from "../context/AktivitaetContext";

interface LektorierenPageProps {
  ordner: string;
  projekt: ProjektDetail | null;
  sshZielId: string;
}

export function LektorierenPage({
  ordner,
  projekt,
  sshZielId,
}: LektorierenPageProps) {
  const [n, setN] = useState(projekt?.kapitel.at(-1) ?? 1);
  const [ergebnis, setErgebnis] = useState<AnwendenAntwort | null>(null);
  const [bearbeitet, setBearbeitet] = useState("");
  const [laedt, setLaedt] = useState(false);
  const [gespeichertHinweis, setGespeichertHinweis] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const { starten, beenden } = useAktivitaet();

  async function lektorieren() {
    setLaedt(true);
    setFehler(null);
    setGespeichertHinweis(null);
    starten(`Lektoriert Kapitel ${n} (Grammatik/Rechtschreibung)...`);
    try {
      const antwort = await api.lektorieren(ordner, n, sshZielId || null);
      setErgebnis(antwort);
      setBearbeitet(antwort.neu);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLaedt(false);
      beenden();
    }
  }

  async function speichern() {
    await api.kapitelSchreiben(ordner, n, bearbeitet);
    setGespeichertHinweis("Gespeichert.");
  }

  return (
    <div className="space-y-6 p-6">
      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <Label>Kapitelnummer</Label>
            <Input type="number" min={1} value={n} onChange={(e) => setN(Number(e.target.value))} className="w-28" />
          </div>
          <Button onClick={lektorieren} disabled={laedt}>
            {laedt ? "Lektoriert..." : "Grammatik/Rechtschreibung lektorieren"}
          </Button>
        </div>
        {fehler && <p className="mt-2 text-sm text-red-400">{fehler}</p>}
      </Card>

      {ergebnis && (
        <Card>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-heading text-lg font-semibold tracking-wide text-text">
              Merge-Ansicht: alt (links) vs. lektoriert (rechts, editierbar)
            </h2>
            <div className="flex items-center gap-3">
              {gespeichertHinweis && <span className="text-xs text-accent-light">{gespeichertHinweis}</span>}
              <Button onClick={speichern}>Aktuellen Stand speichern</Button>
            </div>
          </div>
          <MergeEditor original={ergebnis.alt} modified={bearbeitet} onModifiedChange={setBearbeitet} />
        </Card>
      )}
    </div>
  );
}
