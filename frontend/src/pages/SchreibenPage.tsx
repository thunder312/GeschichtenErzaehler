import { useEffect, useRef, useState } from "react";
import { api, schreibenWebSocketUrl } from "../api/client";
import type {
  AutomatikStatus,
  AutomatikVerlaufEintrag,
  BefundeAntwort,
  Finding,
  ProjektDetail,
  SchreibenNachricht,
} from "../api/types";
import { BefundListe } from "../components/BefundListe";
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

function formatDauer(sekunden: number): string {
  const std = Math.floor(sekunden / 3600);
  const min = Math.round((sekunden % 3600) / 60);
  return std > 0 ? `${std} Std. ${min} Min.` : `${min} Min.`;
}

/** Kurzer, lesbarer Text fuer die globale Fusszeile (StatusFooter) waehrend
 * der Automatikmodus im Hintergrund laeuft. */
function automatikAktionsText(status: AutomatikStatus): string {
  const kapitel = status.aktuelles_kapitel != null
    ? ` Kapitel ${status.aktuelles_kapitel}${status.gesamt_kapitel != null ? `/${status.gesamt_kapitel}` : ""}`
    : "";
  if (status.phase === "schreiben") return `Automatikmodus: schreibt${kapitel}...`;
  if (status.phase === "pruefen") {
    const durchlauf = status.aktueller_durchlauf != null ? `, Durchlauf ${status.aktueller_durchlauf}` : "";
    return `Automatikmodus: prüft${kapitel}${durchlauf}...`;
  }
  return "Automatikmodus läuft...";
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
  const [befunde, setBefunde] = useState<BefundeAntwort | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [phase, setPhase] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const letztesProjekt = useRef<string | null>(null);
  const autoVorgeschlageneNummerRef = useRef<number | null>(null);
  const phaseRef = useRef<string | null>(null);
  const { starten: aktivitaetStarten, beenden: aktivitaetBeenden } = useAktivitaet();

  const [automatikStatus, setAutomatikStatus] = useState<AutomatikStatus | null>(null);
  const [automatikMaxDurchlaeufe, setAutomatikMaxDurchlaeufe] = useState(3);
  const [automatikFehler, setAutomatikFehler] = useState<string | null>(null);
  const [automatikVerlauf, setAutomatikVerlauf] = useState<AutomatikVerlaufEintrag[]>([]);
  const automatikLiefZuvorRef = useRef(false);
  const automatikAktivitaetTextRef = useRef<string | null>(null);

  function automatikVerlaufLaden() {
    api
      .automatikVerlauf(ordner)
      .then(setAutomatikVerlauf)
      .catch(() => {});
  }

  // Pollt den Automatikmodus-Status, solange dieser Tab offen ist - der Lauf
  // selbst haengt NICHT an dieser Verbindung (Hintergrund-Job auf dem
  // Server, siehe app/api/pipeline.py:_automatik_lauf), das Polling zeigt
  // nur den jeweils aktuellen Stand an.
  useEffect(() => {
    let abgebrochen = false;
    automatikLiefZuvorRef.current = false;
    automatikVerlaufLaden();
    function laden() {
      api
        .automatikStatus(ordner)
        .then((status) => {
          if (abgebrochen) return;
          setAutomatikStatus(status);
          // Sobald ein Lauf zu Ende geht (egal ob abgeschlossen, mit
          // Fehler oder gestoppt), ist ein neuer Eintrag in der
          // Verlaufsdatei dazugekommen (siehe app/core/automatik.py:
          // verlauf_eintrag_anhaengen) - genau dann neu laden statt bei
          // jedem 4-Sekunden-Tick.
          if (automatikLiefZuvorRef.current && !status.laeuft) automatikVerlaufLaden();
          automatikLiefZuvorRef.current = status.laeuft;

          // Spiegelt den Automatikmodus-Fortschritt in die globale
          // Fusszeile (StatusFooter) - sonst zeigt die immer "Bereit",
          // waehrend im Hintergrund ein stundenlanger Lauf werkelt. Nur bei
          // TEXT-Aenderung neu "starten()" (das setzt die Sekunden-Uhr in
          // der Fusszeile auf 0 zurueck) statt bei jedem 4-Sekunden-Tick,
          // damit man sieht, wie lange der aktuelle Schritt schon laeuft.
          if (status.laeuft) {
            const text = automatikAktionsText(status);
            if (automatikAktivitaetTextRef.current !== text) {
              automatikAktivitaetTextRef.current = text;
              aktivitaetStarten(text);
            }
          } else if (automatikAktivitaetTextRef.current !== null) {
            automatikAktivitaetTextRef.current = null;
            aktivitaetBeenden();
          }
        })
        .catch(() => {});
    }
    laden();
    const intervall = setInterval(laden, 4000);
    return () => {
      abgebrochen = true;
      clearInterval(intervall);
    };
  }, [ordner]);

  async function automatikStarten(fortsetzen = false) {
    setAutomatikFehler(null);
    try {
      await api.automatikStarten(ordner, automatikMaxDurchlaeufe, sshZielId || null, fortsetzen);
      setAutomatikStatus(await api.automatikStatus(ordner));
    } catch (e) {
      setAutomatikFehler(e instanceof Error ? e.message : String(e));
    }
  }

  async function automatikStoppen() {
    await api.automatikStoppen(ordner);
    setAutomatikStatus(await api.automatikStatus(ordner));
  }

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
    // Direkt nach erfolgreichem Abschluss zeigt "starten()" bereits den
    // frisch geschriebenen Text an, und die Kapitelnummer wurde automatisch
    // auf das naechste (noch nicht existierende) Kapitel hochgezaehlt (siehe
    // "abgeschlossen"-Handler unten). Ohne diese Absicherung wuerde dieser
    // Effekt feuern, sehen dass das NEUE n noch keine Datei hat, und den
    // gerade erst angezeigten, bereits gespeicherten Text wieder leeren -
    // wirkte wie "Kapiteltext verschwindet nach dem Schreiben", obwohl
    // kapitel_NN.md korrekt auf der Platte liegt. Bewusst KEIN einmaliges
    // Verbrauchen des Flags (z.B. per Reset auf false direkt hier): der
    // Effekt haengt auch an "projekt", das durch onKapitelGeschrieben() erst
    // ASYNCHRON (verzoegert, nach diesem ersten Durchlauf) aktualisiert wird
    // und den Effekt dadurch ein zweites Mal feuert - der Vergleich gegen n
    // bleibt deshalb so lange gueltig, bis der Nutzer die Nummer tatsaechlich
    // manuell auf einen anderen Wert aendert.
    if (autoVorgeschlageneNummerRef.current === n) {
      return;
    }
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
    phaseRef.current = "autor";
    setModell(null);

    const socket = new WebSocket(schreibenWebSocketUrl(ordner, n, zusatzhinweis, sshZielId || null));
    socketRef.current = socket;

    aktivitaetStarten(`Schreibt Kapitel ${n}...`);

    socket.onmessage = (ereignis) => {
      const nachricht: SchreibenNachricht = JSON.parse(ereignis.data);
      setPhase(nachricht.phase);
      phaseRef.current = nachricht.phase;
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
        aktivitaetStarten(`Prüft Kapitel ${n} auf Anachronismen, Stimmigkeit, Kontinuität & Lektorat...`);
      }
      if (nachricht.phase === "pruefen" && nachricht.typ === "done") {
        setBefunde(nachricht.befunde);
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
        autoVorgeschlageneNummerRef.current = n + 1;
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
      // Verbindung ist weg, OHNE dass "abgeschlossen" oder "fehler" das schon
      // erklaert hat - z.B. ein Netzwerk-/Tunnel-Aussetzer mitten in der
      // Generierung (haeufigste bekannte Ursache: instabile Strecke zum
      // entfernten KI-Ziel). Ohne diese Behandlung wirkte das wie
      // "Kapiteltext verschwindet nach dem Schreiben": der Reload-Effekt
      // sah beim naechsten Durchlauf (laeuft wird false), dass fuer dieses
      // Kapitel noch keine Datei existiert (sie wurde ja nie fertig und nie
      // gespeichert), und leerte den bereits generierten Text kommentarlos.
      if (phaseRef.current !== "abgeschlossen" && phaseRef.current !== "fehler") {
        setFehler(
          "Verbindung während des Schreibens unerwartet verloren (z.B. Netzwerk-/Tunnel-Aussetzer zum KI-Ziel). " +
            "Das Kapitel wurde NICHT gespeichert. Der bisher generierte Text bleibt unten sichtbar - einfach erneut versuchen.",
        );
        // Verhindert, dass der separate "Lade gespeichertes Kapitel"-Effekt
        // (reagiert auf laeuft-Wechsel) den gerade sichtbaren, unvollstaendigen
        // Text sofort wieder loescht, nur weil kapitel_NN.md nie geschrieben
        // wurde.
        autoVorgeschlageneNummerRef.current = n;
      }
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
            placeholder="z.B. bei starken Kontinuitäts-Brüchen im letzten Versuch..."
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
            <CardTitle>Befunde der Prüfer (Anachronismen, Stimmigkeit &amp; Kontinuität)</CardTitle>
            <BefundListe befunde={befunde.befunde} />
          </Card>
        )}
      </div>

      <Card className="lg:col-span-2">
        <CardTitle>🤖 Automatikmodus</CardTitle>
        <p className="mb-3 text-xs text-text-muted">
          Schreibt alle noch fehlenden Kapitel am Stück und wendet danach für jedes Kapitel automatisch alle
          eindeutigen Prüfer-Korrekturen an. Widersprüchliche Vorschläge und nicht auffindbare Stellen werden
          übersprungen und bleiben wie gewohnt im Tab "Prüfen &amp; Anwenden" zur manuellen Entscheidung.
          Rechtschreibung (hunspell) läuft mit, unbekannte Wörter landen nur im Protokoll (keine automatische
          Ersetzung). Läuft im Hintergrund weiter, auch wenn du diesen Tab schließt oder den Browser zumachst.
        </p>

        {automatikStatus?.laeuft ? (
          <div className="space-y-3">
            <p className="text-sm text-text">
              Phase: <strong>{automatikStatus.phase}</strong>
              {automatikStatus.aktuelles_kapitel != null && (
                <>
                  {" "}
                  · Kapitel {automatikStatus.aktuelles_kapitel}
                  {automatikStatus.gesamt_kapitel != null && <>/{automatikStatus.gesamt_kapitel}</>}
                </>
              )}
              {automatikStatus.aktueller_durchlauf != null && <> · Durchlauf {automatikStatus.aktueller_durchlauf}</>}
            </p>
            <div className="max-h-40 overflow-auto rounded-lg bg-bg p-2 font-mono text-xs text-text-muted">
              {automatikStatus.log.length === 0 ? (
                <p>Startet...</p>
              ) : (
                automatikStatus.log.slice(-20).map((zeile, i) => <div key={i}>{zeile}</div>)
              )}
            </div>
            <Button variant="danger" onClick={automatikStoppen}>
              Stoppen
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {automatikStatus?.fortsetzbar && (
              <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3">
                <p className="text-sm text-text">
                  Letzter Lauf wurde unterbrochen bei: <strong>Kapitel {automatikStatus.aktuelles_kapitel}</strong>
                  {automatikStatus.gesamt_kapitel != null && <>/{automatikStatus.gesamt_kapitel}</>}
                  {", "}Phase <strong>{automatikStatus.phase}</strong>
                  {automatikStatus.aktueller_durchlauf != null && (
                    <>
                      {" "}
                      · Durchlauf <strong>{automatikStatus.aktueller_durchlauf}</strong>
                    </>
                  )}
                  {automatikStatus.gestartet_am && <> (gestartet {automatikStatus.gestartet_am})</>}.
                </p>
                <Button className="mt-2" onClick={() => automatikStarten(true)}>
                  Fortsetzen
                </Button>
              </div>
            )}
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <Label>Max. Durchläufe je Kapitel</Label>
                <Input
                  type="number"
                  min={1}
                  max={10}
                  value={automatikMaxDurchlaeufe}
                  onChange={(e) => setAutomatikMaxDurchlaeufe(Number(e.target.value))}
                  className="w-24"
                />
              </div>
              <Button variant={automatikStatus?.fortsetzbar ? "secondary" : "primary"} onClick={() => automatikStarten(false)}>
                Automatikmodus starten
              </Button>
            </div>
          </div>
        )}

        {automatikFehler && <p className="mt-2 text-sm text-red-400">{automatikFehler}</p>}
        {automatikStatus?.fehler && (
          <p className="mt-2 text-sm text-red-400">Fehler im letzten Lauf: {automatikStatus.fehler}</p>
        )}

        {!automatikStatus?.laeuft && automatikStatus?.abgeschlossen && (
          <details className="mt-3 text-xs text-text-muted">
            <summary className="cursor-pointer text-text">
              Protokoll des letzten Laufs ({automatikStatus.protokoll.length} Einträge)
            </summary>
            <ul className="mt-2 max-h-64 space-y-1 overflow-auto">
              {automatikStatus.protokoll.map((eintrag, i) => (
                <li key={i}>
                  Kapitel {eintrag.kapitel}:{" "}
                  {eintrag.art === "angewendet"
                    ? "✅ angewendet"
                    : eintrag.art === "rechtschreibung"
                      ? `📝 ${eintrag.unbekannte_woerter?.length ?? 0} unbekannte(s) Wort/Wörter`
                      : `⏭️ übersprungen (${eintrag.grund})`}
                  {eintrag.fundstelle && <> – „{eintrag.fundstelle}“</>}
                </li>
              ))}
            </ul>
            <p className="mt-2">Reste findest du wie gewohnt im Tab "Prüfen &amp; Anwenden".</p>
          </details>
        )}

        {automatikVerlauf.length > 0 && (
          <details className="mt-3 text-xs text-text-muted">
            <summary className="cursor-pointer text-text">Lauf-Historie ({automatikVerlauf.length})</summary>
            <ul className="mt-2 max-h-64 space-y-1 overflow-auto">
              {[...automatikVerlauf].reverse().map((eintrag, i) => (
                <li key={i}>
                  {eintrag.datum}: {eintrag.von.slice(11)}–{eintrag.bis.slice(11)} Uhr (
                  {formatDauer(eintrag.dauer_sekunden)}) ·{" "}
                  {eintrag.status === "abgeschlossen"
                    ? "✅ abgeschlossen"
                    : eintrag.status === "fehler"
                      ? "❌ Fehler"
                      : "⏹️ gestoppt"}
                  {eintrag.fortgesetzt && " (Fortsetzung)"}
                  {eintrag.fehler && <> – {eintrag.fehler}</>}
                </li>
              ))}
            </ul>
          </details>
        )}
      </Card>
    </div>
  );
}
