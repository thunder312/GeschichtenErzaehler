import { Editor } from "@monaco-editor/react";
import type { editor as MonacoEditorNS } from "monaco-editor";
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { ProjektDetail, RechtschreibWort } from "../api/types";
import { CollapsibleCard } from "../components/CollapsibleCard";
import { Button, Card, CardTitle } from "../components/ui";
import { kapitelTextSchluessel, useKapitelText } from "../context/KapitelTextContext";
import { kapitelTextZusammenbauen, kapitelUeberschrift, splitteNachKapitel, type Spanne } from "../utils/kapitelKombiniert";

type TextEditor = MonacoEditorNS.IStandaloneCodeEditor;

interface RechtschreibungPageProps {
  ordner: string;
  projekt: ProjektDetail | null;
  sshZielId: string;
}

interface KapitelBlock {
  kapiteltext: string;
  woerter: RechtschreibWort[] | null;
  hunspellVerfuegbar: boolean;
  geladen: boolean;
  laedt: boolean;
  fehler: string | null;
}

interface KapitelTextEditorHandle {
  springeZu: (start: number, end: number) => void;
}

/** Schlichter (Decoration-freier) Editor fuer den gesamten, ueber alle
 * Kapitel durchlaufenden Text - Rechtschreibung markiert nichts dauerhaft
 * im Text, springt per Klick in der Wortliste nur an die Stelle und
 * markiert sie kurz per Auswahl, damit direkt weitergetippt werden kann. */
const KapitelTextEditor = forwardRef<KapitelTextEditorHandle, { text: string; onChange: (text: string) => void }>(
  function KapitelTextEditor({ text, onChange }, ref) {
    const editorRef = useRef<TextEditor | null>(null);

    useImperativeHandle(ref, () => ({
      springeZu: (start, end) => {
        const editor = editorRef.current;
        const model = editor?.getModel();
        if (!editor || !model) return;
        const von = model.getPositionAt(start);
        const bis = model.getPositionAt(end);
        const bereich = {
          startLineNumber: von.lineNumber, startColumn: von.column,
          endLineNumber: bis.lineNumber, endColumn: bis.column,
        };
        editor.revealRangeInCenter(bereich);
        editor.setSelection(bereich);
        editor.focus();
      },
    }), []);

    return (
      <div className="overflow-hidden rounded-xl border border-border">
        <Editor
          height="clamp(320px, 75vh, 900px)"
          language="markdown"
          value={text}
          theme="vs-dark"
          onChange={(value) => {
            // Nur ECHTE Aenderungen weiterreichen - sonst Endlos-Kreislauf,
            // wenn `text` von aussen aktualisiert wird (siehe BefundEditor.tsx).
            if (value !== undefined && value !== text) onChange(value);
          }}
          onMount={(editor) => {
            editorRef.current = editor;
          }}
          options={{ wordWrap: "on", minimap: { enabled: false }, fontSize: 14 }}
        />
      </div>
    );
  },
);

export function RechtschreibungPage({ ordner, projekt, sshZielId }: RechtschreibungPageProps) {
  const [bloecke, setBloecke] = useState<Record<number, KapitelBlock>>({});
  const [kombiniert, setKombiniert] = useState("");
  const [spannen, setSpannen] = useState<Record<number, Spanne>>({});
  const [speichertLaedt, setSpeichertLaedt] = useState(false);
  const [gespeichertHinweis, setGespeichertHinweis] = useState<string | null>(null);
  const editorRef = useRef<KapitelTextEditorHandle | null>(null);
  const kapitelNummern = useMemo(() => [...(projekt?.kapitel ?? [])].sort((a, b) => a - b), [projekt?.kapitel]);
  const geladenRef = useRef<Set<number>>(new Set());
  const angehaengtRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    geladenRef.current = new Set();
    angehaengtRef.current = new Set();
    setBloecke({});
    setKombiniert("");
    setSpannen({});
    setGespeichertHinweis(null);
  }, [ordner]);

  async function pruefeKapitel(n: number) {
    setBloecke((b) => ({
      ...b,
      [n]: { kapiteltext: b[n]?.kapiteltext ?? "", woerter: null, hunspellVerfuegbar: true, geladen: b[n]?.geladen ?? false, laedt: true, fehler: null },
    }));
    try {
      const [kapiteltext, antwort] = await Promise.all([api.kapitel(ordner, n), api.rechtschreibung(ordner, n, sshZielId || null)]);
      setBloecke((b) => ({
        ...b,
        [n]: {
          kapiteltext,
          woerter: antwort.unbekannte_woerter,
          hunspellVerfuegbar: antwort.hunspell_verfuegbar,
          geladen: true,
          laedt: false,
          fehler: null,
        },
      }));
    } catch (e) {
      setBloecke((b) => ({
        ...b,
        [n]: { ...b[n], laedt: false, fehler: e instanceof Error ? e.message : String(e) },
      }));
    }
  }

  useEffect(() => {
    const neue = kapitelNummern.filter((n) => !geladenRef.current.has(n));
    if (neue.length === 0) return;
    for (const n of neue) geladenRef.current.add(n);
    // ALLE Fetches dieser Charge parallel starten, aber erst GEMEINSAM in
    // EINEM setBloecke() uebernehmen, wenn alle fertig sind - sonst wuerde
    // das Anhaengen an den kombinierten Text (naechster Effekt) in der
    // REIHENFOLGE passieren, in der die Netzwerk-Antworten zufaellig
    // eintreffen, statt in numerischer Kapitel-Reihenfolge. Bewusst NICHT
    // ueber pruefeKapitel() (das schreibt sofort je Kapitel einzeln), das
    // bleibt fuer "Alle erneut pruefen" reserviert, wo die Reihenfolge
    // egal ist (die Kapitel sind zu dem Zeitpunkt schon angehaengt).
    let abgebrochen = false;
    Promise.all(
      neue.map(async (n) => {
        try {
          const [kapiteltext, antwort] = await Promise.all([api.kapitel(ordner, n), api.rechtschreibung(ordner, n, sshZielId || null)]);
          return { n, kapiteltext, woerter: antwort.unbekannte_woerter, hunspellVerfuegbar: antwort.hunspell_verfuegbar, fehler: null as string | null };
        } catch (e) {
          return { n, kapiteltext: "", woerter: null, hunspellVerfuegbar: true, fehler: e instanceof Error ? e.message : String(e) };
        }
      }),
    ).then((ergebnisse) => {
      if (abgebrochen) return;
      setBloecke((bisher) => {
        const kopie = { ...bisher };
        for (const r of ergebnisse) {
          kopie[r.n] = {
            kapiteltext: r.kapiteltext, woerter: r.woerter, hunspellVerfuegbar: r.hunspellVerfuegbar,
            geladen: r.fehler === null, laedt: false, fehler: r.fehler,
          };
        }
        return kopie;
      });
    });
    return () => {
      abgebrochen = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ordner, kapitelNummern]);

  // Haengt jedes frisch geprüfte Kapitel an den EINEN gemeinsamen Text an -
  // bewusst ANHAENGEN statt Neuaufbau, damit ungespeicherte Aenderungen an
  // bereits geladenen Kapiteln erhalten bleiben.
  useEffect(() => {
    const neue = kapitelNummern.filter((n) => bloecke[n]?.geladen && !angehaengtRef.current.has(n));
    if (neue.length === 0) return;
    setKombiniert((bisherigerText) => {
      let text = bisherigerText;
      const frischeSpannen: Record<number, Spanne> = {};
      for (const n of neue) {
        const block = bloecke[n]!;
        if (text) text += "\n\n";
        text += `${kapitelUeberschrift(n)}\n\n`;
        const start = text.length;
        text += block.kapiteltext;
        frischeSpannen[n] = { start, end: text.length };
        angehaengtRef.current.add(n);
      }
      setSpannen((bisherigeSpannen) => ({ ...bisherigeSpannen, ...frischeSpannen }));
      return text;
    });
  }, [bloecke, kapitelNummern]);

  const { stand: kapitelStand, veroeffentlichen: kapitelVeroeffentlichen } = useKapitelText();

  // Cross-Tab-Sync: Der Tab "Prüfen & Anwenden" haelt denselben Kapiteltext
  // in einem eigenen, unabhaengigen Zustand (siehe PruefenAnwendenPage.tsx) -
  // beide Tabs bleiben beim Wechseln dauerhaft gemountet (App.tsx). Wurde
  // dort ein hier bereits geladenes Kapitel gespeichert (Text-Edit oder
  // uebernommener Befund), sofort uebernehmen - aber nur, wenn hier selbst
  // keine ungespeicherte Aenderung an GENAU diesem Kapitel existiert (die
  // hat Vorrang, sonst wuerden laufende Eingaben ueberschrieben).
  useEffect(() => {
    if (angehaengtRef.current.size === 0) return;
    const segmente = splitteNachKapitel(kombiniert);
    const uebernahmen = new Map<number, string>();
    for (const n of kapitelNummern) {
      if (!angehaengtRef.current.has(n)) continue;
      const block = bloecke[n];
      const eintrag = kapitelStand[kapitelTextSchluessel(ordner, n)];
      if (!block || !eintrag || eintrag.text === block.kapiteltext) continue;
      const eigenesSegment = segmente.get(n);
      if (eigenesSegment !== undefined && eigenesSegment !== block.kapiteltext) continue;
      uebernahmen.set(n, eintrag.text);
    }
    if (uebernahmen.size === 0) return;

    setBloecke((b) => {
      const kopie = { ...b };
      for (const [n, text] of uebernahmen) kopie[n] = { ...kopie[n], kapiteltext: text };
      return kopie;
    });
    const { text, spannen: neueSpannen } = kapitelTextZusammenbauen(kapitelNummern, (n) =>
      angehaengtRef.current.has(n) ? (uebernahmen.get(n) ?? segmente.get(n) ?? bloecke[n]?.kapiteltext) : undefined,
    );
    setKombiniert(text);
    setSpannen(neueSpannen);
  }, [kapitelStand, ordner, kapitelNummern, bloecke, kombiniert]);

  async function alleErneutPruefen() {
    await Promise.all(kapitelNummern.map((n) => pruefeKapitel(n)));
  }

  async function speichern() {
    setSpeichertLaedt(true);
    setGespeichertHinweis(null);
    try {
      const segmente = splitteNachKapitel(kombiniert);
      const geaendert: number[] = [];
      for (const n of kapitelNummern) {
        const segment = segmente.get(n);
        if (segment === undefined || segment === bloecke[n]?.kapiteltext) continue;
        await api.kapitelSchreiben(ordner, n, segment);
        geaendert.push(n);
        kapitelVeroeffentlichen(ordner, n, segment);
      }
      if (geaendert.length > 0) {
        setBloecke((b) => {
          const kopie = { ...b };
          for (const n of geaendert) kopie[n] = { ...kopie[n], kapiteltext: segmente.get(n)! };
          return kopie;
        });
        setGespeichertHinweis(`Gespeichert (Kapitel ${geaendert.join(", ")}).`);
      } else {
        setGespeichertHinweis("Keine Änderungen.");
      }
    } finally {
      setSpeichertLaedt(false);
    }
  }

  const hatUngespeicherteAenderungen = useMemo(() => {
    const segmente = splitteNachKapitel(kombiniert);
    for (const n of kapitelNummern) {
      const segment = segmente.get(n);
      if (segment !== undefined && segment !== bloecke[n]?.kapiteltext) return true;
    }
    return false;
  }, [kombiniert, bloecke, kapitelNummern]);

  const alleWoerter = useMemo(() => {
    const liste: { kapitel: number; wort: RechtschreibWort; start: number | null; end: number | null }[] = [];
    for (const n of kapitelNummern) {
      const block = bloecke[n];
      const spanne = spannen[n];
      if (!block?.woerter || !spanne) continue;
      for (const wort of block.woerter) {
        liste.push({
          kapitel: n,
          wort,
          start: wort.start !== null ? spanne.start + wort.start : null,
          end: wort.end !== null ? spanne.start + wort.end : null,
        });
      }
    }
    return liste;
  }, [bloecke, spannen, kapitelNummern]);

  const hunspellFehlt = kapitelNummern.some((n) => bloecke[n]?.geladen && !bloecke[n].hunspellVerfuegbar);

  function springeZuWort(start: number | null, end: number | null) {
    if (start === null || end === null) return;
    editorRef.current?.springeZu(start, end);
  }

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle>📖 Rechtschreibung (hunspell)</CardTitle>
          <Button onClick={alleErneutPruefen} disabled={kapitelNummern.length === 0} variant="secondary">
            Alle erneut prüfen
          </Button>
        </div>
        <p className="text-xs text-text-muted">
          Prüft jedes bisher geschriebene Kapitel gegen ein echtes deutsches Wörterbuch (ergänzt die
          Sprachmodell-Prüfung um erfundene, aber grammatisch plausible Wörter). Ein Klick auf ein Wort springt
          direkt an die Fundstelle im Text rechts - dort einfach direkt ausbessern und speichern. Eigennamen und
          Fachbegriffe tauchen zwangsläufig mit auf, kein Fehler.
        </p>
        {hunspellFehlt && (
          <p className="mt-2 text-sm text-amber-300">
            hunspell ist auf dem angesprochenen Ziel nicht verfügbar - für lokale Windows-Entwicklung ein
            SSH-Ziel mit installiertem hunspell auswählen.
          </p>
        )}
      </Card>

      {kapitelNummern.length === 0 ? (
        <Card>
          <p className="text-sm text-text-muted">Noch keine Kapitel geschrieben - siehe Tab „Schreiben".</p>
        </Card>
      ) : !kombiniert ? (
        <Card>
          <p className="text-sm text-text-muted">Lädt...</p>
        </Card>
      ) : (
        <CollapsibleCard
          title="📄 Kapiteltexte & Wörter"
          aktionen={
            <>
              {hatUngespeicherteAenderungen && <span className="text-xs text-text-muted">Noch nicht gespeicherte Änderungen</span>}
              {gespeichertHinweis && <span className="text-xs text-accent-light">{gespeichertHinweis}</span>}
              <Button onClick={speichern} disabled={speichertLaedt || !hatUngespeicherteAenderungen}>
                {speichertLaedt ? "Speichert..." : "Speichern"}
              </Button>
            </>
          }
        >
          <div className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-[2fr_1fr]">
            <KapitelTextEditor ref={editorRef} text={kombiniert} onChange={setKombiniert} />
            <div className="max-h-[clamp(320px,75vh,900px)] space-y-1 overflow-auto pr-1">
              <p className="mb-1 text-xs font-medium uppercase tracking-wider text-text-muted">
                Unbekannte Wörter ({alleWoerter.length})
              </p>
              {alleWoerter.length === 0 ? (
                <p className="text-sm text-text-muted">Keine unbekannten Wörter in den bisher geschriebenen Kapiteln.</p>
              ) : (
                <ul className="space-y-1">
                  {alleWoerter.map(({ kapitel, wort, start, end }, i) => (
                    <li
                      key={`${kapitel}-${wort.wort}-${i}`}
                      onClick={() => springeZuWort(start, end)}
                      className="flex cursor-pointer items-center gap-2 rounded-lg border border-border px-2 py-1.5 text-sm hover:bg-surface-hover"
                    >
                      <span className="rounded-full border border-border px-2 py-0.5 text-xs font-medium text-text-muted">
                        Kapitel {kapitel}
                      </span>
                      <span className="font-mono">{wort.wort}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </CollapsibleCard>
      )}
    </div>
  );
}
