import { Editor } from "@monaco-editor/react";
import type { editor as MonacoEditorNS } from "monaco-editor";
import { useEffect, useRef, useState } from "react";
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
}

/** Einzelner (nicht Diff-)Monaco-Editor ueber dem Kapiteltext, in dem jeder
 * Fund (Anachronismus, Stimmigkeit, Kontinuitaet UND Lektorat - alle drei
 * Pruefer laufen parallel und landen in derselben Liste) als farbige
 * Decoration direkt im Text markiert ist (Farbe je nach Kategorie(n), siehe
 * befundReview.ts) und - sofern ein Vorschlag ohne Konflikt vorliegt - per
 * Klick (Widget im Editor ODER Button in der Liste) uebernommen werden
 * kann: reiner Text-Ersatz im Browser, kein weiterer KI-Aufruf. Ersetzt die
 * alte Vorher/Nachher-Git-Diff-Ansicht (frueher MergeEditor.tsx). */
export function BefundEditor({ kapiteltext, befunde, onKapiteltextChange, height = "520px" }: BefundEditorProps) {
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

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
      <div className="overflow-hidden rounded-xl border border-border">
        <Editor
          height={height}
          language="markdown"
          value={kapiteltext}
          theme="vs-dark"
          onChange={(value) => {
            if (value !== undefined) onKapiteltextChange(value);
          }}
          onMount={(editor, monaco) => {
            editorRef.current = editor;
            reviewRef.current = installBefundReview(editor, monaco, {
              onVerwaist: (id) => setOrphanIds((bisher) => new Set(bisher).add(id)),
              onUebernommen: (id) => setUebernommenIds((bisher) => new Set(bisher).add(id)),
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
      <div className="max-h-[520px] overflow-auto pr-1">
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
}
