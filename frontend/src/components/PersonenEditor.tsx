import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { FundusFigur } from "../api/types";
import { Button, Card, Input, Label, Select } from "./ui";
import { ConfirmDialog } from "./ConfirmDialog";

interface PersonenEditorProps {
  /** Wird nach jeder erfolgreichen Aenderung aufgerufen, damit z.B. die
   * eingeklappte Rohtext-Ansicht (FundusPage.tsx) bei ihrem naechsten
   * Aufklappen den aktuellen Stand zeigt statt eines veralteten. */
  onGeaendert: () => void;
}

function figurSchluessel(f: Pick<FundusFigur, "epoche" | "name">): string {
  return `${f.epoche} ${f.name}`;
}

/** Strukturierter Personen-Editor: alphabetisch/nach Epoche/Alter/Rolle
 * durchsuchbare Liste links, Feld-fuer-Feld-Bearbeitung der ausgewaehlten
 * Figur rechts. Haelt eine EIGENE Kopie der Figuren-Liste (statt sie vom
 * Elternteil zu bekommen), da sie ihre eigenen CRUD-Aufrufe macht und nach
 * jeder Aenderung ohnehin neu laden muss. */
export function PersonenEditor({ onGeaendert }: PersonenEditorProps) {
  const [figuren, setFiguren] = useState<FundusFigur[]>([]);
  const [wirdGeladen, setWirdGeladen] = useState(true);
  const [ausgewaehlt, setAusgewaehlt] = useState<string | null>(null);

  const [epocheFilter, setEpocheFilter] = useState("");
  const [alterFilter, setAlterFilter] = useState("");
  const [rolleFilter, setRolleFilter] = useState("");
  const [suchtext, setSuchtext] = useState("");

  const [bearbeitung, setBearbeitung] = useState<Record<string, string> | null>(null);
  const [neuerName, setNeuerName] = useState("");
  const [bearbeiteteEpoche, setBearbeiteteEpoche] = useState("");
  const [wirdGespeichert, setWirdGespeichert] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  const [zeigtNeuDialog, setZeigtNeuDialog] = useState(false);
  const [neueEpoche, setNeueEpoche] = useState("");
  const [neuerFigurName, setNeuerFigurName] = useState("");

  const [zeigtFeldDialog, setZeigtFeldDialog] = useState(false);
  const [neuesFeldName, setNeuesFeldName] = useState("");
  const [neuesFeldWert, setNeuesFeldWert] = useState("");
  const [neuesFeldFuerAlle, setNeuesFeldFuerAlle] = useState(false);

  const [zeigtKopierenDialog, setZeigtKopierenDialog] = useState(false);
  const [kopierZielEpoche, setKopierZielEpoche] = useState("");
  const [kopierNeuerName, setKopierNeuerName] = useState("");
  const [wirdKopiert, setWirdKopiert] = useState(false);

  const [zeigtLoeschenBestaetigung, setZeigtLoeschenBestaetigung] = useState(false);
  const [wirdGeloescht, setWirdGeloescht] = useState(false);

  useEffect(() => {
    laden();
  }, []);

  function laden() {
    setWirdGeladen(true);
    api
      .fundusFigurenLesen()
      .then((antwort) => setFiguren(antwort.figuren))
      .finally(() => setWirdGeladen(false));
  }

  const epochenListe = useMemo(
    () => Array.from(new Set(figuren.map((f) => f.epoche))).sort((a, b) => a.localeCompare(b, "de")),
    [figuren],
  );

  const gefiltert = useMemo(() => {
    const suche = suchtext.trim().toLowerCase();
    const alter = alterFilter.trim().toLowerCase();
    const rolle = rolleFilter.trim().toLowerCase();
    return figuren
      .filter((f) => !epocheFilter || f.epoche === epocheFilter)
      .filter((f) => !alter || (f.felder["Alter"] ?? "").toLowerCase().includes(alter))
      .filter((f) => !rolle || (f.felder["Stand/Rolle"] ?? "").toLowerCase().includes(rolle))
      .filter((f) => !suche || f.name.toLowerCase().includes(suche))
      .sort((a, b) => a.name.localeCompare(b.name, "de"));
  }, [figuren, epocheFilter, alterFilter, rolleFilter, suchtext]);

  const ausgewaehlteFigur = useMemo(
    () => figuren.find((f) => figurSchluessel(f) === ausgewaehlt) ?? null,
    [figuren, ausgewaehlt],
  );

  function auswaehlen(f: FundusFigur) {
    setAusgewaehlt(figurSchluessel(f));
    setBearbeitung({ ...f.felder });
    setNeuerName(f.name);
    setBearbeiteteEpoche(f.epoche);
    setFehler(null);
  }

  async function speichern() {
    if (!ausgewaehlteFigur || !bearbeitung) return;
    setWirdGespeichert(true);
    setFehler(null);
    try {
      const aktualisiert = await api.fundusFigurAktualisieren(
        ausgewaehlteFigur.epoche,
        ausgewaehlteFigur.name,
        bearbeitung,
        neuerName.trim() !== ausgewaehlteFigur.name ? neuerName.trim() : undefined,
        bearbeiteteEpoche.trim() !== ausgewaehlteFigur.epoche ? bearbeiteteEpoche.trim() : undefined,
      );
      setFiguren((bisher) =>
        bisher.map((f) => (figurSchluessel(f) === ausgewaehlt ? aktualisiert : f)),
      );
      setAusgewaehlt(figurSchluessel(aktualisiert));
      onGeaendert();
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setWirdGespeichert(false);
    }
  }

  async function kopieren() {
    if (!ausgewaehlteFigur || !kopierZielEpoche.trim()) return;
    setWirdKopiert(true);
    setFehler(null);
    try {
      const kopie = await api.fundusFigurKopieren(
        ausgewaehlteFigur.epoche,
        ausgewaehlteFigur.name,
        kopierZielEpoche.trim(),
        kopierNeuerName.trim() || undefined,
      );
      setFiguren((bisher) => [...bisher, kopie]);
      setZeigtKopierenDialog(false);
      setKopierZielEpoche("");
      setKopierNeuerName("");
      auswaehlen(kopie);
      onGeaendert();
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setWirdKopiert(false);
    }
  }

  async function neueFigurAnlegen() {
    if (!neueEpoche.trim() || !neuerFigurName.trim()) return;
    setFehler(null);
    try {
      const figur = await api.fundusFigurAnlegen(neueEpoche.trim(), neuerFigurName.trim(), {});
      setFiguren((bisher) => [...bisher, figur]);
      setZeigtNeuDialog(false);
      setNeueEpoche("");
      setNeuerFigurName("");
      auswaehlen(figur);
      onGeaendert();
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    }
  }

  async function feldHinzufuegen() {
    if (!ausgewaehlteFigur || !neuesFeldName.trim()) return;
    setFehler(null);
    try {
      const aktualisiert = await api.fundusFeldHinzufuegen(
        ausgewaehlteFigur.epoche, ausgewaehlteFigur.name, neuesFeldName.trim(), neuesFeldWert, neuesFeldFuerAlle,
      );
      // Bei "für alle" bekommen auch andere Figuren das (leere) Feld - statt
      // das clientseitig nachzubilden, laden wir die komplette Liste neu.
      await laden();
      setAusgewaehlt(figurSchluessel(aktualisiert));
      setBearbeitung({ ...aktualisiert.felder });
      setNeuerName(aktualisiert.name);
      setZeigtFeldDialog(false);
      setNeuesFeldName("");
      setNeuesFeldWert("");
      setNeuesFeldFuerAlle(false);
      onGeaendert();
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    }
  }

  async function loeschen() {
    if (!ausgewaehlteFigur) return;
    setWirdGeloescht(true);
    try {
      await api.fundusFigurLoeschen(ausgewaehlteFigur.epoche, ausgewaehlteFigur.name);
      setFiguren((bisher) => bisher.filter((f) => figurSchluessel(f) !== ausgewaehlt));
      setAusgewaehlt(null);
      setBearbeitung(null);
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
      <datalist id="fundus-epochen-liste">
        {epochenListe.map((e) => (
          <option key={e} value={e} />
        ))}
      </datalist>

      <Card className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-heading text-sm font-semibold tracking-wide text-text">
            {gefiltert.length} von {figuren.length} Personen
          </h3>
          <Button variant="secondary" onClick={() => setZeigtNeuDialog(true)}>
            + Neue Person
          </Button>
        </div>

        <Input
          placeholder="Name durchsuchen..."
          value={suchtext}
          onChange={(e) => setSuchtext(e.target.value)}
        />
        <div className="grid grid-cols-3 gap-2">
          <Select value={epocheFilter} onChange={(e) => setEpocheFilter(e.target.value)}>
            <option value="">Alle Epochen</option>
            {epochenListe.map((e) => (
              <option key={e} value={e}>
                {e}
              </option>
            ))}
          </Select>
          <Input placeholder="Alter enthält..." value={alterFilter} onChange={(e) => setAlterFilter(e.target.value)} />
          <Input placeholder="Rolle enthält..." value={rolleFilter} onChange={(e) => setRolleFilter(e.target.value)} />
        </div>

        <ul className="max-h-[clamp(320px,60vh,700px)] space-y-1 overflow-y-auto">
          {gefiltert.map((f) => (
            <li key={figurSchluessel(f)}>
              <button
                type="button"
                onClick={() => auswaehlen(f)}
                className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                  figurSchluessel(f) === ausgewaehlt
                    ? "border-accent bg-accent-soft text-accent-light"
                    : "border-border bg-bg text-text hover:bg-surface-hover"
                }`}
              >
                <div className="font-medium">{f.name}</div>
                <div className="text-xs text-text-muted">
                  {f.epoche}
                  {f.felder["Alter"] ? ` · ${f.felder["Alter"]}` : ""}
                  {f.felder["Stand/Rolle"] ? ` · ${f.felder["Stand/Rolle"]}` : ""}
                </div>
              </button>
            </li>
          ))}
          {gefiltert.length === 0 && <p className="text-sm text-text-muted">Keine Personen gefunden.</p>}
        </ul>
      </Card>

      <Card>
        {!ausgewaehlteFigur || !bearbeitung ? (
          <p className="text-sm text-text-muted">Links eine Person auswählen, um sie zu bearbeiten.</p>
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
                    list="fundus-epochen-liste"
                    value={bearbeiteteEpoche}
                    onChange={(e) => setBearbeiteteEpoche(e.target.value)}
                  />
                </div>
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => setZeigtKopierenDialog(true)}>
                  Kopieren
                </Button>
                <Button variant="danger" onClick={() => setZeigtLoeschenBestaetigung(true)}>
                  Löschen
                </Button>
              </div>
            </div>

            {Object.entries(bearbeitung).map(([feld, wert]) => (
              <div key={feld}>
                <Label>{feld}</Label>
                {feld === "Eigenschaften" || feld === "Aussehen" ? (
                  <textarea
                    value={wert}
                    onChange={(e) => setBearbeitung({ ...bearbeitung, [feld]: e.target.value })}
                    rows={2}
                    className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text outline-none transition-colors placeholder:text-text-muted/70 focus:border-accent"
                  />
                ) : (
                  <Input value={wert} onChange={(e) => setBearbeitung({ ...bearbeitung, [feld]: e.target.value })} />
                )}
              </div>
            ))}

            <Button variant="secondary" className="self-start" onClick={() => setZeigtFeldDialog(true)}>
              + Eigenes Feld hinzufügen
            </Button>

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
            <h3 className="font-heading mb-4 text-lg font-semibold text-text">Neue Person anlegen</h3>
            <div className="space-y-3">
              <div>
                <Label>Epoche</Label>
                <Input
                  list="fundus-epochen-liste"
                  value={neueEpoche}
                  onChange={(e) => setNeueEpoche(e.target.value)}
                  placeholder="z.B. Regency"
                />
              </div>
              <div>
                <Label>Name</Label>
                <Input value={neuerFigurName} onChange={(e) => setNeuerFigurName(e.target.value)} />
              </div>
              {fehler && <p className="text-sm text-red-400">{fehler}</p>}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setZeigtNeuDialog(false)}>
                Abbrechen
              </Button>
              <Button onClick={neueFigurAnlegen} disabled={!neueEpoche.trim() || !neuerFigurName.trim()}>
                Anlegen
              </Button>
            </div>
          </div>
        </div>
      )}

      {zeigtFeldDialog && ausgewaehlteFigur && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
          onClick={() => setZeigtFeldDialog(false)}
        >
          <div
            className="relative mx-auto w-full max-w-sm rounded-2xl border border-border bg-surface p-6 shadow-2xl shadow-black/50"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="font-heading mb-4 text-lg font-semibold text-text">Eigenes Feld hinzufügen</h3>
            <div className="space-y-3">
              <div>
                <Label>Feldname</Label>
                <Input value={neuesFeldName} onChange={(e) => setNeuesFeldName(e.target.value)} placeholder="z.B. Blutgruppe" />
              </div>
              <div>
                <Label>Wert für {ausgewaehlteFigur.name}</Label>
                <Input value={neuesFeldWert} onChange={(e) => setNeuesFeldWert(e.target.value)} />
              </div>
              <label className="flex items-center gap-2 text-sm text-text">
                <input
                  type="checkbox"
                  checked={neuesFeldFuerAlle}
                  onChange={(e) => setNeuesFeldFuerAlle(e.target.checked)}
                />
                Feld (leer) auch bei allen anderen Personen ergänzen
              </label>
              {fehler && <p className="text-sm text-red-400">{fehler}</p>}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setZeigtFeldDialog(false)}>
                Abbrechen
              </Button>
              <Button onClick={feldHinzufuegen} disabled={!neuesFeldName.trim()}>
                Hinzufügen
              </Button>
            </div>
          </div>
        </div>
      )}

      {zeigtKopierenDialog && ausgewaehlteFigur && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
          onClick={() => setZeigtKopierenDialog(false)}
        >
          <div
            className="relative mx-auto w-full max-w-sm rounded-2xl border border-border bg-surface p-6 shadow-2xl shadow-black/50"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="font-heading mb-4 text-lg font-semibold text-text">
              "{ausgewaehlteFigur.name}" kopieren
            </h3>
            <div className="space-y-3">
              <div>
                <Label>Ziel-Epoche</Label>
                <Input
                  list="fundus-epochen-liste"
                  value={kopierZielEpoche}
                  onChange={(e) => setKopierZielEpoche(e.target.value)}
                  placeholder="z.B. Mittelalter"
                />
              </div>
              <div>
                <Label>Name der Kopie (optional)</Label>
                <Input
                  value={kopierNeuerName}
                  onChange={(e) => setKopierNeuerName(e.target.value)}
                  placeholder={ausgewaehlteFigur.name}
                />
              </div>
              {fehler && <p className="text-sm text-red-400">{fehler}</p>}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setZeigtKopierenDialog(false)}>
                Abbrechen
              </Button>
              <Button onClick={kopieren} disabled={!kopierZielEpoche.trim() || wirdKopiert}>
                {wirdKopiert ? "Kopiert..." : "Kopieren"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {zeigtLoeschenBestaetigung && ausgewaehlteFigur && (
        <ConfirmDialog
          titel="Person löschen?"
          beschreibung={`"${ausgewaehlteFigur.name}" (${ausgewaehlteFigur.epoche}) wird endgültig aus dem Fundus entfernt.`}
          bestaetigenText="Löschen"
          wirdAusgefuehrt={wirdGeloescht}
          onBestaetigen={loeschen}
          onAbbrechen={() => setZeigtLoeschenBestaetigung(false)}
        />
      )}
    </div>
  );
}
