import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { AutomatikStatus, Befund, BefundeAntwort, ProjektDetail } from "../api/types";
import { BefundEditor, type BefundEditorHandle } from "../components/BefundEditor";
import { BefundListe } from "../components/BefundListe";
import { CollapsibleCard } from "../components/CollapsibleCard";
import { ProjektBereinigenDialog } from "../components/ProjektBereinigenDialog";
import { Button, Card, CardTitle } from "../components/ui";
import { useAktivitaet } from "../context/AktivitaetContext";
import { kapitelTextSchluessel, useKapitelText } from "../context/KapitelTextContext";
import { hatReste } from "../utils/automatik";
import { kapitelTextZusammenbauen, kapitelUeberschrift, splitteNachKapitel, type Spanne } from "../utils/kapitelKombiniert";

interface PruefenAnwendenPageProps {
  ordner: string;
  projekt: ProjektDetail | null;
  sshZielId: string;
  onGeaendert: () => void;
}

interface KapitelBlock {
  kapiteltext: string;
  befunde: BefundeAntwort | null;
  geladen: boolean;
  ladenPruefen: boolean;
  fehler: string | null;
}

export function PruefenAnwendenPage({ ordner, projekt, sshZielId, onGeaendert }: PruefenAnwendenPageProps) {
  const [bloecke, setBloecke] = useState<Record<number, KapitelBlock>>({});
  const [kombiniert, setKombiniert] = useState("");
  const [spannen, setSpannen] = useState<Record<number, Spanne>>({});
  const [aktiveId, setAktiveId] = useState<string | null>(null);
  const [orphanIds, setOrphanIds] = useState<Set<string>>(new Set());
  const [uebernommenIds, setUebernommenIds] = useState<Set<string>>(new Set());
  const [speichertLaedt, setSpeichertLaedt] = useState(false);
  const [gespeichertHinweis, setGespeichertHinweis] = useState<string | null>(null);
  const [automatikStatus, setAutomatikStatus] = useState<AutomatikStatus | null>(null);
  const [resteWirdBestaetigt, setResteWirdBestaetigt] = useState(false);
  const [bulkPruefungLaeuft, setBulkPruefungLaeuft] = useState(false);
  const [zeigeBereinigenDialog, setZeigeBereinigenDialog] = useState(false);
  const [bereinigenLaeuft, setBereinigenLaeuft] = useState(false);
  const [bereinigenHinweis, setBereinigenHinweis] = useState<string | null>(null);
  // Erhoeht sich bei jedem Klick auf "Neu laden" - steht bewusst in den
  // Dependency-Arrays der beiden Lade-Effekte weiter unten, damit ein Reload
  // AUCH DANN neu laedt, wenn sich weder ordner noch kapitelNummern geaendert
  // haben (sonst wuerde React die Effekte trotz zurueckgesetzter Refs gar
  // nicht erst erneut ausfuehren).
  const [reloadToken, setReloadToken] = useState(0);
  const editorRef = useRef<BefundEditorHandle | null>(null);
  const { starten, beenden } = useAktivitaet();
  const kapitelNummern = useMemo(() => [...(projekt?.kapitel ?? [])].sort((a, b) => a - b), [projekt?.kapitel]);
  const geladenRef = useRef<Set<number>>(new Set());
  const angehaengtRef = useRef<Set<number>>(new Set());

  // Projektwechsel bzw. "Neu laden": kompletter Reset.
  useEffect(() => {
    geladenRef.current = new Set();
    angehaengtRef.current = new Set();
    setBloecke({});
    setKombiniert("");
    setSpannen({});
    setGespeichertHinweis(null);
  }, [ordner, reloadToken]);

  // Pollt den Automatikmodus-Status unabhaengig vom Reset oben, damit z.B.
  // der "Prüfung abschließen"-Button sofort erscheint, sobald ein im
  // Hintergrund laufender Automatik-Lauf fertig wird, waehrend der Nutzer
  // schon auf diesem Tab ist - ohne Reload oder erneuten Tab-Wechsel noetig
  // (SchreibenPage.tsx pollt fuer ihre eigene Anzeige nach demselben Muster,
  // haelt aber ihren eigenen State - kein gemeinsamer Cache).
  useEffect(() => {
    let abgebrochen = false;
    function laden() {
      api
        .automatikStatus(ordner)
        .then((status) => {
          if (!abgebrochen) setAutomatikStatus(status);
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
  }, [ordner, kapitelNummern, reloadToken]);

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

  const { stand: kapitelStand, veroeffentlichen: kapitelVeroeffentlichen } = useKapitelText();

  // Cross-Tab-Sync: Der Tab "Rechtschreibung" haelt denselben Kapiteltext in
  // einem eigenen, unabhaengigen Zustand (siehe RechtschreibungPage.tsx) -
  // beide Tabs bleiben beim Wechseln dauerhaft gemountet (App.tsx). Wurde
  // dort ein hier bereits geladenes Kapitel gespeichert, sofort uebernehmen
  // - aber nur, wenn hier selbst keine ungespeicherte Aenderung an GENAU
  // diesem Kapitel existiert (die hat Vorrang, sonst wuerden gerade
  // uebernommene Befund-Vorschlaege oder laufende Eingaben ueberschrieben).
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

  async function pruefen(n: number, fortschritt?: string) {
    setBloecke((b) => ({ ...b, [n]: { ...b[n], ladenPruefen: true, fehler: null } }));
    starten(
      `Prüft Kapitel ${n} auf Anachronismen, Stimmigkeit, Kontinuität & Lektorat...` +
        (fortschritt ? ` (${fortschritt})` : ""),
    );
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

  // Prueft nacheinander (bewusst NICHT parallel - ein einzelner Kapitel-Check
  // feuert bereits 4+ LLM-Aufrufe, mehrere Kapitel gleichzeitig wuerden den
  // meist recht schwachbrüstigen Ollama-Host ueberlasten) alle Kapitel, deren
  // Funde entweder veraltet sind (Text seit letzter Pruefung geaendert) oder
  // die noch nie geprueft wurden (befunde === null).
  const veralteteKapitel = kapitelNummern.filter((n) => !bloecke[n]?.befunde || bloecke[n]?.befunde?.veraltet);

  async function alleVeraltetenPruefen() {
    const ziel = veralteteKapitel;
    if (ziel.length === 0 || bulkPruefungLaeuft) return;
    setBulkPruefungLaeuft(true);
    try {
      for (let i = 0; i < ziel.length; i++) {
        await pruefen(ziel[i], `${i + 1}/${ziel.length}`);
      }
    } finally {
      setBulkPruefungLaeuft(false);
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

  function neuLaden() {
    if (
      hatUngespeicherteAenderungen &&
      !window.confirm("Es gibt noch nicht gespeicherte Änderungen im Editor. Trotzdem neu laden und verwerfen?")
    ) {
      return;
    }
    setOrphanIds(new Set());
    setUebernommenIds(new Set());
    setReloadToken((t) => t + 1);
  }

  async function pruefungAbschliessen() {
    setResteWirdBestaetigt(true);
    try {
      await api.automatikResteBestaetigen(ordner);
      setAutomatikStatus(await api.automatikStatus(ordner));
      // Das Projekte-Label (AutomatikBadge) haengt am selben Status
      // (resten_bestaetigt) und soll ohne Tab-Wechsel sofort mitziehen.
      onGeaendert();
      // Direkt im Anschluss die Aufraeum-Option anbieten - der Nutzer ist
      // gerade fertig mit der Pruefung und muss dafuer nicht extra woanders
      // hinklicken (siehe ProjektBereinigenDialog.tsx).
      setBereinigenHinweis(null);
      setZeigeBereinigenDialog(true);
    } finally {
      setResteWirdBestaetigt(false);
    }
  }

  // Aktualisiert den Personen-Fundus NUR mit den Figuren DIESES Projekts -
  // gibt einen fertigen Hinweistext zurueck statt selbst zu werfen, damit
  // ein Fehler hier das Bereinigen (falls ebenfalls angefordert) nicht
  // verhindert.
  async function fundusFuerProjektAktualisieren(): Promise<string> {
    try {
      const antwort = await api.fundusProjektAktualisieren(ordner, sshZielId || null);
      return antwort.uebersprungen
        ? "Personen-Fundus: keine Figuren erkannt."
        : `Personen-Fundus: ${antwort.gefundene_figuren} Figur(en) übernommen.`;
    } catch (e) {
      return `Personen-Fundus: Fehler - ${e instanceof Error ? e.message : String(e)}`;
    }
  }

  async function bereinigenAusgefuehrt(fundusAktualisieren: boolean) {
    setBereinigenLaeuft(true);
    starten("Bereinigt Projekt...");
    try {
      const hinweise: string[] = [];
      try {
        const ergebnis = await api.projektBereinigen(ordner);
        hinweise.push(
          `${ergebnis.geloeschte_bak} Sicherungsdatei(en) und ${ergebnis.geloeschte_stand} alte(n) ` +
            `Zwischenstand/-stände gelöscht.`,
        );
      } catch (e) {
        hinweise.push(`Bereinigen fehlgeschlagen - ${e instanceof Error ? e.message : String(e)}`);
      }
      if (fundusAktualisieren) hinweise.push(await fundusFuerProjektAktualisieren());
      setBereinigenHinweis(hinweise.join(" "));
      setZeigeBereinigenDialog(false);
    } finally {
      setBereinigenLaeuft(false);
      beenden();
    }
  }

  async function bereinigenUebersprungen(fundusAktualisieren: boolean) {
    if (!fundusAktualisieren) {
      setZeigeBereinigenDialog(false);
      return;
    }
    setBereinigenLaeuft(true);
    starten("Aktualisiert Personen-Fundus...");
    try {
      setBereinigenHinweis(await fundusFuerProjektAktualisieren());
      setZeigeBereinigenDialog(false);
    } finally {
      setBereinigenLaeuft(false);
      beenden();
    }
  }

  function aufFundKlicken(befund: Befund) {
    setAktiveId(befund.id);
    editorRef.current?.springeZu(befund);
  }

  return (
    <div className="space-y-6 p-4 sm:p-6">
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
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button
              variant="secondary"
              onClick={alleVeraltetenPruefen}
              disabled={veralteteKapitel.length === 0 || bulkPruefungLaeuft}
            >
              {bulkPruefungLaeuft
                ? "Prüft..."
                : veralteteKapitel.length === 0
                  ? "Alle Kapitel aktuell geprüft"
                  : `Alle veralteten Kapitel prüfen (${veralteteKapitel.length})`}
            </Button>
          </div>
        )}

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
        <CollapsibleCard
          title="📄 Kapiteltexte & Funde"
          aktionen={
            <>
              {hatUngespeicherteAenderungen && <span className="text-xs text-text-muted">Noch nicht gespeicherte Änderungen</span>}
              {gespeichertHinweis && <span className="text-xs text-accent-light">{gespeichertHinweis}</span>}
              <Button variant="secondary" onClick={neuLaden}>
                Neu laden
              </Button>
              {automatikStatus &&
                !automatikStatus.laeuft &&
                automatikStatus.abgeschlossen &&
                hatReste(automatikStatus.protokoll) &&
                (automatikStatus.resten_bestaetigt ? (
                  <span className="text-xs text-accent-light">✅ Prüfung als abgeschlossen bestätigt.</span>
                ) : (
                  <Button variant="secondary" onClick={pruefungAbschliessen} disabled={resteWirdBestaetigt}>
                    {resteWirdBestaetigt ? "Bestätigt..." : "Prüfung abschließen"}
                  </Button>
                ))}
              {bereinigenHinweis && <span className="text-xs text-text-muted">{bereinigenHinweis}</span>}
              <Button onClick={speichern} disabled={speichertLaedt || !hatUngespeicherteAenderungen}>
                {speichertLaedt ? "Speichert..." : "Speichern"}
              </Button>
            </>
          }
        >
          <div className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-[2fr_1fr]">
            <BefundEditor
              ref={editorRef}
              kapiteltext={kombiniert}
              befunde={shiftedBefunde}
              onKapiteltextChange={setKombiniert}
              zeigeListe={false}
              height="clamp(320px, 75vh, 900px)"
              onOrphan={(id) => setOrphanIds((s) => new Set(s).add(id))}
              onUebernommenChange={(id) => setUebernommenIds((s) => new Set(s).add(id))}
            />
            <div className="max-h-[clamp(320px,75vh,900px)] overflow-auto pr-1">
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
        </CollapsibleCard>
      )}

      {zeigeBereinigenDialog && (
        <ProjektBereinigenDialog
          wirdAusgefuehrt={bereinigenLaeuft}
          onBereinigen={bereinigenAusgefuehrt}
          onUeberspringen={bereinigenUebersprungen}
        />
      )}
    </div>
  );
}
