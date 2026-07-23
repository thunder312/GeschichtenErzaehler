import type { Finding } from "../api/types";

export function FindingsList({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) {
    return <p className="text-sm text-neutral-500">Keine Befunde.</p>;
  }
  return (
    <ul className="space-y-2">
      {findings.map((f, i) => (
        <li
          key={`${f.code}-${i}`}
          className={`rounded-md border px-3 py-2 text-sm ${
            f.schwere === "warnung"
              ? "border-amber-400/40 bg-amber-50 text-amber-900 dark:bg-amber-950/30 dark:text-amber-200"
              : "border-sky-400/40 bg-sky-50 text-sky-900 dark:bg-sky-950/30 dark:text-sky-200"
          }`}
        >
          <span className="mr-2 font-mono text-xs opacity-70">{f.code}</span>
          {f.meldung}
        </li>
      ))}
    </ul>
  );
}
