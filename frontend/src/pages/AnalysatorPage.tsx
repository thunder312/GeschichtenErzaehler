import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { AnalysatorStatus, EpocheKurz } from "../api/types";
import { Button, Card, CardTitle, Input, Label, Select, Textarea } from "../components/ui";

interface AnalysatorPageProps {
  epochen: EpocheKurz[];
  sshZielId: string;
  onProjektErzeugt: (ordner: string) => void;
}

const PHASE_LABEL: Record<string, string> = {
  teilen: "Text wird in Kapitel aufgeteilt...",
  kapitel_analyse: "Kapitel werden analysiert...",
  synthese: "Gesamt-Gerüst wird zusammengefasst...",
  fertig: "Fertig.",
};

/** Neuer Haupt-Tab (siehe ToDo.md "Analysator"): importiert eine bestehende
 * Geschichte/Novelle als Rohtext und lässt daraus automatisch ein
 * komplettes Projekt (Gerüst inkl. Kapitelplan) bauen, ohne dass der Nutzer
 * das Architekten-Interview durchläuft - dritter Weg zu einem Projekt neben
 * "Architekten-Interview" und "Gerüst selbst schreiben" (ProjektePage.tsx).
 * Der eigentliche Analyse-Lauf läuft als Hintergrund-Task auf dem Server
 * (siehe app/api/analysator.py) - dieselbe Statusdatei-Poll-Architektur wie
 * der Automatikmodus (SchreibenPage.tsx), nur linear statt mit Durchläufen. */
export function AnalysatorPage({ epochen, sshZielId, onProjektErzeugt }: AnalysatorPageProps) {
  const [titel, setTitel] = useState("");
  const [epoche, setEpoche] = useState("");
  const [zweiteEpoche, setZweiteEpoche] = useState("");
  const [text, setText] = useState("");
  const [wirdGestartet, setWirdGestartet] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [ordner, setOrdner] = useState<string | null>(null);
  const [status, setStatus] = useState<AnalysatorStatus | null>(null);
  const dateiInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (epoche || epochen.length === 0) return;
    setEpoche(epochen[0].name);
  }, [epochen, epoche]);

  useEffect(() => {
    if (!ordner || status?.abgeschlossen) return;
    let abgebrochen = false;
    const laden = () => {
      api.analysatorStatus(ordner).then((s) => {
        if (!abgebrochen) setStatus(s);
      });
    };
    laden();
    // Bewusst deutlich seltener als das 3s-Intervall bei Automatik/Schreiben
    // (siehe SchreibenPage.tsx) - ein realer Live-Test (2026-08-21, SSH-Ziel
    // "Athene") zeigte, dass haeufiges Pollen WAEHREND eines laufenden
    // Analyse-Aufrufs die eigentliche Ollama-Antwort ueber den SSH-Tunnel
    // massiv verlangsamt (20+ Minuten statt ca. 1 Minute fuer ein einzelnes
    // kurzes Kapitel bei Polling alle 5-7s, ggu. minutenschnell komplett
    // OHNE Polling waehrenddessen) - vermutlich GIL-Konkurrenz zwischen dem
    // Tunnel-Forwarder-Thread (app/core/ssh_manager.py) und den vielen
    // kurzen HTTP-Request-Handlern. Da ein einzelner Analyse-Schritt ohnehin
    // typischerweise 30s-3min dauert, kostet ein groesseres Intervall keine
    // spuerbare UI-Traegheit, verhindert aber genau dieses Antipattern.
    const intervall = setInterval(laden, 10000);
    return () => {
      abgebrochen = true;
      clearInterval(intervall);
    };
  }, [ordner, status?.abgeschlossen]);

  async function dateiGeladen(e: React.ChangeEvent<HTMLInputElement>) {
    const datei = e.target.files?.[0];
    e.target.value = "";
    if (!datei) return;
    setText(await datei.text());
  }

  async function starten() {
    if (!epoche || !text.trim()) return;
    setWirdGestartet(true);
    setFehler(null);
    try {
      const antwort = await api.analysatorStarten(titel.trim(), epoche, text, zweiteEpoche, sshZielId);
      setOrdner(antwort.ordner);
      setStatus(null);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setWirdGestartet(false);
    }
  }

  function neuerImport() {
    setOrdner(null);
    setStatus(null);
    setTitel("");
    setText("");
    setFehler(null);
  }

  const laeuft = ordner !== null && !status?.abgeschlossen && !status?.fehler;
  const woerterAnzahl = text.trim() ? text.trim().split(/\s+/).filter(Boolean).length : 0;
  // Grobe Schaetzung nur fuer die Vorabanzeige - deckt sich in der
  // Groessenordnung mit ZIEL_WOERTER_PRO_ABSCHNITT in app/core/analysator.py,
  // muss aber nicht exakt uebereinstimmen (echte Aufteilung haengt zusaetzlich
  // von erkennbaren Kapitelueberschriften im Text ab).
  const geschaetzteKapitel = Math.max(1, Math.round(woerterAnzahl / 1400));

  return (
    <div className="grid grid-cols-1 gap-6 p-4 sm:p-6 lg:grid-cols-[2fr_1fr]">
      <Card>
        <CardTitle>🔬 Analysator</CardTitle>
        <p className="mb-4 text-sm text-text-muted">
          Importiere eine bestehende Geschichte oder Novelle als Text. Die KI analysiert sie Kapitel für Kapitel
          und baut daraus ein komplettes Gerüst (inkl. Kapitelplan) - ein neues Projekt, das du anschließend im
          Gerüst-Editor prüfst, ergänzt und dann von der KI selbst neu schreiben lässt. Kein Interview nötig.
        </p>

        {!ordner ? (
          <div className="space-y-3">
            <div>
              <Label>Titel (optional)</Label>
              <Input
                autoComplete="off"
                value={titel}
                onChange={(e) => setTitel(e.target.value)}
                placeholder="ergibt sich sonst aus der Analyse"
              />
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <Label>Epoche</Label>
                <Select value={epoche} onChange={(e) => setEpoche(e.target.value)}>
                  {epochen.map((e) => (
                    <option key={e.name} value={e.name}>
                      {e.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label>Zeitsprung: zweite Epoche (optional)</Label>
                <Select value={zweiteEpoche} onChange={(e) => setZweiteEpoche(e.target.value)}>
                  <option value="">Keine - nur eine Epoche</option>
                  {epochen
                    .filter((e) => e.name !== epoche)
                    .map((e) => (
                      <option key={e.name} value={e.name}>
                        {e.name}
                      </option>
                    ))}
                </Select>
              </div>
            </div>
            <div>
              <div className="mb-1 flex items-center justify-between gap-3">
                <Label>Text der Geschichte</Label>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-text-muted">{woerterAnzahl > 0 ? `${woerterAnzahl} Wörter` : ""}</span>
                  <button
                    type="button"
                    onClick={() => dateiInputRef.current?.click()}
                    className="text-xs text-accent-light hover:underline"
                  >
                    Datei laden (.txt, .md)
                  </button>
                  <input
                    ref={dateiInputRef}
                    type="file"
                    accept=".txt,.md,text/plain,text/markdown"
                    onChange={dateiGeladen}
                    className="hidden"
                  />
                </div>
              </div>
              <Textarea
                rows={16}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Text hier einfügen oder eine Datei laden..."
                className="font-mono text-sm"
              />
              {woerterAnzahl > 3000 && (
                <p className="mt-1 text-xs text-text-muted">
                  Geschätzt ca. {geschaetzteKapitel} Kapitel - die Analyse läuft Kapitel für Kapitel nacheinander
                  und kann je nach KI-Ziel mehrere Minuten bis über eine Stunde dauern.
                </p>
              )}
            </div>
            {fehler && <p className="text-sm text-red-400">{fehler}</p>}
            <Button onClick={starten} disabled={wirdGestartet || !epoche || !text.trim()}>
              {wirdGestartet ? "Wird gestartet..." : "Analysieren"}
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm">
              Projekt: <span className="font-medium text-text">{ordner}</span>
            </p>
            {laeuft && (
              <p className="text-sm">
                <strong>{PHASE_LABEL[status?.phase ?? ""] ?? "Wird gestartet..."}</strong>
                {status?.aktuelles_kapitel != null && (
                  <>
                    {" "}
                    · Kapitel {status.aktuelles_kapitel}
                    {status?.gesamt_kapitel != null && <>/{status.gesamt_kapitel}</>}
                  </>
                )}
              </p>
            )}
            <div className="max-h-[300px] overflow-y-auto rounded-lg border border-border bg-bg/40 p-3 font-mono text-xs">
              {status?.log.length ? (
                status.log.map((zeile, i) => <div key={i}>{zeile}</div>)
              ) : (
                <span className="text-text-muted">Wird gestartet...</span>
              )}
            </div>
            {status?.fehler && <p className="text-sm text-red-400">Fehler: {status.fehler}</p>}
            {status?.abgeschlossen && (
              <Button onClick={() => onProjektErzeugt(ordner)}>Jetzt prüfen und bearbeiten →</Button>
            )}
            {(status?.abgeschlossen || status?.fehler) && (
              <Button variant="secondary" onClick={neuerImport}>
                Weiteren Text importieren
              </Button>
            )}
          </div>
        )}
      </Card>

      <Card>
        <CardTitle>So funktioniert's</CardTitle>
        <ol className="list-decimal space-y-2 pl-4 text-sm text-text-muted">
          <li>Text einfügen oder eine .txt/.md-Datei laden.</li>
          <li>Epoche wählen, die zur importierten Geschichte passt.</li>
          <li>
            Die KI teilt den Text in Kapitel, analysiert jedes einzeln (Ort, Figuren, Ereignis, ...) und fasst am
            Ende Rahmen, Titel, Figuren und Konflikt zusammen.
          </li>
          <li>
            Das Ergebnis landet als neues Projekt im Gerüst-Editor - dort kannst du alles prüfen und anpassen,
            bevor die KI die Geschichte in ihren eigenen Worten neu schreibt.
          </li>
        </ol>
        <p className="mt-3 text-xs text-text-muted">
          Bei längeren Texten kann die Analyse mehrere Minuten dauern - der Lauf läuft auf dem Server weiter, auch
          wenn du währenddessen zu einem anderen Tab wechselst. Ein Neuladen der Seite unterbricht dagegen die
          Fortschrittsanzeige hier (der Server-Lauf selbst läuft trotzdem zu Ende).
        </p>
      </Card>
    </div>
  );
}
