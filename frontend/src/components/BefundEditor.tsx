import { Editor } from "@monaco-editor/react";
import type { editor as MonacoEditorNS } from "monaco-editor";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import type { Befund } from "../api/types";
import { installBefundReview } from "./befundReview";
import { BefundListe } from "./BefundListe";

type TextEditor = MonacoEditorNS.IStandaloneCodeEditor;
type Review = ReturnType<typeof installBefundReview>;

interface BefundEditorProps {
  kapiteltext: string;
  befunde: Befund[];
  onKapiteltextChange: (text: string) => void;
  height?: string;
  /** Default true: rendert intern eine BefundListe rechts daneben (Original-
   * Verhalten, ein Editor pro Kapitel). Bei false wird NUR der Editor
   * gerendert (volle Breite) - die Elternkomponente rendert dann selbst
   * eine gemeinsame Liste ueber mehrere BefundEditor-Instanzen hinweg und
   * steuert sie ueber das per ref exponierte Handle (springeZu/uebernehmen/
   * uebernehmenMehrere) sowie onOrphan/onUebernommenChange - siehe
   * PruefenAnwendenPage: EIN durchgehender Text ueber alle Kapitel, EINE
   * Fundliste daneben, statt eines Blocks je Kapitel. */
  zeigeListe?: boolean;
  onOrphan?: (befundId: string) => void;
  onUebernommenChange?: (befundId: string) => void;
}

/** Von aussen aufrufbar (siehe PruefenAnwendenPage: eine uebergreifende
 * Fund-Uebersicht ueber alle Kapitel springt per Klick in den passenden,
 * an anderer Stelle der Seite gerenderten BefundEditor-Block). */
export interface BefundEditorHandle {
  springeZu: (befund: Befund) => void;
  uebernehmen: (befundId: string) => void;
  uebernehmenMehrere: (befundIds: string[]) => void;
  /** Cursor + Ansicht an einen Zeichen-Offset im Text setzen (Zeile oben) -
   * fuer die Kapitel-vor/zurueck-Navigation in PruefenAnwendenPage. */
  springeZuOffset: (offset: number) => void;
  /** Zeichen-Offset der aktuell obersten sichtbaren Zeile - Ausgangspunkt
   * fuer "naechstes/voriges Kapitel". */
  ersteSichtbareOffset: () => number;
  /** Zeichen-Offset der aktuellen Cursor-Position. */
  cursorOffset: () => number;
}

/** Einzelner (nicht Diff-)Monaco-Editor ueber dem Kapiteltext, in dem jeder
 * Fund (Anachronismus, Stimmigkeit, Kontinuitaet UND Lektorat - alle drei
 * Pruefer laufen parallel und landen in derselben Liste) als farbige
 * Decoration direkt im Text markiert ist (Farbe je nach Kategorie(n), siehe
 * befundReview.ts) und - sofern ein Vorschlag ohne Konflikt vorliegt - per
 * Klick (Widget im Editor ODER Button in der Liste) uebernommen werden
 * kann: reiner Text-Ersatz im Browser, kein weiterer KI-Aufruf. Ersetzt die
 * alte Vorher/Nachher-Git-Diff-Ansicht (frueher MergeEditor.tsx). */
export const BefundEditor = forwardRef<BefundEditorHandle, BefundEditorProps>(function BefundEditor(
  { kapiteltext, befunde, onKapiteltextChange, height = "clamp(320px, 60vh, 520px)", zeigeListe = true, onOrphan, onUebernommenChange },
  ref,
) {
  const editorRef = useRef<TextEditor | null>(null);
  const reviewRef = useRef<Review | null>(null);
  const [aktiveId, setAktiveId] = useState<string | null>(null);
  const [orphanIds, setOrphanIds] = useState<Set<string>>(new Set());
  const [uebernommenIds, setUebernommenIds] = useState<Set<string>>(new Set());

  useEffect(() => () => reviewRef.current?.cleanup(), []);

  // Reagiert auf ein neues Pruef-Ergebnis (neue befunde-Referenz, z.B. nach
  // "Erneut pruefen" oder Kapitelwechsel) - NICHT auf jeden Tastenanschlag:
  // bereits angelegte Decorations/Widgets verschieben sich mit Monacos
  // eigener Positions-Nachfuehrung automatisch mit (siehe befundReview.ts).
  // Setzt voraus, dass kapiteltext beim MOUNT bereits vollstaendig geladen
  // ist (siehe PruefenAnwendenPage: rendert BefundEditor erst, wenn beide
  // parallelen Fetches - Text und Befunde - abgeschlossen sind), sonst
  // wuerde setzeBefunde() beim ersten Aufruf gegen ein noch leeres Model
  // pruefen und jeden Fund faelschlich als "verwaist" markieren.
  useEffect(() => {
    reviewRef.current?.setzeBefunde(befunde);
    setOrphanIds(new Set());
    setUebernommenIds(new Set());
  }, [befunde]);

  function aufFundSpringen(befund: Befund) {
    setAktiveId(befund.id);
    const editor = editorRef.current;
    const model = editor?.getModel();
    if (!editor || !model || befund.start === null || befund.end === null) return;
    const start = model.getPositionAt(befund.start);
    const ende = model.getPositionAt(befund.end);
    const bereich = {
      startLineNumber: start.lineNumber, startColumn: start.column,
      endLineNumber: ende.lineNumber, endColumn: ende.column,
    };
    editor.revealRangeInCenter(bereich);
    editor.setSelection(bereich);
  }

  useImperativeHandle(ref, () => ({
    springeZu: aufFundSpringen,
    uebernehmen: (befundId: string) => reviewRef.current?.uebernehmen(befundId),
    uebernehmenMehrere: (befundIds: string[]) => reviewRef.current?.uebernehmenMehrere(befundIds),
    springeZuOffset: (offset: number) => {
      const editor = editorRef.current;
      const model = editor?.getModel();
      if (!editor || !model) return;
      const pos = model.getPositionAt(offset);
      editor.revealLineNearTop(pos.lineNumber);
      editor.setPosition({ lineNumber: pos.lineNumber, column: 1 });
      editor.focus();
    },
    ersteSichtbareOffset: () => {
      const editor = editorRef.current;
      const model = editor?.getModel();
      if (!editor || !model) return 0;
      const bereiche = editor.getVisibleRanges();
      const zeile = bereiche.length > 0 ? bereiche[0].startLineNumber : 1;
      return model.getOffsetAt({ lineNumber: zeile, column: 1 });
    },
    cursorOffset: () => {
      const editor = editorRef.current;
      const model = editor?.getModel();
      const pos = editor?.getPosition();
      if (!model || !pos) return 0;
      return model.getOffsetAt(pos);
    },
  }), []);

  const editorNode = (
    <div className="overflow-hidden rounded-xl border border-border">
      <Editor
        height={height}
        language="markdown"
        value={kapiteltext}
        theme="vs-dark"
        onChange={(value) => {
          // Nur ECHTE Aenderungen weiterreichen: @monaco-editor/react feuert
          // onChange auch, wenn WIR selbst `kapiteltext` von aussen aendern
          // (z.B. PruefenAnwendenPage haengt beim Laden eines weiteren
          // Kapitels Text an) - ohne diesen Vergleich wuerde das einen
          // Endlos-Kreislauf ausloesen: value-Prop aendert sich -> onChange
          // feuert -> onKapiteltextChange setzt State -> value-Prop aendert
          // sich erneut -> ...
          if (value !== undefined && value !== kapiteltext) onKapiteltextChange(value);
        }}
        onMount={(editor, monaco) => {
          editorRef.current = editor;
          reviewRef.current = installBefundReview(editor, monaco, {
            onVerwaist: (id) => {
              setOrphanIds((bisher) => new Set(bisher).add(id));
              onOrphan?.(id);
            },
            onUebernommen: (id) => {
              setUebernommenIds((bisher) => new Set(bisher).add(id));
              onUebernommenChange?.(id);
            },
          });
          reviewRef.current.setzeBefunde(befunde);
        }}
        options={{
          wordWrap: "on",
          minimap: { enabled: false },
          fontSize: 14,
        }}
      />
    </div>
  );

  if (!zeigeListe) return editorNode;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
      {editorNode}
      <div className="max-h-[clamp(320px,60vh,520px)] overflow-auto pr-1">
        <BefundListe
          befunde={befunde}
          aktiveId={aktiveId}
          onSelect={aufFundSpringen}
          orphanIds={orphanIds}
          uebernommenIds={uebernommenIds}
          onUebernehmen={(befund) => reviewRef.current?.uebernehmen(befund.id)}
          onUebernehmenAlle={(alle) => reviewRef.current?.uebernehmenMehrere(alle.map((b) => b.id))}
        />
      </div>
    </div>
  );
});
