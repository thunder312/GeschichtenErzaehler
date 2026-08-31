import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { FundusFigur } from "../api/types";
import {
  abschnittBefuellt,
  leereFigur,
  type FigurEintrag,
  type RahmenFelder,
  type VorAbschnittBearbeitet,
} from "../utils/rahmen";
import { fundusFelderZuDetails, fundusFigurFinden } from "../utils/fundusMatch";
import { Input, Label, Select, Textarea } from "./ui";

interface RahmenEditorProps {
  abschnitte: VorAbschnittBearbeitet[];
  onChange: (abschnitte: VorAbschnittBearbeitet[]) => void;
  /** Fuer den Fundus-Abgleich im Figuren-Abschnitt (siehe FigurenBlock) -
   * beides optional, damit RahmenEditor auch ohne geladenen Fundus/ohne
   * bekannte Epoche (z.B. neues, noch nicht gespeichertes Projekt)
   * funktioniert und den Abgleich dann einfach auslaesst. */
  fundusFiguren?: FundusFigur[];
  epoche?: string | null;
  /** Wird true, sobald der Tab "Architekt / Gerüst" (wieder) betreten wird -
   * stellt dann je Block den Standard-Einklappzustand wieder her (befuellte
   * Bloecke eingeklappt). */
  aktiv?: boolean;
}

const RAHMEN_TEXTFELDER: { feld: keyof RahmenFelder; label: string; placeholder?: string }[] = [
  { feld: "zeitangabe", label: "Zeitangabe (Jahr)", placeholder: "z.B. Jahr 1815" },
  { feld: "ort", label: "Ort" },
  { feld: "jahreszeit", label: "Jahreszeit (optional)" },
  { feld: "erzaehlperspektive", label: "Erzählperspektive" },
  { feld: "tempus", label: "Tempus" },
  { feld: "tonlage", label: "Tonlage" },
];

/** Einzelner, einklappbarer "## "-Abschnitt-Block innerhalb des RahmenEditors
 * - selbes rahmenlose "Karte in der Karte"-Muster wie KapitelplanEditor.tsx
 * (eigener Rand, kein verschachteltes CollapsibleCard). `standardEingeklappt`
 * gilt beim ersten Rendern und wird bei jedem erneuten Betreten des Tabs
 * (`aktiv` wechselt auf true) wieder hergestellt - waehrend der Nutzer auf
 * der Seite ist, bleibt sein manuelles Auf-/Zuklappen unangetastet (kein
 * Neu-Einklappen nur weil er gerade die erste Figur eingetippt hat). */
function AbschnittBlock({
  titel,
  standardEingeklappt = false,
  aktiv,
  children,
}: {
  titel: string;
  standardEingeklappt?: boolean;
  aktiv?: boolean;
  children: ReactNode;
}) {
  const [eingeklappt, setEingeklappt] = useState(standardEingeklappt);
  const standardRef = useRef(standardEingeklappt);
  standardRef.current = standardEingeklappt;
  useEffect(() => {
    if (aktiv) setEingeklappt(standardRef.current);
  }, [aktiv]);

  return (
    <div className="rounded-xl border border-border bg-bg/40 p-4">
      <div className="flex items-center justify-between gap-3">
        <h4 className="font-heading text-sm font-semibold text-text">{titel}</h4>
        <button
          type="button"
          onClick={() => setEingeklappt((e) => !e)}
          className="shrink-0 text-xs text-accent-light hover:underline"
        >
          {eingeklappt ? "Ausklappen" : "Einklappen"}
        </button>
      </div>
      {!eingeklappt && <div className="mt-3">{children}</div>}
    </div>
  );
}

function RahmenFelderBlock({
  felder, onChange, standardEingeklappt, aktiv,
}: {
  felder: RahmenFelder;
  onChange: (felder: RahmenFelder) => void;
  standardEingeklappt?: boolean;
  aktiv?: boolean;
}) {
  function feldAendern<K extends keyof RahmenFelder>(feld: K, wert: RahmenFelder[K]) {
    onChange({ ...felder, [feld]: wert });
  }
  return (
    <AbschnittBlock titel="Rahmen" standardEingeklappt={standardEingeklappt} aktiv={aktiv}>
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

function FigurenBlock({
  figuren, onChange, fundusFiguren = [], epoche, standardEingeklappt, aktiv,
}: {
  figuren: FigurEintrag[];
  onChange: (figuren: FigurEintrag[]) => void;
  fundusFiguren?: FundusFigur[];
  epoche?: string | null;
  standardEingeklappt?: boolean;
  aktiv?: boolean;
}) {
  // Merkt sich per Figuren-Index, welchen Fundus-Treffer der Nutzer bewusst
  // weggeklickt hat ("nicht diese Person") - als "index:gefundenerName", ein
  // spaeterer Namenswechsel bekommt dadurch automatisch wieder einen frischen
  // Vorschlag statt dauerhaft unterdrueckt zu bleiben.
  const [ignoriert, setIgnoriert] = useState<Set<string>>(new Set());

  function figurAendern(index: number, feld: keyof FigurEintrag, wert: string) {
    onChange(figuren.map((f, i) => (i === index ? { ...f, [feld]: wert } : f)));
  }
  function entfernen(index: number) {
    onChange(figuren.filter((_, i) => i !== index));
  }
  function fundusUebernehmen(index: number, treffer: FundusFigur) {
    figurAendern(index, "details", fundusFelderZuDetails(treffer.felder));
  }

  return (
    <AbschnittBlock titel="Figuren" standardEingeklappt={standardEingeklappt} aktiv={aktiv}>
      <div className="space-y-3">
        {figuren.length === 0 && (
          <p className="text-sm text-text-muted">Noch keine Figur. Mit „+ Figur" die erste Figur anlegen.</p>
        )}
        {figuren.map((f, index) => {
          const treffer = fundusFigurFinden(fundusFiguren, epoche, f.name);
          const ignorierenSchluessel = treffer ? `${index}:${treffer.name}` : null;
          const zeigeTreffer = treffer && ignorierenSchluessel && !ignoriert.has(ignorierenSchluessel);
          return (
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
              {zeigeTreffer && (
                <div className="mb-2 flex flex-wrap items-center gap-2 rounded-md border border-accent/40 bg-accent-soft px-2.5 py-1.5 text-xs text-accent-light">
                  <span>📋 „{treffer.name}" steht bereits im Fundus (Epoche: {treffer.epoche}).</span>
                  <button
                    type="button"
                    onClick={() => fundusUebernehmen(index, treffer)}
                    className="ml-auto shrink-0 rounded-md border border-accent/40 bg-accent-soft px-2 py-0.5 font-medium hover:bg-accent-soft/80"
                  >
                    Merkmale übernehmen
                  </button>
                  <button
                    type="button"
                    onClick={() => setIgnoriert((s) => new Set(s).add(ignorierenSchluessel))}
                    className="shrink-0 rounded-md border border-border px-2 py-0.5 text-text-muted hover:bg-surface-hover"
                  >
                    Nicht diese Person
                  </button>
                </div>
              )}
              <Label>Details (Alter, Rang/Stand, Ziel, größte Angst, Geheimnis, Entwicklungsbogen, ...)</Label>
              <Textarea rows={2} value={f.details} onChange={(e) => figurAendern(index, "details", e.target.value)} />
            </div>
          );
        })}
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
export function RahmenEditor({ abschnitte, onChange, fundusFiguren, epoche, aktiv }: RahmenEditorProps) {
  function abschnittAendern(index: number, neu: VorAbschnittBearbeitet) {
    onChange(abschnitte.map((a, i) => (i === index ? neu : a)));
  }

  return (
    <div className="space-y-4 p-4">
      {abschnitte.map((a, index) => {
        // Ein bereits ausgefuellter Block startet eingeklappt (mehr Platz beim
        // spaeteren Erweitern um Kapitel), ein leerer bleibt offen zum
        // Ausfuellen.
        const standardEingeklappt = abschnittBefuellt(a);
        if (a.art === "rahmen") {
          return (
            <RahmenFelderBlock
              key={index}
              felder={a.felder}
              standardEingeklappt={standardEingeklappt}
              aktiv={aktiv}
              onChange={(felder) => abschnittAendern(index, { ...a, felder })}
            />
          );
        }
        if (a.art === "figuren") {
          return (
            <FigurenBlock
              key={index}
              figuren={a.figuren}
              standardEingeklappt={standardEingeklappt}
              aktiv={aktiv}
              onChange={(figuren) => abschnittAendern(index, { ...a, figuren })}
              fundusFiguren={fundusFiguren}
              epoche={epoche}
            />
          );
        }
        const istNebenstrang = a.heading.toLowerCase() === "nebenstrang";
        // "Titel" ist immer eine einzelne Zeile - einzeiliges Input statt
        // Textarea (der Block wird hier ohnehin nie laenger).
        if (a.heading.trim().toLowerCase() === "titel") {
          return (
            <AbschnittBlock key={index} titel={a.heading} standardEingeklappt={standardEingeklappt} aktiv={aktiv}>
              <Input
                value={a.text}
                placeholder="Sprechender Titel der Geschichte"
                onChange={(e) => abschnittAendern(index, { ...a, text: e.target.value })}
              />
            </AbschnittBlock>
          );
        }
        return (
          <AbschnittBlock key={index} titel={a.heading} standardEingeklappt={standardEingeklappt} aktiv={aktiv}>
            <Textarea
              rows={istNebenstrang ? 4 : 3}
              value={a.text}
              // Nebenstrang ist als einziger Abschnitt hier wirklich optional
              // (siehe leeresGeruestSkelett() in geruestVorlage.ts - bleibt
              // dort bewusst LEER statt mit Klammer-Hinweistext vorbefuellt):
              // backend/app/core/geruest.py:nebenstrang_abschnitt_erkennen()
              // haengt ein NICHT-leeres "## Nebenstrang" direkt an den
              // Kontinuitaets-Pruefer-Prompt - ein bloss stehen gelassener
              // Hinweistext wuerde dort faelschlich als echter Nebenstrang
              // interpretiert. Der Hinweis lebt deshalb NUR als echtes
              // HTML-Placeholder (verschwindet beim Tippen, wird bei leerem
              // Feld nie mitgespeichert), nicht als vorbefuellter Wert.
              placeholder={
                istNebenstrang
                  ? "Optional. Falls gewünscht: welche Indizien werden in welchem Kapitel gelegt, wie wird aufgelöst. Leer lassen, falls kein Nebenstrang gewünscht ist."
                  : undefined
              }
              onChange={(e) => abschnittAendern(index, { ...a, text: e.target.value })}
            />
          </AbschnittBlock>
        );
      })}
    </div>
  );
}
