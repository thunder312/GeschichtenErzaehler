import { useState } from "react";
import { Button, Input } from "./ui";

interface OrdnerUmbenennenDialogProps {
  /** Aktueller Ordnername (nur letztes Pfadsegment) - Vorbelegung des Feldes. */
  aktuellerName: string;
  wirdAusgefuehrt: boolean;
  fehler: string | null;
  onUmbenennen: (name: string) => void;
  onAbbrechen: () => void;
}

/** Expliziter "Ordner umbenennen"-Dialog im Gerüst-Tab (siehe GeruestPage).
 * Bewusst ein ausdruecklicher Schritt statt eines Nebeneffekts vom
 * Gerüst-Speichern: der Ordnerpfad ist der Projekt-Identifier. Der
 * eingegebene Name wird serverseitig zu einem dateisystem-tauglichen Slug
 * normalisiert (Umlaute -> ae/oe/ue, Leerzeichen -> "-", Sonderzeichen
 * raus) - deshalb hier nur ein Hinweis statt einer Live-Vorschau, die die
 * Backend-Regel doppeln muesste. Gleiches Overlay-/Karten-Muster wie
 * ConfirmDialog.tsx. */
export function OrdnerUmbenennenDialog({
  aktuellerName,
  wirdAusgefuehrt,
  fehler,
  onUmbenennen,
  onAbbrechen,
}: OrdnerUmbenennenDialogProps) {
  const [name, setName] = useState(aktuellerName);
  const kannUmbenennen = name.trim() !== "" && name.trim() !== aktuellerName && !wirdAusgefuehrt;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={onAbbrechen}
    >
      <div
        className="relative mx-auto max-w-md rounded-2xl border border-border bg-surface p-6 shadow-2xl shadow-black/50"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="font-heading mb-2 text-lg font-semibold text-text">Ordner umbenennen</h3>
        <p className="mb-4 text-sm text-text-muted">
          Benennt den Projektordner „{aktuellerName}" um. Der Titel im Gerüst bleibt unverändert - nur der
          Ordnername (und damit die Anzeige im Projekte-Tab, sofern noch kein Titel erkannt wird) ändert sich.
          Umlaute, Leerzeichen und Sonderzeichen werden automatisch angepasst; existiert der Name schon, hängt
          das System „-2", „-3" … an.
        </p>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (kannUmbenennen) onUmbenennen(name.trim());
          }}
        >
          <Input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={wirdAusgefuehrt}
            aria-label="Neuer Ordnername"
          />

          {fehler && (
            <p className="mt-3 whitespace-pre-line rounded-lg border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-400">
              {fehler}
            </p>
          )}

          <div className="mt-5 flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={onAbbrechen} disabled={wirdAusgefuehrt}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={!kannUmbenennen}>
              {wirdAusgefuehrt ? "..." : "Umbenennen"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
