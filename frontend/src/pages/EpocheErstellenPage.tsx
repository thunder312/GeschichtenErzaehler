import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { EpocheKurz } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Button, Card, CardTitle, Input, Label } from "../components/ui";

interface EpocheErstellenAnfrage {
  name: string;
  genre: string;
  erfunden: boolean;
  beschreibung: string;
  zeitraum: string;
  orte: string;
  gesellschaft: string;
  statusregel: string;
  rang_wort: string;
  anreden: string;
  nebenstrang_typen: string;
  vorbild_franchise: string;
  verbote_start: string;
}

const LEERES_FORMULAR: EpocheErstellenAnfrage = {
  name: "",
  genre: "",
  erfunden: false,
  beschreibung: "",
  zeitraum: "",
  orte: "",
  gesellschaft: "",
  statusregel: "",
  rang_wort: "",
  anreden: "",
  nebenstrang_typen: "",
  vorbild_franchise: "",
  verbote_start: "",
};

function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className="w-full rounded-lg border border-border bg-bg px-3 py-1.5 text-sm text-text outline-none transition-colors focus:border-accent"
    />
  );
}

/** Reines Frageformular (kein LLM-Aufruf) zum Anlegen einer neuen Epoche/
 * eines neuen Settings unter der zentralen Epochen-Bibliothek - portiert
 * aus pre-GUI/novelle.py's cmd_epoche_erstellen(). Das Ergebnis ist
 * bewusst ein ROHENTWURF: verbotsliste.md und pruefer_anachronismus.txt
 * brauchen danach noch echte Recherche (siehe Bedienungsanleitung
 * Abschnitt 10) - am einfachsten ueber ein neues Projekt mit dieser Epoche
 * und den bereits vorhandenen Personas-/Verbotsliste-Editoren. */
export function EpocheErstellenPage() {
  const [formular, setFormular] = useState<EpocheErstellenAnfrage>(LEERES_FORMULAR);
  const [wirdAngelegt, setWirdAngelegt] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [ergebnis, setErgebnis] = useState<{ name: string; ordner: string; dateien: Record<string, string> } | null>(
    null,
  );

  const [epochen, setEpochen] = useState<EpocheKurz[]>([]);
  const [epochenLaden, setEpochenLaden] = useState(true);
  const [loeschenAnfrage, setLoeschenAnfrage] = useState<EpocheKurz | null>(null);
  const [wirdGeloescht, setWirdGeloescht] = useState<string | null>(null);
  const [loeschenFehler, setLoeschenFehler] = useState<string | null>(null);

  function epochenNeuLaden() {
    setEpochenLaden(true);
    api
      .epochen()
      .then(setEpochen)
      .finally(() => setEpochenLaden(false));
  }

  useEffect(() => {
    epochenNeuLaden();
  }, []);

  async function epocheLoeschenBestaetigt() {
    if (!loeschenAnfrage) return;
    const name = loeschenAnfrage.name;
    setWirdGeloescht(name);
    setLoeschenFehler(null);
    try {
      await api.epocheLoeschen(name);
      setLoeschenAnfrage(null);
      epochenNeuLaden();
    } catch (e) {
      setLoeschenFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setWirdGeloescht(null);
    }
  }

  function feld<K extends keyof EpocheErstellenAnfrage>(name: K, wert: EpocheErstellenAnfrage[K]) {
    setFormular((bisher) => ({ ...bisher, [name]: wert }));
  }

  const formularGueltig =
    formular.name.trim() !== "" &&
    formular.beschreibung.trim() !== "" &&
    formular.zeitraum.trim() !== "" &&
    formular.orte.trim() !== "" &&
    formular.gesellschaft.trim() !== "" &&
    formular.statusregel.trim() !== "";

  async function anlegen() {
    setWirdAngelegt(true);
    setFehler(null);
    setErgebnis(null);
    try {
      const antwort = await fetch("/api/epochen", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formular),
      });
      if (!antwort.ok) {
        const body = await antwort.json().catch(() => ({}));
        throw new Error(body.detail ?? antwort.statusText);
      }
      setErgebnis(await antwort.json());
      setFormular(LEERES_FORMULAR);
      epochenNeuLaden();
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setWirdAngelegt(false);
    }
  }

  if (ergebnis) {
    return (
      <div className="p-6">
        <Card className="mx-auto max-w-2xl">
          <CardTitle>✅ Rohentwurf angelegt: {ergebnis.name}</CardTitle>
          <p className="mb-3 text-sm text-text-muted">
            Vier Dateien wurden unter <code className="text-text">epochen/{ergebnis.ordner}/</code> angelegt.
            Das ist ein <strong className="text-text">Rohentwurf</strong>, kein fertiges Setting - vor allem
            zwei Dateien sind noch mit "HIER ERGÄNZEN" markiert und brauchen echte Recherche (am besten mit
            Websuche in einem eigenen Gespräch, nicht dem lokalen Modell überlassen):
          </p>
          <ul className="mb-4 list-inside list-disc text-sm text-text-muted">
            <li>verbotsliste.md</li>
            <li>pruefer_anachronismus.txt</li>
          </ul>
          <p className="mb-4 text-sm text-text-muted">
            Am einfachsten testest und verfeinerst du sie, indem du ein neues Projekt mit dieser Epoche
            anlegst und die Dateien über die Tabs "Personas" bzw. "Architekt / Gerüst" bearbeitest.
          </p>
          <Button onClick={() => setErgebnis(null)}>Weitere Epoche anlegen</Button>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <Card>
        <CardTitle>📜 Vorhandene Epochen</CardTitle>
        {loeschenFehler && <p className="mb-3 text-sm text-red-400">{loeschenFehler}</p>}
        {epochenLaden ? (
          <p className="text-sm text-text-muted">Lädt...</p>
        ) : epochen.length === 0 ? (
          <p className="text-sm text-text-muted">Noch keine Epoche angelegt.</p>
        ) : (
          <ul className="divide-y divide-border">
            {epochen.map((e) => (
              <li key={e.name} className="flex items-center gap-3 px-1 py-2 text-sm">
                <button
                  onClick={() => setLoeschenAnfrage(e)}
                  disabled={wirdGeloescht === e.name}
                  title={`Epoche "${e.name}" löschen`}
                  aria-label={`Epoche "${e.name}" löschen`}
                  className="shrink-0 text-sm leading-none text-red-400/60 transition-colors hover:text-red-400 disabled:opacity-40"
                >
                  ✕
                </button>
                <div>
                  <div className="font-medium text-text">{e.name}</div>
                  {e.genre && <div className="text-xs text-text-muted">{e.genre}</div>}
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-xs text-text-muted">
          Löscht nur die zentrale Epoche aus der Bibliothek - bereits damit angelegte Projekte behalten ihre
          eigenen Kopien der Personas/Verbotsliste und sind davon nicht betroffen.
        </p>
      </Card>

      <Card>
        <CardTitle>🏛️ Neue Epoche / neues Setting anlegen</CardTitle>
        <p className="mb-4 text-sm text-text-muted">
          Reines Frageformular, kein KI-Aufruf - kurze, direkte Antworten reichen. Das Ergebnis ist ein
          Rohentwurf, den du danach im jeweiligen Projekt weiter verfeinern kannst.
        </p>

        <div className="space-y-4">
          <div>
            <Label>1) Name der Epoche/des Settings</Label>
            <Input value={formular.name} onChange={(e) => feld("name", e.target.value)} placeholder="Viktorianisches England" />
          </div>

          <div>
            <Label>2) Verbindungsart des Settings</Label>
            <div className="flex gap-2">
              <button
                onClick={() => feld("erfunden", false)}
                className={`flex-1 rounded-lg border px-3 py-2 text-sm transition-colors ${
                  !formular.erfunden ? "border-accent bg-accent-soft text-accent-light" : "border-border text-text-muted"
                }`}
              >
                Reale Epoche
              </button>
              <button
                onClick={() => feld("erfunden", true)}
                className={`flex-1 rounded-lg border px-3 py-2 text-sm transition-colors ${
                  formular.erfunden ? "border-accent bg-accent-soft text-accent-light" : "border-border text-text-muted"
                }`}
              >
                Komplett erfundenes Setting
              </button>
            </div>
            <p className="mt-1 text-xs text-text-muted">
              Bestimmt, ob der Prüfer später historisch prüft oder auf Welt-Konsistenz und Markenabstand achtet.
            </p>
          </div>

          <div>
            <Label>3) Kurzbeschreibung in einem Satz</Label>
            <TextArea
              rows={2}
              value={formular.beschreibung}
              onChange={(e) => feld("beschreibung", e.target.value)}
              placeholder="dem viktorianischen England, ca. 1837 bis 1901"
            />
          </div>

          <div>
            <Label>4) Zeitangabe/Zeitraum, wie er im Gerüst stehen soll</Label>
            <Input
              value={formular.zeitraum}
              onChange={(e) => feld("zeitraum", e.target.value)}
              placeholder="Jahr innerhalb 1837 bis 1901"
            />
          </div>

          <div>
            <Label>5) Zwei, drei typische Schauplätze, kommagetrennt</Label>
            <Input value={formular.orte} onChange={(e) => feld("orte", e.target.value)} placeholder="Landhaus, London, Küste" />
          </div>

          <div>
            <Label>6) Wie heißt "gesellschaftlicher Stand/Rang" in diesem Setting? (optional)</Label>
            <Input value={formular.rang_wort} onChange={(e) => feld("rang_wort", e.target.value)} placeholder="Stand" />
          </div>

          <div>
            <Label>7) Zentrale Gesellschaftsordnung in zwei, drei Sätzen</Label>
            <TextArea
              rows={3}
              value={formular.gesellschaft}
              onChange={(e) => feld("gesellschaft", e.target.value)}
              placeholder="Was zählt, wer hat Macht, welche Zwänge gibt es?"
            />
          </div>

          <div>
            <Label>8) Die eine zentrale Statusregel als dramaturgisches Spannungsmittel</Label>
            <TextArea
              rows={2}
              value={formular.statusregel}
              onChange={(e) => feld("statusregel", e.target.value)}
              placeholder="Eine unstandesgemäße Heirat ruiniert die Familie gesellschaftlich."
            />
          </div>

          <div>
            <Label>9) Anrede-/Titelkonventionen (optional)</Label>
            <Input value={formular.anreden} onChange={(e) => feld("anreden", e.target.value)} placeholder="Mylord, Miss, Euer Gnaden" />
          </div>

          <div>
            <Label>10) Passende Nebenstrang-Typen, kommagetrennt (optional)</Label>
            <Input
              value={formular.nebenstrang_typen}
              onChange={(e) => feld("nebenstrang_typen", e.target.value)}
              placeholder="Erbstreit, Verrat, Geheimnis"
            />
          </div>

          {formular.erfunden && (
            <div>
              <Label>11) Vorbild-Franchise, von dem Abstand gehalten werden soll (optional)</Label>
              <Input
                value={formular.vorbild_franchise}
                onChange={(e) => feld("vorbild_franchise", e.target.value)}
                placeholder="z.B. Red Dead Redemption"
              />
            </div>
          )}

          <div>
            <Label>12) Konkrete Dinge, die NICHT vorkommen dürfen, kommagetrennt (optional)</Label>
            <Input
              value={formular.verbote_start}
              onChange={(e) => feld("verbote_start", e.target.value)}
              placeholder="Eisenbahn, Fotografie, moderne Anglizismen"
            />
          </div>

          <div>
            <Label>13) Genre-Prägung (optional)</Label>
            <Input
              value={formular.genre}
              onChange={(e) => feld("genre", e.target.value)}
              placeholder="z.B. Krimi, Dark Fantasy, Komödie - Epoche und Genre gehen oft fließend ineinander über"
            />
            <p className="mt-1 text-xs text-text-muted">
              Wird Architekt und Autor als zusätzliche Ton-/Stilvorgabe mitgegeben und bei der Epochen-Auswahl
              für ein neues Projekt angezeigt.
            </p>
          </div>

          {fehler && <p className="text-sm text-red-400">{fehler}</p>}

          <Button onClick={anlegen} disabled={wirdAngelegt || !formularGueltig}>
            {wirdAngelegt ? "Legt an..." : "Epoche anlegen"}
          </Button>
        </div>
      </Card>

      {loeschenAnfrage && (
        <ConfirmDialog
          titel="Epoche löschen?"
          beschreibung={`"${loeschenAnfrage.name}" wird unwiderruflich aus der Epochen-Bibliothek entfernt. Bereits angelegte Projekte mit dieser Epoche sind nicht betroffen, da sie eigene Kopien der Dateien besitzen.`}
          bestaetigenText="Endgültig löschen"
          wirdAusgefuehrt={wirdGeloescht === loeschenAnfrage.name}
          onBestaetigen={epocheLoeschenBestaetigt}
          onAbbrechen={() => setLoeschenAnfrage(null)}
        />
      )}
    </div>
  );
}
