import { useEffect, useRef, useState } from "react";
import { api, schreibenWebSocketUrl } from "../api/client";
import type { Finding, ProjektDetail, SchreibenNachricht } from "../api/types";
import { BefundeView } from "../components/BefundeView";
import { FindingsList } from "../components/FindingsList";
import { Button, Card, CardTitle, Input, Label } from "../components/ui";
import { useAktivitaet } from "../context/AktivitaetContext";
import { alsDateiHerunterladen } from "../utils/download";

interface SchreibenPageProps {
  ordner: string;
  projekt: ProjektDetail | null;
  sshZielId: string;
  onKapitelGeschrieben: () => void;
}

export function SchreibenPage({
  ordner,
  projekt,
  sshZielId,
  onKapitelGeschrieben,
}: SchreibenPageProps) {
  const [n, setN] = useState(1);
  const [zusatzhinweis, setZusatzhinweis] = useState("");
  const [laeuft, setLaeuft] = useState(false);
  const [denktNach, setDenktNach] = useState(false);
  const [autorText, setAutorText] = useState("");
  const [geladenAusDatei, setGeladenAusDatei] = useState(false);
  const [modell, setModell] = useState<string | null>(null);
  const [befunde, setBefunde] = useState<string | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [phase, setPhase] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const letztesProjekt = useRef<string | null>(null);
  const { starten: aktivitaetStarten, beenden: aktivitaetBeenden } = useAktivitaet();

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

  // Zeigt beim (erneuten) Betreten dieses Tabs bzw. bei einer anderen
  // Kapitelnummer den bereits gespeicherten Kapiteltext an, statt immer
  // leer zu starten - vorher wirkte ein schon geschriebenes Kapitel nach
  // einem Tab-Wechsel "verschwunden", obwohl kapitel_NN.md unveraendert auf
  // der Platte lag (die Anzeige war reiner, nicht persistenter React-State).
  useEffect(() => {
    if (laeuft) return;
    let abgebrochen = false;
    setFehler(null);
    if (!projekt?.kapitel.includes(n)) {
      setAutorText("");
      setBefunde(null);
      setGeladenAusDatei(false);
      return;
    }
    api
      .kapitel(ordner, n)
      .then((text) => {
        // Ohne diese Absicherung konnte eine noch laufende, aber
        // ueberholte Anfrage (z.B. fuer die vorherige Kapitelnummer) nach
        // dem Wechsel auf eine neue Nummer verspaetet zurueckkommen und
        // den korrekt zurueckgesetzten Zustand wieder mit dem falschen
        // Kapiteltext ueberschreiben.
        if (abgebrochen) return;
        setAutorText(text);
        setGeladenAusDatei(true);
      })
      .catch(() => {
        if (abgebrochen) return;
        setAutorText("");
        setGeladenAusDatei(false);
      });
    api
      .befunde(ordner, n)
      .then((text) => {
        if (!abgebrochen) setBefunde(text);
      })
      .catch(() => {
        if (!abgebrochen) setBefunde(null);
      });
    return () => {
      abgebrochen = true;
    };
  }, [ordner, n, projekt, laeuft]);

  function starten() {
    setLaeuft(true);
    setAutorText("");
    setGeladenAusDatei(false);
    setBefunde(null);
    setFindings([]);
    setFehler(null);
    setPhase("autor");
    setModell(null);

    const socket = new WebSocket(schreibenWebSocketUrl(ordner, n, zusatzhinweis, sshZielId || null));
    socketRef.current = socket;

    aktivitaetStarten(`Schreibt Kapitel ${n}...`);

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
      if (nachricht.phase === "pruefen" && nachricht.typ === "start") {
        aktivitaetStarten(`Prüft Kapitel ${n} auf Anachronismen & Kontinuität...`);
      }
      if (nachricht.phase === "pruefen" && nachricht.typ === "done") {
        setBefunde(nachricht.text);
      }
      if (nachricht.phase === "abgeschlossen") {
        setLaeuft(false);
        aktivitaetBeenden();
        onKapitelGeschrieben();
        // Nach erfolgreichem Schreiben automatisch zum naechsten Kapitel
        // weiterschalten - sonst blieb die Kapitelnummer auf dem gerade
        // geschriebenen Kapitel stehen (die Nummer wird bewusst NICHT bei
        // jeder Projekt-Aktualisierung neu vorgeschlagen, siehe Kommentar
        // oben), und ein zweiter Klick auf "Schreiben starten" ohne manuelle
        // Anpassung schrieb versehentlich dasselbe Kapitel nochmal (statt
        // das naechste), was wie ein "haengengebliebenes" Fortschreiben
        // aussah.
        setN(n + 1);
      }
      if (nachricht.phase === "fehler") {
        setFehler(nachricht.text);
        setLaeuft(false);
        aktivitaetBeenden();
      }
    };
    socket.onerror = () => {
      setFehler("WebSocket-Verbindung fehlgeschlagen.");
      setLaeuft(false);
      aktivitaetBeenden();
    };
    socket.onclose = () => {
      setLaeuft(false);
      aktivitaetBeenden();
    };
  }

  function abbrechen() {
    socketRef.current?.close();
    setLaeuft(false);
    aktivitaetBeenden();
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
          {!zielWoerter && !!projekt?.letztes_geplantes_kapitel && n > projekt.letztes_geplantes_kapitel && (
            <p className="mt-1 text-xs text-text-muted">
              Kapitel {n} ist im Kapitelplan nicht vorgesehen (geplant bis Kapitel{" "}
              {projekt.letztes_geplantes_kapitel}) - es wird ohne festen Zielumfang geschrieben. Nutze bei
              Bedarf den Hinweis unten, um vorzugeben, was in diesem Kapitel passieren soll.
            </p>
          )}
          {projekt?.kapitel.includes(n) && (
            <p className="mt-1 text-xs text-amber-300">
              Kapitel {n} wurde bereits geschrieben - "Schreiben starten" überschreibt es (alte Fassung wird
              als .bak gesichert).
            </p>
          )}
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
            <h2 className="font-heading text-lg font-semibold tracking-wide text-text">
              Autor {modell && <span className="font-sans font-normal text-text-muted">({modell})</span>}
            </h2>
            {denktNach && <span className="text-xs italic text-accent-light">denkt nach...</span>}
            {!laeuft && geladenAusDatei && (
              <span className="text-xs text-text-muted">📄 gespeicherter Stand von kapitel_{String(n).padStart(2, "0")}.md</span>
            )}
            {phase && phase !== "autor" && laeuft && (
              <span className="text-xs text-text-muted">Phase: {phase}</span>
            )}
            {!laeuft && autorText && (
              <button
                onClick={() => alsDateiHerunterladen(`kapitel_${String(n).padStart(2, "0")}.md`, autorText)}
                className="text-xs text-accent-light hover:underline"
              >
                ⬇️ Herunterladen
              </button>
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
            <BefundeView text={befunde} />
          </Card>
        )}
      </div>
    </div>
  );
}
