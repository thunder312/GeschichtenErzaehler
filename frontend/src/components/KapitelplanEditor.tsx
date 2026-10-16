import { useEffect, useState } from "react";
import type { FundusFigur, Ort } from "../api/types";
import type { KapitelEintrag, KapitelplanFehler } from "../utils/kapitelplan";
import { FUNKTION_IM_SPANNUNGSBOGEN_OPTIONEN, leeresKapitel } from "../utils/kapitelplan";
import { ConfirmDialog } from "./ConfirmDialog";
import { FigurenAuswahl } from "./FigurenAuswahl";
import { OrtAuswahl } from "./OrtAuswahl";
import { Button, Input, Label, Select, Textarea } from "./ui";

const EIGENE_ANGABE = "__eigene__";

/** true, wenn der gespeicherte Wert (Freitext-Feld, siehe KapitelEintrag.
 * funktionImSpannungsbogen) exakt einer der bekannten Kategorien entspricht -
 * Bestandsprojekte koennen hier aber auch aelteren, frei formulierten Text
 * stehen haben (das Feld war bis jetzt reiner Freitext), deshalb bewusst KEIN
 * erzwungenes Uebersetzen/Verwerfen, siehe Select unten. */
function istBekannteFunktion(wert: string): boolean {
  return (FUNKTION_IM_SPANNUNGSBOGEN_OPTIONEN as readonly string[]).includes(wert.trim());
}

interface KapitelplanEditorProps {
  kapitel: KapitelEintrag[];
  onChange: (kapitel: KapitelEintrag[]) => void;
  fehler: KapitelplanFehler[];
  /** Fuer den Fundus-gespeisten Vorschlag in "Anwesende Figuren" (siehe
   * FigurenAuswahl.tsx) - beides optional, analog zu RahmenEditor.tsx. */
  fundusFiguren?: FundusFigur[];
  /** Fuer den Fundus-gespeisten Vorschlag im Feld "Ort" (siehe OrtAuswahl.tsx). */
  orte?: Ort[];
  epoche?: string | null;
  /** Wird true, sobald der Tab "Architekt / Gerüst" (wieder) betreten wird -
   * klappt dann alle Kapitel-Karten ein, damit man mit demselben
   * aufgeraeumten Ueberblick startet wie beim ersten Befuellen. */
  aktiv?: boolean;
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
export function KapitelplanEditor({ kapitel, onChange, fehler, fundusFiguren, orte, epoche, aktiv }: KapitelplanEditorProps) {
  // Eigenes Bestaetigen-Popup statt window.confirm() - ein natives
  // confirm() blockiert den kompletten Tab (auch fuer Browser-Automation,
  // siehe ConfirmDialog.tsx), das App-Design vermeidet es deshalb ueberall.
  const [zuLoeschenderIndex, setZuLoeschenderIndex] = useState<number | null>(null);
  const fehlerKeys = new Set(fehler.map((f) => `${f.index}:${f.feld}`));

  // Aktuell gewaehltes Kapitel der Tab-Leiste - nur dessen Felder werden
  // gezeigt (statt aller Kapitel untereinander, das erzwang viel Scrollen).
  const [auswahl, setAuswahl] = useState(0);
  const aktuellerIndex = Math.min(auswahl, Math.max(kapitel.length - 1, 0));

  // Indizes, die der Nutzer explizit auf "Eigene Angabe" im Funktion-im-
  // Spannungsbogen-Dropdown umgeschaltet hat, OBWOHL das Feld gerade leer ist
  // (sonst wuerde die Auswahl sofort wieder auf den Platzhalter zurueckfallen,
  // siehe istEigeneAngabe() unten - ein bereits mit unbekanntem Freitext
  // befuelltes Feld erkennt den Freitext-Modus ohnehin automatisch, dafuer ist
  // dieses Set nicht noetig). Bewusst kein Reindexieren bei Loeschen/
  // Verschieben - betrifft im schlimmsten Fall kurz das
  // falsche Kapitel, ohne dass dabei je Text verloren geht.
  const [eigeneAngabeIndizes, setEigeneAngabeIndizes] = useState<Set<number>>(new Set());

  function istEigeneAngabe(index: number, wert: string): boolean {
    if (wert.trim() && !istBekannteFunktion(wert)) return true;
    return eigeneAngabeIndizes.has(index);
  }
  const indizesMitFehler = new Set(fehler.map((f) => f.index));

  // Ein neu gemeldeter Pflichtfeld-Fehler wechselt zum ersten betroffenen
  // Kapitel - sonst bliebe die rote Markierung in einem nicht gezeigten
  // Kapitel unsichtbar.
  useEffect(() => {
    if (fehler.length === 0) return;
    setAuswahl(Math.min(...fehler.map((f) => f.index)));
  }, [fehler]);

  // Erneutes Betreten des Tabs "Architekt / Gerüst": wieder bei Kapitel 1 starten.
  useEffect(() => {
    if (aktiv) setAuswahl(0);
  }, [aktiv]);

  function feldAendern<K extends keyof KapitelEintrag>(index: number, feld: K, wert: KapitelEintrag[K]) {
    onChange(kapitel.map((k, i) => (i === index ? { ...k, [feld]: wert } : k)));
  }

  function hinzufuegen() {
    onChange([...kapitel, leeresKapitel()]);
    setAuswahl(kapitel.length);
  }

  function entfernenBestaetigt() {
    if (zuLoeschenderIndex === null) return;
    const geloeschterIndex = zuLoeschenderIndex;
    onChange(kapitel.filter((_, i) => i !== geloeschterIndex));
    setAuswahl(Math.max(0, Math.min(aktuellerIndex, kapitel.length - 2)));
    setZuLoeschenderIndex(null);
  }

  function verschieben(index: number, richtung: -1 | 1) {
    const ziel = index + richtung;
    if (ziel < 0 || ziel >= kapitel.length) return;
    const kopie = [...kapitel];
    [kopie[index], kopie[ziel]] = [kopie[ziel], kopie[index]];
    onChange(kopie);
    setAuswahl(ziel);
  }

  function klasse(index: number, feld: string): string {
    return fehlerKeys.has(`${index}:${feld}`) ? "border-red-400/70 focus:border-red-400" : "";
  }

  return (
    <div className="space-y-4 p-4">
      {kapitel.length === 0 && (
        <p className="text-sm text-text-muted">Noch kein Kapitelplan. Mit „+ Kapitel" das erste Kapitel anlegen.</p>
      )}

      {kapitel.length > 0 && (
        <div className="flex flex-wrap gap-1 border-b border-border">
          {kapitel.map((_, index) => {
            const gewaehlt = index === aktuellerIndex;
            const hatFehler = indizesMitFehler.has(index);
            return (
              <button
                key={index}
                type="button"
                onClick={() => setAuswahl(index)}
                className={`-mb-px rounded-t-lg border px-3 py-1.5 text-sm ${
                  gewaehlt
                    ? "border-border border-b-bg bg-bg/40 font-semibold text-text"
                    : "border-transparent text-text-muted hover:bg-surface-hover"
                } ${hatFehler ? "text-red-400" : ""}`}
              >
                Kapitel {index + 1}
              </button>
            );
          })}
        </div>
      )}

      {kapitel.slice(aktuellerIndex, aktuellerIndex + 1).map((k) => {
        const index = aktuellerIndex;
        return (
        <div key={index} className="rounded-xl border border-border bg-bg/40 p-4">
          <div className="flex items-center justify-between gap-2">
            <span className="font-heading text-sm font-semibold text-text">Kapitel {index + 1}</span>
            <div className="flex shrink-0 items-center gap-1">
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

          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <Label>Titel</Label>
              <Input
                value={k.titel}
                onChange={(e) => feldAendern(index, "titel", e.target.value)}
                placeholder="Sprechender Untertitel"
                className={klasse(index, "titel")}
              />
            </div>
            {index > 0 && (
              <div className="sm:col-span-2">
                <Label>Vergangene Zeit seit dem vorigen Kapitel</Label>
                <Input
                  value={k.vergangeneZeit}
                  onChange={(e) => feldAendern(index, "vergangeneZeit", e.target.value)}
                  placeholder='Leer = Autor wählt automatisch den kürzesten logischen Zeitsprung. Z.B. "drei Tage später, ein neuer Abend"'
                />
              </div>
            )}
            <div>
              <Label>Ort</Label>
              <OrtAuswahl
                value={k.ort}
                onChange={(wert) => feldAendern(index, "ort", wert)}
                orte={orte}
                epoche={epoche}
                className={klasse(index, "ort")}
              />
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
              <FigurenAuswahl
                value={k.anwesendeFiguren}
                onChange={(wert) => feldAendern(index, "anwesendeFiguren", wert)}
                fundusFiguren={fundusFiguren}
                epoche={epoche}
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
              {/* Das Dropdown bleibt IMMER sichtbar - auch bei frei formuliertem
                  Altbestand-Text (z.B. "Einführung der Figuren und des Konflikts"),
                  damit sich jederzeit eine der sechs Kategorien wählen lässt. Das
                  Freitext-Feld erscheint zusätzlich nur im Modus "Eigene Angabe". */}
              <Select
                value={istEigeneAngabe(index, k.funktionImSpannungsbogen) ? EIGENE_ANGABE : k.funktionImSpannungsbogen}
                onChange={(e) => {
                  if (e.target.value === EIGENE_ANGABE) {
                    setEigeneAngabeIndizes((bisher) => new Set(bisher).add(index));
                    return;
                  }
                  setEigeneAngabeIndizes((bisher) => {
                    const neu = new Set(bisher);
                    neu.delete(index);
                    return neu;
                  });
                  feldAendern(index, "funktionImSpannungsbogen", e.target.value);
                }}
                className={klasse(index, "funktionImSpannungsbogen")}
              >
                <option value="">– auswählen –</option>
                {FUNKTION_IM_SPANNUNGSBOGEN_OPTIONEN.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
                <option value={EIGENE_ANGABE}>Eigene Angabe...</option>
              </Select>
              {istEigeneAngabe(index, k.funktionImSpannungsbogen) && (
                <Input
                  value={k.funktionImSpannungsbogen}
                  onChange={(e) => feldAendern(index, "funktionImSpannungsbogen", e.target.value)}
                  placeholder="Eigene Angabe"
                  className={`mt-1 ${klasse(index, "funktionImSpannungsbogen")}`}
                />
              )}
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
        );
      })}

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
