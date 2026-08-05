import Editor from "@monaco-editor/react";
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

const EPOCHE_DATEI_BESCHRIFTUNG: Record<string, string> = {
  "architekt.txt": "🗺️ Architekt",
  "autor.txt": "✍️ Autor",
  "pruefer_anachronismus.txt": "🔍 Anachronismus- & Stimmigkeits-Prüfer",
  "verbotsliste.md": "🚫 Verbotsliste",
};

/** Editor fuer den Rohentwurf EINER zentralen Epoche (die vier Dateien aus
 * app/core/epoche.py:epoche_dateien_erzeugen plus das optionale Genre) -
 * anders als PersonasPage.tsx wirken Aenderungen hier NICHT nur auf ein
 * einzelnes Projekt, sondern auf die Bibliothek selbst, aus der zukuenftig
 * angelegte Projekte ihre Kopie ziehen (siehe app/api/epochen.py). */
function EpocheBearbeiten({
  ordner,
  genre,
  onEpochenGeaendert,
}: {
  ordner: string;
  genre: string | null;
  onEpochenGeaendert: () => void;
}) {
  const [dateinamen, setDateinamen] = useState<string[]>([]);
  const [ausgewaehlt, setAusgewaehlt] = useState<string | null>(null);
  const [inhalt, setInhalt] = useState("");
  const [wirdGeladen, setWirdGeladen] = useState(true);
  const [wirdGespeichert, setWirdGespeichert] = useState(false);
  const [gespeichertHinweis, setGespeichertHinweis] = useState<string | null>(null);

  const [genreEntwurf, setGenreEntwurf] = useState(genre ?? "");
  const [genreWirdGespeichert, setGenreWirdGespeichert] = useState(false);
  const [genreGespeichertHinweis, setGenreGespeichertHinweis] = useState<string | null>(null);

  useEffect(() => {
    api.epocheDateienAuflisten(ordner).then((liste) => {
      setDateinamen(liste);
      if (liste.length > 0) setAusgewaehlt(liste[0]);
    });
  }, [ordner]);

  useEffect(() => {
    if (!ausgewaehlt) return;
    setWirdGeladen(true);
    setGespeichertHinweis(null);
    api.epocheDateiLesen(ordner, ausgewaehlt).then((text) => {
      setInhalt(text);
      setWirdGeladen(false);
    });
  }, [ordner, ausgewaehlt]);

  async function dateiSpeichern() {
    if (!ausgewaehlt) return;
    setWirdGespeichert(true);
    setGespeichertHinweis(null);
    try {
      await api.epocheDateiSchreiben(ordner, ausgewaehlt, inhalt);
      setGespeichertHinweis("Gespeichert.");
    } finally {
      setWirdGespeichert(false);
    }
  }

  async function genreSpeichern() {
    setGenreWirdGespeichert(true);
    setGenreGespeichertHinweis(null);
    try {
      await api.epocheGenreSchreiben(ordner, genreEntwurf);
      setGenreGespeichertHinweis("Gespeichert.");
      onEpochenGeaendert();
    } finally {
      setGenreWirdGespeichert(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-4 border-t border-border bg-bg/40 p-4 lg:grid-cols-[1fr_2fr]">
      <div className="space-y-4">
        <div>
          <Label>Genre-Prägung</Label>
          <div className="flex gap-2">
            <Input
              value={genreEntwurf}
              onChange={(e) => setGenreEntwurf(e.target.value)}
              placeholder="z.B. Krimi, Dark Fantasy"
            />
            <Button variant="secondary" onClick={genreSpeichern} disabled={genreWirdGespeichert}>
              {genreWirdGespeichert ? "..." : "OK"}
            </Button>
          </div>
          {genreGespeichertHinweis && <p className="mt-1 text-xs text-accent-light">{genreGespeichertHinweis}</p>}
        </div>
        <div>
          <Label>Dateien</Label>
          <ul className="space-y-1">
            {dateinamen.map((name) => (
              <li key={name}>
                <button
                  onClick={() => setAusgewaehlt(name)}
                  className={`w-full rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                    ausgewaehlt === name
                      ? "bg-accent-soft text-accent-light"
                      : "text-text-muted hover:bg-surface-hover hover:text-text"
                  }`}
                >
                  {EPOCHE_DATEI_BESCHRIFTUNG[name] ?? name}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium text-text">
            {ausgewaehlt ? (EPOCHE_DATEI_BESCHRIFTUNG[ausgewaehlt] ?? ausgewaehlt) : "Datei wählen"}
          </span>
          <div className="flex items-center gap-2">
            {gespeichertHinweis && <span className="text-xs text-accent-light">{gespeichertHinweis}</span>}
            <Button onClick={dateiSpeichern} disabled={wirdGespeichert || wirdGeladen || !ausgewaehlt}>
              {wirdGespeichert ? "Speichert..." : "Speichern"}
            </Button>
          </div>
        </div>
        <Editor
          height="440px"
          defaultLanguage="markdown"
          value={inhalt}
          onChange={(v) => setInhalt(v ?? "")}
          theme="vs-dark"
          options={{ wordWrap: "on", minimap: { enabled: false }, fontSize: 14 }}
        />
      </div>
    </div>
  );
}

interface EpocheErstellenPageProps {
  epochen: EpocheKurz[];
  onEpochenGeaendert: () => void;
}

/** Reines Frageformular (kein LLM-Aufruf) zum Anlegen einer neuen Epoche/
 * eines neuen Settings unter der zentralen Epochen-Bibliothek - portiert
 * aus pre-GUI/novelle.py's cmd_epoche_erstellen(). Das Ergebnis ist
 * bewusst ein ROHENTWURF: verbotsliste.md und pruefer_anachronismus.txt
 * brauchen danach noch echte Recherche (siehe Bedienungsanleitung
 * Abschnitt 10) - direkt hier ueber "Bearbeiten" bei der jeweiligen Epoche
 * (siehe EpocheBearbeiten oben), alternativ ueber ein neues Projekt mit
 * dieser Epoche und den Personas-/Verbotsliste-Editoren dort (wirkt dann
 * aber nur auf die Kopie dieses einen Projekts, nicht auf die Bibliothek).
 * `epochen` kommt von App.tsx (zusammen mit `onEpochenGeaendert`), damit
 * eine hier neu angelegte oder geloeschte Epoche sofort auch im "Neues
 * Projekt"-Dropdown von ProjektePage auftaucht, ohne Reload. */
export function EpocheErstellenPage({ epochen, onEpochenGeaendert }: EpocheErstellenPageProps) {
  const [formular, setFormular] = useState<EpocheErstellenAnfrage>(LEERES_FORMULAR);
  const [wirdAngelegt, setWirdAngelegt] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [ergebnis, setErgebnis] = useState<{ name: string; ordner: string; dateien: Record<string, string> } | null>(
    null,
  );

  const [loeschenAnfrage, setLoeschenAnfrage] = useState<EpocheKurz | null>(null);
  const [wirdGeloescht, setWirdGeloescht] = useState<string | null>(null);
  const [loeschenFehler, setLoeschenFehler] = useState<string | null>(null);
  const [bearbeiteOrdner, setBearbeiteOrdner] = useState<string | null>(null);

  async function epocheLoeschenBestaetigt() {
    if (!loeschenAnfrage) return;
    const name = loeschenAnfrage.name;
    setWirdGeloescht(name);
    setLoeschenFehler(null);
    try {
      await api.epocheLoeschen(name);
      setLoeschenAnfrage(null);
      if (bearbeiteOrdner === name) setBearbeiteOrdner(null);
      onEpochenGeaendert();
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
      onEpochenGeaendert();
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
            Am einfachsten verfeinerst du sie direkt hier: Klick unten in der Liste "Vorhandene Epochen" auf
            "Bearbeiten" bei <strong className="text-text">{ergebnis.name}</strong>.
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
        {epochen.length === 0 ? (
          <p className="text-sm text-text-muted">Noch keine Epoche angelegt.</p>
        ) : (
          <ul className="divide-y divide-border">
            {epochen.map((e) => (
              <li key={e.name}>
                <div className="flex items-center gap-3 px-1 py-2 text-sm">
                  <button
                    onClick={() => setLoeschenAnfrage(e)}
                    disabled={wirdGeloescht === e.name}
                    title={`Epoche "${e.name}" löschen`}
                    aria-label={`Epoche "${e.name}" löschen`}
                    className="shrink-0 text-sm leading-none text-red-400/60 transition-colors hover:text-red-400 disabled:opacity-40"
                  >
                    ✕
                  </button>
                  <div className="flex-1">
                    <div className="font-medium text-text">{e.name}</div>
                    {e.genre && <div className="text-xs text-text-muted">{e.genre}</div>}
                  </div>
                  <button
                    onClick={() => setBearbeiteOrdner((bisher) => (bisher === e.name ? null : e.name))}
                    className={`shrink-0 rounded-lg border px-3 py-1.5 text-xs transition-colors ${
                      bearbeiteOrdner === e.name
                        ? "border-accent bg-accent-soft text-accent-light"
                        : "border-border text-text-muted hover:bg-surface-hover hover:text-text"
                    }`}
                  >
                    {bearbeiteOrdner === e.name ? "Schließen" : "✏️ Bearbeiten"}
                  </button>
                </div>
                {bearbeiteOrdner === e.name && (
                  <EpocheBearbeiten key={e.name} ordner={e.name} genre={e.genre ?? null} onEpochenGeaendert={onEpochenGeaendert} />
                )}
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
