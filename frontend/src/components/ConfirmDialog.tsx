import { Button } from "./ui";

interface ConfirmDialogProps {
  titel: string;
  beschreibung: string;
  bestaetigenText?: string;
  abbrechenText?: string;
  wirdAusgefuehrt?: boolean;
  onBestaetigen: () => void;
  onAbbrechen: () => void;
}

/** Eigenes Bestätigen-Popup im App-Design statt des nativen
 * window.confirm() - fuer unwiderrufliche Aktionen wie Projekt loeschen.
 * Gleiches Overlay-/Karten-Muster wie AboutDialog.tsx. */
export function ConfirmDialog({
  titel,
  beschreibung,
  bestaetigenText = "Bestätigen",
  abbrechenText = "Abbrechen",
  wirdAusgefuehrt = false,
  onBestaetigen,
  onAbbrechen,
}: ConfirmDialogProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={onAbbrechen}
    >
      <div
        className="relative mx-auto max-w-sm rounded-2xl border border-border bg-surface p-6 shadow-2xl shadow-black/50"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="font-heading mb-2 text-lg font-semibold text-text">{titel}</h3>
        <p className="mb-5 text-sm text-text-muted">{beschreibung}</p>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onAbbrechen} disabled={wirdAusgefuehrt}>
            {abbrechenText}
          </Button>
          <Button variant="danger" onClick={onBestaetigen} disabled={wirdAusgefuehrt}>
            {wirdAusgefuehrt ? "..." : bestaetigenText}
          </Button>
        </div>
      </div>
    </div>
  );
}
