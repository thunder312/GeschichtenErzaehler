import { useState } from "react";
import { api } from "../api/client";
import type { AnwendenAntwort, ProjektDetail, RechtschreibWort, SSHZiel } from "../api/types";
import { MergeEditor } from "../components/MergeEditor";
import { Button, Card, CardTitle, Input, Label, Select } from "../components/ui";

interface LektorierenPageProps {
  ordner: string;
  projekt: ProjektDetail | null;
  sshZiele: SSHZiel[];
}

export function LektorierenPage({ ordner, projekt, sshZiele }: LektorierenPageProps) {
  const [n, setN] = useState(projekt?.kapitel.at(-1) ?? 1);
  const [sshZielId, setSshZielId] = useState("");
  const [ergebnis, setErgebnis] = useState<AnwendenAntwort | null>(null);
  const [bearbeitet, setBearbeitet] = useState("");
  const [laedt, setLaedt] = useState(false);
  const [gespeichertHinweis, setGespeichertHinweis] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  const [woerter, setWoerter] = useState<RechtschreibWort[] | null>(null);
  const [hunspellVerfuegbar, setHunspellVerfuegbar] = useState(true);
  const [ersatzWerte, setErsatzWerte] = useState<Record<string, string>>({});
  const [ladenRechtschreibung, setLadenRechtschreibung] = useState(false);

  async function lektorieren() {
    setLaedt(true);
    setFehler(null);
    setGespeichertHinweis(null);
    try {
      const antwort = await api.lektorieren(ordner, n, sshZielId || null);
      setErgebnis(antwort);
      setBearbeitet(antwort.neu);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLaedt(false);
    }
  }

  async function speichern() {
    await api.kapitelSchreiben(ordner, n, bearbeitet);
    setGespeichertHinweis("Gespeichert.");
  }

  async function rechtschreibungPruefen() {
    setLadenRechtschreibung(true);
    setFehler(null);
    try {
      const antwort = await api.rechtschreibung(ordner, n, sshZielId || null);
      setWoerter(antwort.unbekannte_woerter);
      setHunspellVerfuegbar(antwort.hunspell_verfuegbar);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLadenRechtschreibung(false);
    }
  }

  async function ersetzenUndSpeichern() {
    const eintraege = Object.entries(ersatzWerte).filter(([, ersatz]) => ersatz.trim() !== "");
    if (eintraege.length === 0) return;
    let text = await api.kapitel(ordner, n);
    for (const [wort, ersatz] of eintraege) {
      text = text.replace(new RegExp(`\\b${wort}\\b`, "g"), ersatz);
    }
    await api.kapitelSchreiben(ordner, n, text);
    setErsatzWerte({});
    setWoerter(null);
  }

  return (
    <div className="space-y-6 p-6">
      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <Label>Kapitelnummer</Label>
            <Input type="number" min={1} value={n} onChange={(e) => setN(Number(e.target.value))} className="w-28" />
          </div>
          <div>
            <Label>KI-Ziel (optional)</Label>
            <Select value={sshZielId} onChange={(e) => setSshZielId(e.target.value)} className="w-56">
              <option value="">Lokal / Standard-Ollama</option>
              {sshZiele.map((z) => (
                <option key={z.id} value={z.id}>
                  {z.name} ({z.host})
                </option>
              ))}
            </Select>
          </div>
          <Button onClick={lektorieren} disabled={laedt}>
            {laedt ? "Lektoriert..." : "Grammatik/Rechtschreibung lektorieren"}
          </Button>
          <Button onClick={rechtschreibungPruefen} variant="secondary" disabled={ladenRechtschreibung}>
            {ladenRechtschreibung ? "Prüft..." : "Wörterbuch-Prüfung (hunspell)"}
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

      {woerter && (
        <Card>
          <CardTitle>📖 Unbekannte Wörter</CardTitle>
          {!hunspellVerfuegbar && (
            <p className="mb-2 text-sm text-amber-300">
              hunspell ist auf dem angesprochenen Ziel nicht verfügbar - für lokale Windows-Entwicklung ein
              SSH-Ziel mit installiertem hunspell auswählen.
            </p>
          )}
          {woerter.length === 0 ? (
            <p className="text-sm text-text-muted">Keine unbekannten Wörter gefunden.</p>
          ) : (
            <div className="space-y-2">
              {woerter.map((w) => (
                <div key={w.wort} className="flex items-center gap-3 border-b border-border pb-2 last:border-0">
                  <div className="w-40 shrink-0 font-mono text-sm">{w.wort}</div>
                  <div className="flex-1 text-xs text-text-muted">{w.satz ?? "(kein Satzkontext gefunden)"}</div>
                  <Input
                    placeholder="Ersatzwort (leer = behalten)"
                    className="w-56"
                    value={ersatzWerte[w.wort] ?? ""}
                    onChange={(e) => setErsatzWerte((bisher) => ({ ...bisher, [w.wort]: e.target.value }))}
                  />
                </div>
              ))}
              <Button onClick={ersetzenUndSpeichern} className="mt-2">
                Ersetzungen übernehmen &amp; speichern
              </Button>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
