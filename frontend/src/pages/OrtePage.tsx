import Editor from "@monaco-editor/react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { CollapsibleCard } from "../components/CollapsibleCard";
import { OrteEditor } from "../components/OrteEditor";
import { Button, Card, CardTitle } from "../components/ui";

/** Orte-Fundus: strukturierter Editor (OrteEditor.tsx) als Standardansicht,
 * gleicher Aufbau wie FundusPage.tsx (Personen-Fundus) - die rohe orte.md
 * bleibt als Kontroll-/Notfall-Ansicht verfuegbar (eingeklappte
 * CollapsibleCard). Anders als beim Personen-Fundus gibt es hier keinen
 * Import-Button - Orte werden ausschliesslich manuell gepflegt. */
export function OrtePage() {
  const [inhalt, setInhalt] = useState("");
  const [wirdGeladen, setWirdGeladen] = useState(true);
  const [wirdGespeichert, setWirdGespeichert] = useState(false);
  const [gespeichertHinweis, setGespeichertHinweis] = useState<string | null>(null);

  useEffect(() => {
    laden();
  }, []);

  function laden() {
    setWirdGeladen(true);
    api.orteLesen().then((text) => {
      setInhalt(text);
      setWirdGeladen(false);
    });
  }

  async function speichern() {
    setWirdGespeichert(true);
    setGespeichertHinweis(null);
    try {
      await api.orteSchreiben(inhalt);
      setGespeichertHinweis("Gespeichert.");
    } finally {
      setWirdGespeichert(false);
    }
  }

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <Card>
        <CardTitle>🗺️ Orte-Fundus</CardTitle>
        <p className="text-sm text-text-muted">
          Sammelt wiederverwendbare Schauplätze mit Beschreibung, getrennt nach Epoche - beim Ausfüllen des
          Kapitelplans im Feld "Ort" auswählbar, analog zum Personen-Fundus.
        </p>
      </Card>

      <OrteEditor onGeaendert={laden} />

      <CollapsibleCard title="📄 Rohtext (.md) zur Kontrolle" defaultOffen={false}>
        <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
          <p className="text-xs text-text-muted">
            Nur zur Kontrolle oder für Bearbeitungen, die der Editor oben (noch) nicht abdeckt.
          </p>
          <div className="flex items-center gap-3">
            {gespeichertHinweis && <span className="text-xs text-accent-light">{gespeichertHinweis}</span>}
            <Button onClick={speichern} disabled={wirdGespeichert || wirdGeladen}>
              {wirdGespeichert ? "Speichert..." : "Speichern"}
            </Button>
          </div>
        </div>
        <Editor
          height="clamp(320px, 70vh, 640px)"
          defaultLanguage="markdown"
          value={inhalt}
          onChange={(v) => setInhalt(v ?? "")}
          theme="vs-dark"
          options={{ wordWrap: "on", minimap: { enabled: false }, fontSize: 14 }}
        />
      </CollapsibleCard>
    </div>
  );
}
