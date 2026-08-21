import { Input, Label } from "./ui";

export interface EpocheFormularWerte {
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

export const LEERES_EPOCHE_FORMULAR: EpocheFormularWerte = {
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

export function epocheFormularGueltig(f: EpocheFormularWerte): boolean {
  return (
    f.name.trim() !== "" &&
    f.beschreibung.trim() !== "" &&
    f.zeitraum.trim() !== "" &&
    f.orte.trim() !== "" &&
    f.gesellschaft.trim() !== "" &&
    f.statusregel.trim() !== ""
  );
}

export function EpocheTextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className="w-full rounded-lg border border-border bg-bg px-3 py-1.5 text-sm text-text outline-none transition-colors focus:border-accent"
    />
  );
}

interface EpocheFormularProps {
  werte: EpocheFormularWerte;
  onChange: <K extends keyof EpocheFormularWerte>(feld: K, wert: EpocheFormularWerte[K]) => void;
}

/** Die 13 Formularfelder fuer ein Epoche-/Setting-Profil (siehe
 * app/core/epoche.py:EpocheAntworten) - herausgeloest aus
 * EpocheErstellenPage.tsx, damit dieselben Felder auch fuer den vom
 * Analysator vorgeschlagenen (und vom Nutzer vor dem Speichern noch
 * editierbaren) Epoche-Entwurf wiederverwendet werden koennen
 * (AnalysatorPage.tsx), statt die komplette Feldliste ein zweites Mal zu
 * pflegen. Reiner kontrollierter Formular-Baustein ohne eigenen Zustand -
 * das Anlegen/Speichern bleibt Sache des jeweiligen Aufrufers. */
export function EpocheFormular({ werte, onChange }: EpocheFormularProps) {
  return (
    <div className="space-y-4">
      <div>
        <Label>1) Name der Epoche/des Settings</Label>
        <Input value={werte.name} onChange={(e) => onChange("name", e.target.value)} placeholder="Viktorianisches England" />
      </div>

      <div>
        <Label>2) Verbindungsart des Settings</Label>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => onChange("erfunden", false)}
            className={`flex-1 rounded-lg border px-3 py-2 text-sm transition-colors ${
              !werte.erfunden ? "border-accent bg-accent-soft text-accent-light" : "border-border text-text-muted"
            }`}
          >
            Reale Epoche
          </button>
          <button
            type="button"
            onClick={() => onChange("erfunden", true)}
            className={`flex-1 rounded-lg border px-3 py-2 text-sm transition-colors ${
              werte.erfunden ? "border-accent bg-accent-soft text-accent-light" : "border-border text-text-muted"
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
        <EpocheTextArea
          rows={2}
          value={werte.beschreibung}
          onChange={(e) => onChange("beschreibung", e.target.value)}
          placeholder="dem viktorianischen England, ca. 1837 bis 1901"
        />
      </div>

      <div>
        <Label>4) Zeitangabe/Zeitraum, wie er im Gerüst stehen soll</Label>
        <Input
          value={werte.zeitraum}
          onChange={(e) => onChange("zeitraum", e.target.value)}
          placeholder="Jahr innerhalb 1837 bis 1901"
        />
      </div>

      <div>
        <Label>5) Zwei, drei typische Schauplätze, kommagetrennt</Label>
        <Input value={werte.orte} onChange={(e) => onChange("orte", e.target.value)} placeholder="Landhaus, London, Küste" />
      </div>

      <div>
        <Label>6) Wie heißt "gesellschaftlicher Stand/Rang" in diesem Setting? (optional)</Label>
        <Input value={werte.rang_wort} onChange={(e) => onChange("rang_wort", e.target.value)} placeholder="Stand" />
      </div>

      <div>
        <Label>7) Zentrale Gesellschaftsordnung in zwei, drei Sätzen</Label>
        <EpocheTextArea
          rows={3}
          value={werte.gesellschaft}
          onChange={(e) => onChange("gesellschaft", e.target.value)}
          placeholder="Was zählt, wer hat Macht, welche Zwänge gibt es?"
        />
      </div>

      <div>
        <Label>8) Die eine zentrale Statusregel als dramaturgisches Spannungsmittel</Label>
        <EpocheTextArea
          rows={2}
          value={werte.statusregel}
          onChange={(e) => onChange("statusregel", e.target.value)}
          placeholder="Eine unstandesgemäße Heirat ruiniert die Familie gesellschaftlich."
        />
      </div>

      <div>
        <Label>9) Anrede-/Titelkonventionen (optional)</Label>
        <Input value={werte.anreden} onChange={(e) => onChange("anreden", e.target.value)} placeholder="Mylord, Miss, Euer Gnaden" />
      </div>

      <div>
        <Label>10) Passende Nebenstrang-Typen, kommagetrennt (optional)</Label>
        <Input
          value={werte.nebenstrang_typen}
          onChange={(e) => onChange("nebenstrang_typen", e.target.value)}
          placeholder="Erbstreit, Verrat, Geheimnis"
        />
      </div>

      {werte.erfunden && (
        <div>
          <Label>11) Vorbild-Franchise, von dem Abstand gehalten werden soll (optional)</Label>
          <Input
            value={werte.vorbild_franchise}
            onChange={(e) => onChange("vorbild_franchise", e.target.value)}
            placeholder="z.B. Red Dead Redemption"
          />
          {werte.vorbild_franchise.trim() && (
            <p className="mt-1 text-xs text-amber-300">
              ⚠️ Der Einleitungssatz dieser Epoche bekommt automatisch einen FanFic-Hinweis (keine Rechte am
              Original, keine kommerzielle Nutzung) - sichtbar auf der Titelseite jeder damit geschriebenen
              Geschichte.
            </p>
          )}
        </div>
      )}

      <div>
        <Label>12) Konkrete Dinge, die NICHT vorkommen dürfen, kommagetrennt (optional)</Label>
        <Input
          value={werte.verbote_start}
          onChange={(e) => onChange("verbote_start", e.target.value)}
          placeholder="Eisenbahn, Fotografie, moderne Anglizismen"
        />
      </div>

      <div>
        <Label>13) Genre-Prägung (optional)</Label>
        <Input
          value={werte.genre}
          onChange={(e) => onChange("genre", e.target.value)}
          placeholder="z.B. Krimi, Dark Fantasy, Komödie - Epoche und Genre gehen oft fließend ineinander über"
        />
        <p className="mt-1 text-xs text-text-muted">
          Wird Architekt und Autor als zusätzliche Ton-/Stilvorgabe mitgegeben und bei der Epochen-Auswahl für ein
          neues Projekt angezeigt.
        </p>
      </div>
    </div>
  );
}
