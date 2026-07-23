import { useEffect, useRef, useState } from "react";
import { schreibenWebSocketUrl } from "../api/client";
import type { Finding, ProjektDetail, SSHZiel, SchreibenNachricht } from "../api/types";
import { FindingsList } from "../components/FindingsList";
import { Button, Card, CardTitle, Input, Label, Select } from "../components/ui";

interface SchreibenPageProps {
  ordner: string;
  projekt: ProjektDetail | null;
  sshZiele: SSHZiel[];
  onKapitelGeschrieben: () => void;
}

export function SchreibenPage({ ordner, projekt, sshZiele, onKapitelGeschrieben }: SchreibenPageProps) {
  const [n, setN] = useState(1);
  const [zusatzhinweis, setZusatzhinweis] = useState("");
  const [sshZielId, setSshZielId] = useState("");
  const [laeuft, setLaeuft] = useState(false);
  const [denktNach, setDenktNach] = useState(false);
  const [autorText, setAutorText] = useState("");
  const [modell, setModell] = useState<string | null>(null);
  const [befunde, setBefunde] = useState<string | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [phase, setPhase] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const letztesProjekt = useRef<string | null>(null);

  useEffect(() => {
    // Kapitelnummer nur beim WECHSEL des Projekts neu vorschlagen, nicht bei
    // jeder Aktualisierung von projekt (sonst ueberschreibt jede erneute
    // Detail-Ladung eine bereits vom Nutzer getippte Kapitelnummer).
    if (projekt && letztesProjekt.current !== projekt.ordner) {
      letztesProjekt.current = projekt.ordner;
      setN((projekt.kapitel.length || 0) + 1);
    }
  }, [projekt]);

  useEffect(() => () => socketRef.current?.close(), []);

  function starten() {
    setLaeuft(true);
    setAutorText("");
    setBefunde(null);
    setFindings([]);
    setFehler(null);
    setPhase("autor");
    setModell(null);

    const socket = new WebSocket(schreibenWebSocketUrl(ordner, n, zusatzhinweis, sshZielId || null));
    socketRef.current = socket;

    socket.onmessage = (ereignis) => {
      const nachricht: SchreibenNachricht = JSON.parse(ereignis.data);
      setPhase(nachricht.phase);
      if (nachricht.phase === "autor") {
        if (nachricht.typ === "start") setModell(nachricht.modell);
        if (nachricht.typ === "thinking") setDenktNach(true);
        if (nachricht.typ === "content") {
          setDenktNach(false);
          setAutorText((bisher) => bisher + nachricht.text);
        }
        if (nachricht.typ === "done") setDenktNach(false);
        if (nachricht.typ === "error") setFehler(nachricht.text);
      }
      if (nachricht.phase === "nachbearbeitung" && nachricht.typ === "done") {
        setFindings(nachricht.findings);
      }
      if (nachricht.phase === "pruefen" && nachricht.typ === "done") {
        setBefunde(nachricht.text);
      }
      if (nachricht.phase === "abgeschlossen") {
        setLaeuft(false);
        onKapitelGeschrieben();
      }
      if (nachricht.phase === "fehler") {
        setFehler(nachricht.text);
        setLaeuft(false);
      }
    };
    socket.onerror = () => {
      setFehler("WebSocket-Verbindung fehlgeschlagen.");
      setLaeuft(false);
    };
    socket.onclose = () => setLaeuft(false);
  }

  function abbrechen() {
    socketRef.current?.close();
    setLaeuft(false);
  }

  const zielWoerter = projekt?.kapitelplan[n];

  return (
    <div className="grid grid-cols-1 gap-6 p-6 lg:grid-cols-[1fr_2fr]">
      <Card className="h-fit space-y-3">
        <CardTitle>✍️ Kapitel schreiben</CardTitle>
        <div>
          <Label>Kapitelnummer</Label>
          <Input type="number" min={1} value={n} onChange={(e) => setN(Number(e.target.value))} disabled={laeuft} />
          {zielWoerter && <p className="mt-1 text-xs text-text-muted">Zielumfang laut Gerüst: ~{zielWoerter} Wörter</p>}
        </div>
        <div>
          <Label>Zusätzlicher Hinweis (nur für diesen Versuch)</Label>
          <textarea
            className="w-full rounded-lg border border-border bg-bg px-3 py-1.5 text-sm text-text outline-none transition-colors focus:border-accent"
            rows={4}
            value={zusatzhinweis}
            onChange={(e) => setZusatzhinweis(e.target.value)}
            disabled={laeuft}
            placeholder="z.B. bei starken Kontinuitaets-Bruechen im letzten Versuch..."
          />
        </div>
        <div>
          <Label>KI über SSH-Ziel ansprechen (optional)</Label>
          <Select value={sshZielId} onChange={(e) => setSshZielId(e.target.value)} disabled={laeuft}>
            <option value="">Lokal / Standard-Ollama</option>
            {sshZiele.map((z) => (
              <option key={z.id} value={z.id}>
                {z.name} ({z.host})
              </option>
            ))}
          </Select>
        </div>
        {!laeuft ? (
          <Button onClick={starten} className="w-full">
            Schreiben starten
          </Button>
        ) : (
          <Button onClick={abbrechen} variant="danger" className="w-full">
            Abbrechen
          </Button>
        )}
        {fehler && <p className="text-sm text-red-400">{fehler}</p>}
      </Card>

      <div className="space-y-4">
        <Card>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-heading text-sm font-semibold tracking-wide text-text">
              Autor {modell && <span className="font-sans font-normal text-text-muted">({modell})</span>}
            </h2>
            {denktNach && <span className="text-xs italic text-accent-light">denkt nach...</span>}
            {phase && phase !== "autor" && (
              <span className="text-xs text-text-muted">Phase: {phase}</span>
            )}
          </div>
          <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap rounded-lg bg-bg p-3 text-sm leading-relaxed text-text">
            {autorText || "Noch kein Text erzeugt."}
          </pre>
        </Card>

        {findings.length > 0 && (
          <Card>
            <CardTitle>Automatische Sicherheitsnetze</CardTitle>
            <FindingsList findings={findings} />
          </Card>
        )}

        {befunde && (
          <Card>
            <CardTitle>Befunde der Prüfer (Anachronismen &amp; Kontinuität)</CardTitle>
            <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap rounded-lg bg-bg p-3 text-sm text-text">
              {befunde}
            </pre>
          </Card>
        )}
      </div>
    </div>
  );
}
