import type { ReactNode } from "react";
import {
  leereFigur,
  type FigurEintrag,
  type RahmenFelder,
  type VorAbschnittBearbeitet,
} from "../utils/rahmen";
import { Input, Label, Select, Textarea } from "./ui";

interface RahmenEditorProps {
  abschnitte: VorAbschnittBearbeitet[];
  onChange: (abschnitte: VorAbschnittBearbeitet[]) => void;
}

const RAHMEN_TEXTFELDER: { feld: keyof RahmenFelder; label: string; placeholder?: string }[] = [
  { feld: "zeitangabe", label: "Zeitangabe (Jahr)", placeholder: "z.B. Jahr 1815" },
  { feld: "ort", label: "Ort" },
  { feld: "jahreszeit", label: "Jahreszeit (optional)" },
  { feld: "erzaehlperspektive", label: "Erzählperspektive" },
  { feld: "tempus", label: "Tempus" },
  { feld: "tonlage", label: "Tonlage" },
];

/** Kopfzeile fuer einen einzelnen "## "-Abschnitt-Block innerhalb des
 * RahmenEditors - selbes rahmenlose "Karte in der Karte"-Muster wie
 * KapitelplanEditor.tsx (eigener Rand, kein verschachteltes CollapsibleCard). */
function AbschnittBlock({ titel, children }: { titel: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-bg/40 p-4">
      <h4 className="font-heading mb-3 text-sm font-semibold text-text">{titel}</h4>
      {children}
    </div>
  );
}

function RahmenFelderBlock({ felder, onChange }: { felder: RahmenFelder; onChange: (felder: RahmenFelder) => void }) {
  function feldAendern<K extends keyof RahmenFelder>(feld: K, wert: RahmenFelder[K]) {
    onChange({ ...felder, [feld]: wert });
  }
  return (
    <AbschnittBlock titel="Rahmen">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {RAHMEN_TEXTFELDER.map(({ feld, label, placeholder }) => (
          <div key={feld}>
            <Label>{label}</Label>
            <Input
              value={felder[feld] as string}
              placeholder={placeholder}
              onChange={(e) => feldAendern(feld, e.target.value)}
            />
          </div>
        ))}
        <div>
          <Label>Jugendschutz-Stufe</Label>
          <Select
            value={felder.jugendschutzStufe}
            onChange={(e) => feldAendern("jugendschutzStufe", e.target.value as RahmenFelder["jugendschutzStufe"])}
          >
            <option value="voll">Voll explizit</option>
            <option value="angedeutet">Angedeutet/romantisch</option>
            <option value="jugendfrei">Jugendfrei</option>
          </Select>
        </div>
        <div>
          <Label>Automatische Fortsetzung</Label>
          <Select
            value={felder.automatischeFortsetzung}
            onChange={(e) =>
              feldAendern("automatischeFortsetzung", e.target.value as RahmenFelder["automatischeFortsetzung"])
            }
          >
            <option value="aus">Aus (empfohlen)</option>
            <option value="ein">Ein</option>
          </Select>
        </div>
        <div>
          <Label>Autor-Modell</Label>
          <Input value="Mistral" disabled className="opacity-60" />
        </div>
      </div>
      {felder.weitereAngaben.trim() && (
        <div className="mt-3">
          <Label>Weitere Angaben (nicht automatisch erkannt, bleiben erhalten)</Label>
          <Textarea
            rows={2}
            value={felder.weitereAngaben}
            onChange={(e) => feldAendern("weitereAngaben", e.target.value)}
          />
        </div>
      )}
    </AbschnittBlock>
  );
}

function FigurenBlock({ figuren, onChange }: { figuren: FigurEintrag[]; onChange: (figuren: FigurEintrag[]) => void }) {
  function figurAendern(index: number, feld: keyof FigurEintrag, wert: string) {
    onChange(figuren.map((f, i) => (i === index ? { ...f, [feld]: wert } : f)));
  }
  function entfernen(index: number) {
    onChange(figuren.filter((_, i) => i !== index));
  }
  return (
    <AbschnittBlock titel="Figuren">
      <div className="space-y-3">
        {figuren.length === 0 && (
          <p className="text-sm text-text-muted">Noch keine Figur. Mit „+ Figur" die erste Figur anlegen.</p>
        )}
        {figuren.map((f, index) => (
          <div key={index} className="rounded-lg border border-border/70 p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="flex-1">
                <Label>Name</Label>
                <Input value={f.name} onChange={(e) => figurAendern(index, "name", e.target.value)} />
              </div>
              <button
                type="button"
                onClick={() => entfernen(index)}
                title="Figur löschen"
                className="mt-5 rounded px-2 py-1 text-xs text-red-400/80 hover:bg-red-400/10 hover:text-red-400"
              >
                ✕
              </button>
            </div>
            <Label>Details (Alter, Rang/Stand, Ziel, größte Angst, Geheimnis, Entwicklungsbogen, ...)</Label>
            <Textarea rows={2} value={f.details} onChange={(e) => figurAendern(index, "details", e.target.value)} />
          </div>
        ))}
        <button
          type="button"
          onClick={() => onChange([...figuren, leereFigur()])}
          className="w-full rounded-lg border border-dashed border-border py-2 text-sm text-text-muted hover:border-accent hover:text-accent-light"
        >
          + Figur
        </button>
      </div>
    </AbschnittBlock>
  );
}

/** Strukturierte Ansicht des "vor"-Teils von geruest.md (alles vor
 * "## Kapitelplan", siehe GeruestPage.tsx und utils/rahmen.ts) - ein Block je
 * "## "-Ueberschrift statt eines einzigen Freitext-Editors, analog zum
 * bereits bestehenden KapitelplanEditor fuer den Kapitelplan-Teil. */
export function RahmenEditor({ abschnitte, onChange }: RahmenEditorProps) {
  function abschnittAendern(index: number, neu: VorAbschnittBearbeitet) {
    onChange(abschnitte.map((a, i) => (i === index ? neu : a)));
  }

  return (
    <div className="space-y-4 p-4">
      {abschnitte.map((a, index) => {
        if (a.art === "rahmen") {
          return (
            <RahmenFelderBlock
              key={index}
              felder={a.felder}
              onChange={(felder) => abschnittAendern(index, { ...a, felder })}
            />
          );
        }
        if (a.art === "figuren") {
          return (
            <FigurenBlock
              key={index}
              figuren={a.figuren}
              onChange={(figuren) => abschnittAendern(index, { ...a, figuren })}
            />
          );
        }
        return (
          <AbschnittBlock key={index} titel={a.heading}>
            <Textarea
              rows={a.heading.toLowerCase() === "nebenstrang" ? 4 : 3}
              value={a.text}
              onChange={(e) => abschnittAendern(index, { ...a, text: e.target.value })}
            />
          </AbschnittBlock>
        );
      })}
    </div>
  );
}
