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
import { CollapsibleCard } from "../components/CollapsibleCard";
import { FindingsList } from "../components/FindingsList";
import { Button, Card, CardTitle, Input, Label } from "../components/ui";
import { useAktivitaet } from "../context/AktivitaetContext";
import { hatReste, resteZusammenfassen } from "../utils/automatik";
import { alsDateiHerunterladen } from "../utils/download";

interface SchreibenPageProps {
  ordner: string;
  projekt: ProjektDetail | null;
  sshZielId: string;
  onKapitelGeschrieben: () => void;
}

// Grund-Codes aus app/core/automatik.py:befunde_anwenden() - lesbare Texte
// statt der rohen Codes in der Zusammenfassung/Protokollliste.
const GRUND_LABEL: Record<string, string> = {
  kein_vorschlag: "kein Korrekturvorschlag (unsicher)",
  konflikt: "widersprüchliche Vorschläge zweier Prüfer",
  nicht_gefunden: "Textstelle nicht mehr auffindbar",
  verdaechtiger_vorschlag: "verdächtiger Vorschlag verworfen",
};

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
  // "Frage zur Geschichte" (siehe fragen() unten) - rein informationell,
  // NICHT zu verwechseln mit "zusatzhinweis" oben, das Wuensche fuer das
  // naechste geschriebene Kapitel entgegennimmt. Nur session-lokal, keine
  // Persistenz noetig - eine kurze Nachschlage-Historie fuer diesen Besuch.
  const [frage, setFrage] = useState("");
  const [frageVerlauf, setFrageVerlauf] = useState<{ frage: string; antwort: string }[]>([]);
  const [ladenFrage, setLadenFrage] = useState(false);
  const [frageFehler, setFrageFehler] = useState<string | null>(null);
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

  async function fragen() {
    const text = frage.trim();
    if (!text) return;
    setLadenFrage(true);
    setFrageFehler(null);
    try {
      const antwort = await api.storyFrage(ordner, text, sshZielId || null);
      setFrageVerlauf((bisher) => [...bisher, { frage: text, antwort: antwort.antwort }]);
      setFrage("");
    } catch (e) {
      setFrageFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLadenFrage(false);
    }
  }

  function abbrechen() {
    socketRef.current?.close();
    setLaeuft(false);
    aktivitaetBeenden();
  }

  const zielWoerter = projekt?.kapitelplan[n];

  return (
    <div className="grid grid-cols-1 gap-6 p-6 lg:grid-cols-[1fr_2fr]">
      <div className="space-y-4">
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

        <Card className="h-fit space-y-3">
          <CardTitle>❓ Frage zur Geschichte</CardTitle>
          <p className="text-xs text-text-muted">
            Frag zwischendurch etwas zum bisherigen Verlauf (z.B. Namen, Details) - wird aus Gerüst und
            aktuellem Stand beantwortet, ohne die Geschichte fortzuschreiben. Für Wünsche ans nächste Kapitel
            nutze stattdessen den "Zusätzlichen Hinweis" oben.
          </p>
          {frageVerlauf.length > 0 && (
            <div className="max-h-56 space-y-2 overflow-auto rounded-lg bg-bg p-2 text-sm">
              {frageVerlauf.map((eintrag, i) => (
                <div key={i} className="space-y-0.5">
                  <p className="text-text-muted">❓ {eintrag.frage}</p>
                  <p className="text-text">{eintrag.antwort}</p>
                </div>
              ))}
            </div>
          )}
          <div className="flex gap-2">
            <textarea
              className="flex-1 resize-none rounded-lg border border-border bg-bg px-3 py-1.5 text-sm text-text outline-none transition-colors focus:border-accent"
              rows={2}
              value={frage}
              onChange={(e) => setFrage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  fragen();
                }
              }}
              placeholder="z.B. Wie hieß die Nebenfigur aus Kapitel 2 nochmal?"
              disabled={ladenFrage}
            />
            <Button onClick={fragen} disabled={ladenFrage || !frage.trim()}>
              {ladenFrage ? "..." : "Fragen"}
            </Button>
          </div>
          {frageFehler && <p className="text-sm text-red-400">{frageFehler}</p>}
        </Card>
      </div>

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
              <div className="flex flex-wrap items-center gap-3">
                <Button onClick={() => automatikStarten(true)}>Fortsetzen</Button>
                {automatikStatus.fehler_schritt && (
                  <p className="text-sm text-text-muted">
                    {automatikStatus.fehler_schritt.fehler_nummer ?? "Fehler"}: versuchter Schritt war: Kapitel{" "}
                    {automatikStatus.fehler_schritt.kapitel}, Phase {automatikStatus.fehler_schritt.phase}
                    {automatikStatus.fehler_schritt.durchlauf != null && (
                      <>, Durchlauf {automatikStatus.fehler_schritt.durchlauf}</>
                    )}
                  </p>
                )}
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

        {!automatikStatus?.laeuft && automatikStatus != null && automatikStatus.protokoll.length > 0 && (() => {
          const reste = hatReste(automatikStatus.protokoll);
          const zusammenfassung = resteZusammenfassen(automatikStatus.protokoll);
          const uebersprungenGesamt = zusammenfassung.gesamt - zusammenfassung.angewendet;
          return (
            <>
              {reste && !automatikStatus.abgeschlossen && (
                <div className="mt-3 rounded-lg border border-amber-400/40 bg-amber-400/10 px-4 py-3 text-sm text-amber-300">
                  ⏸️ Automatikmodus angehalten: ungelöste Prüfer-Funde seit Laufbeginn vorhanden. Im Tab "Prüfen
                  &amp; Anwenden" durchsehen, bevor du mit "Fortsetzen" weitermachst - sonst häufen sich ungelöste
                  Kontinuitätsprobleme über weitere Kapitel hinweg an.
                </div>
              )}
              <CollapsibleCard
                title={`Protokoll des letzten Laufs (${zusammenfassung.angewendet}/${zusammenfassung.gesamt} angewendet${
                  uebersprungenGesamt > 0 ? `, ${uebersprungenGesamt} übersprungen` : ""
                })`}
                defaultOffen={reste}
                className="mt-3"
              >
                <div className="space-y-2 p-4 text-xs text-text-muted">
                  {uebersprungenGesamt > 0 && (
                    <p>
                      {uebersprungenGesamt} von {zusammenfassung.gesamt} Korrekturvorschlägen übersprungen:{" "}
                      {Object.entries(zusammenfassung.uebersprungenNachGrund)
                        .map(([grund, anzahl]) => `${anzahl}× ${GRUND_LABEL[grund] ?? grund}`)
                        .join(", ")}
                      .
                    </p>
                  )}
                  {zusammenfassung.unbekannteWoerter > 0 && (
                    <p>{zusammenfassung.unbekannteWoerter} unbekannte(s) Wort/Wörter (Rechtschreibung, hunspell).</p>
                  )}
                  <ul className="max-h-64 space-y-1 overflow-auto">
                    {automatikStatus.protokoll.map((eintrag, i) => (
                      <li key={i}>
                        Kapitel {eintrag.kapitel}:{" "}
                        {eintrag.art === "angewendet"
                          ? "✅ angewendet"
                          : eintrag.art === "rechtschreibung"
                            ? `📝 ${eintrag.unbekannte_woerter?.length ?? 0} unbekannte(s) Wort/Wörter`
                            : `⏭️ übersprungen (${GRUND_LABEL[eintrag.grund ?? ""] ?? eintrag.grund})`}
                        {eintrag.fundstelle && <> – „{eintrag.fundstelle}“</>}
                      </li>
                    ))}
                  </ul>
                  <p>
                    Reste findest du wie gewohnt im Tab "Prüfen &amp; Anwenden"
                    {reste && !automatikStatus.resten_bestaetigt && (
                      <> - dort auch der Button "Prüfung abschließen".</>
                    )}
                  </p>
                  {reste && automatikStatus.resten_bestaetigt && (
                    <p className="text-accent-light">✅ Prüfung als abgeschlossen bestätigt.</p>
                  )}
                </div>
              </CollapsibleCard>
            </>
          );
        })()}

        {automatikVerlauf.length > 0 && (
          <CollapsibleCard title={`Lauf-Historie (${automatikVerlauf.length})`} defaultOffen={false} className="mt-3">
            <ul className="max-h-64 space-y-1 overflow-auto p-4 text-xs text-text-muted">
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
          </CollapsibleCard>
        )}
      </Card>
    </div>
  );
}
