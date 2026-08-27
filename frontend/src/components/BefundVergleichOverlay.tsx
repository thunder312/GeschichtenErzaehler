import type { Befund, BefundKategorie } from "../api/types";
import { KATEGORIE_LABEL } from "./BefundListe";

interface BefundVergleichOverlayProps {
  befund: Befund;
  onClose: () => void;
}

/** Zeigt Fundstelle ("Alt") und Vorschlag/Konflikt-Vorschlaege ("Neu") eines
 * einzelnen Befunds gross und uebersichtlich untereinander an - in der
 * kompakten BefundListe-Karte ist dafuer bei laengeren Texten zu wenig Platz,
 * und "Fundstelle"/"Vorschlag" ohne direkten Vergleich nebeneinander liess
 * unklar, welcher Text der aktuelle (alte) und welcher der vorgeschlagene
 * (neue) ist. Gleiches Overlay-Muster wie ConfirmDialog.tsx/AboutDialog.tsx. */
export function BefundVergleichOverlay({ befund, onClose }: BefundVergleichOverlayProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative mx-auto max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-border bg-surface p-6 shadow-2xl shadow-black/50"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <h3 className="font-heading text-lg font-semibold text-text">Alt/Neu-Vergleich</h3>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-md border border-border px-2 py-1 text-xs font-medium text-text-muted hover:bg-surface-hover"
          >
            Schließen
          </button>
        </div>

        <div className="mb-4 flex flex-wrap gap-1.5">
          {befund.kategorien.map((k) => (
            <span key={k} className="rounded-full border border-border px-2 py-0.5 text-xs font-medium text-text-muted">
              {KATEGORIE_LABEL[k]}
            </span>
          ))}
        </div>

        <div className="mb-4 space-y-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Alt (aktuelle Textstelle)</p>
          <p className="whitespace-pre-wrap rounded-lg border border-border bg-canvas px-3 py-2 font-mono text-sm text-text">
            {befund.fundstelle}
          </p>
        </div>

        {befund.konflikt && befund.konflikt_vorschlaege ? (
          <div className="space-y-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              Neu - widersprüchliche Vorschläge (manuell entscheiden)
            </p>
            {befund.konflikt_vorschlaege.map((v, i) => (
              <div key={i} className="space-y-1">
                <p className="text-xs text-text-muted">{KATEGORIE_LABEL[v.quelle as BefundKategorie] ?? v.quelle}</p>
                <p className="whitespace-pre-wrap rounded-lg border border-red-400/40 bg-red-400/10 px-3 py-2 font-mono text-sm text-text">
                  {v.text}
                </p>
              </div>
            ))}
          </div>
        ) : befund.vorschlag ? (
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Neu (Vorschlag)</p>
            <p className="whitespace-pre-wrap rounded-lg border border-accent/40 bg-accent-soft px-3 py-2 font-mono text-sm text-text">
              {befund.vorschlag}
            </p>
          </div>
        ) : (
          <p className="text-sm text-text-muted">Kein Ersatztext vorhanden (unsicherer Fund, manuell prüfen).</p>
        )}

        {befund.beschreibungen.length > 0 && (
          <div className="mt-4 space-y-1 border-t border-border pt-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Begründung</p>
            {befund.beschreibungen.map((b, i) => (
              <p key={i} className="text-sm text-text">
                <span className="text-text-muted">{KATEGORIE_LABEL[b.quelle as BefundKategorie] ?? b.quelle}:</span>{" "}
                {b.text}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
