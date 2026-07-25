import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AnwendenAntwort, ProjektDetail } from "../api/types";
import { MergeEditor } from "../components/MergeEditor";
import { Button, Card, CardTitle, Input, Label } from "../components/ui";
import { useAktivitaet } from "../context/AktivitaetContext";
import { useLetztesKapitelSync } from "../utils/useLetztesKapitelSync";

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
  const [offeneAenderungen, setOffeneAenderungen] = useState(0);
  const { starten, beenden } = useAktivitaet();
  useLetztesKapitelSync(projekt, setN);

  // Beim Wechsel auf ein anderes Kapitel die Merge-Ansicht des vorherigen
  // Kapitels verwerfen - sonst blieb sie stehen und "Aktuellen Stand
  // speichern" haette versehentlich das falsche Kapitel ueberschrieben.
  useEffect(() => {
    setErgebnis(null);
    setBearbeitet("");
    setGespeichertHinweis(null);
    setOffeneAenderungen(0);
    setFehler(null);
  }, [ordner, n]);

  async function lektorieren() {
    setLaedt(true);
    setFehler(null);
    setGespeichertHinweis(null);
    starten(`Lektoriert Kapitel ${n} (Grammatik & Stil)...`);
    try {
      const antwort = await api.lektorieren(ordner, n, sshZielId || null);
      setErgebnis(antwort);
      setBearbeitet(antwort.neu);
      setOffeneAenderungen(0);
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
        <CardTitle>🪄 Lektorieren</CardTitle>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <Label>Kapitelnummer</Label>
            <Input type="number" min={1} value={n} onChange={(e) => setN(Number(e.target.value))} className="w-28" />
          </div>
          <Button onClick={lektorieren} disabled={laedt}>
            {laedt ? "Lektoriert..." : "Grammatik & Stil lektorieren"}
          </Button>
        </div>
        <p className="mt-2 text-xs text-text-muted">
          Die Wörterbuch-Prüfung auf unbekannte Wörter findest du im Tab "Rechtschreibung". Kontinuitätsprobleme
          aus dem Tab "Prüfen & Anwenden" werden nicht automatisch korrigiert - in der editierbaren
          Merge-Ansicht unten kannst du sie nach dem Lektorieren von Hand einarbeiten.
        </p>
        {fehler && <p className="mt-2 text-sm text-red-400">{fehler}</p>}
      </Card>

      {ergebnis && (
        <Card>
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h2 className="font-heading text-lg font-semibold tracking-wide text-text">
                Merge-Ansicht: alt (links) vs. lektoriert (rechts, editierbar)
              </h2>
              {offeneAenderungen > 0 ? (
                <span className="rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-medium text-accent-light">
                  {offeneAenderungen} offene {offeneAenderungen === 1 ? "Änderung" : "Änderungen"}
                </span>
              ) : (
                <span className="text-xs text-text-muted">Alle Änderungen durchgesehen</span>
              )}
            </div>
            <div className="flex items-center gap-3">
              {gespeichertHinweis && <span className="text-xs text-accent-light">{gespeichertHinweis}</span>}
              <Button onClick={speichern}>Aktuellen Stand speichern</Button>
            </div>
          </div>
          <p className="mb-2 text-xs text-text-muted">
            Jede Änderung hat am Ende ihrer ersten Zeile ein ✓/✗-Symbol: ✓ übernimmt die Korrektur des Lektors,
            ✗ verwirft sie und stellt die Original-Stelle wieder her.
          </p>
          <MergeEditor
            original={ergebnis.alt}
            modified={bearbeitet}
            onModifiedChange={setBearbeitet}
            hunkweiseBestaetigen
            onOffeneAenderungen={setOffeneAenderungen}
          />
        </Card>
      )}
    </div>
  );
}
