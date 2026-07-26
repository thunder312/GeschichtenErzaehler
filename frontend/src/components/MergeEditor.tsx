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
  /** "anachronismus" hebt die Hunks farblich (Amber) von der normalen
   * Diff-Faerbung ab - fuer PruefenAnwendenPage, wo ganze Kapitel-Bloecke
   * statt einzelner Woerter vorgeschlagen werden und sich das klar von
   * Lektorat-Aenderungen (Standardfarbe, LektorierenPage) unterscheiden
   * soll. Ohne Angabe (bzw. "lektorat") bleibt die Standardfarbe. */
  hunkArt?: "lektorat" | "anachronismus";
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
  hunkArt = "lektorat",
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
          // Monaco setzt wordWrapOverride2 auf der ORIGINAL-Seite intern
          // wieder auf "off" zurueck (Annahme: renderSideBySide sei noch
          // nicht aktiv), und zwar zeitlich nicht zuverlaessig fassbar -
          // weder ein sofortiger noch ein verzoegerter (naechster Macrotask/
          // mehrere Animationsframes) Gegen-Aufruf direkt nach dem Mount
          // bleibt zuverlaessig stehen, der interne Reset kann noch danach
          // erfolgen (per Live-Test in den DevTools verifiziert). Deshalb
          // hier direkt die Quelle abgeklemmt: updateOptions() der
          // ORIGINAL-Seite wird umgebaut, sodass JEDER Versuch (auch von
          // Monaco selbst, ganz gleich zu welchem Zeitpunkt), wordWrapOverride2
          // zu setzen, zwangsweise auf "inherit" umgebogen wird.
          const originalEditor = editor.getOriginalEditor();
          const echtesUpdateOptions = originalEditor.updateOptions.bind(originalEditor);
          originalEditor.updateOptions = (optionen) => {
            if (optionen && "wordWrapOverride2" in optionen) {
              optionen = { ...optionen, wordWrapOverride2: "inherit" };
            }
            echtesUpdateOptions(optionen);
          };
          echtesUpdateOptions({ wordWrapOverride2: "inherit" });

          const modifiedEditor = editor.getModifiedEditor();
          modifiedEditor.onDidChangeModelContent(() => {
            onModifiedChange?.(modifiedEditor.getValue());
          });

          if (hunkweiseBestaetigen) {
            hunkCleanupRef.current = installHunkReview(
              editor,
              monaco,
              onOffeneAenderungen,
              hunkArt === "anachronismus" ? "hunk-review-anachronismus" : undefined,
            );
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
