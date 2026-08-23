import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, MouseEvent } from "react";
import { api } from "../api/client";
import type { AutomatikZustand, EpocheKurz, ProjektKurz } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Badge, Button, Card, CardTitle, Input, Label, Select } from "../components/ui";
import { epochenAnhaltspunkteAusArchitektTxt, leeresGeruestSkelett } from "../utils/geruestVorlage";

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
  onEpochenGeaendert: () => void;
  onProjektAuswaehlen: (ordner: string) => void;
  onProjektGeloescht: (ordner: string) => void;
  onNeuSchreibenGestartet: (ordner: string) => void;
}

export function ProjektePage({
  projekte,
  epochen,
  aktuellesProjekt,
  onProjekteGeaendert,
  onEpochenGeaendert,
  onProjektAuswaehlen,
  onProjektGeloescht,
  onNeuSchreibenGestartet,
}: ProjektePageProps) {
  const [titel, setTitel] = useState("");
  // Alternative zum Architekten-Interview (siehe ToDo.md): statt der
  // conversational KI-Befragung kann der Gerüst-Editor (GeruestPage) direkt
  // mit einem Platzhalter-Skelett geoeffnet werden. App.tsx entscheidet rein
  // danach, ob `projektDetail.geruest` bereits gesetzt ist - ein frisch
  // angelegtes Projekt hat das nur, wenn wir hier "manuell" waehlen und
  // sofort nach dem Anlegen leeresGeruestSkelett() speichern.
  const [startModus, setStartModus] = useState<"interview" | "manuell">("interview");
  const [epoche, setEpoche] = useState("");
  const [zweiteEpoche, setZweiteEpoche] = useState("");
  const [epocheEinleitungssatz, setEpocheEinleitungssatz] = useState<string | null>(null);
  const [epocheInfoLaedt, setEpocheInfoLaedt] = useState(false);
  // Ort/Zeitraum-Anhaltspunkte fuer leeresGeruestSkelett() (Weg "Gerüst
  // selbst schreiben"), extrahiert aus dem architekt.txt der gewaehlten
  // Epoche - siehe geruestVorlage.ts:epochenAnhaltspunkteAusArchitektTxt.
  const [epocheAnhaltspunkte, setEpocheAnhaltspunkte] = useState<{ ort: string | null; zeitraum: string | null }>({
    ort: null,
    zeitraum: null,
  });
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
  // Filter "Unfertig" (siehe istUnfertig() unten) - zeigt nur Projekte mit
  // noch offener Pruefung oder weniger geschriebenen als geplanten Kapiteln.
  const [nurUnfertige, setNurUnfertige] = useState(false);
  // Ordner-Darstellung ist die Standardsicht (siehe ToDo.md) - flache Liste
  // bleibt als Alternative per Toggle erreichbar.
  const [ordnerAnsicht, setOrdnerAnsicht] = useState(true);
  // Epoche-Schluessel (wie in gruppierteProjekte, "" = unbekannte Epoche)
  // der eingeklappten Ordner - Standard ist "alle eingeklappt bis auf den
  // Ordner mit dem zuletzt bearbeiteten Projekt" (siehe Effekt unten), nicht
  // hier als Initialwert, weil `projekte` beim ersten Rendern noch leer
  // sein kann (Ladezustand von App.tsx).
  const [eingeklappteOrdner, setEingeklappteOrdner] = useState<Set<string>>(new Set());
  // Epoche einer Geschichte verschieben (siehe projektZeile() unten) -
  // `verschiebenOffenFuer` ist der Ordnerpfad des Projekts, dessen Epoche-
  // Auswahl gerade eingeblendet ist. Urspruenglich als Drag&Drop geplant,
  // das aber in der Praxis bei mind. einem Nutzer/Browser zuverlaessig gar
  // nicht ausgeloest hat (vermutlich Interaktion zwischen den Zeilen-Klick-
  // Handlern und dem nativen HTML5-Drag-Events) - eine explizite Auswahl
  // per Klick ist robuster und braucht keine Maus-Drag-Geste.
  const [verschiebenOffenFuer, setVerschiebenOffenFuer] = useState<string | null>(null);
  const [verschiebenFehler, setVerschiebenFehler] = useState<string | null>(null);
  // Inline-Umbenennen einer Epoche direkt im Ordner-Header - `schluessel`
  // ist der Ordner-/Identifier-Name (siehe EpocheKurz.name), NICHT der
  // Anzeigename, der gerade bearbeitet wird.
  const [umbenennenSchluessel, setUmbenennenSchluessel] = useState<string | null>(null);
  const [umbenennenText, setUmbenennenText] = useState("");
  const [umbenennenLaedt, setUmbenennenLaedt] = useState(false);
  const [umbenennenFehler, setUmbenennenFehler] = useState<string | null>(null);

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

  // Ordner-/Identifier-Name -> Anzeigename (siehe EpocheKurz.anzeigename) -
  // fuer Projekte, deren ".epoche"-Marker keiner (mehr) bekannten Epoche
  // entspricht (z.B. geloescht, oder ein per Analysator-Import roh
  // uebernommener Ordnername), ersatzweise Bindestriche in Leerzeichen
  // zurueckwandeln statt gar nichts anzuzeigen.
  const epocheAnzeigenameMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const e of epochen) map.set(e.name, e.anzeigename);
    return map;
  }, [epochen]);

  function epocheAnzeige(name: string): string {
    return epocheAnzeigenameMap.get(name) ?? name.replace(/-/g, " ");
  }

  // Filter "Unfertig": weniger Kapitel geschrieben als geplant, ODER die
  // Pruefung ist noch nicht sauber abgeschlossen (siehe automatik_zustand -
  // app/core/automatik.py:zustand_zusammenfassen). "null" (Automatikmodus
  // fuer dieses Projekt noch nie gestartet) zaehlt NICHT automatisch als
  // unfertig - sonst waere jedes rein manuell geschriebene/geprüfte Projekt
  // faelschlich dauerhaft "unfertig", nur weil es die Automatik-Pipeline nie
  // genutzt hat.
  function istUnfertig(p: ProjektKurz): boolean {
    const zuWenigeKapitel = p.letztes_geplantes_kapitel != null && p.anzahl_kapitel < p.letztes_geplantes_kapitel;
    const pruefungOffen =
      p.automatik_zustand === "laeuft" ||
      p.automatik_zustand === "fehler" ||
      p.automatik_zustand === "gestoppt" ||
      p.automatik_zustand === "abgeschlossen_mit_resten";
    return zuWenigeKapitel || pruefungOffen;
  }

  const gefilterteProjekte = useMemo(() => {
    const suchtextNormalisiert = suchtext.trim().toLowerCase();
    const gefiltert = projekte.filter((p) => {
      if (epocheFilter && p.epoche !== epocheFilter) return false;
      if (nurUnfertige && !istUnfertig(p)) return false;
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
  }, [projekte, suchtext, epocheFilter, nurUnfertige, sortierungAbsteigend]);

  // Fuer die Ordner-Darstellung: `gefilterteProjekte` (bereits sortiert)
  // nach Epoche gruppieren - Reihenfolge der Ordner selbst bleibt bewusst
  // immer A -> Z, unabhaengig von `sortierungAbsteigend` (die betrifft nur
  // die Projekte innerhalb eines Ordners), sonst wirkt der Toggle bei
  // aktiver Ordner-Ansicht widerspruechlich.
  const gruppierteProjekte = useMemo(() => {
    const gruppen = new Map<string, ProjektKurz[]>();
    for (const p of gefilterteProjekte) {
      const schluessel = p.epoche ?? "";
      const liste = gruppen.get(schluessel);
      if (liste) liste.push(p);
      else gruppen.set(schluessel, [p]);
    }
    // "Unbekannt" ist die feste Sammelablage fuer Geschichten mit noch
    // ungeklaerter Epoche (siehe app/data/epochen/Unbekannt) - bleibt
    // IMMER sichtbar, auch leer, damit man jederzeit etwas dorthin
    // verschieben kann.
    if (epochen.some((e) => e.name === "Unbekannt") && !gruppen.has("Unbekannt")) {
      gruppen.set("Unbekannt", []);
    }
    return Array.from(gruppen.entries())
      .map(([epoche, liste]) => ({ epoche: epoche || null, liste }))
      .sort((a, b) => {
        // "Unbekannt" ist keine echte Epoche, sondern eine Sammelablage -
        // steht deshalb immer ganz unten, unabhaengig von der Alphabet-
        // Reihenfolge der echten Epochen.
        const aUnbekannt = a.epoche === "Unbekannt";
        const bUnbekannt = b.epoche === "Unbekannt";
        if (aUnbekannt !== bUnbekannt) return aUnbekannt ? 1 : -1;
        return (a.epoche ?? "unbekannte Epoche").localeCompare(b.epoche ?? "unbekannte Epoche", "de");
      });
  }, [gefilterteProjekte, epochen]);

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

  // Ordner-Darstellung: beim ersten Laden der (von App.tsx gelieferten)
  // Projektliste alle Ordner einklappen AUSSER dem, der das zuletzt
  // bearbeitete Projekt enthaelt (hoechstes zuletzt_bearbeitet_am) - danach
  // nicht mehr automatisch eingreifen, sonst wuerde jeder manuelle Auf-/
  // Zuklapp-Klick durch einen spaeteren Datenrefresh (z.B. nach dem
  // Speichern eines Geruests) wieder zurueckgesetzt.
  const ordnerVorbelegungGesetzt = useRef(false);
  useEffect(() => {
    if (ordnerVorbelegungGesetzt.current || projekte.length === 0) return;
    ordnerVorbelegungGesetzt.current = true;
    let zuletztBearbeitetSchluessel = "";
    let neuesteZeit = "";
    for (const p of projekte) {
      if (p.zuletzt_bearbeitet_am && p.zuletzt_bearbeitet_am > neuesteZeit) {
        neuesteZeit = p.zuletzt_bearbeitet_am;
        zuletztBearbeitetSchluessel = p.epoche ?? "";
      }
    }
    const alleSchluessel = new Set(projekte.map((p) => p.epoche ?? ""));
    alleSchluessel.delete(zuletztBearbeitetSchluessel);
    setEingeklappteOrdner(alleSchluessel);
  }, [projekte]);

  function ordnerUmschalten(schluessel: string) {
    setEingeklappteOrdner((bisher) => {
      const kopie = new Set(bisher);
      if (kopie.has(schluessel)) kopie.delete(schluessel);
      else kopie.add(schluessel);
      return kopie;
    });
  }

  // Projekt `ordner` in die Epoche `neueEpoche` verschieben (siehe PUT
  // .../epoche in app/api/projects.py) - verschiebt bei aktiver
  // "Unterordner je Epoche"-Einstellung serverseitig auch den physischen
  // Projektordner, der zurueckgegebene `ordner` kann sich dadurch aendern.
  async function projektEpocheVerschieben(ordner: string, neueEpoche: string) {
    setVerschiebenFehler(null);
    try {
      const aktualisiert = await api.projektEpocheAendern(ordner, neueEpoche);
      onProjekteGeaendert();
      if (aktuellesProjekt === ordner && aktualisiert.ordner !== ordner) {
        onProjektAuswaehlen(aktualisiert.ordner);
      }
    } catch (e) {
      setVerschiebenFehler(e instanceof Error ? e.message : String(e));
    }
  }

  function umbenennenStarten(ereignis: MouseEvent, epocheOrdner: string) {
    // Verhindert, dass der Klick zusaetzlich den Auf-/Zuklapp-Handler des
    // Ordner-Headers ausloest.
    ereignis.stopPropagation();
    setUmbenennenSchluessel(epocheOrdner);
    setUmbenennenText(epocheAnzeige(epocheOrdner));
    setUmbenennenFehler(null);
  }

  async function umbenennenBestaetigen(ereignis: FormEvent, alterOrdner: string) {
    ereignis.preventDefault();
    ereignis.stopPropagation();
    const neuerName = umbenennenText.trim();
    if (!neuerName) {
      setUmbenennenSchluessel(null);
      return;
    }
    setUmbenennenLaedt(true);
    setUmbenennenFehler(null);
    try {
      await api.epocheUmbenennen(alterOrdner, neuerName);
      setUmbenennenSchluessel(null);
      // Ordnername der Epoche kann sich mitgeaendert haben (siehe
      // app/api/epochen.py:epoche_umbenennen) - dann tragen bestehende
      // Projekte serverseitig bereits den neuen Namen im ".epoche"-Marker,
      // die Projektliste muss das nur noch nachladen.
      onEpochenGeaendert();
      onProjekteGeaendert();
    } catch (e) {
      setUmbenennenFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setUmbenennenLaedt(false);
    }
  }

  // Einleitungssatz-Vorlage der gewaehlten Epoche fuer die Info-Box unten im
  // "Neues Projekt anlegen"-Container (siehe app/api/epochen.py - eine der
  // vier/fuenf Rohentwurf-Dateien der Epochen-Bibliothek).
  useEffect(() => {
    if (!epoche) {
      setEpocheEinleitungssatz(null);
      setEpocheAnhaltspunkte({ ort: null, zeitraum: null });
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
    api
      .epocheDateiLesen(epoche, "architekt.txt")
      .then((text) => {
        if (!abgebrochen) setEpocheAnhaltspunkte(epochenAnhaltspunkteAusArchitektTxt(text));
      })
      .catch(() => {
        if (!abgebrochen) setEpocheAnhaltspunkte({ ort: null, zeitraum: null });
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

  // Backend liefert "YYYY-MM-DD HH:MM" (siehe app/api/projects.py -
  // _erstellt_am/_zuletzt_bearbeitet_am) - hier nur fuers deutsche
  // Anzeigeformat auseinandernehmen statt ueber Date() zu parsen (der
  // Bindestrich-Zeitstempel ist ohne Zeitzone nicht ueberall verlaesslich
  // interpretierbar).
  function formatDatum(zeitstempel: string | null | undefined, mitUhrzeit: boolean): string {
    if (!zeitstempel) return "–";
    const [datum, uhrzeit] = zeitstempel.split(" ");
    const [jahr, monat, tag] = datum.split("-");
    return mitUhrzeit ? `${tag}.${monat}.${jahr} ${uhrzeit}` : `${tag}.${monat}.${jahr}`;
  }

  // Eine einzelne Projektzeile - identisch fuer Ordner- und flache Sicht,
  // damit Klick-/Loeschen-/Neu-schreiben-Verhalten nicht doppelt gepflegt
  // werden muss.
  function projektZeile(p: ProjektKurz) {
    const verschiebenOffen = verschiebenOffenFuer === p.ordner;
    return (
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
        {verschiebenOffen ? (
          <select
            autoFocus
            defaultValue=""
            onClick={(e) => e.stopPropagation()}
            onBlur={() => setVerschiebenOffenFuer(null)}
            onChange={(e) => {
              const neueEpoche = e.target.value;
              setVerschiebenOffenFuer(null);
              if (neueEpoche) projektEpocheVerschieben(p.ordner, neueEpoche);
            }}
            className="shrink-0 rounded-lg border border-accent bg-bg px-2 py-1 text-xs text-text outline-none"
          >
            <option value="" disabled>
              Wohin verschieben?
            </option>
            {epochen
              .filter((e) => e.name !== p.epoche)
              .map((e) => (
                <option key={e.name} value={e.name}>
                  {e.anzeigename}
                </option>
              ))}
          </select>
        ) : (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setVerschiebenFehler(null);
              setVerschiebenOffenFuer(p.ordner);
            }}
            title={`"${p.titel ?? p.ordner}" in eine andere Epoche verschieben`}
            aria-label={`"${p.titel ?? p.ordner}" in eine andere Epoche verschieben`}
            className="shrink-0 text-sm leading-none text-text-muted/60 transition-colors hover:text-text"
          >
            📁
          </button>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {p.epoche && epocheFarbe.get(p.epoche) && (
              <span
                aria-hidden="true"
                title={epocheAnzeige(p.epoche)}
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
            {p.epoche ? epocheAnzeige(p.epoche) : "unbekannte Epoche"}
            {p.zweite_epoche ? ` ↔ ${epocheAnzeige(p.zweite_epoche)} (Zeitsprung)` : ""} · {p.anzahl_kapitel} Kapitel
            {p.letztes_geplantes_kapitel ? ` von ${p.letztes_geplantes_kapitel} geplant` : ""}
          </div>
        </div>
        <div className="shrink-0 text-right text-[11px] leading-tight text-text-muted">
          <div title="Anlage-Datum des Projektordners">Erstellt: {formatDatum(p.erstellt_am, false)}</div>
          <div title="Letzte Aenderung am Gerüst">Bearbeitet: {formatDatum(p.zuletzt_bearbeitet_am, true)}</div>
        </div>
      </li>
    );
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
      // "Gerüst selbst schreiben": das frisch angelegte Projekt hat noch
      // kein geruest.md - App.tsx wuerde ohne dieses Skelett automatisch das
      // Architekten-Interview erzwingen (siehe dortiger Kommentar bei
      // `interviewErzwungen || !projektDetail?.geruest`). Ein Fehler hier
      // (z.B. Netzwerkaussetzer) darf das bereits angelegte Projekt nicht
      // verstecken - Projekt bleibt in jedem Fall nutzbar, notfalls landet
      // man dann eben doch im Interview und kann spaeter manuell wechseln.
      if (startModus === "manuell") {
        try {
          const skelett = leeresGeruestSkelett(titel.trim(), {
            ...epocheAnhaltspunkte,
            genre: epochen.find((e) => e.name === epoche)?.genre,
          });
          await api.geruestSchreiben(neues.ordner, skelett);
        } catch {
          // Bewusst verschluckt, siehe Kommentar oben.
        }
      }
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
                  {epocheAnzeige(name)}
                </option>
              ))}
            </Select>
            <button
              onClick={() => setNurUnfertige((bisher) => !bisher)}
              title={
                nurUnfertige
                  ? "Filter aufheben (alle Projekte zeigen)"
                  : "Nur Projekte mit offener Prüfung oder fehlenden Kapiteln zeigen"
              }
              className={`rounded-lg border px-3 py-1.5 text-sm transition-colors ${
                nurUnfertige
                  ? "border-accent bg-accent/10 text-text"
                  : "border-border text-text-muted hover:bg-surface-hover hover:text-text"
              }`}
            >
              ⚠️ Unfertig
            </button>
            <button
              onClick={() => setSortierungAbsteigend((bisher) => !bisher)}
              title={sortierungAbsteigend ? "Sortierung: Z → A (klicken für A → Z)" : "Sortierung: A → Z (klicken für Z → A)"}
              className="rounded-lg border border-border px-3 py-1.5 text-sm text-text-muted transition-colors hover:bg-surface-hover hover:text-text"
            >
              {sortierungAbsteigend ? "Z → A" : "A → Z"}
            </button>
            <button
              onClick={() => setOrdnerAnsicht((bisher) => !bisher)}
              title={ordnerAnsicht ? "Zur flachen Liste wechseln" : "Zur Ordner-Darstellung (nach Epoche) wechseln"}
              className={`rounded-lg border px-3 py-1.5 text-sm transition-colors ${
                ordnerAnsicht
                  ? "border-accent bg-accent/10 text-text"
                  : "border-border text-text-muted hover:bg-surface-hover hover:text-text"
              }`}
            >
              {ordnerAnsicht ? "🗂️ Ordner" : "📋 Liste"}
            </button>
          </div>
        )}
        {(verschiebenFehler || umbenennenFehler) && (
          <p className="mb-3 text-sm text-red-400">{verschiebenFehler || umbenennenFehler}</p>
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
                setNurUnfertige(false);
              }}
              className="text-accent-light hover:underline"
            >
              Filter zurücksetzen
            </button>
          </p>
        ) : ordnerAnsicht ? (
          <div className="space-y-4">
            {gruppierteProjekte.map(({ epoche, liste }) => {
              const farbe = epoche ? epocheFarbe.get(epoche) : undefined;
              const schluessel = epoche ?? "";
              const eingeklappt = eingeklappteOrdner.has(schluessel);
              const wirdUmbenannt = epoche != null && umbenennenSchluessel === epoche;
              // Nur Ordner mit eigenem Projekt zeigen, plus die feste
              // Sammelablage "Unbekannt" (siehe gruppierteProjekte oben).
              const sichtbar = liste.length > 0 || schluessel === "Unbekannt";
              if (!sichtbar) return null;
              return (
                <div key={schluessel || "__unbekannt"} className="rounded-lg border border-border">
                  <div
                    className={`flex items-center gap-2 border-border px-3 py-2 transition-colors ${
                      eingeklappt ? "rounded-lg" : "rounded-t-lg border-b"
                    }`}
                    style={{ backgroundColor: farbe ? `${farbe}22` : undefined }}
                  >
                    <button
                      type="button"
                      onClick={() => ordnerUmschalten(schluessel)}
                      className="flex flex-1 items-center gap-2 text-left outline-none"
                    >
                      <span className="text-xs text-text-muted">{eingeklappt ? "▶" : "▼"}</span>
                      {!wirdUmbenannt && (
                        <>
                          <span className="text-sm font-semibold text-text">
                            {/* "Unbekannt" ist keine echte Epoche, sondern eine
                                Sammelablage (siehe app/data/epochen/Unbekannt) -
                                eigenes Symbol, damit sie sich optisch von den
                                echten Epoche-Ordnern abhebt. */}
                            {epoche === "Unbekannt" ? "📥" : "📁"}{" "}
                            {epoche ? epocheAnzeige(epoche) : "unbekannte Epoche"}
                          </span>
                          <span className="text-xs text-text-muted">
                            ({liste.length} {liste.length === 1 ? "Projekt" : "Projekte"})
                          </span>
                        </>
                      )}
                    </button>
                    {wirdUmbenannt && epoche && (
                      <form
                        onSubmit={(e) => umbenennenBestaetigen(e, epoche)}
                        onClick={(e) => e.stopPropagation()}
                        className="flex flex-1 items-center gap-1"
                      >
                        <input
                          autoFocus
                          value={umbenennenText}
                          onChange={(e) => setUmbenennenText(e.target.value)}
                          disabled={umbenennenLaedt}
                          className="min-w-0 flex-1 rounded border border-border bg-bg px-2 py-0.5 text-sm text-text outline-none focus:border-accent"
                        />
                        <button
                          type="submit"
                          disabled={umbenennenLaedt}
                          title="Übernehmen"
                          className="shrink-0 text-sm text-accent-light hover:underline disabled:opacity-40"
                        >
                          ✓
                        </button>
                        <button
                          type="button"
                          onClick={() => setUmbenennenSchluessel(null)}
                          disabled={umbenennenLaedt}
                          title="Abbrechen"
                          className="shrink-0 text-sm text-text-muted hover:text-text disabled:opacity-40"
                        >
                          ✕
                        </button>
                      </form>
                    )}
                    {epoche && !wirdUmbenannt && (
                      <button
                        type="button"
                        onClick={(e) => umbenennenStarten(e, epoche)}
                        title="Epoche umbenennen"
                        aria-label="Epoche umbenennen"
                        className="shrink-0 text-xs text-text-muted/70 transition-colors hover:text-text"
                      >
                        ✏️
                      </button>
                    )}
                  </div>
                  {!eingeklappt && <ul className="divide-y divide-border">{liste.map((p) => projektZeile(p))}</ul>}
                </div>
              );
            })}
          </div>
        ) : (
          <ul className="divide-y divide-border">{gefilterteProjekte.map((p) => projektZeile(p))}</ul>
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
                  {e.anzeigename}
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
                    {e.anzeigename}
                  </option>
                ))}
            </Select>
            <p className="mt-1 text-xs text-text-muted">
              Für Geschichten mit Zeitsprung (Zeitreise-Gerät, Ritual, o.ä.) zwischen zwei Epochen. Architekt,
              Autor und Prüfer bekommen dann beide Settings und fragen im Interview zusätzlich nach dem
              Zeitsprung-Mechanismus.
            </p>
          </div>
          <div>
            <Label>Wie soll das Gerüst entstehen?</Label>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => setStartModus("interview")}
                className={`rounded-lg border p-3 text-left text-sm transition-colors ${
                  startModus === "interview"
                    ? "border-accent bg-accent/10 text-text"
                    : "border-border text-text-muted hover:bg-surface-hover"
                }`}
              >
                <span className="font-medium">🗣️ Architekten-Interview</span>
                <p className="mt-0.5 text-xs text-text-muted">
                  Die KI befragt dich Schritt für Schritt und baut das Gerüst aus den Antworten.
                </p>
              </button>
              <button
                type="button"
                onClick={() => setStartModus("manuell")}
                className={`rounded-lg border p-3 text-left text-sm transition-colors ${
                  startModus === "manuell"
                    ? "border-accent bg-accent/10 text-text"
                    : "border-border text-text-muted hover:bg-surface-hover"
                }`}
              >
                <span className="font-medium">📝 Gerüst selbst schreiben</span>
                <p className="mt-0.5 text-xs text-text-muted">
                  Öffnet direkt den Gerüst-Editor mit einem Platzhalter-Skelett zum Ausfüllen - kein Gespräch.
                </p>
              </button>
            </div>
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
