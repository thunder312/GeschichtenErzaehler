import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { Befund, BefundeAntwort, ProjektDetail } from "../api/types";
import { BefundEditor, type BefundEditorHandle } from "../components/BefundEditor";
import { BefundListe } from "../components/BefundListe";
import { Button, Card, CardTitle } from "../components/ui";
import { useAktivitaet } from "../context/AktivitaetContext";

interface PruefenAnwendenPageProps {
  ordner: string;
  projekt: ProjektDetail | null;
  sshZielId: string;
}

interface KapitelBlock {
  kapiteltext: string;
  befunde: BefundeAntwort | null;
  geladen: boolean;
  ladenPruefen: boolean;
  fehler: string | null;
}

interface Spanne {
  start: number;
  end: number;
}

const kapitelUeberschrift = (n: number) => `## Kapitel ${n}`;
const KAPITEL_MARKER_MUSTER = /^## Kapitel (\d+)\s*$/gm;

/** Teilt den kombinierten Text anhand der "## Kapitel N"-Ueberschriften
 * wieder in einzelne Kapitel auf - Gegenstueck zum Zusammenbauen beim Laden
 * (siehe useEffect unten). Wird nur beim Speichern gebraucht. */
function splitteNachKapitel(text: string): Map<number, string> {
  const treffer = [...text.matchAll(KAPITEL_MARKER_MUSTER)];
  const ergebnis = new Map<number, string>();
  for (let i = 0; i < treffer.length; i++) {
    const n = Number(treffer[i][1]);
    const startInhalt = treffer[i].index! + treffer[i][0].length;
    const endeInhalt = i + 1 < treffer.length ? treffer[i + 1].index! : text.length;
    ergebnis.set(n, text.slice(startInhalt, endeInhalt).trim());
  }
  return ergebnis;
}

export function PruefenAnwendenPage({ ordner, projekt, sshZielId }: PruefenAnwendenPageProps) {
  const [bloecke, setBloecke] = useState<Record<number, KapitelBlock>>({});
  const [kombiniert, setKombiniert] = useState("");
  const [spannen, setSpannen] = useState<Record<number, Spanne>>({});
  const [aktiveId, setAktiveId] = useState<string | null>(null);
  const [orphanIds, setOrphanIds] = useState<Set<string>>(new Set());
  const [uebernommenIds, setUebernommenIds] = useState<Set<string>>(new Set());
  const [speichertLaedt, setSpeichertLaedt] = useState(false);
  const [gespeichertHinweis, setGespeichertHinweis] = useState<string | null>(null);
  const editorRef = useRef<BefundEditorHandle | null>(null);
  const { starten, beenden } = useAktivitaet();
  const kapitelNummern = useMemo(() => [...(projekt?.kapitel ?? [])].sort((a, b) => a - b), [projekt?.kapitel]);
  const geladenRef = useRef<Set<number>>(new Set());
  const angehaengtRef = useRef<Set<number>>(new Set());

  // Projektwechsel: kompletter Reset.
  useEffect(() => {
    geladenRef.current = new Set();
    angehaengtRef.current = new Set();
    setBloecke({});
    setKombiniert("");
    setSpannen({});
    setGespeichertHinweis(null);
  }, [ordner]);

  // Laedt jedes bislang unbekannte Kapitel GENAU EINMAL.
  useEffect(() => {
    const neue = kapitelNummern.filter((n) => !geladenRef.current.has(n));
    if (neue.length === 0) return;
    for (const n of neue) geladenRef.current.add(n);
    let abgebrochen = false;
    // ALLE Fetches dieser Charge parallel starten, aber erst GEMEINSAM in
    // EINEM setBloecke() uebernehmen, wenn alle fertig sind - sonst wuerde
    // das Anhaengen an den kombinierten Text (naechster Effekt) in der
    // REIHENFOLGE passieren, in der die Netzwerk-Antworten zufaellig
    // eintreffen, statt in numerischer Kapitel-Reihenfolge.
    Promise.all(
      neue.map((n) =>
        Promise.allSettled([api.kapitel(ordner, n), api.befunde(ordner, n)]).then(([textErgebnis, befundeErgebnis]) => ({
          n,
          kapiteltext: textErgebnis.status === "fulfilled" ? textErgebnis.value : "",
          befunde: befundeErgebnis.status === "fulfilled" ? befundeErgebnis.value : null,
          fehler: textErgebnis.status === "rejected"
            ? `Kapiteltext konnte nicht geladen werden: ${textErgebnis.reason instanceof Error ? textErgebnis.reason.message : String(textErgebnis.reason)}`
            : null,
        })),
      ),
    ).then((ergebnisse) => {
      if (abgebrochen) return;
      setBloecke((bisher) => {
        const kopie = { ...bisher };
        for (const r of ergebnisse) {
          kopie[r.n] = { kapiteltext: r.kapiteltext, befunde: r.befunde, geladen: true, ladenPruefen: false, fehler: r.fehler };
        }
        return kopie;
      });
    });
    return () => {
      abgebrochen = true;
    };
  }, [ordner, kapitelNummern]);

  // Haengt jedes frisch geladene Kapitel an den EINEN gemeinsamen Text an -
  // bewusst ANHAENGEN statt kompletter Neuaufbau, damit bereits im Editor
  // eingetippte, noch ungespeicherte Aenderungen an frueher geladenen
  // Kapiteln nicht verloren gehen, nur weil im Hintergrund ein weiteres
  // Kapitel dazukommt (Tab bleibt beim Wechseln aktiv, siehe App.tsx).
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

  // Verschiebt jeden Fund von "Offset im eigenen Kapitel" auf "Offset im
  // gemeinsamen Text" (siehe `spannen`) und macht die ID projektweit
  // eindeutig (befunde_merge.py vergibt IDs nur PRO Pruef-Lauf neu ab "b1" -
  // ueber mehrere Kapitel hinweg koennten sie sonst kollidieren).
  const alleShiftedBefunde = useMemo(() => {
    const liste: { kapitel: number; shifted: Befund }[] = [];
    for (const n of kapitelNummern) {
      const block = bloecke[n];
      const spanne = spannen[n];
      if (!block?.befunde || !spanne) continue;
      for (const befund of block.befunde.befunde) {
        const verschoben = befund.start !== null && befund.end !== null
          ? { start: spanne.start + befund.start, end: spanne.start + befund.end }
          : { start: null, end: null };
        liste.push({ kapitel: n, shifted: { ...befund, id: `${n}-${befund.id}`, ...verschoben } });
      }
    }
    return liste;
  }, [bloecke, spannen, kapitelNummern]);

  const shiftedBefunde = useMemo(() => alleShiftedBefunde.map((x) => x.shifted), [alleShiftedBefunde]);
  const kapitelVonId = useMemo(() => {
    const map = new Map<string, number>();
    for (const x of alleShiftedBefunde) map.set(x.shifted.id, x.kapitel);
    return map;
  }, [alleShiftedBefunde]);

  const hatUngespeicherteAenderungen = useMemo(() => {
    const segmente = splitteNachKapitel(kombiniert);
    for (const n of kapitelNummern) {
      const segment = segmente.get(n);
      if (segment !== undefined && segment !== bloecke[n]?.kapiteltext) return true;
    }
    return false;
  }, [kombiniert, bloecke, kapitelNummern]);

  async function pruefen(n: number) {
    setBloecke((b) => ({ ...b, [n]: { ...b[n], ladenPruefen: true, fehler: null } }));
    starten(`Prüft Kapitel ${n} auf Anachronismen, Stimmigkeit, Kontinuität & Lektorat...`);
    try {
      const antwort = await api.pruefen(ordner, n, sshZielId || null);
      setBloecke((b) => ({ ...b, [n]: { ...b[n], befunde: antwort, ladenPruefen: false } }));
    } catch (e) {
      setBloecke((b) => ({
        ...b,
        [n]: { ...b[n], ladenPruefen: false, fehler: e instanceof Error ? e.message : String(e) },
      }));
    } finally {
      beenden();
    }
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

  function aufFundKlicken(befund: Befund) {
    setAktiveId(befund.id);
    editorRef.current?.springeZu(befund);
  }

  return (
    <div className="space-y-6 p-6">
      <Card>
        <CardTitle>🔍 Prüfen &amp; Anwenden</CardTitle>
        <p className="text-xs text-text-muted">
          Anachronismus/Stimmigkeit, Kontinuität und Lektorat laufen automatisch parallel direkt nach dem
          Schreiben eines Kapitels (Tab „Schreiben"). Jeder Fund ist im Text unten farbig markiert (Amber:
          Anachronismus, Violett: Stimmigkeit, Sky: Kontinuität, Grün: Lektorat, Türkis: von mehreren Prüfern
          gemeldet, Rot: widersprüchliche Vorschläge - hier manuell entscheiden). Text direkt im Editor
          bearbeiten, dann speichern - beim Speichern wird der Text anhand der „## Kapitel N"-Überschriften
          wieder auf die einzelnen Kapitel aufgeteilt.
        </p>

        {kapitelNummern.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {kapitelNummern.map((n) => (
              <div key={n} className="flex items-center gap-1.5 rounded-lg border border-border px-2 py-1 text-xs">
                <span className="font-medium">Kapitel {n}</span>
                {bloecke[n]?.befunde?.veraltet && (
                  <span title="Befunde veraltet gegen aktuellen Text - erneut prüfen" className="text-amber-400">⚠</span>
                )}
                <button
                  type="button"
                  onClick={() => pruefen(n)}
                  disabled={bloecke[n]?.ladenPruefen}
                  className="text-accent-light hover:underline disabled:opacity-40"
                >
                  {bloecke[n]?.ladenPruefen ? "prüft..." : "erneut prüfen"}
                </button>
              </div>
            ))}
          </div>
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
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
          <div className="space-y-3">
            <div className="flex items-center justify-end gap-3">
              {hatUngespeicherteAenderungen && <span className="text-xs text-text-muted">Noch nicht gespeicherte Änderungen</span>}
              {gespeichertHinweis && <span className="text-xs text-accent-light">{gespeichertHinweis}</span>}
              <Button onClick={speichern} disabled={speichertLaedt || !hatUngespeicherteAenderungen}>
                {speichertLaedt ? "Speichert..." : "Speichern"}
              </Button>
            </div>
            <BefundEditor
              ref={editorRef}
              kapiteltext={kombiniert}
              befunde={shiftedBefunde}
              onKapiteltextChange={setKombiniert}
              zeigeListe={false}
              height="75vh"
              onOrphan={(id) => setOrphanIds((s) => new Set(s).add(id))}
              onUebernommenChange={(id) => setUebernommenIds((s) => new Set(s).add(id))}
            />
          </div>
          <div className="max-h-[75vh] overflow-auto pr-1">
            <BefundListe
              befunde={shiftedBefunde}
              aktiveId={aktiveId}
              onSelect={aufFundKlicken}
              orphanIds={orphanIds}
              uebernommenIds={uebernommenIds}
              kapitelVon={(befund) => kapitelVonId.get(befund.id) ?? 0}
              onUebernehmen={(befund) => editorRef.current?.uebernehmen(befund.id)}
              onUebernehmenAlle={(alle) => editorRef.current?.uebernehmenMehrere(alle.map((b) => b.id))}
            />
          </div>
        </div>
      )}
    </div>
  );
}
