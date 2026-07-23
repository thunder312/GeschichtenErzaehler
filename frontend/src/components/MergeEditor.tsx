import { DiffEditor } from "@monaco-editor/react";

interface MergeEditorProps {
  original: string;
  modified: string;
  onModifiedChange?: (value: string) => void;
  height?: string;
}

/** Side-by-side Merge-Ansicht: links die alte Fassung (nur lesbar), rechts
 * die neue KI-Fassung, dort weiter frei editierbar - bevor sie explizit
 * gespeichert wird (siehe Aufrufer: PruefenAnwendenPage/LektorierenPage). */
export function MergeEditor({ original, modified, onModifiedChange, height = "480px" }: MergeEditorProps) {
  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <DiffEditor
        height={height}
        language="markdown"
        original={original}
        modified={modified}
        theme="vs-dark"
        onMount={(editor) => {
          const modifiedEditor = editor.getModifiedEditor();
          modifiedEditor.onDidChangeModelContent(() => {
            onModifiedChange?.(modifiedEditor.getValue());
          });
        }}
        options={{
          originalEditable: false,
          wordWrap: "on",
          minimap: { enabled: false },
          fontSize: 14,
          renderSideBySide: true,
        }}
      />
    </div>
  );
}
