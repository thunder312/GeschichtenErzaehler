import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { AnalysatorStatus, EpocheKurz } from "../api/types";
import { EpocheFormular, epocheFormularGueltig, type EpocheFormularWerte } from "../components/EpocheFormular";
import { Button, Card, CardTitle, Input, Label, Select, Textarea } from "../components/ui";

interface AnalysatorPageProps {
  epochen: EpocheKurz[];
  sshZielId: string;
  onProjektErzeugt: (ordner: string) => void;
  onEpochenGeaendert: () => void;
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
export function AnalysatorPage({ epochen, sshZielId, onProjektErzeugt, onEpochenGeaendert }: AnalysatorPageProps) {
  const [titel, setTitel] = useState("");
  const [epoche, setEpoche] = useState("");
  const [zweiteEpoche, setZweiteEpoche] = useState("");
  const [text, setText] = useState("");
  const [wirdGestartet, setWirdGestartet] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [ordner, setOrdner] = useState<string | null>(null);
  const [status, setStatus] = useState<AnalysatorStatus | null>(null);
  const dateiInputRef = useRef<HTMLInputElement>(null);

  // Alternative zur bestehenden Epoche (siehe ToDo.md "erweitere den
  // Analysator"): die KI schlägt aus dem importierten Text ein neues
  // Epoche-/Setting-Profil vor (app/api/analysator.py:
  // analysator_epoche_vorschlagen), das der Nutzer hier noch bearbeitet.
  // Speichern (POST /api/epochen, bereits bestehender Endpunkt) ist
  // bewusst ein EIGENER Schritt, unabhängig vom Start der Analyse - die
  // Epoche landet in der zentralen Bibliothek und ist damit auch für
  // andere/spätere Projekte nutzbar, nicht nur für diesen einen Import.
  const [epocheModus, setEpocheModus] = useState<"bestehend" | "ableiten">("bestehend");
  const [epocheEntwurf, setEpocheEntwurf] = useState<EpocheFormularWerte | null>(null);
  const [wirdEpocheVorgeschlagen, setWirdEpocheVorgeschlagen] = useState(false);
  const [epocheVorschlagFehler, setEpocheVorschlagFehler] = useState<string | null>(null);
  const [epocheGespeichert, setEpocheGespeichert] = useState<{ name: string; ordner: string } | null>(null);
  const [wirdEpocheGespeichert, setWirdEpocheGespeichert] = useState(false);
  const [epocheSpeichernFehler, setEpocheSpeichernFehler] = useState<string | null>(null);

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

  async function epocheVorschlagen() {
    if (!text.trim()) return;
    setWirdEpocheVorgeschlagen(true);
    setEpocheVorschlagFehler(null);
    try {
      const vorschlag = await api.analysatorEpocheVorschlagen(text, sshZielId);
      setEpocheEntwurf(vorschlag);
      setEpocheGespeichert(null);
    } catch (e) {
      setEpocheVorschlagFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setWirdEpocheVorgeschlagen(false);
    }
  }

  function epocheEntwurfFeld<K extends keyof EpocheFormularWerte>(feld: K, wert: EpocheFormularWerte[K]) {
    setEpocheEntwurf((bisher) => (bisher ? { ...bisher, [feld]: wert } : bisher));
    // Eine Bearbeitung NACH dem Speichern wuerde sonst unbemerkt von der
    // tatsaechlich gespeicherten Epoche abweichen - lieber den
    // "gespeichert"-Status verwerfen und erneutes Speichern verlangen, als
    // still eine veraltete Epoche weiterzuverwenden (siehe starten() unten).
    setEpocheGespeichert(null);
  }

  async function epocheSpeichern() {
    if (!epocheEntwurf || !epocheFormularGueltig(epocheEntwurf)) return;
    setWirdEpocheGespeichert(true);
    setEpocheSpeichernFehler(null);
    try {
      const antwort = await api.epocheErstellen(epocheEntwurf);
      setEpocheGespeichert({ name: antwort.name, ordner: antwort.ordner });
      onEpochenGeaendert();
    } catch (e) {
      setEpocheSpeichernFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setWirdEpocheGespeichert(false);
    }
  }

  async function starten() {
    if (!text.trim()) return;
    if (epocheModus === "bestehend" && !epoche) return;
    if (epocheModus === "ableiten" && (!epocheEntwurf || !epocheFormularGueltig(epocheEntwurf))) return;

    setWirdGestartet(true);
    setFehler(null);
    try {
      let zielEpoche = epoche;
      if (epocheModus === "ableiten" && epocheEntwurf) {
        // Bereits per "Epoche speichern" angelegt? Dann nicht ein zweites
        // Mal anlegen (das schluege mit 409 fehl, da der Ordner schon
        // existiert) - einfach die schon gespeicherte Epoche verwenden.
        if (epocheGespeichert) {
          zielEpoche = epocheGespeichert.ordner;
        } else {
          const neueEpoche = await api.epocheErstellen(epocheEntwurf);
          zielEpoche = neueEpoche.ordner;
          onEpochenGeaendert();
        }
      }
      const antwort = await api.analysatorStarten(titel.trim(), zielEpoche, text, zweiteEpoche, sshZielId);
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
    setEpocheModus("bestehend");
    setEpocheEntwurf(null);
    setEpocheVorschlagFehler(null);
    setEpocheGespeichert(null);
    setEpocheSpeichernFehler(null);
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
            <div>
              <Label>Epoche</Label>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <button
                  type="button"
                  onClick={() => setEpocheModus("bestehend")}
                  className={`rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                    epocheModus === "bestehend"
                      ? "border-accent bg-accent/10 text-text"
                      : "border-border text-text-muted hover:bg-surface-hover"
                  }`}
                >
                  <span className="font-medium">📚 Bestehende Epoche verwenden</span>
                </button>
                <button
                  type="button"
                  onClick={() => setEpocheModus("ableiten")}
                  className={`rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                    epocheModus === "ableiten"
                      ? "border-accent bg-accent/10 text-text"
                      : "border-border text-text-muted hover:bg-surface-hover"
                  }`}
                >
                  <span className="font-medium">🧬 Neue Epoche aus dieser Geschichte ableiten</span>
                </button>
              </div>
            </div>

            {epocheModus === "bestehend" ? (
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
            ) : (
              <div className="rounded-xl border border-border bg-bg/40 p-4">
                {!epocheEntwurf ? (
                  <div className="space-y-2">
                    <p className="text-sm text-text-muted">
                      Die KI liest den Text weiter unten und schlägt daraus ein neues Setting vor - Name,
                      Zeitraum, Gesellschaftsordnung, ggf. ein erkanntes Franchise. Du kannst den Vorschlag
                      danach vor dem Speichern noch bearbeiten.
                    </p>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={epocheVorschlagen}
                      disabled={wirdEpocheVorgeschlagen || !text.trim()}
                    >
                      {wirdEpocheVorgeschlagen ? "Schlägt vor..." : "Epoche aus Text vorschlagen"}
                    </Button>
                    {!text.trim() && (
                      <p className="text-xs text-text-muted">Erst den Text weiter unten einfügen.</p>
                    )}
                    {epocheVorschlagFehler && <p className="text-sm text-red-400">{epocheVorschlagFehler}</p>}
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm text-text-muted">
                        Von der KI vorgeschlagen - bitte prüfen und bei Bedarf anpassen.
                      </p>
                      <button
                        type="button"
                        onClick={() => {
                          setEpocheEntwurf(null);
                          setEpocheGespeichert(null);
                        }}
                        className="shrink-0 text-xs text-accent-light hover:underline"
                      >
                        Neu vorschlagen
                      </button>
                    </div>
                    <EpocheFormular werte={epocheEntwurf} onChange={epocheEntwurfFeld} />
                    <div className="flex items-center gap-3 border-t border-border pt-3">
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={epocheSpeichern}
                        disabled={wirdEpocheGespeichert || !epocheFormularGueltig(epocheEntwurf) || !!epocheGespeichert}
                      >
                        {wirdEpocheGespeichert ? "Speichert..." : epocheGespeichert ? "Gespeichert ✓" : "Epoche speichern"}
                      </Button>
                      <p className="text-xs text-text-muted">
                        {epocheGespeichert
                          ? `„${epocheGespeichert.name}" liegt jetzt in der Epochen-Bibliothek - auch unabhängig von dieser Analyse nutzbar.`
                          : "Optional: unabhängig von der Analyse in der Epochen-Bibliothek ablegen. \"Analysieren\" unten speichert sie sonst automatisch mit."}
                      </p>
                    </div>
                    {epocheSpeichernFehler && <p className="text-sm text-red-400">{epocheSpeichernFehler}</p>}
                  </div>
                )}
              </div>
            )}
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
            <Button
              onClick={starten}
              disabled={
                wirdGestartet ||
                !text.trim() ||
                (epocheModus === "bestehend" ? !epoche : !epocheEntwurf || !epocheFormularGueltig(epocheEntwurf))
              }
            >
              {wirdGestartet
                ? epocheModus === "ableiten"
                  ? "Legt Epoche an..."
                  : "Wird gestartet..."
                : "Analysieren"}
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
          <li>
            Epoche wählen, die zur importierten Geschichte passt - oder die KI aus dem Text ein neues Setting
            vorschlagen lassen (samt erkanntem Franchise, falls vorhanden) und vor dem Speichern noch anpassen.
          </li>
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
        <p className="mt-2 text-xs text-text-muted">
          Basiert die Geschichte erkennbar auf einem bekannten Franchise, weist die abgeleitete Epoche automatisch
          darauf hin, dass es sich um ein Fan-Projekt ohne Rechte am Original und ohne kommerzielle Absicht
          handelt (sichtbar auf der Titelseite jeder damit geschriebenen Geschichte).
        </p>
      </Card>
    </div>
  );
}
