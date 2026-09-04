import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { Ort } from "../api/types";
import { Button, Card, Input, Label, Select, Textarea } from "./ui";
import { ConfirmDialog } from "./ConfirmDialog";

interface OrteEditorProps {
  /** Wird nach jeder erfolgreichen Aenderung aufgerufen, damit z.B. die
   * eingeklappte Rohtext-Ansicht (OrtePage.tsx) bei ihrem naechsten
   * Aufklappen den aktuellen Stand zeigt statt eines veralteten. */
  onGeaendert: () => void;
}

function ortSchluessel(o: Pick<Ort, "epoche" | "name">): string {
  return `${o.epoche} ${o.name}`;
}

/** Strukturierter Orte-Editor - verschlankte Variante von PersonenEditor.tsx
 * (Personen-Fundus): durchsuchbare Liste links, Name/Epoche/Beschreibung-
 * Bearbeitung rechts. Anders als bei Figuren gibt es hier nur zwei Felder
 * und keine dynamischen Zusatzfelder, deshalb auch keine "Eigenes Feld"-/
 * "Kopieren"-Dialoge. */
export function OrteEditor({ onGeaendert }: OrteEditorProps) {
  const [orte, setOrte] = useState<Ort[]>([]);
  const [wirdGeladen, setWirdGeladen] = useState(true);
  const [ausgewaehlt, setAusgewaehlt] = useState<string | null>(null);

  const [epocheFilter, setEpocheFilter] = useState("");
  const [suchtext, setSuchtext] = useState("");

  const [neuerName, setNeuerName] = useState("");
  const [bearbeiteteEpoche, setBearbeiteteEpoche] = useState("");
  const [bearbeiteteBeschreibung, setBearbeiteteBeschreibung] = useState("");
  const [wirdGespeichert, setWirdGespeichert] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  const [zeigtNeuDialog, setZeigtNeuDialog] = useState(false);
  const [neueEpoche, setNeueEpoche] = useState("");
  const [neuerOrtName, setNeuerOrtName] = useState("");

  const [zeigtLoeschenBestaetigung, setZeigtLoeschenBestaetigung] = useState(false);
  const [wirdGeloescht, setWirdGeloescht] = useState(false);

  useEffect(() => {
    laden();
  }, []);

  function laden() {
    setWirdGeladen(true);
    api
      .orteListeLesen()
      .then((antwort) => setOrte(antwort.orte))
      .finally(() => setWirdGeladen(false));
  }

  const epochenListe = useMemo(
    () => Array.from(new Set(orte.map((o) => o.epoche))).sort((a, b) => a.localeCompare(b, "de")),
    [orte],
  );

  const gefiltert = useMemo(() => {
    const suche = suchtext.trim().toLowerCase();
    return orte
      .filter((o) => !epocheFilter || o.epoche === epocheFilter)
      .filter((o) => !suche || `${o.name} ${o.beschreibung}`.toLowerCase().includes(suche))
      .sort((a, b) => a.name.localeCompare(b.name, "de"));
  }, [orte, epocheFilter, suchtext]);

  const ausgewaehlterOrt = useMemo(
    () => orte.find((o) => ortSchluessel(o) === ausgewaehlt) ?? null,
    [orte, ausgewaehlt],
  );

  function auswaehlen(o: Ort) {
    setAusgewaehlt(ortSchluessel(o));
    setNeuerName(o.name);
    setBearbeiteteEpoche(o.epoche);
    setBearbeiteteBeschreibung(o.beschreibung);
    setFehler(null);
  }

  async function speichern() {
    if (!ausgewaehlterOrt) return;
    setWirdGespeichert(true);
    setFehler(null);
    try {
      const aktualisiert = await api.ortAktualisieren(
        ausgewaehlterOrt.epoche, ausgewaehlterOrt.name, bearbeiteteBeschreibung,
        neuerName.trim() !== ausgewaehlterOrt.name ? neuerName.trim() : undefined,
        bearbeiteteEpoche.trim() !== ausgewaehlterOrt.epoche ? bearbeiteteEpoche.trim() : undefined,
      );
      setOrte((bisher) => bisher.map((o) => (ortSchluessel(o) === ausgewaehlt ? aktualisiert : o)));
      setAusgewaehlt(ortSchluessel(aktualisiert));
      onGeaendert();
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setWirdGespeichert(false);
    }
  }

  async function neuenOrtAnlegen() {
    if (!neueEpoche.trim() || !neuerOrtName.trim()) return;
    setFehler(null);
    try {
      const ort = await api.ortAnlegen(neueEpoche.trim(), neuerOrtName.trim(), "");
      setOrte((bisher) => [...bisher, ort]);
      setZeigtNeuDialog(false);
      setNeueEpoche("");
      setNeuerOrtName("");
      auswaehlen(ort);
      onGeaendert();
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    }
  }

  async function loeschen() {
    if (!ausgewaehlterOrt) return;
    setWirdGeloescht(true);
    try {
      await api.ortLoeschen(ausgewaehlterOrt.epoche, ausgewaehlterOrt.name);
      setOrte((bisher) => bisher.filter((o) => ortSchluessel(o) !== ausgewaehlt));
      setAusgewaehlt(null);
      setZeigtLoeschenBestaetigung(false);
      onGeaendert();
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setWirdGeloescht(false);
    }
  }

  if (wirdGeladen) {
    return (
      <Card>
        <p className="text-sm text-text-muted">Lädt...</p>
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.1fr_1.4fr]">
      <datalist id="orte-epochen-liste">
        {epochenListe.map((e) => (
          <option key={e} value={e} />
        ))}
      </datalist>

      <Card className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-heading text-sm font-semibold tracking-wide text-text">
            {gefiltert.length} von {orte.length} Orten
          </h3>
          <Button variant="secondary" onClick={() => setZeigtNeuDialog(true)}>
            + Neuer Ort
          </Button>
        </div>

        <Input
          placeholder="Name oder Beschreibung durchsuchen..."
          value={suchtext}
          onChange={(e) => setSuchtext(e.target.value)}
        />
        <Select value={epocheFilter} onChange={(e) => setEpocheFilter(e.target.value)}>
          <option value="">Alle Epochen</option>
          {epochenListe.map((e) => (
            <option key={e} value={e}>
              {e}
            </option>
          ))}
        </Select>

        <ul className="max-h-[clamp(320px,60vh,700px)] space-y-1 overflow-y-auto">
          {gefiltert.map((o) => (
            <li key={ortSchluessel(o)}>
              <button
                type="button"
                onClick={() => auswaehlen(o)}
                className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                  ortSchluessel(o) === ausgewaehlt
                    ? "border-accent bg-accent-soft text-accent-light"
                    : "border-border bg-bg text-text hover:bg-surface-hover"
                }`}
              >
                <div className="font-medium">{o.name}</div>
                <div className="text-xs text-text-muted">{o.epoche}</div>
              </button>
            </li>
          ))}
          {gefiltert.length === 0 && <p className="text-sm text-text-muted">Keine Orte gefunden.</p>}
        </ul>
      </Card>

      <Card>
        {!ausgewaehlterOrt ? (
          <p className="text-sm text-text-muted">Links einen Ort auswählen, um ihn zu bearbeiten.</p>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="flex flex-wrap gap-2">
                <div>
                  <Label>Name</Label>
                  <Input value={neuerName} onChange={(e) => setNeuerName(e.target.value)} />
                </div>
                <div>
                  <Label>Epoche</Label>
                  <Input
                    list="orte-epochen-liste"
                    value={bearbeiteteEpoche}
                    onChange={(e) => setBearbeiteteEpoche(e.target.value)}
                  />
                </div>
              </div>
              <Button variant="danger" onClick={() => setZeigtLoeschenBestaetigung(true)}>
                Löschen
              </Button>
            </div>

            <div>
              <Label>Beschreibung</Label>
              <Textarea
                rows={4}
                value={bearbeiteteBeschreibung}
                onChange={(e) => setBearbeiteteBeschreibung(e.target.value)}
              />
            </div>

            {fehler && <p className="text-sm text-red-400">{fehler}</p>}

            <div className="flex justify-end">
              <Button onClick={speichern} disabled={wirdGespeichert}>
                {wirdGespeichert ? "Speichert..." : "Speichern"}
              </Button>
            </div>
          </div>
        )}
      </Card>

      {zeigtNeuDialog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
          onClick={() => setZeigtNeuDialog(false)}
        >
          <div
            className="relative mx-auto w-full max-w-sm rounded-2xl border border-border bg-surface p-6 shadow-2xl shadow-black/50"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="font-heading mb-4 text-lg font-semibold text-text">Neuen Ort anlegen</h3>
            <div className="space-y-3">
              <div>
                <Label>Epoche</Label>
                <Input
                  list="orte-epochen-liste"
                  value={neueEpoche}
                  onChange={(e) => setNeueEpoche(e.target.value)}
                  placeholder="z.B. Regency"
                />
              </div>
              <div>
                <Label>Name</Label>
                <Input value={neuerOrtName} onChange={(e) => setNeuerOrtName(e.target.value)} />
              </div>
              {fehler && <p className="text-sm text-red-400">{fehler}</p>}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setZeigtNeuDialog(false)}>
                Abbrechen
              </Button>
              <Button onClick={neuenOrtAnlegen} disabled={!neueEpoche.trim() || !neuerOrtName.trim()}>
                Anlegen
              </Button>
            </div>
          </div>
        </div>
      )}

      {zeigtLoeschenBestaetigung && ausgewaehlterOrt && (
        <ConfirmDialog
          titel="Ort löschen?"
          beschreibung={`"${ausgewaehlterOrt.name}" (${ausgewaehlterOrt.epoche}) wird endgültig aus dem Fundus entfernt.`}
          bestaetigenText="Löschen"
          wirdAusgefuehrt={wirdGeloescht}
          onBestaetigen={loeschen}
          onAbbrechen={() => setZeigtLoeschenBestaetigung(false)}
        />
      )}
    </div>
  );
}
