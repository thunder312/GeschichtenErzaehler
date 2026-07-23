import Editor from "@monaco-editor/react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ProjektDetail } from "../api/types";
import { Badge, Button, Card } from "../components/ui";

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
        <div className="flex items-center justify-between border-b border-neutral-200 px-4 py-2 dark:border-neutral-800">
          <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-200">geruest.md</h2>
          <div className="flex items-center gap-3">
            {gespeichertHinweis && <span className="text-xs text-emerald-600">{gespeichertHinweis}</span>}
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
          theme={window.matchMedia("(prefers-color-scheme: dark)").matches ? "vs-dark" : "light"}
          options={{ wordWrap: "on", minimap: { enabled: false }, fontSize: 14 }}
        />
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-neutral-700 dark:text-neutral-200">
          Erkannte Felder
        </h2>
        <dl className="space-y-2.5 text-sm">
          <div className="flex items-center justify-between">
            <dt className="text-neutral-500">Jahr</dt>
            <dd>{projekt?.jahr ?? "–"}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-neutral-500">Jugendschutz-Stufe</dt>
            <dd>
              <Badge tone={projekt?.jugendschutz_stufe === "voll" ? "amber" : "green"}>
                {projekt?.jugendschutz_stufe ?? "–"}
              </Badge>
            </dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-neutral-500">Autor-Modell</dt>
            <dd>{projekt?.autor_modell ?? "–"}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-neutral-500">Automatische Fortsetzung</dt>
            <dd>
              <Badge tone={projekt?.automatische_fortsetzung ? "amber" : "green"}>
                {projekt?.automatische_fortsetzung ? "Ein" : "Aus"}
              </Badge>
            </dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-neutral-500">Letztes geplantes Kapitel</dt>
            <dd>{projekt?.letztes_geplantes_kapitel ?? "–"}</dd>
          </div>
        </dl>

        {projekt && Object.keys(projekt.kapitelplan).length > 0 && (
          <>
            <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-neutral-500">
              Kapitelplan (Zielwortzahl)
            </h3>
            <ul className="space-y-1 text-sm">
              {Object.entries(projekt.kapitelplan)
                .sort(([a], [b]) => Number(a) - Number(b))
                .map(([n, ziel]) => (
                  <li key={n} className="flex justify-between">
                    <span>Kapitel {n}</span>
                    <span className="text-neutral-500">{ziel} Woerter</span>
                  </li>
                ))}
            </ul>
          </>
        )}
      </Card>
    </div>
  );
}
