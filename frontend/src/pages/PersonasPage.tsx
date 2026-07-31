import Editor from "@monaco-editor/react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Button, Card, CardTitle } from "../components/ui";

interface PersonasPageProps {
  ordner: string;
}

const BESCHRIFTUNG: Record<string, string> = {
  architekt: "🗺️ Architekt",
  autor: "✍️ Autor",
  pruefer_anachronismus: "🔍 Anachronismus- & Stimmigkeits-Prüfer",
  chronist: "📖 Chronist",
  pruefer_kontinuitaet: "🔗 Kontinuitäts-Prüfer",
  lektor: "🪄 Lektor",
  pruefer_satzbau: "📐 Satzbau-Prüfer (Verb-Letzt)",
};

/** Editor fuer die Rollen-Prompts (personas/*.txt) dieses Projekts. Jedes
 * Projekt haelt beim Anlegen eine eigene Kopie der 6 Personas (siehe
 * app/core/projekt_dateien.py:projekt_anlegen) - Aenderungen hier wirken
 * sich deshalb nur auf DIESES Projekt aus, nicht auf die zentrale
 * Epochen-/Personas-Bibliothek. */
export function PersonasPage({ ordner }: PersonasPageProps) {
  const [namen, setNamen] = useState<string[]>([]);
  const [ausgewaehlt, setAusgewaehlt] = useState<string | null>(null);
  const [inhalt, setInhalt] = useState("");
  const [wirdGeladen, setWirdGeladen] = useState(true);
  const [wirdGespeichert, setWirdGespeichert] = useState(false);
  const [gespeichertHinweis, setGespeichertHinweis] = useState<string | null>(null);

  useEffect(() => {
    api.personasAuflisten(ordner).then((liste) => {
      setNamen(liste);
      if (liste.length > 0) setAusgewaehlt(liste[0]);
    });
  }, [ordner]);

  useEffect(() => {
    if (!ausgewaehlt) return;
    setWirdGeladen(true);
    setGespeichertHinweis(null);
    api.personaLesen(ordner, ausgewaehlt).then((text) => {
      setInhalt(text);
      setWirdGeladen(false);
    });
  }, [ordner, ausgewaehlt]);

  async function speichern() {
    if (!ausgewaehlt) return;
    setWirdGespeichert(true);
    setGespeichertHinweis(null);
    try {
      await api.personaSchreiben(ordner, ausgewaehlt, inhalt);
      setGespeichertHinweis("Gespeichert.");
    } finally {
      setWirdGespeichert(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 p-6 lg:grid-cols-[1fr_3fr]">
      <Card>
        <CardTitle>🎭 Personas</CardTitle>
        <ul className="space-y-1">
          {namen.map((name) => (
            <li key={name}>
              <button
                onClick={() => setAusgewaehlt(name)}
                className={`w-full rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                  ausgewaehlt === name
                    ? "bg-accent-soft text-accent-light"
                    : "text-text-muted hover:bg-surface-hover hover:text-text"
                }`}
              >
                {BESCHRIFTUNG[name] ?? name}
              </button>
            </li>
          ))}
        </ul>
      </Card>

      <Card className="p-0">
        <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
          <h2 className="font-heading text-lg font-semibold tracking-wide text-text">
            {ausgewaehlt ? (BESCHRIFTUNG[ausgewaehlt] ?? ausgewaehlt) : "Persona wählen"}
          </h2>
          <div className="flex items-center gap-3">
            {gespeichertHinweis && <span className="text-xs text-accent-light">{gespeichertHinweis}</span>}
            <Button onClick={speichern} disabled={wirdGespeichert || wirdGeladen || !ausgewaehlt}>
              {wirdGespeichert ? "Speichert..." : "Speichern"}
            </Button>
          </div>
        </div>
        <Editor
          height="640px"
          defaultLanguage="markdown"
          value={inhalt}
          onChange={(v) => setInhalt(v ?? "")}
          theme="vs-dark"
          options={{ wordWrap: "on", minimap: { enabled: false }, fontSize: 14 }}
        />
      </Card>
    </div>
  );
}
