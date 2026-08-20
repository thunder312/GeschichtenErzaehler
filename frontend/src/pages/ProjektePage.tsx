import { useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent } from "react";
import { api } from "../api/client";
import type { AutomatikZustand, EpocheKurz, ProjektKurz } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Badge, Button, Card, CardTitle, Input, Label, Select } from "../components/ui";

function AutomatikBadge({ zustand }: { zustand: AutomatikZustand }) {
  if (zustand === "laeuft") return <Badge tone="amber">🤖 Automatik läuft</Badge>;
  if (zustand === "fehler") return <Badge tone="amber">⚠️ Automatik-Fehler</Badge>;
  if (zustand === "gestoppt") return <Badge tone="amber">⏸️ Automatik angehalten</Badge>;
  // "abgeschlossen_mit_resten" bleibt (echter Handlungsbedarf - Reste
  // pruefen), "abgeschlossen_sauber" (alles fertig, nichts zu tun) zeigt
  // bewusst KEINEN Badge mehr - unnoetig, die Kapitelzahl in der Zeile
  // darunter sagt bereits "X von Y geplant".
  if (zustand === "abgeschlossen_mit_resten") return <Badge tone="amber">⚠️ Automatik fertig – Reste prüfen</Badge>;
  return null;
}

interface ProjektePageProps {
  projekte: ProjektKurz[];
  epochen: EpocheKurz[];
  aktuellesProjekt: string | null;
  onProjekteGeaendert: () => void;
  onProjektAuswaehlen: (ordner: string) => void;
  onProjektGeloescht: (ordner: string) => void;
  onNeuSchreibenGestartet: (ordner: string) => void;
}

export function ProjektePage({
  projekte,
  epochen,
  aktuellesProjekt,
  onProjekteGeaendert,
  onProjektAuswaehlen,
  onProjektGeloescht,
  onNeuSchreibenGestartet,
}: ProjektePageProps) {
  const [titel, setTitel] = useState("");
  const [epoche, setEpoche] = useState("");
  const [zweiteEpoche, setZweiteEpoche] = useState("");
  const [epocheEinleitungssatz, setEpocheEinleitungssatz] = useState<string | null>(null);
  const [epocheInfoLaedt, setEpocheInfoLaedt] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [wirdAngelegt, setWirdAngelegt] = useState(false);
  const [wirdGeloescht, setWirdGeloescht] = useState<string | null>(null);
  const [loeschenAnfrage, setLoeschenAnfrage] = useState<ProjektKurz | null>(null);
  const [wirdNeuGeschrieben, setWirdNeuGeschrieben] = useState<string | null>(null);
  const [neuSchreibenAnfrage, setNeuSchreibenAnfrage] = useState<ProjektKurz | null>(null);
  const [neuSchreibenFehler, setNeuSchreibenFehler] = useState<string | null>(null);
  const [suchtext, setSuchtext] = useState("");
  const [epocheFilter, setEpocheFilter] = useState("");
  const [sortierungAbsteigend, setSortierungAbsteigend] = useState(false);

  // Nur tatsaechlich vorkommende Epochen zur Auswahl anbieten, nicht alle
  // jemals angelegten (siehe `epochen`-Prop unten fuer "Neues Projekt") -
  // ein Filter auf eine Epoche ohne eigene Projekte waere sinnlos.
  const vorhandeneEpochen = useMemo(() => {
    const gefunden = new Set(projekte.map((p) => p.epoche).filter((e): e is string => !!e));
    return Array.from(gefunden).sort((a, b) => a.localeCompare(b));
  }, [projekte]);

  // Epoche -> Hex-Farbe, fuer das farbige Quadrat je Projektzeile (siehe
  // ToDo.md) - `epochen` kommt bereits fertig aus App.tsx, hier nur als
  // Lookup umgebaut statt bei jeder Zeile erneut linear zu suchen.
  const epocheFarbe = useMemo(() => {
    const map = new Map<string, string>();
    for (const e of epochen) if (e.farbe) map.set(e.name, e.farbe);
    return map;
  }, [epochen]);

  const gefilterteProjekte = useMemo(() => {
    const suchtextNormalisiert = suchtext.trim().toLowerCase();
    const gefiltert = projekte.filter((p) => {
      if (epocheFilter && p.epoche !== epocheFilter) return false;
      if (suchtextNormalisiert && !(p.titel ?? p.ordner).toLowerCase().includes(suchtextNormalisiert)) {
        return false;
      }
      return true;
    });
    const sortiert = [...gefiltert].sort((a, b) =>
      (a.titel ?? a.ordner).localeCompare(b.titel ?? b.ordner, "de"),
    );
    if (sortierungAbsteigend) sortiert.reverse();
    return sortiert;
  }, [projekte, suchtext, epocheFilter, sortierungAbsteigend]);

  // Vorbelegung nur EINMAL setzen, sobald die (von App.tsx geladene) Liste
  // erstmals nicht leer ist - nicht bei jeder spaeteren Aenderung von
  // `epochen` (z.B. weil im Tab "Epoche erstellen" eine neue Epoche
  // hinzukam), sonst wuerde eine bereits laufende manuelle Auswahl hier
  // unerwartet ueberschrieben.
  const vorbelegungGesetzt = useRef(false);
  useEffect(() => {
    if (vorbelegungGesetzt.current || epochen.length === 0) return;
    vorbelegungGesetzt.current = true;
    // Zuletzt gewaehlte Epoche vorbelegen statt immer die alphabetisch
    // erste - sonst landet ein neues Projekt leicht in der falschen
    // Epoche, wenn man sich beim erneuten Oeffnen der Seite auf die
    // zuletzt benutzte Epoche verlaesst, ohne die Auswahl zu pruefen.
    const letzte = window.localStorage.getItem("letzte-epoche");
    const vorbelegung = letzte && epochen.some((e) => e.name === letzte) ? letzte : epochen[0].name;
    setEpoche(vorbelegung);
  }, [epochen]);

  // Einleitungssatz-Vorlage der gewaehlten Epoche fuer die Info-Box unten im
  // "Neues Projekt anlegen"-Container (siehe app/api/epochen.py - eine der
  // vier/fuenf Rohentwurf-Dateien der Epochen-Bibliothek).
  useEffect(() => {
    if (!epoche) {
      setEpocheEinleitungssatz(null);
      return;
    }
    let abgebrochen = false;
    setEpocheInfoLaedt(true);
    api
      .epocheDateiLesen(epoche, "einleitungssatz.txt")
      .then((text) => {
        if (!abgebrochen) setEpocheEinleitungssatz(text);
      })
      .catch(() => {
        if (!abgebrochen) setEpocheEinleitungssatz(null);
      })
      .finally(() => {
        if (!abgebrochen) setEpocheInfoLaedt(false);
      });
    return () => {
      abgebrochen = true;
    };
  }, [epoche]);

  function loeschenAnfordern(ereignis: MouseEvent, p: ProjektKurz) {
    // Verhindert, dass der Klick auf das "X" zusaetzlich den Zeilen-Klick-
    // Handler ausloest, der das Projekt oeffnen wuerde.
    ereignis.stopPropagation();
    setLoeschenAnfrage(p);
  }

  async function loeschenBestaetigt() {
    if (!loeschenAnfrage) return;
    const ordner = loeschenAnfrage.ordner;
    setWirdGeloescht(ordner);
    try {
      await api.projektLoeschen(ordner);
      setLoeschenAnfrage(null);
      onProjektGeloescht(ordner);
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    } finally {
      setWirdGeloescht(null);
    }
  }

  function neuSchreibenAnfordern(ereignis: MouseEvent, p: ProjektKurz) {
    // Wie loeschenAnfordern() oben - verhindert, dass der Zeilen-Klick
    // (oeffnet das Projekt) zusaetzlich ausgeloest wird.
    ereignis.stopPropagation();
    setNeuSchreibenFehler(null);
    setNeuSchreibenAnfrage(p);
  }

  async function neuSchreibenBestaetigt() {
    if (!neuSchreibenAnfrage) return;
    const ordner = neuSchreibenAnfrage.ordner;
    setWirdNeuGeschrieben(ordner);
    setNeuSchreibenFehler(null);
    try {
      // Nur die Dateikopie (siehe app/api/projects.py:projekt_neu_schreiben) -
      // der Automatikmodus wird bewusst NICHT automatisch mitgestartet, der
      // Nutzer landet stattdessen im Gerüst-Tab und stoesst das Schreiben
      // selbst an, wenn/wann er will (siehe App.tsx:neuSchreibenGestartet).
      const kopie = await api.projektNeuSchreiben(ordner);
      setNeuSchreibenAnfrage(null);
      onProjekteGeaendert();
      onNeuSchreibenGestartet(kopie.ordner);
    } catch (e) {
      setNeuSchreibenFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setWirdNeuGeschrieben(null);
    }
  }

  function epocheAuswaehlen(name: string) {
    setEpoche(name);
    window.localStorage.setItem("letzte-epoche", name);
    // Zweite Epoche muss sich von der ersten unterscheiden (siehe Backend-
    // Validierung in app/api/projects.py) - bei Kollision zuruecksetzen,
    // statt den Nutzer erst beim Absenden mit einem Fehler zu konfrontieren.
    if (zweiteEpoche === name) setZweiteEpoche("");
  }

  async function anlegen() {
    if (!epoche) return;
    setWirdAngelegt(true);
    setFehler(null);
    try {
      const neues = await api.projektAnlegen(titel.trim(), epoche, zweiteEpoche);
      setTitel("");
      setZweiteEpoche("");
      onProjekteGeaendert();
      onProjektAuswaehlen(neues.ordner);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setWirdAngelegt(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 p-4 sm:p-6 md:grid-cols-[2fr_1fr]">
      <Card>
        <CardTitle>📚 Vorhandene Projekte</CardTitle>
        {projekte.length > 0 && (
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Input
              autoComplete="off"
              value={suchtext}
              onChange={(e) => setSuchtext(e.target.value)}
              placeholder="🔍 Nach Namen suchen..."
              className="max-w-[220px]"
            />
            <Select value={epocheFilter} onChange={(e) => setEpocheFilter(e.target.value)} className="max-w-[200px]">
              <option value="">Alle Epochen</option>
              {vorhandeneEpochen.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </Select>
            <button
              onClick={() => setSortierungAbsteigend((bisher) => !bisher)}
              title={sortierungAbsteigend ? "Sortierung: Z → A (klicken für A → Z)" : "Sortierung: A → Z (klicken für Z → A)"}
              className="rounded-lg border border-border px-3 py-1.5 text-sm text-text-muted transition-colors hover:bg-surface-hover hover:text-text"
            >
              {sortierungAbsteigend ? "Z → A" : "A → Z"}
            </button>
          </div>
        )}
        {projekte.length === 0 ? (
          <p className="text-sm text-text-muted">Noch kein Projekt angelegt.</p>
        ) : gefilterteProjekte.length === 0 ? (
          <p className="text-sm text-text-muted">
            Kein Projekt passt zu den Filtern.{" "}
            <button
              onClick={() => {
                setSuchtext("");
                setEpocheFilter("");
              }}
              className="text-accent-light hover:underline"
            >
              Filter zurücksetzen
            </button>
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {gefilterteProjekte.map((p) => (
              <li
                key={p.ordner}
                onClick={() => onProjektAuswaehlen(p.ordner)}
                className={`flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors hover:bg-surface-hover ${
                  aktuellesProjekt === p.ordner ? "bg-accent-soft" : ""
                }`}
              >
                <button
                  onClick={(e) => loeschenAnfordern(e, p)}
                  disabled={wirdGeloescht === p.ordner}
                  title={`"${p.titel ?? p.ordner}" löschen`}
                  aria-label={`"${p.titel ?? p.ordner}" löschen`}
                  className="shrink-0 text-sm leading-none text-red-400/60 transition-colors hover:text-red-400 disabled:opacity-40"
                >
                  ✕
                </button>
                {p.letztes_geplantes_kapitel && (
                  <button
                    onClick={(e) => neuSchreibenAnfordern(e, p)}
                    disabled={wirdNeuGeschrieben === p.ordner || p.automatik_zustand === "laeuft"}
                    title={`"${p.titel ?? p.ordner}" als Kopie neu schreiben lassen (Schreiber: Mistral)`}
                    aria-label={`"${p.titel ?? p.ordner}" neu schreiben`}
                    className="shrink-0 text-sm leading-none text-text-muted/60 transition-colors hover:text-text disabled:opacity-40"
                  >
                    🔄
                  </button>
                )}
                <div>
                  <div className="flex items-center gap-2">
                    {p.epoche && epocheFarbe.get(p.epoche) && (
                      <span
                        aria-hidden="true"
                        title={p.epoche}
                        className="h-2.5 w-2.5 shrink-0 rounded-sm"
                        style={{ backgroundColor: epocheFarbe.get(p.epoche) }}
                      />
                    )}
                    <div className="font-medium text-text">{p.titel ?? p.ordner}</div>
                    {p.neu_geschrieben_aus && (
                      <span title={`Neu geschrieben - Kopie von "${p.neu_geschrieben_aus}"`} className="cursor-help text-sm">
                        🔄
                      </span>
                    )}
                    <AutomatikBadge zustand={p.automatik_zustand} />
                  </div>
                  <div className="text-xs text-text-muted">
                    {p.epoche ?? "unbekannte Epoche"}
                    {p.zweite_epoche ? ` ↔ ${p.zweite_epoche} (Zeitsprung)` : ""} · {p.anzahl_kapitel} Kapitel
                    {p.letztes_geplantes_kapitel ? ` von ${p.letztes_geplantes_kapitel} geplant` : ""}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <CardTitle>✨ Neues Projekt anlegen</CardTitle>
        <div className="space-y-3">
          <div>
            <Label>Titel (optional)</Label>
            <Input
              autoComplete="off"
              value={titel}
              onChange={(e) => setTitel(e.target.value)}
              placeholder="ergibt sich oft erst im Architekten-Interview"
            />
          </div>
          <div>
            <Label>Epoche</Label>
            <Select value={epoche} onChange={(e) => epocheAuswaehlen(e.target.value)}>
              {epochen.map((e) => (
                <option key={e.name} value={e.name}>
                  {e.name}
                </option>
              ))}
            </Select>
            {epoche && (
              <div className="mt-2 rounded-lg border border-border bg-bg/40 p-3 text-xs text-text-muted">
                <p>
                  <span className="font-medium text-text">Genre-Prägung: </span>
                  {epochen.find((e) => e.name === epoche)?.genre || "(keine)"}
                </p>
                <p className="mt-1">
                  <span className="font-medium text-text">Einleitungssatz: </span>
                  {epocheInfoLaedt ? "…" : epocheEinleitungssatz || "(keine Vorlage hinterlegt)"}
                </p>
              </div>
            )}
          </div>
          <div>
            <Label>Zeitsprung: zweite Epoche (optional)</Label>
            <Select value={zweiteEpoche} onChange={(e) => setZweiteEpoche(e.target.value)}>
              <option value="">Keine - nur eine Epoche</option>
              {epochen
                .filter((e) => e.name !== epoche)
                .map((e) => (
                  <option key={e.name} value={e.name}>
                    {e.name}
                  </option>
                ))}
            </Select>
            <p className="mt-1 text-xs text-text-muted">
              Für Geschichten mit Zeitsprung (Zeitreise-Gerät, Ritual, o.ä.) zwischen zwei Epochen. Architekt,
              Autor und Prüfer bekommen dann beide Settings und fragen im Interview zusätzlich nach dem
              Zeitsprung-Mechanismus.
            </p>
          </div>
          {fehler && <p className="text-sm text-red-400">{fehler}</p>}
          <Button onClick={anlegen} disabled={wirdAngelegt || !epoche}>
            {wirdAngelegt ? "Wird angelegt..." : "Anlegen"}
          </Button>
        </div>
      </Card>

      {loeschenAnfrage && (
        <ConfirmDialog
          titel="Projekt löschen?"
          beschreibung={`"${loeschenAnfrage.titel ?? loeschenAnfrage.ordner}" wird unwiderruflich gelöscht - der komplette Ordner wird vom Server entfernt, es gibt keine .bak-Sicherung wie sonst üblich.`}
          bestaetigenText="Endgültig löschen"
          wirdAusgefuehrt={wirdGeloescht === loeschenAnfrage.ordner}
          onBestaetigen={loeschenBestaetigt}
          onAbbrechen={() => setLoeschenAnfrage(null)}
        />
      )}

      {neuSchreibenAnfrage && (
        <ConfirmDialog
          titel="Projekt neu schreiben?"
          beschreibung={
            `"${neuSchreibenAnfrage.titel ?? neuSchreibenAnfrage.ordner}" wird als Kopie ` +
            `("${neuSchreibenAnfrage.ordner}_v2") angelegt - Personas, Verbotsliste, Gerüst und die Ausgangslage vor ` +
            `Kapitel eins bleiben erhalten, alle bisherigen Kapitel/Prüfungen/Automatik-Ergebnisse NICHT (das ` +
            `Original bleibt unangetastet). Der Automatikmodus wird dabei NICHT automatisch gestartet - das Duplikat ` +
            `landet im Gerüst-Tab, du entscheidest selbst, wann es weitergeschrieben werden soll.` +
            (neuSchreibenFehler ? `\n\nFehler: ${neuSchreibenFehler}` : "")
          }
          bestaetigenText="Duplizieren"
          wirdAusgefuehrt={wirdNeuGeschrieben === neuSchreibenAnfrage.ordner}
          onBestaetigen={neuSchreibenBestaetigt}
          onAbbrechen={() => setNeuSchreibenAnfrage(null)}
        />
      )}
    </div>
  );
}
