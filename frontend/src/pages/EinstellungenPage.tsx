import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Einstellungen } from "../api/types";
import { Badge, Button, Card, CardTitle, Input, Label } from "../components/ui";

export function EinstellungenPage() {
  const [einstellungen, setEinstellungen] = useState<Einstellungen | null>(null);
  const [pfad, setPfad] = useState("");
  const [unterordnerJeEpoche, setUnterordnerJeEpoche] = useState(false);
  const [bildgeneratorUrl, setBildgeneratorUrl] = useState("");
  const [laden, setLaden] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [gespeichert, setGespeichert] = useState(false);

  useEffect(() => {
    api.einstellungen().then((e) => {
      setEinstellungen(e);
      setPfad(e.projects_dir);
      setUnterordnerJeEpoche(e.unterordner_je_epoche);
      setBildgeneratorUrl(e.bildgenerator_url);
    });
  }, []);

  async function speichern(neuerPfad: string, neuUnterordnerJeEpoche: boolean, neueBildgeneratorUrl: string) {
    setLaden(true);
    setFehler(null);
    setGespeichert(false);
    try {
      const antwort = await api.einstellungenSchreiben(neuerPfad, neuUnterordnerJeEpoche, neueBildgeneratorUrl);
      setEinstellungen(antwort);
      setPfad(antwort.projects_dir);
      setUnterordnerJeEpoche(antwort.unterordner_je_epoche);
      setBildgeneratorUrl(antwort.bildgenerator_url);
      setGespeichert(true);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLaden(false);
    }
  }

  async function unterordnerUmschalten(checked: boolean) {
    setUnterordnerJeEpoche(checked);
    await speichern(pfad, checked, bildgeneratorUrl);
  }

  return (
    <div className="max-w-2xl space-y-6 p-4 sm:p-6">
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
              <Button
                onClick={() => speichern(pfad, unterordnerJeEpoche, bildgeneratorUrl)}
                disabled={laden || pfad.trim() === ""}
              >
                {laden ? "Speichert..." : "Speichern"}
              </Button>
              {!einstellungen.ist_standard && (
                <Button
                  variant="secondary"
                  onClick={() => speichern("", unterordnerJeEpoche, bildgeneratorUrl)}
                  disabled={laden}
                >
                  Zurück auf Standard
                </Button>
              )}
            </div>
            <p className="text-xs text-text-muted">
              Bereits angelegte Projekte bleiben an ihrem bisherigen Ort - die Änderung gilt für neu
              angelegte Projekte und dafür, wo die Projektliste nachschaut.
            </p>

            <label className="flex items-start gap-2 border-t border-border pt-3 text-sm text-text">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={unterordnerJeEpoche}
                onChange={(e) => unterordnerUmschalten(e.target.checked)}
                disabled={laden}
              />
              <span>
                Automatisch Unterordner je Epoche anlegen und benutzen
                <span className="mt-0.5 block text-xs text-text-muted">
                  Ein neues Projekt landet dann in "Ordner für Projekte/&lt;Epoche&gt;/&lt;Geschichte&gt;" statt
                  direkt in "Ordner für Projekte/&lt;Geschichte&gt;" - erspart das manuelle Umstellen des
                  Speicherorts beim Wechsel zwischen Epochen. Gilt nur für neu angelegte Projekte.
                </span>
              </span>
            </label>
          </div>
        )}
      </Card>

      <Card>
        <CardTitle>🎨 Externer Bildgenerator</CardTitle>
        <p className="mb-3 text-sm text-text-muted">
          Link zu einer Web-Oberfläche, mit der sich von Hand (z. B. kostenlos) ein Titelbild
          erzeugen lässt - erscheint als Schnellzugriff im Titelbild-Bereich unter "Stand &amp;
          Export", neben dem Hochladen eines fertigen Bildes.
        </p>
        {einstellungen && (
          <div className="space-y-3">
            <div>
              <Label>Link zum Bildgenerator</Label>
              <Input
                value={bildgeneratorUrl}
                onChange={(e) => setBildgeneratorUrl(e.target.value)}
                placeholder={einstellungen.bildgenerator_url}
              />
            </div>
            <div className="flex items-center gap-2 text-xs text-text-muted">
              {einstellungen.bildgenerator_url_ist_standard ? (
                <Badge>Standard-Link</Badge>
              ) : (
                <Badge tone="green">Angepasster Link</Badge>
              )}
            </div>
            <div className="flex gap-2">
              <Button
                onClick={() => speichern(pfad, unterordnerJeEpoche, bildgeneratorUrl)}
                disabled={laden || bildgeneratorUrl.trim() === ""}
              >
                {laden ? "Speichert..." : "Speichern"}
              </Button>
              {!einstellungen.bildgenerator_url_ist_standard && (
                <Button
                  variant="secondary"
                  onClick={() => speichern(pfad, unterordnerJeEpoche, "")}
                  disabled={laden}
                >
                  Zurück auf Standard
                </Button>
              )}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
