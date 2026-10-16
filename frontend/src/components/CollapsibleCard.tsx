import { useState, type ReactNode } from "react";
import { Card } from "./ui";

interface CollapsibleCardProps {
  title: ReactNode;
  children: ReactNode;
  /** Startzustand beim ersten Rendern - true fuer Container, die man i.d.R.
   * gleich braucht (Editoren), false fuer eher selten gebrauchte Zusatzinfos
   * (z.B. Lauf-Historie). */
  defaultOffen?: boolean;
  className?: string;
  /** Zusaetzliche Elemente in der Kopfzeile, links vom Auf/Zu-Toggle (z.B.
   * "Gespeichert."-Hinweis, Speichern-Button). */
  aktionen?: ReactNode;
}

/** Verallgemeinerte Fassung des Auf/Zu-Musters, das zuerst beim
 * Architekten-Gespraech-Container (GeruestPage) eingefuehrt wurde: Kopfzeile
 * mit Titel + Text-Toggle, Inhalt nur gerendert, wenn aufgeklappt. Bewusst
 * KEIN natives `<details>` (das kollabiert Editor-Kinder wie Monaco nicht
 * sauber, weil sie beim Aufklappen ihre Groesse nicht neu berechnen) und
 * bewusst kein Padding um `children` (Editoren sollen randlos bleiben,
 * Aufrufer mit anderem Inhalt padden selbst). */
export function CollapsibleCard({ title, children, defaultOffen = true, className = "", aktionen }: CollapsibleCardProps) {
  const [offen, setOffen] = useState(defaultOffen);
  return (
    <Card className={`p-0 ${offen ? "" : "!shrink-0"} ${className}`}>
      {/* Die ganze Kopfzeile ist klickbar; Elemente in `aktionen` (Buttons,
          Hinweise) stoppen das Event, damit sie nicht mit-umschalten. */}
      <div
        onClick={() => setOffen((bisher) => !bisher)}
        className={`flex cursor-pointer flex-wrap items-center justify-between gap-3 px-4 py-2.5 hover:bg-surface-hover/40 ${offen ? "border-b border-border" : ""}`}
      >
        <h2 className="font-heading text-lg font-semibold tracking-wide text-text">{title}</h2>
        <div className="flex flex-wrap items-center gap-3">
          <div onClick={(e) => e.stopPropagation()} className="flex flex-wrap items-center gap-3 cursor-default">
            {aktionen}
          </div>
          <span className="text-xs text-accent-light">{offen ? "Einklappen" : "Ausklappen"}</span>
        </div>
      </div>
      {offen && children}
    </Card>
  );
}
