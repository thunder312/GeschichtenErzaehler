import { befundeAufteilen } from "../utils/befunde";

export function BefundeView({ text }: { text: string }) {
  const abschnitte = befundeAufteilen(text);

  if (!abschnitte.erkannt) {
    return (
      <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap rounded-lg bg-bg p-3 text-sm text-text">
        {abschnitte.anachronismen}
      </pre>
    );
  }

  return (
    <div className="space-y-3">
      {abschnitte.header && (
        <p className="whitespace-pre-wrap text-xs text-text-muted">{abschnitte.header}</p>
      )}
      <div>
        <h3 className="mb-1 text-sm font-semibold text-amber-300">⏳ Anachronismen</h3>
        <pre className="max-h-[300px] overflow-auto whitespace-pre-wrap rounded-lg border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-text">
          {abschnitte.anachronismen || "Keine Befunde."}
        </pre>
      </div>
      <div>
        <h3 className="mb-1 text-sm font-semibold text-sky-300">🔗 Kontinuität &amp; Logik</h3>
        <pre className="max-h-[300px] overflow-auto whitespace-pre-wrap rounded-lg border border-sky-400/30 bg-sky-400/10 p-3 text-sm text-text">
          {abschnitte.kontinuitaet || "Keine Befunde."}
        </pre>
      </div>
    </div>
  );
}