import Editor from "@monaco-editor/react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ProjektDetail } from "../api/types";
import { CollapsibleCard } from "../components/CollapsibleCard";
import { Badge, Button, Card, CardTitle } from "../components/ui";

// Anzeige-Mapping der intern aus dem Gerüst erkannten Content-Stufe (siehe
// backend/app/core/rollen.py: STUFE_DIREKTIVEN) auf die aus Filmen bekannten
// FSK-Alterskennzeichen - "voll" klang vorher wie "Jugendschutz voll aktiv",
// war aber genau das Gegenteil (voll explizit, keine Einschraenkung).
const JUGENDSCHUTZ_ANZEIGE: Record<string, { label: string; tone: "green" | "amber" }> = {
  jugendfrei: { label: "FSK 0 · jugendfrei", tone: "green" },
  angedeutet: { label: "FSK 12 · angedeutet", tone: "green" },
  voll: { label: "FSK 18 · voll explizit", tone: "amber" },
};

interface GeruestPageProps {
  ordner: string;
  projekt: ProjektDetail | null;
  onGeaendert: () => void;
  onOrdnerUmbenannt: (neuerOrdner: string) => void;
  onInterviewStarten: () => void;
}

/** Rohtext-Ansicht von geruest.md, fuer die manuelle Nachjustierung NACH dem
 * Architekten-Interview (siehe ArchitektInterviewPage - das ist der
 * eigentliche Weg, ein Gerüst zu erzeugen). Die Feldererkennung (Jahr,
 * Jugendschutz-Stufe, Autor-Modell, Kapitelplan, ...) laeuft serverseitig
 * exakt wie im CLI (siehe backend/app/core/geruest.py) und wird hier zur
 * Kontrolle angezeigt. Verbotsliste (fuer die Anachronismus-Pruefung)
 * liegt gleich daneben, da beide Dateien zusammen das Setting definieren. */
export function GeruestPage({ ordner, projekt, onGeaendert, onOrdnerUmbenannt, onInterviewStarten }: GeruestPageProps) {
  const [inhalt, setInhalt] = useState(projekt?.geruest ?? "");
  const [wirdGespeichert, setWirdGespeichert] = useState(false);
  const [gespeichertHinweis, setGespeichertHinweis] = useState<string | null>(null);

  const [verbotslisteInhalt, setVerbotslisteInhalt] = useState(projekt?.verbotsliste ?? "");
  const [verbotslisteWirdGespeichert, setVerbotslisteWirdGespeichert] = useState(false);
  const [verbotslisteHinweis, setVerbotslisteHinweis] = useState<string | null>(null);

  const [architektenGespraech, setArchitektenGespraech] = useState<string | null>(null);

  useEffect(() => {
    setInhalt(projekt?.geruest ?? "");
    setVerbotslisteInhalt(projekt?.verbotsliste ?? "");
    setArchitektenGespraech(null);
    api
      .architektenGespraech(ordner)
      .then(setArchitektenGespraech)
      .catch(() => setArchitektenGespraech(null));
  }, [projekt?.geruest, projekt?.verbotsliste, ordner]);

  async function speichern() {
    setWirdGespeichert(true);
    setGespeichertHinweis(null);
    try {
      const antwort = await api.geruestSchreiben(ordner, inhalt);
      if (antwort.neuer_ordner) {
        onOrdnerUmbenannt(antwort.neuer_ordner);
        setGespeichertHinweis(`Gespeichert - Ordner umbenannt in "${antwort.neuer_ordner}".`);
      } else {
        onGeaendert();
        setGespeichertHinweis("Gespeichert.");
      }
    } finally {
      setWirdGespeichert(false);
    }
  }

  async function verbotslisteSpeichern() {
    setVerbotslisteWirdGespeichert(true);
    setVerbotslisteHinweis(null);
    try {
      await api.verbotslisteSchreiben(ordner, verbotslisteInhalt);
      onGeaendert();
      setVerbotslisteHinweis("Gespeichert.");
    } finally {
      setVerbotslisteWirdGespeichert(false);
    }
  }

  return (
    <div className="grid grid-cols-1 items-start gap-6 p-6 lg:grid-cols-[2fr_1fr]">
      <CollapsibleCard
        title="🗺️ geruest.md"
        aktionen={
          <>
            {gespeichertHinweis && <span className="text-xs text-accent-light">{gespeichertHinweis}</span>}
            <Button variant="secondary" onClick={onInterviewStarten}>
              Interview neu führen
            </Button>
            <Button onClick={speichern} disabled={wirdGespeichert}>
              {wirdGespeichert ? "Speichert..." : "Speichern"}
            </Button>
          </>
        }
      >
        <Editor
          height="560px"
          defaultLanguage="markdown"
          value={inhalt}
          onChange={(v) => setInhalt(v ?? "")}
          theme="vs-dark"
          options={{ wordWrap: "on", minimap: { enabled: false }, fontSize: 14 }}
        />
      </CollapsibleCard>

      <div className="space-y-6">
        <Card>
          <CardTitle>Erkannte Felder</CardTitle>
          <dl className="space-y-2.5 text-sm">
            <div className="flex items-center justify-between">
              <dt className="text-text-muted">Jahr</dt>
              <dd>{projekt?.jahr ?? "–"}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-text-muted">Content-Stufe</dt>
              <dd>
                {projekt?.jugendschutz_stufe && JUGENDSCHUTZ_ANZEIGE[projekt.jugendschutz_stufe] ? (
                  <Badge tone={JUGENDSCHUTZ_ANZEIGE[projekt.jugendschutz_stufe].tone}>
                    {JUGENDSCHUTZ_ANZEIGE[projekt.jugendschutz_stufe].label}
                  </Badge>
                ) : (
                  <Badge>–</Badge>
                )}
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

        <CollapsibleCard
          title="🚫 verbotsliste.md"
          aktionen={
            <>
              {verbotslisteHinweis && <span className="text-xs text-accent-light">{verbotslisteHinweis}</span>}
              <Button onClick={verbotslisteSpeichern} disabled={verbotslisteWirdGespeichert}>
                {verbotslisteWirdGespeichert ? "Speichert..." : "Speichern"}
              </Button>
            </>
          }
        >
          <Editor
            height="320px"
            defaultLanguage="markdown"
            value={verbotslisteInhalt}
            onChange={(v) => setVerbotslisteInhalt(v ?? "")}
            theme="vs-dark"
            options={{ wordWrap: "on", minimap: { enabled: false }, fontSize: 13 }}
          />
        </CollapsibleCard>

        {architektenGespraech && (
          <CollapsibleCard title="📜 Architekten-Gespräch" defaultOffen={false}>
            <pre className="max-h-[400px] overflow-auto whitespace-pre-wrap p-4 text-sm text-text">
              {architektenGespraech}
            </pre>
          </CollapsibleCard>
        )}
      </div>
    </div>
  );
}
