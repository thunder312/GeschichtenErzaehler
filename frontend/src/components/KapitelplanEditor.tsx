import { useEffect, useState } from "react";
import type { KapitelEintrag, KapitelplanFehler } from "../utils/kapitelplan";
import { FUNKTION_IM_SPANNUNGSBOGEN_OPTIONEN, leeresKapitel } from "../utils/kapitelplan";
import { ConfirmDialog } from "./ConfirmDialog";
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

  // Einklappzustand je Kapitel-Karte (siehe ToDo.md: mehr Platz fuer den
  // Block, an dem gerade gearbeitet wird, bei vielen Kapiteln sonst viel
  // Scrollen). Enthaelt die Indizes der EINGEKLAPPTEN Karten - default leer
  // (alle offen), damit sich am bisherigen Verhalten nichts aendert, solange
  // niemand aktiv einklappt. Ein Index mit einem Pflichtfeld-Fehler bleibt
  // beim Einklappen-Versuch trotzdem sichtbar offen (siehe toggle()), sonst
  // waere die rote Markierung unsichtbar, ohne dass der Nutzer weiss, wo.
  const [eingeklappt, setEingeklappt] = useState<Set<number>>(new Set());

  // Indizes, die der Nutzer explizit auf "Eigene Angabe" im Funktion-im-
  // Spannungsbogen-Dropdown umgeschaltet hat, OBWOHL das Feld gerade leer ist
  // (sonst wuerde die Auswahl sofort wieder auf den Platzhalter zurueckfallen,
  // siehe istEigeneAngabe() unten - ein bereits mit unbekanntem Freitext
  // befuelltes Feld erkennt den Freitext-Modus ohnehin automatisch, dafuer ist
  // dieses Set nicht noetig). Bewusst kein Reindexieren bei Loeschen/
  // Verschieben wie bei `eingeklappt` - betrifft im schlimmsten Fall kurz das
  // falsche Kapitel, ohne dass dabei je Text verloren geht.
  const [eigeneAngabeIndizes, setEigeneAngabeIndizes] = useState<Set<number>>(new Set());

  function istEigeneAngabe(index: number, wert: string): boolean {
    if (wert.trim() && !istBekannteFunktion(wert)) return true;
    return eigeneAngabeIndizes.has(index);
  }
  const indizesMitFehler = new Set(fehler.map((f) => f.index));

  // Ein neu gemeldeter Pflichtfeld-Fehler klappt seine Karte automatisch
  // wieder auf - sonst bliebe die rote Markierung in einer eingeklappten
  // Karte unsichtbar und der Nutzer muesste sie erst suchen gehen.
  useEffect(() => {
    if (fehler.length === 0) return;
    setEingeklappt((bisher) => {
      const neu = new Set(bisher);
      for (const f of fehler) neu.delete(f.index);
      return neu;
    });
  }, [fehler]);

  function toggle(index: number) {
    setEingeklappt((bisher) => {
      const neu = new Set(bisher);
      if (neu.has(index)) neu.delete(index);
      else if (!indizesMitFehler.has(index)) neu.add(index);
      return neu;
    });
  }

  function alleEinklappen() {
    setEingeklappt(new Set(kapitel.map((_, i) => i).filter((i) => !indizesMitFehler.has(i))));
  }

  function alleAusklappen() {
    setEingeklappt(new Set());
  }

  function feldAendern<K extends keyof KapitelEintrag>(index: number, feld: K, wert: KapitelEintrag[K]) {
    onChange(kapitel.map((k, i) => (i === index ? { ...k, [feld]: wert } : k)));
  }

  function hinzufuegen() {
    onChange([...kapitel, leeresKapitel()]);
  }

  function entfernenBestaetigt() {
    if (zuLoeschenderIndex === null) return;
    const geloeschterIndex = zuLoeschenderIndex;
    onChange(kapitel.filter((_, i) => i !== geloeschterIndex));
    // Einklapp-Zustand haengt am Inhalt, nicht an der Array-Position - nach
    // dem Loeschen ruecken alle nachfolgenden Kapitel eine Nummer auf, ihr
    // Einklapp-Zustand muss mitwandern, sonst zeigt Index N ploetzlich den
    // Zustand des FALSCHEN (jetzt an dieser Stelle stehenden) Kapitels.
    setEingeklappt((bisher) => {
      const neu = new Set<number>();
      for (const i of bisher) {
        if (i < geloeschterIndex) neu.add(i);
        else if (i > geloeschterIndex) neu.add(i - 1);
      }
      return neu;
    });
    setZuLoeschenderIndex(null);
  }

  function verschieben(index: number, richtung: -1 | 1) {
    const ziel = index + richtung;
    if (ziel < 0 || ziel >= kapitel.length) return;
    const kopie = [...kapitel];
    [kopie[index], kopie[ziel]] = [kopie[ziel], kopie[index]];
    onChange(kopie);
    // Wie oben: Einklapp-Zustand tauscht mit den beiden vertauschten Karten.
    setEingeklappt((bisher) => {
      const indexOffen = bisher.has(index);
      const zielOffen = bisher.has(ziel);
      if (indexOffen === zielOffen) return bisher;
      const neu = new Set(bisher);
      if (zielOffen) neu.add(index); else neu.delete(index);
      if (indexOffen) neu.add(ziel); else neu.delete(ziel);
      return neu;
    });
  }

  function klasse(index: number, feld: string): string {
    return fehlerKeys.has(`${index}:${feld}`) ? "border-red-400/70 focus:border-red-400" : "";
  }

  return (
    <div className="space-y-4 p-4">
      {kapitel.length === 0 && (
        <p className="text-sm text-text-muted">Noch kein Kapitelplan. Mit „+ Kapitel" das erste Kapitel anlegen.</p>
      )}

      {kapitel.length > 1 && (
        <div className="flex justify-end gap-3 text-xs">
          <button type="button" onClick={alleEinklappen} className="text-accent-light hover:underline">
            Alle einklappen
          </button>
          <button type="button" onClick={alleAusklappen} className="text-accent-light hover:underline">
            Alle ausklappen
          </button>
        </div>
      )}

      {kapitel.map((k, index) => {
        const offen = !eingeklappt.has(index);
        return (
        <div key={index} className="rounded-xl border border-border bg-bg/40 p-4">
          <div className={offen ? "mb-3 flex items-center justify-between gap-2" : "flex items-center justify-between gap-2"}>
            <button
              type="button"
              onClick={() => toggle(index)}
              className="flex min-w-0 flex-1 items-center gap-2 text-left"
            >
              <span className="text-xs text-text-muted">{offen ? "▾" : "▸"}</span>
              <span className="font-heading text-sm font-semibold text-text">Kapitel {index + 1}</span>
              {!offen && (
                <span className="truncate text-xs text-text-muted">
                  {[k.titel, k.ort].filter(Boolean).join(" · ") || "(noch leer)"}
                </span>
              )}
            </button>
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

          {offen && (
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
              {istEigeneAngabe(index, k.funktionImSpannungsbogen) ? (
                <div className="space-y-1">
                  <Input
                    value={k.funktionImSpannungsbogen}
                    onChange={(e) => feldAendern(index, "funktionImSpannungsbogen", e.target.value)}
                    placeholder="Eigene Angabe"
                    className={klasse(index, "funktionImSpannungsbogen")}
                  />
                  <button
                    type="button"
                    onClick={() => {
                      setEigeneAngabeIndizes((bisher) => {
                        const neu = new Set(bisher);
                        neu.delete(index);
                        return neu;
                      });
                      feldAendern(index, "funktionImSpannungsbogen", "");
                    }}
                    className="text-xs text-accent-light hover:underline"
                  >
                    Kategorie stattdessen auswählen
                  </button>
                </div>
              ) : (
                <Select
                  value={k.funktionImSpannungsbogen}
                  onChange={(e) => {
                    if (e.target.value === EIGENE_ANGABE) {
                      setEigeneAngabeIndizes((bisher) => new Set(bisher).add(index));
                      return;
                    }
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
          )}
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
