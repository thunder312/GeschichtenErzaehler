import { useState } from "react";
import { api } from "../api/client";
import type { AnwendenAntwort, ProjektDetail } from "../api/types";
import { BefundeView } from "../components/BefundeView";
import { MergeEditor } from "../components/MergeEditor";
import { Badge, Button, Card, CardTitle, Input, Label } from "../components/ui";
import { useAktivitaet } from "../context/AktivitaetContext";
import { useLetztesKapitelSync } from "../utils/useLetztesKapitelSync";

interface PruefenAnwendenPageProps {
  ordner: string;
  projekt: ProjektDetail | null;
  sshZielId: string;
}

export function PruefenAnwendenPage({
  ordner,
  projekt,
  sshZielId,
}: PruefenAnwendenPageProps) {
  const [n, setN] = useState(projekt?.kapitel.at(-1) ?? 1);
  const [befunde, setBefunde] = useState<string | null>(null);
  const [ergebnis, setErgebnis] = useState<AnwendenAntwort | null>(null);
  const [bearbeitet, setBearbeitet] = useState("");
  const [ladenPruefen, setLadenPruefen] = useState(false);
  const [ladenAnwenden, setLadenAnwenden] = useState(false);
  const [gespeichertHinweis, setGespeichertHinweis] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const { starten, beenden } = useAktivitaet();
  useLetztesKapitelSync(projekt, setN);

  async function pruefen() {
    setLadenPruefen(true);
    setFehler(null);
    starten(`Prüft Kapitel ${n} auf Anachronismen & Kontinuität...`);
    try {
      const antwort = await api.pruefen(ordner, n, sshZielId || null);
      setBefunde(antwort.inhalt);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLadenPruefen(false);
      beenden();
    }
  }

  async function anwenden() {
    setLadenAnwenden(true);
    setFehler(null);
    setGespeichertHinweis(null);
    starten(`Wendet Anachronismus-Korrekturen auf Kapitel ${n} an...`);
    try {
      const antwort = await api.anwenden(ordner, n, sshZielId || null);
      setErgebnis(antwort);
      setBearbeitet(antwort.neu);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLadenAnwenden(false);
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
          <Button onClick={pruefen} disabled={ladenPruefen} variant="secondary">
            {ladenPruefen ? "Prüft..." : "Prüfen"}
          </Button>
          <Button onClick={anwenden} disabled={ladenAnwenden}>
            {ladenAnwenden ? "Wendet an..." : "Sichere Anachronismus-Funde anwenden"}
          </Button>
        </div>
        {fehler && <p className="mt-2 text-sm text-red-400">{fehler}</p>}
      </Card>

      {befunde && (
        <Card>
          <CardTitle>🔍 Befunde</CardTitle>
          <BefundeView text={befunde} />
        </Card>
      )}

      {ergebnis && (
        <Card>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-heading text-lg font-semibold tracking-wide text-text">
              Merge-Ansicht: alt (links) vs. korrigiert (rechts, editierbar)
            </h2>
            <div className="flex items-center gap-3">
              {ergebnis.gesichert_als === null ? (
                <Badge tone="amber">Nicht automatisch übernommen (deutlich kürzer)</Badge>
              ) : (
                <Badge tone="green">Automatisch übernommen, Original gesichert als {ergebnis.gesichert_als}</Badge>
              )}
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
