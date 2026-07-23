import type { Finding } from "../api/types";

export function FindingsList({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) {
    return <p className="text-sm text-text-muted">Keine Befunde.</p>;
  }
  return (
    <ul className="space-y-2">
      {findings.map((f, i) => (
        <li
          key={`${f.code}-${i}`}
          className={`rounded-lg border px-3 py-2 text-sm ${
            f.schwere === "warnung"
              ? "border-amber-400/30 bg-amber-400/10 text-amber-200"
              : "border-sky-400/30 bg-sky-400/10 text-sky-200"
          }`}
        >
          <span className="mr-2 font-mono text-xs opacity-70">{f.code}</span>
          {f.meldung}
        </li>
      ))}
    </ul>
  );
}
