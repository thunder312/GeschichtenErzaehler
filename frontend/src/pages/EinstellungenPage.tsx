import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Einstellungen } from "../api/types";
import { Badge, Button, Card, CardTitle, Input, Label } from "../components/ui";

export function EinstellungenPage() {
  const [einstellungen, setEinstellungen] = useState<Einstellungen | null>(null);
  const [pfad, setPfad] = useState("");
  const [laden, setLaden] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [gespeichert, setGespeichert] = useState(false);

  useEffect(() => {
    api.einstellungen().then((e) => {
      setEinstellungen(e);
      setPfad(e.projects_dir);
    });
  }, []);

  async function speichern(neuerPfad: string) {
    setLaden(true);
    setFehler(null);
    setGespeichert(false);
    try {
      const antwort = await api.einstellungenSchreiben(neuerPfad);
      setEinstellungen(antwort);
      setPfad(antwort.projects_dir);
      setGespeichert(true);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLaden(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-6 p-6">
      <Card>
        <CardTitle>🗂️ Speicherort der Geschichten</CardTitle>
        <p className="mb-3 text-sm text-text-muted">
          Hier legen alle Projekte ihre Dateien ab (Gerüst, Kapitel, Personas, ...) - unabhängig vom
          gewählten KI-Ziel. Athene &amp; Co. bekommen den Text nur zum Schreiben/Prüfen geschickt, die
          Ergebnisse landen ausschließlich hier auf dieser Festplatte.
        </p>
        {einstellungen && (
          <div className="space-y-3">
            <div>
              <Label>Ordner für Projekte</Label>
              <Input value={pfad} onChange={(e) => setPfad(e.target.value)} placeholder={einstellungen.standard_projects_dir} />
            </div>
            <div className="flex items-center gap-2 text-xs text-text-muted">
              {einstellungen.ist_standard ? (
                <Badge>Standardpfad</Badge>
              ) : (
                <Badge tone="green">Angepasster Pfad</Badge>
              )}
              <span>Standard: {einstellungen.standard_projects_dir}</span>
            </div>
            {fehler && <p className="text-sm text-red-400">{fehler}</p>}
            {gespeichert && !fehler && <p className="text-sm text-accent-light">Gespeichert.</p>}
            <div className="flex gap-2">
              <Button onClick={() => speichern(pfad)} disabled={laden || pfad.trim() === ""}>
                {laden ? "Speichert..." : "Speichern"}
              </Button>
              {!einstellungen.ist_standard && (
                <Button variant="secondary" onClick={() => speichern("")} disabled={laden}>
                  Zurück auf Standard
                </Button>
              )}
            </div>
            <p className="text-xs text-text-muted">
              Bereits angelegte Projekte bleiben an ihrem bisherigen Ort - die Änderung gilt für neu
              angelegte Projekte und dafür, wo die Projektliste nachschaut.
            </p>
          </div>
        )}
      </Card>
    </div>
  );
}
