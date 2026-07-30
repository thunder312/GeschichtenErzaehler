import type { Monaco } from "@monaco-editor/react";
import type { editor as MonacoEditorNS } from "monaco-editor";
import type { Befund, BefundKategorie } from "../api/types";

type TextEditor = MonacoEditorNS.IStandaloneCodeEditor;
type TextModel = MonacoEditorNS.ITextModel;

interface TrackedBefund {
  decorationId: string;
  /** Nur gesetzt, wenn dieser Fund ein Ein-Klick-Apply anbietet (Vorschlag
   * vorhanden, kein Konflikt) - Ankerpunkt + Widget direkt hinter der
   * Fundstelle. */
  ankerDecorationId: string | null;
  widget: MonacoEditorNS.IContentWidget | null;
}

function cssKlasse(befund: Befund): string {
  if (befund.konflikt) return "finding-konflikt";
  if (befund.kategorien.length > 1) return "finding-multi";
  const kategorie: BefundKategorie = befund.kategorien[0];
  return `finding-${kategorie}`;
}

function kannUebernommenWerden(befund: Befund): boolean {
  return befund.gefunden && !befund.konflikt && !!befund.vorschlag;
}

function erstelleWidgetKnoten(onUebernehmen: () => void): HTMLElement {
  const knoten = document.createElement("div");
  knoten.className =
    "flex items-center rounded-md border border-border bg-surface px-1 py-0.5 shadow-lg shadow-black/40";
  const button = document.createElement("button");
  button.type = "button";
  button.title = "Vorschlag übernehmen";
  button.textContent = "✓";
  button.className = "rounded px-1.5 text-xs font-bold leading-5 text-accent-light hover:bg-accent-soft";
  button.onclick = (e) => {
    e.preventDefault();
    onUebernehmen();
  };
  knoten.appendChild(button);
  return knoten;
}

export interface BefundReviewCallbacks {
  /** Die Fundstelle wurde durch eine ueberlappende manuelle Bearbeitung
   * entfernt (Decoration-Range kollabiert) - Fund bleibt in der Liste,
   * bekommt aber ein "nicht mehr vorhanden"-Badge statt der Apply-Option. */
  onVerwaist: (befundId: string) => void;
  /** Der Vorschlag wurde uebernommen (per Widget oder Listen-Button). */
  onUebernommen: (befundId: string) => void;
}

/** Verwaltet Inline-Decorations + schwebende Uebernehmen-Widgets fuer die
 * Funde im BefundEditor (Decorations "leben" auf demselben Model und
 * verschieben sich bei Edits an anderer Stelle automatisch mit; Live-
 * Position wird nie aus einer gespeicherten Zeilennummer, sondern immer per
 * model.getDecorationRange() gelesen - urspruenglich vom inzwischen
 * entfernten hunkReview.ts/MergeEditor.tsx uebernommenes Muster, hier aber
 * fuer zeichengenaue Spannen statt ganzer Zeilen-Hunks: der Anker sitzt
 * direkt hinter der Fundstelle, nicht am Zeilenende). */
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
    if (t.widget) editor.removeContentWidget(t.widget);
    const ids = [t.decorationId, ...(t.ankerDecorationId ? [t.ankerDecorationId] : [])];
    model.deltaDecorations(ids, []);
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

  function setzeBefunde(befunde: Befund[]) {
    if (!model) return;
    aktuelleBefunde = new Map(befunde.map((b) => [b.id, b]));

    // Voller Reset bei JEDEM Aufruf (auch bei identischen IDs ueber zwei
    // Aufrufe hinweg, z.B. weil die IDs pro Pruef-Lauf neu ab "b1" vergeben
    // werden, siehe befunde_merge.py) - ein neuer Aufruf bedeutet immer ein
    // frisches Pruef-Ergebnis vom Server, gegen das alte, evtl. laengst
    // ungueltige Decorations/Uebernommen-Markierungen nicht mehr sinnvoll
    // waeren. Innerhalb EINES Aufrufs bleiben bereits gesetzte Decorations
    // dagegen erhalten und verschieben sich mit Monacos eigener
    // Positions-Nachfuehrung automatisch mit, wenn im Editor weitergetippt
    // wird (kein erneuter setzeBefunde()-Aufruf dabei noetig).
    for (const id of Array.from(verfolgt.keys())) entferneTracked(id);
    erledigt.clear();

    for (const befund of befunde) {
      if (!befund.gefunden || befund.start === null || befund.end === null) continue;

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

      if (!kannUebernommenWerden(befund)) {
        verfolgt.set(befund.id, { decorationId, ankerDecorationId: null, widget: null });
        continue;
      }

      const [ankerDecorationId] = model.deltaDecorations([], [{
        range: new monaco.Range(endPos.lineNumber, endPos.column, endPos.lineNumber, endPos.column),
        options: {},
      }]);

      const domKnoten = erstelleWidgetKnoten(() => uebernehmen(befund.id));
      const widget: MonacoEditorNS.IContentWidget = {
        getId: () => `befund-widget-${decorationId}`,
        getDomNode: () => domKnoten,
        getPosition: () => {
          const liveRange = model.getDecorationRange(ankerDecorationId);
          return {
            position: {
              lineNumber: liveRange ? liveRange.startLineNumber : endPos.lineNumber,
              column: liveRange ? liveRange.startColumn : endPos.column,
            },
            preference: [monaco.editor.ContentWidgetPositionPreference.EXACT],
          };
        },
      };

      editor.addContentWidget(widget);
      verfolgt.set(befund.id, { decorationId, ankerDecorationId, widget });
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
