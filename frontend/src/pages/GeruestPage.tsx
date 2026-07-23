import Editor from "@monaco-editor/react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ProjektDetail } from "../api/types";
import { Badge, Button, Card, CardTitle } from "../components/ui";

interface GeruestPageProps {
  ordner: string;
  projekt: ProjektDetail | null;
  onGeaendert: () => void;
}

/** "Architekt"-Tab. Das volle interaktive Interview aus novelle.py
 * (13 Fragen per input()) ist hier bewusst noch nicht als gefuehrter Dialog
 * nachgebaut - fuer den ersten Ausbauschritt kann das Gerüst direkt als
 * Markdown editiert werden. Die Feldererkennung (Jahr, Jugendschutz-Stufe,
 * Autor-Modell, Kapitelplan, ...) laeuft serverseitig exakt wie im CLI
 * (siehe backend/app/core/geruest.py) und wird hier zur Kontrolle
 * angezeigt. */
export function GeruestPage({ ordner, projekt, onGeaendert }: GeruestPageProps) {
  const [inhalt, setInhalt] = useState(projekt?.geruest ?? "");
  const [wirdGespeichert, setWirdGespeichert] = useState(false);
  const [gespeichertHinweis, setGespeichertHinweis] = useState<string | null>(null);

  useEffect(() => {
    setInhalt(projekt?.geruest ?? "");
  }, [projekt?.geruest, ordner]);

  async function speichern() {
    setWirdGespeichert(true);
    setGespeichertHinweis(null);
    try {
      await api.geruestSchreiben(ordner, inhalt);
      onGeaendert();
      setGespeichertHinweis("Gespeichert.");
    } finally {
      setWirdGespeichert(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 p-6 lg:grid-cols-[2fr_1fr]">
      <Card className="p-0">
        <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
          <h2 className="font-heading text-lg font-semibold tracking-wide text-text">🗺️ geruest.md</h2>
          <div className="flex items-center gap-3">
            {gespeichertHinweis && <span className="text-xs text-accent-light">{gespeichertHinweis}</span>}
            <Button onClick={speichern} disabled={wirdGespeichert}>
              {wirdGespeichert ? "Speichert..." : "Speichern"}
            </Button>
          </div>
        </div>
        <Editor
          height="560px"
          defaultLanguage="markdown"
          value={inhalt}
          onChange={(v) => setInhalt(v ?? "")}
          theme="vs-dark"
          options={{ wordWrap: "on", minimap: { enabled: false }, fontSize: 14 }}
        />
      </Card>

      <Card>
        <CardTitle>Erkannte Felder</CardTitle>
        <dl className="space-y-2.5 text-sm">
          <div className="flex items-center justify-between">
            <dt className="text-text-muted">Jahr</dt>
            <dd>{projekt?.jahr ?? "–"}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-text-muted">Jugendschutz-Stufe</dt>
            <dd>
              <Badge tone={projekt?.jugendschutz_stufe === "voll" ? "amber" : "green"}>
                {projekt?.jugendschutz_stufe ?? "–"}
              </Badge>
            </dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-text-muted">Autor-Modell</dt>
            <dd>{projekt?.autor_modell ?? "–"}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-text-muted">Automatische Fortsetzung</dt>
            <dd>
              <Badge tone={projekt?.automatische_fortsetzung ? "amber" : "green"}>
                {projekt?.automatische_fortsetzung ? "Ein" : "Aus"}
              </Badge>
            </dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-text-muted">Letztes geplantes Kapitel</dt>
            <dd>{projekt?.letztes_geplantes_kapitel ?? "–"}</dd>
          </div>
        </dl>

        {projekt && Object.keys(projekt.kapitelplan).length > 0 && (
          <>
            <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-text-muted">
              Kapitelplan (Zielwortzahl)
            </h3>
            <ul className="space-y-1 text-sm">
              {Object.entries(projekt.kapitelplan)
                .sort(([a], [b]) => Number(a) - Number(b))
                .map(([n, ziel]) => (
                  <li key={n} className="flex justify-between">
                    <span>Kapitel {n}</span>
                    <span className="text-text-muted">{ziel} Woerter</span>
                  </li>
                ))}
            </ul>
          </>
        )}
      </Card>
    </div>
  );
}
