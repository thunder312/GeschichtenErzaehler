import { useEffect, useRef, useState } from "react";
import { architektWebSocketUrl } from "../api/client";
import type { ArchitektNachricht } from "../api/types";
import { Button, Card } from "../components/ui";

interface ArchitektInterviewPageProps {
  ordner: string;
  sshZielId: string;
  onAbgeschlossen: (neuerOrdner: string) => void;
}

interface ChatEintrag {
  rolle: "architekt" | "ich";
  text: string;
}

interface Antwortoption {
  buchstabe: string;
  zeile: string;
}

/** Erkennt feste Mehrfachauswahl-Optionen ("a) ...", "b) ...", ...) in einer
 * Architekten-Frage, damit sie als Knoepfe statt nur als Freitext bedienbar
 * sind - der Architekt formuliert Fragen fast immer in diesem Schema. */
function optionenErkennen(text: string): Antwortoption[] {
  const treffer: Antwortoption[] = [];
  for (const zeile of text.split("\n")) {
    const match = zeile.match(/^\s*([a-f])\)\s*(.+)$/i);
    if (match) {
      treffer.push({ buchstabe: match[1].toLowerCase(), zeile: zeile.trim() });
    }
  }
  return treffer;
}

/** Geführtes Architekten-Interview - ersetzt den frueheren Rohtext-Editor
 * fuer ein noch leeres Gerüst. Portiert aus pre-GUI/novelle.py's
 * cmd_architekt(): ein echtes Mehrschritt-Gespraech ueber WebSocket, bei
 * dem der komplette Verlauf serverseitig bei jedem Zug neu an die Rolle
 * 'architekt' geschickt wird (siehe backend/app/api/architekt.py). Endet
 * automatisch, sobald die Persona ein vollstaendiges '# STORY-GERUEST'
 * liefert - das Backend speichert dann geruest.md (+ ggf. stand_00.md) und
 * benennt den Projektordner passend zum gewaehlten Titel um. */
export function ArchitektInterviewPage({
  ordner,
  sshZielId,
  onAbgeschlossen,
}: ArchitektInterviewPageProps) {
  const [gestartet, setGestartet] = useState(false);
  const [nachrichten, setNachrichten] = useState<ChatEintrag[]>([]);
  const [eingabe, setEingabe] = useState("");
  const [wartetAufAntwort, setWartetAufAntwort] = useState(false);
  const [denktNach, setDenktNach] = useState(false);
  const [abgeschlossen, setAbgeschlossen] = useState(false);
  const [beendetOhneSpeichern, setBeendetOhneSpeichern] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const chatEndeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndeRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [nachrichten, wartetAufAntwort]);

  useEffect(() => () => socketRef.current?.close(), []);

  function starten() {
    setGestartet(true);
    setNachrichten([]);
    setFehler(null);
    setAbgeschlossen(false);
    setBeendetOhneSpeichern(false);
    setWartetAufAntwort(true);

    const socket = new WebSocket(architektWebSocketUrl(ordner, sshZielId || null));
    socketRef.current = socket;

    socket.onmessage = (ereignis) => {
      const nachricht: ArchitektNachricht = JSON.parse(ereignis.data);
      if (nachricht.phase === "frage" && nachricht.typ === "start") {
        setWartetAufAntwort(true);
        setDenktNach(false);
      }
      if (nachricht.phase === "frage" && nachricht.typ === "denkt_nach") {
        setDenktNach(true);
      }
      if (nachricht.phase === "frage" && nachricht.typ === "fertig") {
        setDenktNach(false);
        setWartetAufAntwort(false);
        setNachrichten((bisher) => [...bisher, { rolle: "architekt", text: nachricht.text }]);
      }
      if (nachricht.phase === "abgeschlossen") {
        setAbgeschlossen(true);
        setWartetAufAntwort(false);
        onAbgeschlossen(nachricht.neuer_ordner);
      }
      if (nachricht.phase === "beendet_ohne_speichern") {
        setBeendetOhneSpeichern(true);
        setWartetAufAntwort(false);
      }
      if (nachricht.phase === "fehler") {
        setFehler(nachricht.text);
        setWartetAufAntwort(false);
      }
    };
    socket.onerror = () => {
      setFehler("WebSocket-Verbindung fehlgeschlagen.");
      setWartetAufAntwort(false);
    };
  }

  function senden() {
    const text = eingabe.trim();
    if (!text || !socketRef.current || wartetAufAntwort) return;
    setNachrichten((bisher) => [...bisher, { rolle: "ich", text }]);
    socketRef.current.send(JSON.stringify({ eingabe: text }));
    setEingabe("");
    setWartetAufAntwort(true);
  }

  function beenden() {
    socketRef.current?.send(JSON.stringify({ eingabe: "ende" }));
  }

  const kannAntworten = !wartetAufAntwort && !abgeschlossen && !beendetOhneSpeichern;
  const letzteNachricht = nachrichten.at(-1);
  const optionen =
    kannAntworten && letzteNachricht?.rolle === "architekt" ? optionenErkennen(letzteNachricht.text) : [];

  if (!gestartet) {
    return (
      <div className="p-6">
        <Card className="mx-auto max-w-xl text-center">
          <div className="mb-3 text-4xl">🗺️</div>
          <h2 className="font-heading mb-2 text-lg font-semibold text-text">Architekten-Interview</h2>
          <p className="mb-4 text-sm text-text-muted">
            Der Architekt stellt dir Schritt für Schritt Fragen zu Setting, Figuren, Konflikt und
            Kapitelplan und erstellt daraus automatisch das Story-Gerüst dieses Projekts.
          </p>
          <Button onClick={starten}>Interview starten</Button>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-8.5rem)] max-w-3xl flex-col gap-4 p-6">
      <Card className="flex-1 overflow-y-auto">
        <div className="space-y-4">
          {nachrichten.map((eintrag, i) => (
            <div key={i} className={`flex ${eintrag.rolle === "ich" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm ${
                  eintrag.rolle === "ich"
                    ? "bg-accent-soft text-accent-light"
                    : "bg-surface-hover text-text"
                }`}
              >
                {eintrag.rolle === "architekt" && <div className="mb-1 text-xs text-text-muted">🗺️ Architekt</div>}
                {eintrag.text}
              </div>
            </div>
          ))}
          {wartetAufAntwort && (
            <div className="flex justify-start">
              <div className="rounded-2xl bg-surface-hover px-4 py-2.5 text-sm italic text-text-muted">
                {denktNach ? "🗺️ Architekt denkt nach..." : "🗺️ Architekt antwortet..."}
              </div>
            </div>
          )}
          {abgeschlossen && (
            <div className="rounded-lg border border-accent-soft bg-accent-soft/40 px-4 py-3 text-sm text-accent-light">
              ✅ Story-Gerüst erstellt und gespeichert. Wechsle oben zum Reiter, um es zu sehen oder von Hand
              nachzujustieren.
            </div>
          )}
          {beendetOhneSpeichern && (
            <div className="rounded-lg border border-border bg-surface-hover px-4 py-3 text-sm text-text-muted">
              Gespräch beendet, ohne dass ein Gerüst gespeichert wurde. Du kannst das Interview jederzeit neu
              starten.
            </div>
          )}
          {fehler && <p className="text-sm text-red-400">{fehler}</p>}
          <div ref={chatEndeRef} />
        </div>
      </Card>

      {optionen.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {optionen.map((option) => (
            <button
              key={option.buchstabe}
              onClick={() => setEingabe(option.zeile)}
              className="rounded-full border border-border bg-surface-hover px-3.5 py-1.5 text-sm text-text transition-colors hover:border-accent hover:text-accent-light"
            >
              {option.zeile}
            </button>
          ))}
        </div>
      )}

      {!abgeschlossen && !beendetOhneSpeichern && (
        <div className="flex gap-2">
          <textarea
            className="flex-1 resize-none rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text outline-none transition-colors focus:border-accent"
            rows={2}
            value={eingabe}
            onChange={(e) => setEingabe(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                senden();
              }
            }}
            placeholder="Deine Antwort... (Enter zum Senden, Umschalt+Enter für neue Zeile)"
            disabled={wartetAufAntwort}
          />
          <div className="flex flex-col gap-2">
            <Button onClick={senden} disabled={wartetAufAntwort || !eingabe.trim()}>
              Senden
            </Button>
            <Button onClick={beenden} variant="secondary" disabled={wartetAufAntwort}>
              Beenden
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
