import type { Monaco } from "@monaco-editor/react";
import type { editor as MonacoEditorNS } from "monaco-editor";
import type { Befund, BefundKategorie } from "../api/types";

type TextEditor = MonacoEditorNS.IStandaloneCodeEditor;
type TextModel = MonacoEditorNS.ITextModel;

interface TrackedBefund {
  decorationId: string;
}

function cssKlasse(befund: Befund): string {
  if (befund.konflikt) return "finding-konflikt";
  if (befund.kategorien.length > 1) return "finding-multi";
  const kategorie: BefundKategorie = befund.kategorien[0];
  return `finding-${kategorie}`;
}

export interface BefundReviewCallbacks {
  /** Die Fundstelle wurde durch eine ueberlappende manuelle Bearbeitung
   * entfernt (Decoration-Range kollabiert) - Fund bleibt in der Liste,
   * bekommt aber ein "nicht mehr vorhanden"-Badge statt der Apply-Option. */
  onVerwaist: (befundId: string) => void;
  /** Der Vorschlag wurde uebernommen (per Listen-Button). */
  onUebernommen: (befundId: string) => void;
}

/** Verwaltet Inline-Decorations (Hervorhebung + Hover-Tooltip) fuer die Funde
 * im BefundEditor - das eigentliche Uebernehmen laeuft ausschliesslich ueber
 * den Listen-Button in BefundListe.tsx (frueher gab es zusaetzlich ein
 * schwebendes Widget direkt im Text, das wurde entfernt: es verdeckte
 * gelegentlich Text ungünstig und war ein zweiter, unnoetiger Weg zu
 * demselben uebernehmen()). Decorations "leben" auf demselben Model und
 * verschieben sich bei Edits an anderer Stelle automatisch mit; Live-
 * Position wird nie aus einer gespeicherten Zeilennummer, sondern immer per
 * model.getDecorationRange() gelesen - urspruenglich vom inzwischen
 * entfernten hunkReview.ts/MergeEditor.tsx uebernommenes Muster, hier aber
 * fuer zeichengenaue Spannen statt ganzer Zeilen-Hunks. */
export function installBefundReview(
  editor: TextEditor,
  monaco: Monaco,
  callbacks: BefundReviewCallbacks,
): {
  setzeBefunde: (befunde: Befund[]) => void;
  uebernehmen: (befundId: string) => void;
  uebernehmenMehrere: (befundIds: string[]) => void;
  cleanup: () => void;
} {
  const model: TextModel | null = editor.getModel();
  const verfolgt = new Map<string, TrackedBefund>();
  const erledigt = new Set<string>(); // uebernommen ODER verwaist - nie erneut anlegen
  // Merkt sich die zuletzt uebergebene Fund-Liste, damit uebernehmen() ohne
  // weiteren Parameter auf den aktuellen Vorschlagstext zugreifen kann.
  let aktuelleBefunde = new Map<string, Befund>();

  function entferneTracked(id: string) {
    const t = verfolgt.get(id);
    if (!t || !model) return;
    model.deltaDecorations([t.decorationId], []);
    verfolgt.delete(id);
  }

  function uebernehmen(befundId: string) {
    if (!model) return;
    const t = verfolgt.get(befundId);
    if (!t) return;
    const liveRange = model.getDecorationRange(t.decorationId);
    if (!liveRange) return; // sollte durch pruefeVerwaist() bereits abgefangen sein
    const befund = aktuelleBefunde.get(befundId);
    if (!befund?.vorschlag) return;
    editor.executeEdits("befund-apply", [{ range: liveRange, text: befund.vorschlag }]);
    erledigt.add(befundId);
    entferneTracked(befundId);
    callbacks.onUebernommen(befundId);
  }

  function pruefeVerwaist() {
    if (!model) return;
    for (const [id, t] of Array.from(verfolgt)) {
      if (!model.getDecorationRange(t.decorationId)) {
        entferneTracked(id);
        erledigt.add(id);
        callbacks.onVerwaist(id);
      }
    }
  }

  function unveraendert(a: Befund, b: Befund): boolean {
    return a.start === b.start && a.end === b.end && a.fundstelle === b.fundstelle;
  }

  function setzeBefunde(befunde: Befund[]) {
    if (!model) return;
    const vorherigeBefunde = aktuelleBefunde;
    aktuelleBefunde = new Map(befunde.map((b) => [b.id, b]));

    // KEIN voller Reset mehr bei jedem Aufruf: setzeBefunde() feuert nicht
    // nur bei einem echten neuen Pruef-Ergebnis vom Server, sondern in
    // PruefenAnwendenPage (zeigeListe=false) bei JEDER Aenderung der
    // `befunde`-Prop-Referenz - z.B. rein clientseitig, wenn "Ablehnen"
    // `abgelehntIds` aktualisiert und dadurch `shiftedBefunde` neu berechnet
    // wird. Ein voller Reset wuerde dann auch bereits korrekt lebend
    // getrackte Funde anhand ihrer STATISCHEN start/end-Offsets neu
    // validieren - die aber laengst veraltet sein koennen, wenn VORHER schon
    // ein anderer Fund per "Uebernehmen" angewendet und dadurch der
    // nachfolgende Text verschoben wurde (echter, live beobachteter Vorfall:
    // ein Klick auf "Ablehnen" liess dadurch scheinbar die GESAMTE Liste
    // verschwinden). Deshalb: nur ids entfernen, die in der neuen Liste
    // fehlen, und fuer weiterhin vorhandene ids mit UNVERAENDERTEM Inhalt die
    // bestehende (von Monaco automatisch mitverschobene) Decoration in Ruhe
    // lassen statt sie neu aufzubauen. Nur bei inhaltlich geaenderten Funden
    // (z.B. derselbe id-String "3-b1" durch einen frischen Pruef-Lauf mit
    // neuem Inhalt wiederverwendet, siehe befunde_merge.py) wird neu
    // validiert.
    const neueIds = new Set(befunde.map((b) => b.id));
    for (const id of Array.from(verfolgt.keys())) {
      if (!neueIds.has(id)) entferneTracked(id);
    }

    for (const befund of befunde) {
      if (verfolgt.has(befund.id) || erledigt.has(befund.id)) {
        const vorher = vorherigeBefunde.get(befund.id);
        if (vorher && unveraendert(vorher, befund)) continue;
        entferneTracked(befund.id);
        erledigt.delete(befund.id);
      }

      // "gefunden: false" (Backend fand die vom Pruefer zitierte Fundstelle
      // schon beim Pruef-Lauf selbst nicht im Kapiteltext, siehe
      // fundstellen.py) hat KEIN start/end und landet deshalb nie in
      // `verfolgt` - ohne dieses onVerwaist() bliebe der Fund fuer immer in
      // der Liste stehen (nie "verwaist", weil er nie getrackt wurde), auch
      // nachdem alle anderen laengst ungueltigen Funde nach einem Neuladen
      // sauber in den "X weitere ausgeblendet"-Sammler wandern.
      if (!befund.gefunden || befund.start === null || befund.end === null) {
        erledigt.add(befund.id);
        callbacks.onVerwaist(befund.id);
        continue;
      }

      const startPos = model.getPositionAt(befund.start);
      const endPos = model.getPositionAt(befund.end);
      const range = new monaco.Range(startPos.lineNumber, startPos.column, endPos.lineNumber, endPos.column);

      // Anker-Check: befund.start/end wurden serverseitig gegen EINEN
      // bestimmten Kapiteltext berechnet (siehe fundstellen.py). Weicht der
      // jetzt im Editor stehende Text an dieser Stelle vom erwarteten
      // `fundstelle` ab - z.B. weil "Erneut pruefen" waehrend ungespeicherter
      // Edits lief, oder die Kapiteldatei zwischen Pruefung und Laden
      // ueberschrieben wurde (siehe befunde_lesen()/`veraltet`-Flag) - zeigt
      // start/end auf die falsche Stelle. Statt dort eine irrefuehrende
      // Decoration/Apply-Option anzubieten (und im schlimmsten Fall per
      // Klick beliebigen Text zu ueberschreiben), den Fund sofort als
      // verwaist behandeln.
      if (model.getValueInRange(range) !== befund.fundstelle) {
        erledigt.add(befund.id);
        callbacks.onVerwaist(befund.id);
        continue;
      }

      const [decorationId] = model.deltaDecorations([], [{
        range,
        options: {
          className: cssKlasse(befund),
          hoverMessage: { value: befund.beschreibungen.map((d) => d.text).join("\n\n") },
        },
      }]);

      verfolgt.set(befund.id, { decorationId });
    }
  }

  function uebernehmenMehrere(befundIds: string[]) {
    // Jeder Einzelaufruf liest die LIVE Decoration-Range im Moment seiner
    // eigenen Ausfuehrung (siehe uebernehmen()), daher ist die Reihenfolge
    // hier unerheblich - vorangegangene Ersetzungen in derselben Schleife
    // verschieben die Positionen der uebrigen automatisch mit.
    for (const id of befundIds) uebernehmen(id);
  }

  const abo = editor.onDidChangeModelContent(() => pruefeVerwaist());

  return {
    setzeBefunde,
    uebernehmen,
    uebernehmenMehrere,
    cleanup: () => {
      abo.dispose();
      for (const id of Array.from(verfolgt.keys())) entferneTracked(id);
    },
  };
}
