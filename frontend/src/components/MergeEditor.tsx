import { useEffect, useRef } from "react";
import { DiffEditor } from "@monaco-editor/react";
import { installHunkReview } from "./hunkReview";

interface MergeEditorProps {
  original: string;
  modified: string;
  onModifiedChange?: (value: string) => void;
  height?: string;
  /** Zeigt pro Aenderung ein Uebernehmen/Verwerfen-Widget direkt im Editor
   * (wie VS Code/GitHub), statt nur einen einzigen Gesamt-Diff anzuzeigen. */
  hunkweiseBestaetigen?: boolean;
  onOffeneAenderungen?: (anzahl: number) => void;
}

/** Side-by-side Merge-Ansicht: links die alte Fassung (nur lesbar), rechts
 * die neue KI-Fassung, dort weiter frei editierbar - bevor sie explizit
 * gespeichert wird (siehe Aufrufer: PruefenAnwendenPage/LektorierenPage). */
export function MergeEditor({
  original,
  modified,
  onModifiedChange,
  height = "480px",
  hunkweiseBestaetigen = false,
  onOffeneAenderungen,
}: MergeEditorProps) {
  const hunkCleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => () => hunkCleanupRef.current?.(), []);

  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <DiffEditor
        height={height}
        language="markdown"
        original={original}
        modified={modified}
        theme="vs-dark"
        onMount={(editor, monaco) => {
          // Beim ALLERERSTEN Aufbau des Diff-Editors setzt Monaco intern
          // kurzzeitig wordWrapOverride2 auf "off" (Annahme: renderSideBySide
          // sei noch nicht aktiv) und das bleibt danach haengen - es
          // ueberstimmt "wordWrap"/"diffWordWrap" komplett und ist der Grund,
          // warum bisher nur die rechte Seite umbrach. Erst ein expliziter
          // updateOptions()-Aufruf NACH dem Mount setzt es zuverlaessig auf
          // "inherit" zurueck, damit "diffWordWrap" wirklich fuer beide
          // Seiten greift (per Live-Test in den DevTools verifiziert).
          editor.getOriginalEditor().updateOptions({ wordWrapOverride2: "inherit" });

          const modifiedEditor = editor.getModifiedEditor();
          modifiedEditor.onDidChangeModelContent(() => {
            onModifiedChange?.(modifiedEditor.getValue());
          });

          if (hunkweiseBestaetigen) {
            hunkCleanupRef.current = installHunkReview(editor, monaco, onOffeneAenderungen);
          }
        }}
        options={{
          originalEditable: false,
          wordWrap: "on",
          diffWordWrap: "on",
          minimap: { enabled: false },
          fontSize: 14,
          renderSideBySide: true,
          renderOverviewRuler: false,
          // Laesst schwebende Widgets (unser Uebernehmen/Verwerfen-Widget)
          // an document.body statt am eigenen, per "overflow-hidden"
          // abgerundeten Editor-Wrapper haengen - sonst wuerden Widgets nahe
          // dem oberen Rand teilweise abgeschnitten.
          fixedOverflowWidgets: true,
        }}
      />
    </div>
  );
}
