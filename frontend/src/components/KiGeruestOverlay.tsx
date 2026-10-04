import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api/client";
import type { FundusFigur, KiGeruestFigurEingabe, KiGeruestRandbedingungen, KiGeruestStatus } from "../api/types";
import { fundusFigurenFuerEpoche } from "../utils/fundusMatch";
import { Button, Input, Label, Select, Textarea } from "./ui";

interface KiGeruestOverlayProps {
  ordner: string;
  /** Vorbelegung fuer das Feld "Setting/Kanon-Detail" (Anzeigename der Epoche). */
  epocheAnzeigename: string;
  /** Ordner-/Identifier-Name der Projekt-Epoche - fuer den Fundus-Abgleich
   * der Figuren-Auswahl (siehe fundusFigurenFuerEpoche). */
  epoche?: string | null;
  /** Personen-Fundus des Nutzers (GeruestPage laedt ihn ohnehin) - erlaubt,
   * Hauptfiguren aus dem Fundus der passenden Epoche zu uebernehmen statt
   * neu einzutippen. */
  fundusFiguren?: FundusFigur[];
  sshZielId: string;
  /** "eingabe": normal (Formular). "laeuft": beim Oeffnen lief schon ein
   * Entwurf (z.B. aus ProjektePage angestossen) - direkt in die
   * Fortschrittsansicht. */
  startphase: "eingabe" | "laeuft";
  /** Direkt nach erfolgreichem Start eines Entwurfs - der Aufrufer (GeruestPage)
   * wirft daraufhin sein eigenes Hintergrund-Polling an, damit der Lauf auch
   * nach dem Schliessen des Overlays im Editor sichtbar bleibt. */
  onGestartet?: () => void;
  /** KI-Lauf fertig - der Aufrufer laedt das Geruest neu und schliesst das
   * Overlay. */
  onFertig: () => void;
  onAbbrechen: () => void;
}

const LEERE_FIGUR: KiGeruestFigurEingabe = { name: "", alter: "", rolle: "", kurzbeschreibung: "" };

/** Kleines "?"-Icon neben einem Feld-Label: MouseOver zeigt den Kurztext als
 * nativen Tooltip, Klick blendet den ausführlichen Hilfetext als kleine
 * Karte darunter ein. */
function FeldHilfe({ kurz, children }: { kurz: string; children: ReactNode }) {
  const [offen, setOffen] = useState(false);
  const wrapperRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!offen) return;
    const onDoc = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) setOffen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [offen]);

  return (
    <span ref={wrapperRef} className="relative inline-block">
      <button
        type="button"
        title={kurz}
        aria-label="Hilfe"
        onClick={() => setOffen((o) => !o)}
        className="flex h-4 w-4 items-center justify-center rounded-full border border-border text-[10px] font-bold text-text-muted hover:border-accent hover:text-accent-light"
      >
        ?
      </button>
      {offen && (
        <div className="absolute left-0 top-6 z-20 w-72 rounded-lg border border-border bg-surface p-3 text-xs leading-relaxed text-text shadow-lg">
          {children}
        </div>
      )}
    </span>
  );
}

const HILFE_PRAEMISSE_VERLAUF = (
  <>
    <p className="mb-1">
      <strong>Prämisse</strong> = die Grundsituation der ganzen Geschichte (wer sind die Figuren,
      was bringt sie zusammen, worum geht es im Kern). Zeitlos, der Ausgangspunkt.
    </p>
    <p className="mb-1">
      <strong>Grober Verlauf</strong> = die Form des Bogens über die Kapitel (wie sich das
      entwickelt). Leer lassen = die KI verteilt den Spannungsbogen selbst.
    </p>
    <p className="text-text-muted">
      Beispiel Prämisse: „Zwei Schüler aus verschiedenen Häusern finden über ihren Wissensdurst
      zueinander." — Verlauf: „Kap. 1 Kennenlernen, Kap. 2–7 Annäherung, Kap. 8 Happy End."
    </p>
  </>
);

const SCHRITTE = ["Grundlagen", "Figuren", "Handlung"];

const PHASE_LABEL: Record<string, string> = {
  entwurf: "Die KI entwirft den Kapitelplan...",
  fertig: "Fertig.",
};

/** Overlay fuer den vierten Weg zu einem Gerüst (ToDo.md: "KI designt Gerüst
 * aus ein paar Randbedingungen"): kurzes Formular -> Hintergrund-Task auf dem
 * Server (backend/app/api/geruest_ki.py) -> Fortschrittsanzeige mit Polling
 * (Muster wie AnalysatorPage.tsx). Das Ergebnis landet als geruest.md; der
 * Aufrufer (GeruestPage) laedt es danach neu in den Editor. */
export function KiGeruestOverlay({
  ordner,
  epocheAnzeigename,
  epoche,
  fundusFiguren = [],
  sshZielId,
  startphase,
  onGestartet,
  onFertig,
  onAbbrechen,
}: KiGeruestOverlayProps) {
  const [phase, setPhase] = useState<"eingabe" | "laeuft">(startphase);
  const [status, setStatus] = useState<KiGeruestStatus | null>(null);
  const [wirdGestartet, setWirdGestartet] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  // Formular in drei Schritten (Grundlagen / Figuren / Handlung) - ein einziges
  // langes Formular war für die Figuren-Beschreibungen zu eng.
  const [schritt, setSchritt] = useState(0);
  // Sicherheitsabfrage vor dem Schließen mit ausgefülltem Formular - das
  // Overlay schließt NICHT mehr per Klick auf den Hintergrund (zu leicht aus
  // Versehen ausgelöst, Eingaben gingen verloren), nur noch über ✕/Abbrechen,
  // und die fragen bei vorhandenem Inhalt zuerst nach.
  const [abbruchNachfrage, setAbbruchNachfrage] = useState(false);

  // Formularfelder (Spez. Kapitel 2 + eigene Felder jahr / jugendschutz_stufe).
  const [praemisse, setPraemisse] = useState("");
  const [kapitelanzahl, setKapitelanzahl] = useState(8);
  const [setting, setSetting] = useState(epocheAnzeigename);
  const [genre, setGenre] = useState("");
  const [jahr, setJahr] = useState("");
  const [jugendschutzStufe, setJugendschutzStufe] = useState("voll");
  const [zielwortzahl, setZielwortzahl] = useState(1500);
  const [verlauf, setVerlauf] = useState("");
  const [konflikt, setKonflikt] = useState("");
  const [dramatik, setDramatik] = useState("");
  const [zeitraum, setZeitraum] = useState("");
  const [schluss, setSchluss] = useState("");
  const [tabus, setTabus] = useState("");
  const [figuren, setFiguren] = useState<KiGeruestFigurEingabe[]>([]);
  // Hinweis, wenn die Felder aus einem früheren (fehlgeschlagenen/abgebrochenen)
  // Lauf vorbefüllt wurden.
  const [ausLetztemLauf, setAusLetztemLauf] = useState(false);

  const onFertigRef = useRef(onFertig);
  onFertigRef.current = onFertig;

  // Beim Öffnen des Formulars: zuletzt abgeschickte Randbedingungen dieses
  // Projekts holen und vorbefüllen (backend/app/api/geruest_ki.py speichert
  // sie bei jedem Start). Nur einmal, nur solange der Nutzer noch nichts
  // getippt hat.
  const eingabeGeladen = useRef(false);
  useEffect(() => {
    if (phase !== "eingabe" || eingabeGeladen.current) return;
    eingabeGeladen.current = true;
    api
      .kiGeruestEingabe(ordner)
      .then((e) => {
        if (!e || praemisse.trim()) return;
        setPraemisse(e.praemisse ?? "");
        setKapitelanzahl(e.kapitelanzahl || 8);
        if (e.setting) setSetting(e.setting);
        setGenre(e.genre ?? "");
        setJahr(e.jahr ?? "");
        setJugendschutzStufe(e.jugendschutz_stufe || "voll");
        setZielwortzahl(e.zielwortzahl_pro_kapitel || 1500);
        setVerlauf(e.verlauf ?? "");
        setKonflikt(e.konflikt ?? "");
        setDramatik(e.dramatik ?? "");
        setZeitraum(e.zeitraum ?? "");
        setSchluss(e.schluss ?? "");
        setTabus(e.tabus ?? "");
        setFiguren(e.figuren ?? []);
        setAusLetztemLauf(true);
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, ordner]);

  function formularLeeren() {
    setPraemisse(""); setKapitelanzahl(8); setSetting(epocheAnzeigename); setGenre("");
    setJahr(""); setJugendschutzStufe("voll"); setZielwortzahl(1500); setVerlauf("");
    setKonflikt(""); setDramatik(""); setZeitraum(""); setSchluss(""); setTabus("");
    setFiguren([]); setAusLetztemLauf(false);
  }

  // Fortschritt pollen, solange ein Lauf laeuft. Intervall bewusst 10 s (nicht
  // 3-4 s wie bei Automatik/Schreiben) - haeufiges Pollen WAEHREND eines
  // laufenden Ollama-Aufrufs ueber den SSH-Tunnel verlangsamt die Antwort
  // massiv (GIL-Konkurrenz mit dem Tunnel-Forwarder-Thread, siehe
  // AnalysatorPage.tsx und Memory "Polling verlangsamt SSH-Tunnel-LLM-Aufruf").
  useEffect(() => {
    if (phase !== "laeuft") return;
    let abgebrochen = false;
    const laden = () => {
      api
        .kiGeruestStatus(ordner)
        .then((s) => {
          if (abgebrochen) return;
          setStatus(s);
          if (s.abgeschlossen && !s.fehler) onFertigRef.current();
        })
        .catch(() => {});
    };
    laden();
    const intervall = setInterval(laden, 10000);
    return () => {
      abgebrochen = true;
      clearInterval(intervall);
    };
  }, [phase, ordner]);

  function figurAendern(index: number, feld: keyof KiGeruestFigurEingabe, wert: string) {
    setFiguren((bisher) => bisher.map((f, i) => (i === index ? { ...f, [feld]: wert } : f)));
  }

  // Figuren aus dem Personen-Fundus der passenden Epoche (plus "## Allgemein"),
  // die noch nicht in der Liste stehen - Vorschlag im Dropdown "aus Fundus".
  const fundusOptionen = useMemo(() => {
    const schonDrin = new Set(figuren.map((f) => f.name.trim().toLowerCase()).filter(Boolean));
    return fundusFigurenFuerEpoche(fundusFiguren, epoche).filter(
      (f) => !schonDrin.has(f.name.trim().toLowerCase()),
    );
  }, [fundusFiguren, epoche, figuren]);

  function figurAusFundusUebernehmen(name: string) {
    const treffer = fundusFiguren.find((f) => f.name === name);
    if (!treffer) return;
    const felder = treffer.felder ?? {};
    // Standardfelder des Fundus (backend/app/core/fundus.py:STANDARD_FELDER):
    // Alter, Stand/Rolle, Eigenschaften, Aussehen, Ziel, Angst, Geheimnis.
    // Alter + Stand/Rolle wandern in die eigenen Spalten, der Rest wird zur
    // Kurzbeschreibung zusammengefasst (ohne die "Geschichten"-Liste).
    const rest = Object.entries(felder)
      .filter(([k, v]) => v.trim() && k !== "Geschichten" && k !== "Alter" && k !== "Stand/Rolle")
      .map(([, v]) => v.trim())
      .join("; ");
    setFiguren((bisher) => [
      ...bisher,
      {
        name: treffer.name,
        alter: (felder["Alter"] ?? "").trim(),
        rolle: (felder["Stand/Rolle"] ?? "").trim(),
        kurzbeschreibung: rest,
      },
    ]);
  }

  const formularHatInhalt =
    praemisse.trim() !== "" ||
    verlauf.trim() !== "" ||
    konflikt.trim() !== "" ||
    zeitraum.trim() !== "" ||
    schluss.trim() !== "" ||
    tabus.trim() !== "" ||
    genre.trim() !== "" ||
    jahr.trim() !== "" ||
    figuren.some((f) => f.name.trim() || f.kurzbeschreibung.trim());

  /** Schließen-Wunsch (✕ / Abbrechen / Escape). Im Formular mit Inhalt erst
   * eine Sicherheitsabfrage, sonst direkt zu. Während ein Lauf läuft, ist
   * Schließen unkritisch (der Task läuft serverseitig weiter). */
  function schliessenAnfragen() {
    if (phase === "eingabe" && formularHatInhalt && !wirdGestartet) {
      setAbbruchNachfrage(true);
      return;
    }
    onAbbrechen();
  }

  // Escape schließt (mit derselben Sicherheitsabfrage).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (abbruchNachfrage) setAbbruchNachfrage(false);
        else schliessenAnfragen();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  async function starten() {
    if (!praemisse.trim() || kapitelanzahl < 1) return;
    setWirdGestartet(true);
    setFehler(null);
    const randbedingungen: KiGeruestRandbedingungen = {
      praemisse: praemisse.trim(),
      kapitelanzahl,
      setting: setting.trim(),
      zielwortzahl_pro_kapitel: zielwortzahl || 1500,
      figuren: figuren.filter((f) => f.name.trim()),
      genre: genre.trim(),
      verlauf: verlauf.trim(),
      konflikt: konflikt.trim(),
      dramatik,
      zeitraum: zeitraum.trim(),
      schluss: schluss.trim(),
      tabus: tabus.trim(),
      sprache: "Deutsch",
      jahr: jahr.trim(),
      jugendschutz_stufe: jugendschutzStufe,
    };
    try {
      await api.kiGeruestStarten(ordner, randbedingungen, sshZielId);
      setStatus(null);
      setPhase("laeuft");
      onGestartet?.();
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setWirdGestartet(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 backdrop-blur-sm"
    >
      <div className="relative my-4 w-full max-w-5xl rounded-2xl border border-border bg-surface p-6 shadow-2xl shadow-black/50">
        {abbruchNachfrage && (
          <div className="absolute inset-0 z-30 flex items-center justify-center rounded-2xl bg-surface/95 p-6">
            <div className="max-w-sm text-center">
              <h4 className="font-heading mb-2 text-base font-semibold text-text">Eingaben verwerfen?</h4>
              <p className="mb-4 text-sm text-text-muted">
                Deine Vorgaben im Formular gehen dabei verloren.
              </p>
              <div className="flex justify-center gap-2">
                <Button variant="secondary" onClick={() => setAbbruchNachfrage(false)}>
                  Weiter bearbeiten
                </Button>
                <Button variant="danger" onClick={onAbbrechen}>
                  Verwerfen
                </Button>
              </div>
            </div>
          </div>
        )}

        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h3 className="font-heading text-lg font-semibold text-text">✨ KI entwirft das Gerüst</h3>
            <p className="mt-1 text-sm text-text-muted">
              Gib ein paar Randbedingungen vor - die KI baut daraus einen kompletten Kapitelplan-Erstentwurf.
              Danach kannst du alles im Editor prüfen und ändern.
            </p>
          </div>
          <button
            type="button"
            onClick={schliessenAnfragen}
            className="shrink-0 text-text-muted hover:text-text"
            aria-label="Schließen"
          >
            ✕
          </button>
        </div>

        {phase === "eingabe" ? (
          <div className="space-y-3">
            {ausLetztemLauf && (
              <div className="flex items-center justify-between gap-3 rounded-lg border border-accent-light/30 bg-accent-soft px-3 py-2 text-xs text-accent-light">
                <span>↩️ Vorbefüllt mit deinen Vorgaben aus dem letzten Entwurf für dieses Projekt.</span>
                <button type="button" onClick={formularLeeren} className="shrink-0 hover:underline">
                  Formular leeren
                </button>
              </div>
            )}
            <div className="flex gap-2 border-b border-border pb-3">
              {SCHRITTE.map((name, i) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => setSchritt(i)}
                  className={`flex-1 rounded-lg border px-3 py-2 text-sm transition-colors ${
                    i === schritt
                      ? "border-accent bg-accent-soft text-accent-light"
                      : "border-border text-text-muted hover:border-accent"
                  }`}
                >
                  {i + 1}. {name}
                </button>
              ))}
            </div>

            {schritt === 0 && (
              <div className="space-y-3">
            <div>
              <div className="flex items-center gap-1.5">
                <Label>Prämisse (Pflicht)</Label>
                <FeldHilfe kurz="Die Grundsituation der Geschichte - nicht der Verlauf über die Kapitel (das ist 'Grober Verlauf').">
                  {HILFE_PRAEMISSE_VERLAUF}
                </FeldHilfe>
              </div>
              <Textarea
                rows={5}
                value={praemisse}
                onChange={(e) => setPraemisse(e.target.value)}
                placeholder="Ein bis drei Sätze: Worum geht es? Wer trifft wen, was verbindet sie?"
              />
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div>
                <Label>Kapitelanzahl (Pflicht)</Label>
                <Input
                  type="number"
                  min={1}
                  max={30}
                  value={kapitelanzahl}
                  onChange={(e) => setKapitelanzahl(Number(e.target.value) || 0)}
                />
              </div>
              <div>
                <Label>Jahr (vierstellig)</Label>
                <Input
                  value={jahr}
                  onChange={(e) => setJahr(e.target.value)}
                  placeholder="z.B. 1815"
                />
              </div>
              <div>
                <Label>Content-Stufe</Label>
                <Select value={jugendschutzStufe} onChange={(e) => setJugendschutzStufe(e.target.value)}>
                  <option value="voll">Voll explizit</option>
                  <option value="angedeutet">Angedeutet / romantisch</option>
                  <option value="jugendfrei">Jugendfrei</option>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <Label>Setting / Kanon-Detail</Label>
                <Input
                  value={setting}
                  onChange={(e) => setSetting(e.target.value)}
                  placeholder='z.B. "Hogwarts, Schuljahr 1995/96"'
                />
              </div>
              <div>
                <Label>Genre</Label>
                <Input
                  value={genre}
                  onChange={(e) => setGenre(e.target.value)}
                  placeholder="z.B. Romantik, Krimi, Abenteuer"
                />
              </div>
            </div>

              </div>
            )}

            {schritt === 1 && (
              <div className="space-y-3">
            <div>
              <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                <Label>Hauptfiguren (optional)</Label>
                <div className="flex items-center gap-3">
                  {fundusOptionen.length > 0 && (
                    <select
                      value=""
                      onChange={(e) => {
                        if (e.target.value) figurAusFundusUebernehmen(e.target.value);
                        e.target.value = "";
                      }}
                      className="rounded-lg border border-border bg-bg px-2 py-1 text-xs text-text outline-none focus:border-accent"
                    >
                      <option value="">📋 aus Fundus übernehmen…</option>
                      {fundusOptionen.map((f) => (
                        <option key={f.name} value={f.name}>
                          {f.name}
                        </option>
                      ))}
                    </select>
                  )}
                  <button
                    type="button"
                    onClick={() => setFiguren((b) => [...b, { ...LEERE_FIGUR }])}
                    className="text-xs text-accent-light hover:underline"
                  >
                    + Figur
                  </button>
                </div>
              </div>
              <div className="space-y-2">
                {figuren.map((f, i) => (
                  <div key={i} className="space-y-2 rounded-lg border border-border bg-bg/40 p-3">
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1.4fr_0.6fr_1fr_auto]">
                      <Input value={f.name} onChange={(e) => figurAendern(i, "name", e.target.value)} placeholder="Name" />
                      <Input value={f.alter} onChange={(e) => figurAendern(i, "alter", e.target.value)} placeholder="Alter" />
                      <Input value={f.rolle} onChange={(e) => figurAendern(i, "rolle", e.target.value)} placeholder="Rolle" />
                      <button
                        type="button"
                        onClick={() => setFiguren((b) => b.filter((_, j) => j !== i))}
                        className="text-red-400/70 hover:text-red-400"
                        aria-label="Figur entfernen"
                      >
                        ✕
                      </button>
                    </div>
                    <Textarea
                      rows={5}
                      value={f.kurzbeschreibung}
                      onChange={(e) => figurAendern(i, "kurzbeschreibung", e.target.value)}
                      placeholder="Beschreibung: Eigenschaften, Aussehen, Ziele, Ängste, Geheimnisse ..."
                    />
                  </div>
                ))}
              </div>
            </div>

              </div>
            )}

            {schritt === 2 && (
              <div className="space-y-3">

                <div>
                  <div className="flex items-center gap-1.5">
                    <Label>Grober Verlauf</Label>
                    <FeldHilfe kurz="Der Weg über die Kapitel - nicht die Ausgangssituation (das ist die Prämisse).">
                      {HILFE_PRAEMISSE_VERLAUF}
                    </FeldHilfe>
                  </div>
                  <Textarea
                    rows={4}
                    value={verlauf}
                    onChange={(e) => setVerlauf(e.target.value)}
                    placeholder='z.B. "Kapitel 1 Kennenlernen, Kapitel 2-7 Annäherung, Kapitel 8 Happy End"'
                  />
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <Label>Konflikt / Hindernis</Label>
                    <Input value={konflikt} onChange={(e) => setKonflikt(e.target.value)} placeholder='oder "kein Konflikt"' />
                  </div>
                  <div>
                    <Label>Dramatik</Label>
                    <Select value={dramatik} onChange={(e) => setDramatik(e.target.value)}>
                      <option value="">– keine Angabe –</option>
                      <option value="niedrig">niedrig</option>
                      <option value="mittel">mittel</option>
                      <option value="hoch">hoch</option>
                    </Select>
                  </div>
                  <div>
                    <Label>Zeitraum</Label>
                    <Input value={zeitraum} onChange={(e) => setZeitraum(e.target.value)} placeholder='z.B. "ein Schuljahr", "ein Sommer"' />
                  </div>
                  <div>
                    <Label>Zielwortzahl pro Kapitel</Label>
                    <Input type="number" min={100} value={zielwortzahl} onChange={(e) => setZielwortzahl(Number(e.target.value) || 0)} />
                  </div>
                  <div className="sm:col-span-2">
                    <Label>Gewünschtes Ende</Label>
                    <Input value={schluss} onChange={(e) => setSchluss(e.target.value)} placeholder="in einem Satz" />
                  </div>
                  <div className="sm:col-span-2">
                    <Label>Tabus (was nicht vorkommen darf)</Label>
                    <Input value={tabus} onChange={(e) => setTabus(e.target.value)} />
                  </div>
                </div>
              </div>
            )}

            {fehler && <p className="text-sm text-red-400">{fehler}</p>}

            <div className="flex justify-between gap-2 border-t border-border pt-3">
              <Button variant="secondary" onClick={schliessenAnfragen} disabled={wirdGestartet}>
                Abbrechen
              </Button>
              <div className="flex gap-2">
                {schritt > 0 && (
                  <Button variant="secondary" onClick={() => setSchritt(schritt - 1)} disabled={wirdGestartet}>
                    ← Zurück
                  </Button>
                )}
                {schritt < SCHRITTE.length - 1 ? (
                  <Button onClick={() => setSchritt(schritt + 1)}>Weiter →</Button>
                ) : (
                  <Button onClick={starten} disabled={wirdGestartet || !praemisse.trim() || kapitelanzahl < 1}>
                    {wirdGestartet ? "Startet..." : "✨ Gerüst entwerfen lassen"}
                  </Button>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm">
              <strong>{PHASE_LABEL[status?.phase ?? ""] ?? "Wird gestartet..."}</strong>
            </p>
            <p className="text-xs text-text-muted">
              Der Entwurf läuft auf dem Server weiter, auch wenn du dieses Fenster schließt oder den Tab wechselst.
              Je nach KI-Ziel dauert es einige Minuten.
            </p>
            <div className="max-h-[240px] overflow-y-auto rounded-lg border border-border bg-bg/40 p-3 font-mono text-xs">
              {status?.log.length ? (
                status.log.map((zeile, i) => <div key={i}>{zeile}</div>)
              ) : (
                <span className="text-text-muted">Wird gestartet...</span>
              )}
            </div>
            {status?.fehler && <p className="text-sm text-red-400">Fehler: {status.fehler}</p>}
            <div className="flex justify-end gap-2 border-t border-border pt-3">
              {status?.fehler ? (
                <>
                  <Button variant="secondary" onClick={onAbbrechen}>
                    Schließen
                  </Button>
                  <Button onClick={() => { setStatus(null); setFehler(null); setPhase("eingabe"); }}>
                    Nochmal versuchen
                  </Button>
                </>
              ) : (
                <Button variant="secondary" onClick={onAbbrechen}>
                  Im Hintergrund weiterlaufen lassen
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
