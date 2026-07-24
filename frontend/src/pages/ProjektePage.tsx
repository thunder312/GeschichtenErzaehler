import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { EpocheKurz, ProjektKurz } from "../api/types";
import { Button, Card, CardTitle, Input, Label, Select } from "../components/ui";

interface ProjektePageProps {
  projekte: ProjektKurz[];
  aktuellesProjekt: string | null;
  onProjekteGeaendert: () => void;
  onProjektAuswaehlen: (ordner: string) => void;
}

export function ProjektePage({
  projekte,
  aktuellesProjekt,
  onProjekteGeaendert,
  onProjektAuswaehlen,
}: ProjektePageProps) {
  const [epochen, setEpochen] = useState<EpocheKurz[]>([]);
  const [titel, setTitel] = useState("");
  const [epoche, setEpoche] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [wirdAngelegt, setWirdAngelegt] = useState(false);

  useEffect(() => {
    api.epochen().then((liste) => {
      setEpochen(liste);
      if (liste.length > 0) setEpoche(liste[0].name);
    });
  }, []);

  async function anlegen() {
    if (!epoche) return;
    setWirdAngelegt(true);
    setFehler(null);
    try {
      const neues = await api.projektAnlegen(titel.trim(), epoche);
      setTitel("");
      onProjekteGeaendert();
      onProjektAuswaehlen(neues.ordner);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setWirdAngelegt(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 p-6 md:grid-cols-[2fr_1fr]">
      <Card>
        <CardTitle>📚 Vorhandene Projekte</CardTitle>
        {projekte.length === 0 ? (
          <p className="text-sm text-text-muted">Noch kein Projekt angelegt.</p>
        ) : (
          <ul className="divide-y divide-border">
            {projekte.map((p) => (
              <li
                key={p.ordner}
                onClick={() => onProjektAuswaehlen(p.ordner)}
                className={`cursor-pointer rounded-lg px-3 py-2.5 text-sm transition-colors hover:bg-surface-hover ${
                  aktuellesProjekt === p.ordner ? "bg-accent-soft" : ""
                }`}
              >
                <div className="font-medium text-text">{p.titel ?? p.ordner}</div>
                <div className="text-xs text-text-muted">
                  {p.epoche ?? "unbekannte Epoche"} · {p.anzahl_kapitel} Kapitel
                  {p.letztes_geplantes_kapitel ? ` von ${p.letztes_geplantes_kapitel} geplant` : ""}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <CardTitle>✨ Neues Projekt anlegen</CardTitle>
        <div className="space-y-3">
          <div>
            <Label>Titel (optional)</Label>
            <Input value={titel} onChange={(e) => setTitel(e.target.value)} placeholder="ergibt sich oft erst im Architekten-Interview" />
          </div>
          <div>
            <Label>Epoche</Label>
            <Select value={epoche} onChange={(e) => setEpoche(e.target.value)}>
              {epochen.map((e) => (
                <option key={e.name} value={e.name}>
                  {e.name}
                </option>
              ))}
            </Select>
          </div>
          {fehler && <p className="text-sm text-red-400">{fehler}</p>}
          <Button onClick={anlegen} disabled={wirdAngelegt || !epoche}>
            {wirdAngelegt ? "Wird angelegt..." : "Anlegen"}
          </Button>
        </div>
      </Card>
    </div>
  );
}
