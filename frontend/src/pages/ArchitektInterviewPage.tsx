import { useEffect, useRef, useState } from "react";
import { api, architektWebSocketUrl } from "../api/client";
import type { ArchitektNachricht } from "../api/types";
import { Button, Card } from "../components/ui";
import { useAktivitaet } from "../context/AktivitaetContext";
import { alsDateiHerunterladen } from "../utils/download";

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

/** Wandelt einen rohen Backend-Verlauf ("Ich: ..."/"Du: ..."-Zeilen) in
 * Chat-Eintraege um - gemeinsam genutzt fuer "fortgesetzt" (Verlauf endet
 * immer mit der noch offenen Frage, siehe backend/app/api/architekt.py)
 * und "zurueckgesetzt" (Verlauf endet stattdessen mit der gerade bearbeiteten
 * eigenen Antwort, die naechste Frage kommt erst noch per "frage"/"fertig") -
 * die Aufrufer schneiden den jeweils passenden Rand vorher selbst zu. */
function verlaufZuChat(verlauf: string[]): ChatEintrag[] {
  return verlauf.map((zeile): ChatEintrag => {
    if (zeile.startsWith("Ich: ")) return { rolle: "ich", text: zeile.slice("Ich: ".length) };
    if (zeile.startsWith("Du: ")) return { rolle: "architekt", text: zeile.slice("Du: ".length) };
    return { rolle: "architekt", text: zeile };
  });
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
  const [pausiert, setPausiert] = useState(false);
  const [fortsetzbar, setFortsetzbar] = useState(false);
  // Offline ausgefuelltes Vorlage-Dokument (siehe backend architekt-vorlage/
  // ArchitektInterviewPage-Kommentar zu starten()) - nur vor einem frischen
  // Start relevant, macht beim Fortsetzen eines gespeicherten Gespraechs
  // keinen Sinn (das laeuft laengst am importierten Kontext entlang weiter).
  const [vorlageZeigen, setVorlageZeigen] = useState(false);
  const [vorlageText, setVorlageText] = useState("");
  const [ladenVorlage, setLadenVorlage] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [verbindungVerloren, setVerbindungVerloren] = useState(false);
  // Index (in `nachrichten`) der eigenen Antwort, die gerade bearbeitet
  // wird - null ausserhalb des Bearbeiten-Modus. Ermoeglicht "Schritte
  // zurueckgehen": eine frühere eigene Antwort korrigieren oder um eine neue
  // Idee erweitern, wodurch alle seither gestellten Fragen/Antworten
  // verworfen werden und der Architekt ab dort neu weiterfragt.
  const [bearbeiteIndex, setBearbeiteIndex] = useState<number | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const chatEndeRef = useRef<HTMLDivElement>(null);
  // true, sobald das Gespraech ueber eine reguläre Nachricht (abgeschlossen,
  // beendet_ohne_speichern, fehler) oder bewusst per "Spaeter fortsetzen"
  // beendet wurde - unterscheidet im onclose-Handler ein erwartetes Ende von
  // einem unerwarteten Verbindungsabbruch (z.B. Server-Neustart waehrend der
  // Architekt noch ueberlegt), bei dem sonst "Architekt denkt nach..." ewig
  // stehen bliebe, ohne dass sichtbar waere, dass gar nichts mehr laeuft.
  const kontrolliertBeendetRef = useRef(false);
  const { starten: aktivitaetStarten, beenden: aktivitaetBeenden } = useAktivitaet();

  useEffect(() => {
    chatEndeRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [nachrichten, wartetAufAntwort]);

  useEffect(() => () => socketRef.current?.close(), []);

  // Zeigt auf dem Start-Bildschirm an, ob es fuer dieses Projekt bereits ein
  // zwischengespeichertes, noch nicht abgeschlossenes Interview gibt (siehe
  // backend/app/api/architekt.py: architekt_verlauf.json).
  useEffect(() => {
    api
      .architektFortsetzbar(ordner)
      .then((antwort) => setFortsetzbar(antwort.fortsetzbar))
      .catch(() => setFortsetzbar(false));
  }, [ordner]);

  function starten() {
    setGestartet(true);
    setNachrichten([]);
    setFehler(null);
    setAbgeschlossen(false);
    setBeendetOhneSpeichern(false);
    setPausiert(false);
    setVerbindungVerloren(false);
    setWartetAufAntwort(true);
    kontrolliertBeendetRef.current = false;

    const socket = new WebSocket(architektWebSocketUrl(ordner, sshZielId || null));
    socketRef.current = socket;

    aktivitaetStarten("Architekt denkt nach...");

    socket.onopen = () => {
      // Bei einem frischen Start wartet das Backend absichtlich auf diese
      // Initialnachricht (siehe backend/app/api/architekt.py:ws_architekt),
      // um optional ein offline ausgefuelltes Vorlage-Dokument entgegen-
      // zunehmen. Beim Fortsetzen eines gespeicherten Gespraechs erwartet
      // das Backend dagegen KEINE Initialnachricht - die naechste vom
      // Server erwartete Nachricht ist dort direkt die Antwort auf die
      // letzte offene Frage.
      if (!fortsetzbar) {
        socket.send(JSON.stringify({ vorlage_text: vorlageText.trim() || null }));
      }
    };

    socket.onmessage = (ereignis) => {
      const nachricht: ArchitektNachricht = JSON.parse(ereignis.data);
      if (nachricht.phase === "fortgesetzt") {
        // Erster ("Ich: Lass uns anfangen...") und letzter Eintrag
        // (die gerade noch offene Frage) werden ausgelassen - Ersterer wird
        // auch beim frischen Start nie als eigene Chat-Blase gezeigt,
        // Letzterer kommt gleich danach ganz normal per "frage"/"fertig".
        setNachrichten(verlaufZuChat(nachricht.verlauf.slice(1, -1)));
      }
      if (nachricht.phase === "zurueckgesetzt") {
        // Antwort auf eine "bearbeite_ab"-Anfrage (siehe senden()):
        // der Verlauf endet hier mit der gerade bearbeiteten eigenen
        // Antwort, NICHT mit einer offenen Frage - nur den synthetischen
        // ersten Eintrag abschneiden, den Rest komplett uebernehmen. Die
        // naechste Frage kommt gleich danach ganz normal per "frage"/"fertig".
        setNachrichten(verlaufZuChat(nachricht.verlauf.slice(1)));
        setBearbeiteIndex(null);
      }
      if (nachricht.phase === "frage" && nachricht.typ === "start") {
        setWartetAufAntwort(true);
        setDenktNach(false);
        aktivitaetStarten("Architekt denkt nach...");
      }
      if (nachricht.phase === "frage" && nachricht.typ === "denkt_nach") {
        setDenktNach(true);
      }
      if (nachricht.phase === "frage" && nachricht.typ === "fertig") {
        setDenktNach(false);
        setWartetAufAntwort(false);
        setNachrichten((bisher) => [...bisher, { rolle: "architekt", text: nachricht.text }]);
        aktivitaetBeenden();
      }
      if (nachricht.phase === "abgeschlossen") {
        kontrolliertBeendetRef.current = true;
        setAbgeschlossen(true);
        setWartetAufAntwort(false);
        aktivitaetBeenden();
        onAbgeschlossen(nachricht.neuer_ordner);
      }
      if (nachricht.phase === "beendet_ohne_speichern") {
        kontrolliertBeendetRef.current = true;
        setBeendetOhneSpeichern(true);
        setWartetAufAntwort(false);
        aktivitaetBeenden();
      }
      if (nachricht.phase === "fehler") {
        kontrolliertBeendetRef.current = true;
        setFehler(nachricht.text);
        setWartetAufAntwort(false);
        aktivitaetBeenden();
      }
    };
    socket.onerror = () => {
      setFehler("WebSocket-Verbindung fehlgeschlagen.");
      setWartetAufAntwort(false);
      aktivitaetBeenden();
    };
    socket.onclose = () => {
      // Verbindung ist weg, OHNE dass eine der obigen Nachrichten (oder
      // "Spaeter fortsetzen") das schon erklaert hat - z.B. weil der Server
      // mitten im Gespraech neu gestartet wurde, waehrend der Architekt noch
      // ueberlegt hat. Ohne diesen Fall wuerde "Architekt denkt nach..." ewig
      // stehen bleiben, obwohl laengst nichts mehr laeuft.
      if (!kontrolliertBeendetRef.current) {
        setVerbindungVerloren(true);
        setWartetAufAntwort(false);
        setDenktNach(false);
        aktivitaetBeenden();
      }
    };
  }

  function senden() {
    const text = eingabe.trim();
    if (!text || !socketRef.current || wartetAufAntwort) return;
    if (bearbeiteIndex !== null) {
      // Optimistisch schon hier auf den Stand vor der bearbeiteten Antwort
      // kuerzen und die neue Antwort anhaengen - fuehlt sich sofort
      // reaktionsschnell an. Die serverseitige "zurueckgesetzt"-Antwort
      // bestaetigt denselben Zustand gleich danach (siehe socket.onmessage).
      const index = bearbeiteIndex;
      setNachrichten((bisher) => [...bisher.slice(0, index), { rolle: "ich", text }]);
      socketRef.current.send(JSON.stringify({ eingabe: text, bearbeite_ab: bearbeiteIndex }));
    } else {
      setNachrichten((bisher) => [...bisher, { rolle: "ich", text }]);
      socketRef.current.send(JSON.stringify({ eingabe: text }));
    }
    setEingabe("");
    setWartetAufAntwort(true);
    aktivitaetStarten("Architekt denkt nach...");
  }

  /** Startet den Bearbeiten-Modus fuer eine frühere eigene Antwort (Klick auf
   * "Bearbeiten" an einer "ich"-Chat-Blase) - laedt ihren Text ins Eingabefeld,
   * `senden()` schickt ihn beim naechsten Absenden als Korrektur statt als
   * neue Antwort auf die aktuell offene Frage. */
  function bearbeiten(index: number) {
    if (wartetAufAntwort || abgeschlossen || beendetOhneSpeichern || pausiert || verbindungVerloren) return;
    const eintrag = nachrichten[index];
    if (!eintrag || eintrag.rolle !== "ich") return;
    setBearbeiteIndex(index);
    setEingabe(eintrag.text);
  }

  async function vorlageHerunterladen() {
    setLadenVorlage(true);
    try {
      const antwort = await api.architektVorlage(ordner);
      alsDateiHerunterladen("architekt-vorlage.md", antwort.vorlage);
    } finally {
      setLadenVorlage(false);
    }
  }

  function vorlageDateiGewaehlt(datei: File) {
    const reader = new FileReader();
    reader.onload = () => setVorlageText(String(reader.result ?? ""));
    reader.readAsText(datei);
  }

  function bearbeitenAbbrechen() {
    setBearbeiteIndex(null);
    setEingabe("");
  }

  function beenden() {
    socketRef.current?.send(JSON.stringify({ eingabe: "ende" }));
  }

  function spaeterFortsetzen() {
    // Kein "ende" senden - der zuletzt gespeicherte Verlauf (siehe Backend)
    // bleibt dadurch als Zwischenstand erhalten und wird beim naechsten
    // Verbindungsaufbau zu diesem Projekt automatisch fortgesetzt.
    kontrolliertBeendetRef.current = true;
    socketRef.current?.close();
    setPausiert(true);
    setWartetAufAntwort(false);
    aktivitaetBeenden();
  }

  const kannAntworten =
    !wartetAufAntwort && !abgeschlossen && !beendetOhneSpeichern && !pausiert && !verbindungVerloren;
  const letzteNachricht = nachrichten.at(-1);
  // Waehrend eine frühere Antwort bearbeitet wird, gehoeren die Schnellwahl-
  // Optionen der aktuell noch offenen (aber gleich verworfenen) Frage nicht
  // hierher - sie wuerden sonst das Bearbeiten-Feld ueberschreiben.
  const optionen =
    kannAntworten && bearbeiteIndex === null && letzteNachricht?.rolle === "architekt"
      ? optionenErkennen(letzteNachricht.text)
      : [];

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
          {fortsetzbar && (
            <p className="mb-4 text-sm text-accent-light">
              Es gibt ein zwischengespeichertes, noch nicht abgeschlossenes Interview für dieses Projekt.
            </p>
          )}
          {!fortsetzbar && (
            <div className="mb-4 text-left">
              <button
                type="button"
                onClick={() => setVorlageZeigen((v) => !v)}
                className="mb-2 text-xs text-accent-light hover:underline"
              >
                {vorlageZeigen ? "▾" : "▸"} Vorlage offline ausfüllen (optional)
              </button>
              {vorlageZeigen && (
                <div className="rounded-lg border border-border bg-bg p-3">
                  <p className="mb-2 text-xs text-text-muted">
                    Lade eine Vorlage herunter, fülle sie in Ruhe offline aus und füge den Text unten
                    ein - der Architekt fragt dann nur noch nach dem, was fehlt oder unklar ist, statt
                    den kompletten Fragenkatalog von vorne abzuarbeiten.
                  </p>
                  <div className="mb-2 flex flex-wrap gap-2">
                    <Button variant="secondary" onClick={vorlageHerunterladen} disabled={ladenVorlage}>
                      {ladenVorlage ? "Lädt..." : "⬇️ Vorlage herunterladen"}
                    </Button>
                    <label className="flex cursor-pointer items-center rounded-lg border border-border bg-surface-hover px-3 py-1.5 text-sm text-text hover:border-accent">
                      📄 Datei wählen...
                      <input
                        type="file"
                        accept=".md,.txt"
                        className="hidden"
                        onChange={(e) => {
                          const datei = e.target.files?.[0];
                          if (datei) vorlageDateiGewaehlt(datei);
                          e.target.value = "";
                        }}
                      />
                    </label>
                  </div>
                  <textarea
                    value={vorlageText}
                    onChange={(e) => setVorlageText(e.target.value)}
                    rows={6}
                    className="w-full resize-none rounded-lg border border-border bg-bg px-3 py-2 text-xs text-text outline-none transition-colors focus:border-accent"
                    placeholder="...oder den ausgefüllten Text hier einfügen."
                  />
                </div>
              )}
            </div>
          )}
          <Button onClick={starten}>
            {fortsetzbar
              ? "Interview fortsetzen"
              : vorlageText.trim()
                ? "Interview mit Vorlage starten"
                : "Interview starten"}
          </Button>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-8.5rem)] max-w-3xl flex-col gap-4 p-6">
      <Card className="flex-1 overflow-y-auto">
        <div className="space-y-4">
          {nachrichten.map((eintrag, i) => (
            <div
              key={i}
              className={`group flex items-start gap-1.5 ${eintrag.rolle === "ich" ? "justify-end" : "justify-start"}`}
            >
              {eintrag.rolle === "ich" && kannAntworten && bearbeiteIndex === null && (
                <button
                  onClick={() => bearbeiten(i)}
                  title="Diese Antwort bearbeiten und Interview ab hier neu fortsetzen"
                  className="mt-2.5 shrink-0 text-xs text-text-muted opacity-0 transition-opacity hover:text-accent-light group-hover:opacity-100"
                >
                  ✏️
                </button>
              )}
              <div
                className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm ${
                  eintrag.rolle === "ich"
                    ? `bg-accent-soft text-accent-light ${i === bearbeiteIndex ? "ring-2 ring-accent" : ""}`
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
          {pausiert && (
            <div className="rounded-lg border border-accent-soft bg-accent-soft/40 px-4 py-3 text-sm text-accent-light">
              <p className="mb-2">Fortschritt zwischengespeichert.</p>
              <Button onClick={starten}>Interview fortsetzen</Button>
            </div>
          )}
          {verbindungVerloren && (
            <div className="rounded-lg border border-amber-400/40 bg-amber-400/10 px-4 py-3 text-sm text-amber-300">
              <p className="mb-2">
                ⚠️ Verbindung verloren, während der Architekt noch überlegt hat (z. B. weil der Server
                zwischendurch neu gestartet wurde). Dein Fortschritt bis zur letzten Antwort ist gespeichert.
              </p>
              <Button onClick={starten}>Erneut verbinden</Button>
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

      {!abgeschlossen && !beendetOhneSpeichern && !pausiert && !verbindungVerloren && (
        <div className="flex flex-col gap-2">
          {bearbeiteIndex !== null && (
            <div className="flex items-center justify-between rounded-lg border border-accent-soft bg-accent-soft/20 px-3 py-1.5 text-xs text-accent-light">
              <span>✏️ Antwort wird bearbeitet – alle danach gestellten Fragen werden verworfen.</span>
              <button onClick={bearbeitenAbbrechen} className="ml-2 shrink-0 underline hover:no-underline">
                Abbrechen
              </button>
            </div>
          )}
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
                if (e.key === "Escape" && bearbeiteIndex !== null) {
                  bearbeitenAbbrechen();
                }
              }}
              placeholder="Deine Antwort... (Enter zum Senden, Umschalt+Enter für neue Zeile)"
              disabled={wartetAufAntwort}
            />
            <div className="flex flex-col gap-2">
              <Button onClick={senden} disabled={wartetAufAntwort || !eingabe.trim()}>
                {bearbeiteIndex !== null ? "Antwort ändern" : "Senden"}
              </Button>
              <Button onClick={spaeterFortsetzen} variant="secondary" disabled={wartetAufAntwort}>
                Später fortsetzen
              </Button>
              <Button onClick={beenden} variant="secondary" disabled={wartetAufAntwort}>
                Beenden
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
