import Editor from "@monaco-editor/react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Button, Card, CardTitle } from "../components/ui";
import { useAktivitaet } from "../context/AktivitaetContext";

interface FundusPageProps {
  sshZielId: string;
}

/** Editor fuer den Personen-Fundus (fundus.md) - eine einzige, nutzerweite
 * Datei statt einer Auswahlliste wie bei PersonasPage, da es hier keine
 * mehreren Rollen-Dateien gibt (siehe backend/app/core/fundus.py). Der
 * Import-Button braucht sshZielId wie jede andere Ollama-aufrufende Seite
 * (siehe SchreibenPage/PruefenAnwendenPage) - ohne das faellt der Aufruf
 * serverseitig auf das lokale Standard-Ollama zurueck, das z.B. auf dem
 * Produktivserver gar nicht existiert. */
export function FundusPage({ sshZielId }: FundusPageProps) {
  const [inhalt, setInhalt] = useState("");
  const [wirdGeladen, setWirdGeladen] = useState(true);
  const [wirdGespeichert, setWirdGespeichert] = useState(false);
  const [gespeichertHinweis, setGespeichertHinweis] = useState<string | null>(null);
  const [importHinweis, setImportHinweis] = useState<string | null>(null);
  const { aktivitaet, starten, beenden } = useAktivitaet();

  useEffect(() => {
    laden();
  }, []);

  function laden() {
    setWirdGeladen(true);
    api.fundusLesen().then((text) => {
      setInhalt(text);
      setWirdGeladen(false);
    });
  }

  async function speichern() {
    setWirdGespeichert(true);
    setGespeichertHinweis(null);
    try {
      await api.fundusSchreiben(inhalt);
      setGespeichertHinweis("Gespeichert.");
    } finally {
      setWirdGespeichert(false);
    }
  }

  async function importieren() {
    setImportHinweis(null);
    starten("Durchsucht vorhandene Geschichten nach Figuren...");
    try {
      const antwort = await api.fundusImportieren(sshZielId);
      setImportHinweis(
        `${antwort.importierte_projekte} Projekt(e) durchsucht, ` +
          `${antwort.gefundene_figuren} Figur(en) gefunden` +
          (antwort.uebersprungen.length > 0
            ? ` (${antwort.uebersprungen.length} ohne Figuren-Abschnitt übersprungen).`
            : "."),
      );
      laden();
    } finally {
      beenden();
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 p-6 lg:grid-cols-[1fr_3fr]">
      <Card>
        <CardTitle>🧬 Personen-Fundus</CardTitle>
        <p className="text-sm text-text-muted">
          Sammelt Figuren aus abgeschlossenen Geschichten, getrennt nach Epoche, damit der Architekt sie bei neuen
          Geschichten vorschlagen kann.
        </p>
        <Button
          className="mt-4 w-full"
          variant="secondary"
          onClick={importieren}
          disabled={!!aktivitaet}
        >
          {aktivitaet ? "Importiert..." : "Aus vorhandenen Geschichten importieren"}
        </Button>
        {importHinweis && <p className="mt-2 text-xs text-text-muted">{importHinweis}</p>}
      </Card>

      <Card className="p-0">
        <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
          <h2 className="font-heading text-lg font-semibold tracking-wide text-text">Personen-Fundus</h2>
          <div className="flex items-center gap-3">
            {gespeichertHinweis && <span className="text-xs text-accent-light">{gespeichertHinweis}</span>}
            <Button onClick={speichern} disabled={wirdGespeichert || wirdGeladen}>
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
