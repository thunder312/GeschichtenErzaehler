import { useState } from "react";
import { Button } from "./ui";

/** Was mit der Kopie des Projekts auf der ANDEREN Seite des Abgleichs
 * (siehe SyncPanel.tsx) passieren kann:
 * - "lokal": dies ist der PC, der Server ist die Gegenstelle - die lokalen
 *   Projektdateien lassen sich direkt entfernen (nach Hochladen/Abgleich).
 * - "vormerken": dies ist der Server, es gibt vermutlich eine Kopie auf dem
 *   PC - sie wird beim nächsten Abgleich dort zum Entfernen angeboten.
 * - null: kein Abgleich eingerichtet bzw. keine Kopie vorhanden. */
export type AbgleichAufraeumen = "lokal" | "vormerken" | null;

interface ProjektBereinigenDialogProps {
  wirdAusgefuehrt: boolean;
  abgleichAufraeumen: AbgleichAufraeumen;
  onBereinigen: (fundusAktualisieren: boolean, abgleichAufraeumen: boolean) => void;
  onUeberspringen: (fundusAktualisieren: boolean, abgleichAufraeumen: boolean) => void;
}

/** Dialog nach "Prüfung abschließen" (siehe PruefenAnwendenPage.tsx) - bietet
 * an, das fertig geprüfte Projekt von Backup- und Zwischenstand-Dateien zu
 * befreien. Der Fundus-Haken ist bewusst UNABHÄNGIG von "Bereinigen"/
 * "Nicht bereinigen": beide Buttons respektieren ihn gleichermaßen, nur die
 * Datei-Aufräumung selbst ist optional. Gleiches Overlay-/Karten-Muster wie
 * ConfirmDialog.tsx, aber mit einer eigenen Komponente statt einer Erweiterung
 * von ConfirmDialog, weil hier zusätzlich zum Text noch die Checkbox und ein
 * dritter Zustand (Bereinigen vs. Überspringen, beide ggf. mit Fundus-Update)
 * gebraucht werden. */
export function ProjektBereinigenDialog({
  wirdAusgefuehrt,
  abgleichAufraeumen,
  onBereinigen,
  onUeberspringen,
}: ProjektBereinigenDialogProps) {
  const [fundusAktualisieren, setFundusAktualisieren] = useState(true);
  const [kopieAufraeumen, setKopieAufraeumen] = useState(true);
  const aufraeumenAktiv = abgleichAufraeumen !== null && kopieAufraeumen;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={() => onUeberspringen(fundusAktualisieren, aufraeumenAktiv)}
    >
      <div
        className="relative mx-auto max-w-md rounded-2xl border border-border bg-surface p-6 shadow-2xl shadow-black/50"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="font-heading mb-2 text-lg font-semibold text-text">Projekt bereinigen?</h3>
        <p className="mb-4 text-sm text-text-muted">
          Löscht alle „.bak"-Sicherungsdateien sowie alle Zwischenstände bis auf den letzten. Kapitel, Gerüst,
          Verbotsliste und Personas bleiben unangetastet - das Projekt bleibt vollständig für ein späteres
          „Neu schreiben" nutzbar.
        </p>

        <label className="mb-5 flex items-start gap-2 border-t border-border pt-4 text-sm text-text">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={fundusAktualisieren}
            onChange={(e) => setFundusAktualisieren(e.target.checked)}
            disabled={wirdAusgefuehrt}
          />
          <span>
            Personen-Fundus mit den Figuren dieses Projekts aktualisieren
            <span className="block text-xs text-text-muted">
              Unabhängig davon, ob das Projekt bereinigt wird.
            </span>
          </span>
        </label>

        {abgleichAufraeumen && (
          <label className="mb-5 flex items-start gap-2 text-sm text-text">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={kopieAufraeumen}
              onChange={(e) => setKopieAufraeumen(e.target.checked)}
              disabled={wirdAusgefuehrt}
            />
            <span>
              {abgleichAufraeumen === "lokal"
                ? "Lokale Projektdateien auf diesem PC aufräumen"
                : "Kopie auf dem PC beim nächsten Abgleich aufräumen"}
              <span className="block text-xs text-text-muted">
                {abgleichAufraeumen === "lokal"
                  ? "Der Stand wird vorher zum Server übertragen, danach wird der lokale Projektordner entfernt. Exportierte PDFs daneben bleiben."
                  : "Merkt die lokale Kopie zum Entfernen vor – der PC bietet es im Abgleich an."}
              </span>
            </span>
          </label>
        )}

        <div className="flex justify-end gap-2">
          <Button
            variant="secondary"
            onClick={() => onUeberspringen(fundusAktualisieren, aufraeumenAktiv)}
            disabled={wirdAusgefuehrt}
          >
            Nicht bereinigen
          </Button>
          <Button onClick={() => onBereinigen(fundusAktualisieren, aufraeumenAktiv)} disabled={wirdAusgefuehrt}>
            {wirdAusgefuehrt ? "..." : "Bereinigen"}
          </Button>
        </div>
      </div>
    </div>
  );
}
