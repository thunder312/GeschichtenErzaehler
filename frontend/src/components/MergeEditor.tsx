import { DiffEditor } from "@monaco-editor/react";
import { useEffect, useState } from "react";

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
  const [dunkel, setDunkel] = useState(
    window.matchMedia("(prefers-color-scheme: dark)").matches,
  );

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => setDunkel(e.matches);
    query.addEventListener("change", handler);
    return () => query.removeEventListener("change", handler);
  }, []);

  return (
    <div className="overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800">
      <DiffEditor
        height={height}
        language="markdown"
        original={original}
        modified={modified}
        theme={dunkel ? "vs-dark" : "light"}
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
