import { useState } from "react";
import type { KapitelEintrag, KapitelplanFehler } from "../utils/kapitelplan";
import { leeresKapitel } from "../utils/kapitelplan";
import { ConfirmDialog } from "./ConfirmDialog";
import { Button, Input, Label, Textarea } from "./ui";

interface KapitelplanEditorProps {
  kapitel: KapitelEintrag[];
  onChange: (kapitel: KapitelEintrag[]) => void;
  fehler: KapitelplanFehler[];
}

/** Strukturierter Block-Editor NUR fuer den "## Kapitelplan"-Abschnitt von
 * geruest.md (siehe GeruestPage.tsx und utils/kapitelplan.ts) - Phase 2 der
 * in ToDo.md skizzierten Gerüst-Editor-Idee. Ein Kapitel = eine Karte mit
 * Formularfeldern statt Freitext-Bulletliste, Zielwortzahl als
 * Pflicht-Zahlenfeld statt einer leicht vergessbaren Textzeile (siehe
 * Vorfall a-Blut-und-Ahornlaub-Die-Ehre-des-Verbotenen). "+ Kapitel" haengt
 * ein neues Kapitel an, ▲/▼ tauschen mit dem Nachbarn (kein Drag&Drop noetig
 * fuer die ueberschaubare Kapitelzahl typischer Projekte), "Löschen" nimmt
 * das Kapitel komplett raus - die Kapitelnummer ergibt sich in allen Faellen
 * automatisch aus der Position im Array, nicht aus einem eigenen Feld. */
export function KapitelplanEditor({ kapitel, onChange, fehler }: KapitelplanEditorProps) {
  // Eigenes Bestaetigen-Popup statt window.confirm() - ein natives
  // confirm() blockiert den kompletten Tab (auch fuer Browser-Automation,
  // siehe ConfirmDialog.tsx), das App-Design vermeidet es deshalb ueberall.
  const [zuLoeschenderIndex, setZuLoeschenderIndex] = useState<number | null>(null);
  const fehlerKeys = new Set(fehler.map((f) => `${f.index}:${f.feld}`));

  function feldAendern<K extends keyof KapitelEintrag>(index: number, feld: K, wert: KapitelEintrag[K]) {
    onChange(kapitel.map((k, i) => (i === index ? { ...k, [feld]: wert } : k)));
  }

  function hinzufuegen() {
    onChange([...kapitel, leeresKapitel()]);
  }

  function entfernenBestaetigt() {
    if (zuLoeschenderIndex === null) return;
    onChange(kapitel.filter((_, i) => i !== zuLoeschenderIndex));
    setZuLoeschenderIndex(null);
  }

  function verschieben(index: number, richtung: -1 | 1) {
    const ziel = index + richtung;
    if (ziel < 0 || ziel >= kapitel.length) return;
    const kopie = [...kapitel];
    [kopie[index], kopie[ziel]] = [kopie[ziel], kopie[index]];
    onChange(kopie);
  }

  function klasse(index: number, feld: string): string {
    return fehlerKeys.has(`${index}:${feld}`) ? "border-red-400/70 focus:border-red-400" : "";
  }

  return (
    <div className="space-y-4 p-4">
      {kapitel.length === 0 && (
        <p className="text-sm text-text-muted">Noch kein Kapitelplan. Mit „+ Kapitel" das erste Kapitel anlegen.</p>
      )}

      {kapitel.map((k, index) => (
        <div key={index} className="rounded-xl border border-border bg-bg/40 p-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <span className="font-heading text-sm font-semibold text-text">Kapitel {index + 1}</span>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => verschieben(index, -1)}
                disabled={index === 0}
                title="Nach oben verschieben"
                className="rounded px-2 py-1 text-xs text-text-muted hover:bg-surface-hover disabled:opacity-30"
              >
                ▲
              </button>
              <button
                type="button"
                onClick={() => verschieben(index, 1)}
                disabled={index === kapitel.length - 1}
                title="Nach unten verschieben"
                className="rounded px-2 py-1 text-xs text-text-muted hover:bg-surface-hover disabled:opacity-30"
              >
                ▼
              </button>
              <button
                type="button"
                onClick={() => setZuLoeschenderIndex(index)}
                title="Kapitel löschen"
                className="rounded px-2 py-1 text-xs text-red-400/80 hover:bg-red-400/10 hover:text-red-400"
              >
                ✕ Löschen
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <Label>Titel</Label>
              <Input
                value={k.titel}
                onChange={(e) => feldAendern(index, "titel", e.target.value)}
                placeholder="Sprechender Untertitel"
                className={klasse(index, "titel")}
              />
            </div>
            <div>
              <Label>Ort</Label>
              <Input value={k.ort} onChange={(e) => feldAendern(index, "ort", e.target.value)} className={klasse(index, "ort")} />
            </div>
            <div>
              <Label>Zielwortzahl</Label>
              <Input
                type="number"
                min={1}
                value={k.zielwortzahl ?? ""}
                onChange={(e) => feldAendern(index, "zielwortzahl", e.target.value ? Number(e.target.value) : null)}
                placeholder="z.B. 1000"
                className={klasse(index, "zielwortzahl")}
              />
            </div>
            <div className="sm:col-span-2">
              <Label>Anwesende Figuren</Label>
              <Input
                value={k.anwesendeFiguren}
                onChange={(e) => feldAendern(index, "anwesendeFiguren", e.target.value)}
                className={klasse(index, "anwesendeFiguren")}
              />
            </div>
            <div className="sm:col-span-2">
              <Label>Ereignis</Label>
              <Textarea
                rows={3}
                value={k.ereignis}
                onChange={(e) => feldAendern(index, "ereignis", e.target.value)}
                className={klasse(index, "ereignis")}
              />
            </div>
            <div>
              <Label>Funktion im Spannungsbogen</Label>
              <Input
                value={k.funktionImSpannungsbogen}
                onChange={(e) => feldAendern(index, "funktionImSpannungsbogen", e.target.value)}
                className={klasse(index, "funktionImSpannungsbogen")}
              />
            </div>
            <div>
              <Label>Stand der Liebeshandlung</Label>
              <Input
                value={k.standDerLiebeshandlung}
                onChange={(e) => feldAendern(index, "standDerLiebeshandlung", e.target.value)}
                className={klasse(index, "standDerLiebeshandlung")}
              />
            </div>
            <div className="sm:col-span-2">
              <Label>Zustand am Kapitelende</Label>
              <Textarea
                rows={2}
                value={k.zustandAmKapitelende}
                onChange={(e) => feldAendern(index, "zustandAmKapitelende", e.target.value)}
                className={klasse(index, "zustandAmKapitelende")}
              />
            </div>
          </div>
        </div>
      ))}

      <Button variant="secondary" onClick={hinzufuegen} className="w-full">
        + Kapitel
      </Button>

      {zuLoeschenderIndex !== null && (
        <ConfirmDialog
          titel="Kapitel löschen?"
          beschreibung={`Kapitel ${zuLoeschenderIndex + 1} wirklich löschen? Nachfolgende Kapitel rücken eine Nummer auf.`}
          bestaetigenText="Löschen"
          onBestaetigen={entfernenBestaetigt}
          onAbbrechen={() => setZuLoeschenderIndex(null)}
        />
      )}
    </div>
  );
}
