import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { EpocheKurz, ProjektKurz } from "../api/types";
import { Button, Card, Input, Label, Select } from "../components/ui";

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
    if (!titel.trim() || !epoche) return;
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
        <h2 className="mb-3 text-sm font-semibold text-neutral-700 dark:text-neutral-200">
          Vorhandene Projekte
        </h2>
        {projekte.length === 0 ? (
          <p className="text-sm text-neutral-500">Noch kein Projekt angelegt.</p>
        ) : (
          <ul className="divide-y divide-neutral-200 dark:divide-neutral-800">
            {projekte.map((p) => (
              <li
                key={p.ordner}
                onClick={() => onProjektAuswaehlen(p.ordner)}
                className={`cursor-pointer rounded-md px-2 py-2.5 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-800/60 ${
                  aktuellesProjekt === p.ordner ? "bg-purple-50 dark:bg-purple-950/30" : ""
                }`}
              >
                <div className="font-medium text-neutral-900 dark:text-neutral-100">
                  {p.titel ?? p.ordner}
                </div>
                <div className="text-xs text-neutral-500">
                  {p.epoche ?? "unbekannte Epoche"} · {p.anzahl_kapitel} Kapitel
                  {p.letztes_geplantes_kapitel ? ` von ${p.letztes_geplantes_kapitel} geplant` : ""}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-neutral-700 dark:text-neutral-200">
          Neues Projekt anlegen
        </h2>
        <div className="space-y-3">
          <div>
            <Label>Titel</Label>
            <Input value={titel} onChange={(e) => setTitel(e.target.value)} placeholder="Der Markt von Rothenfeld" />
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
          {fehler && <p className="text-sm text-red-600">{fehler}</p>}
          <Button onClick={anlegen} disabled={wirdAngelegt || !titel.trim()}>
            {wirdAngelegt ? "Wird angelegt..." : "Anlegen"}
          </Button>
        </div>
      </Card>
    </div>
  );
}
