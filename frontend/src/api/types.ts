// Spiegelt backend/app/schemas.py - bei Aenderungen dort bitte hier nachziehen.

export interface EpocheKurz {
  // Ordner-/Identifier-Name - stabil, siehe backend/app/schemas.py:
  // EpocheKurz. Fuer Anzeigezwecke immer `anzeigename` verwenden.
  name: string;
  anzeigename: string;
  genre?: string | null;
  farbe?: string | null;
}

// PUT /api/epochen/{ordner}/name
export interface EpocheUmbenennenAntwort {
  ordner: string;
  anzeigename: string;
  aktualisierte_projekte: number;
}

// Siehe app/core/automatik.py:zustand_zusammenfassen() für die Bedeutung
// der einzelnen Werte - null heißt: Automatikmodus wurde für dieses
// Projekt noch nie gestartet.
export type AutomatikZustand = "laeuft" | "fehler" | "gestoppt" | "abgeschlossen_mit_resten" | "abgeschlossen_sauber" | null;

export interface ProjektKurz {
  ordner: string;
  titel: string | null;
  epoche: string | null;
  // Nur gesetzt bei einem Zeitsprung-Projekt (zweite, per Zeitsprung
  // erreichte Epoche) - siehe ProjektAnlegenAnfrage.zweite_epoche.
  zweite_epoche?: string | null;
  anzahl_kapitel: number;
  letztes_geplantes_kapitel: number | null;
  automatik_zustand: AutomatikZustand;
  // Nur gesetzt, wenn dieses Projekt per "Neu schreiben" aus einem anderen
  // dupliziert wurde - Ordnerpfad des Quellprojekts (Titel/Gerüst werden
  // 1:1 mitkopiert, ohne dieses Feld waeren beide Projekte in der Liste
  // nicht unterscheidbar).
  neu_geschrieben_aus?: string | null;
  // "YYYY-MM-DD HH:MM", siehe backend/app/api/projects.py:_erstellt_am /
  // _zuletzt_bearbeitet_am.
  erstellt_am?: string | null;
  zuletzt_bearbeitet_am?: string | null;
}

export interface ProjektDetail {
  ordner: string;
  epoche: string | null;
  zweite_epoche?: string | null;
  geruest: string | null;
  verbotsliste: string | null;
  stilproben: string | null;
  kapitel: number[];
  jahr: string | null;
  jugendschutz_stufe: string | null;
  autor_modell: string | null;
  automatische_fortsetzung: boolean | null;
  letztes_geplantes_kapitel: number | null;
  kapitelplan: Record<number, number>;
}

export type AuthMethod = "password" | "private_key" | "agent" | "direct";

export interface SSHZiel {
  id: string;
  name: string;
  host: string;
  port: number;
  username: string;
  auth_method: AuthMethod;
  remote_ollama_port: number;
  // Port eines sd-server-Containers auf demselben Host (Bildgenerierung,
  // siehe api.coverPromptVorschlagen/coverGenerieren) - null = dieses
  // KI-Ziel bietet keine Bildgenerierung an.
  bildki_port: number | null;
  favorit: boolean;
  created_at: string;
  updated_at: string;
}

export interface SSHZielEingabe {
  name: string;
  host: string;
  port: number;
  username: string;
  auth_method: AuthMethod;
  password?: string;
  private_key_pem?: string;
  private_key_passphrase?: string;
  remote_ollama_port: number;
  bildki_port?: number | null;
}

export interface SSHTestErgebnis {
  erfolgreich: boolean;
  meldung: string;
}

export interface OllamaModellInfo {
  name: string;
  parameter_size: string | null;
  size_bytes: number | null;
}

// /api/persona-modelle - globale Admin-Zuordnung Persona -> Ollama-Modell
// (Tab "KI-Ziele" -> Persona-Modell-Zuordnung).
export interface PersonaModell {
  persona: string;
  default_modell: string;
  override_modell: string | null;
  effektives_modell: string;
}

export interface Finding {
  code: string;
  meldung: string;
  schwere: "warnung" | "info";
}

export type BefundKategorie = "anachronismus" | "stimmigkeit" | "kontinuitaet" | "lektorat";

export interface BefundBeschreibung {
  quelle: string;
  text: string;
}

export interface Befund {
  id: string;
  kategorien: BefundKategorie[];
  fundstelle: string;
  beschreibungen: BefundBeschreibung[];
  sicherheit: "hoch" | "mittel" | "gering" | null;
  vorschlag: string | null;
  konflikt: boolean;
  konflikt_vorschlaege: BefundBeschreibung[] | null;
  gefunden: boolean;
  start: number | null;
  end: number | null;
}

export interface BefundeAntwort {
  kapitel: number;
  erzeugt_am: string;
  jahr: string | null;
  befunde: Befund[];
  quelltext_sha256: string | null;
  /** true, wenn der Kapiteltext seit dieser Pruefung ueberschrieben wurde -
   * die start/end-Offsets in `befunde` koennen dann auf falsche Stellen
   * zeigen (siehe befunde_lesen() im Backend). */
  veraltet: boolean;
}

export interface RechtschreibWort {
  wort: string;
  satz: string | null;
  // Zeichen-Offsets der ersten Fundstelle im vollen Kapiteltext, fuer den
  // Sprung-zur-Stelle-Klick - siehe app/core/heuristik.py:wort_position_finden.
  start: number | null;
  end: number | null;
}

export interface RechtschreibAntwort {
  unbekannte_woerter: RechtschreibWort[];
  hunspell_verfuegbar: boolean;
}

// /api/projects/{ordner}/automatik/* - schreibt alle fehlenden Kapitel am
// Stück und wendet danach automatisch alle eindeutigen Prüfer-Korrekturen
// an (siehe app/core/automatik.py). Läuft als Hintergrund-Job unabhängig
// von einer offenen Browser-Verbindung - dieser Status wird per Polling
// abgefragt, nicht per WebSocket.
export interface AutomatikProtokollEintrag {
  art: "angewendet" | "uebersprungen" | "rechtschreibung";
  grund?: string | null;
  fundstelle?: string | null;
  vorschlag?: string | null;
  kapitel?: number;
  durchlauf?: number;
  unbekannte_woerter?: string[];
}

// Deckungsgleich mit EpocheFormularWerte (components/EpocheFormular.tsx) -
// bewusst als eigener API-Antworttyp gefuehrt (kein Re-Export), damit
// api/types.ts nicht von components/ abhaengt; AnalysatorPage.tsx weist das
// Ergebnis direkt in ein EpocheFormularWerte-State, da beide Formen
// strukturell identisch sind.
export interface EpocheVorschlagAntwort {
  name: string;
  erfunden: boolean;
  beschreibung: string;
  zeitraum: string;
  orte: string;
  gesellschaft: string;
  statusregel: string;
  genre: string;
  rang_wort: string;
  anreden: string;
  nebenstrang_typen: string;
  vorbild_franchise: string;
  verbote_start: string;
}

export interface EpocheErstellenAntwort {
  name: string;
  ordner: string;
  dateien: Record<string, string>;
}

export interface AnalysatorStatus {
  laeuft: boolean;
  phase: string | null;
  aktuelles_kapitel: number | null;
  gesamt_kapitel: number | null;
  log: string[];
  abgeschlossen: boolean;
  fehler: string | null;
}

// /api/analysator/analysen - dauerhaft gespeicherte Rohtexte importierter
// Geschichten (siehe backend/app/core/analysator.py:analyse_speichern).
export interface AnalyseEintrag {
  dateiname: string;
  titel: string;
  erstellt_am: string;
  woerter: number;
}

export interface AutomatikStatus {
  laeuft: boolean;
  gestartet_am: string | null;
  phase: string | null;
  aktuelles_kapitel: number | null;
  gesamt_kapitel: number | null;
  aktueller_durchlauf: number | null;
  log: string[];
  protokoll: AutomatikProtokollEintrag[];
  stop_angefordert: boolean;
  abgeschlossen: boolean;
  fehler: string | null;
  fortsetzbar: boolean;
  resten_bestaetigt: boolean;
  // Nur gesetzt, wenn der letzte Lauf nach ausgeschoepften 502/503-Retries
  // pausiert wurde (siehe app/api/pipeline.py:_automatik_mit_retry) - fuer
  // die kompakte Fortsetzen-Zeile.
  /** Live-Text des Autors waehrend des Automatikmodus (siehe
   * app/api/pipeline.py:_automatik_on_event) - fuellt dasselbe "Autor"-
   * Fenster wie beim interaktiven Schreiben, nur ohne WebSocket. */
  aktueller_text: string | null;
  fehler_schritt: {
    kapitel: number;
    phase: string;
    durchlauf: number | null;
    fehler_nummer?: string;
  } | null;
}

// Ein Eintrag pro bisherigem Automatik-Lauf dieses Projekts (dauerhaftes
// Protokoll, unabhaengig vom aktuellen Status) - siehe
// app/core/automatik.py:verlauf_eintrag_anhaengen.
export interface AutomatikVerlaufEintrag {
  datum: string;
  von: string;
  bis: string;
  dauer_sekunden: number;
  status: "abgeschlossen" | "fehler" | "gestoppt";
  fehler: string | null;
  fortgesetzt: boolean;
}

// Vorschau vor dem inkrementellen Erweitern ("Weitere Kapitel schreiben") -
// siehe app/api/pipeline.py:automatik_fortsetzen_vorschau. Reine
// Datei-/Kapitelplan-Auswertung, kein KI-Aufruf.
export interface AutomatikAnknuepfpunkt {
  kapitel: number;
  stand_vorhanden: boolean;
  stand_text: string | null;
  stand_veraltet: boolean;
}

export interface AutomatikFortsetzenVorschau {
  geplant_bis: number | null;
  kapitelplan: Record<number, number>;
  geschrieben: number[];
  naechstes_kapitel: number | null;
  zu_schreiben: number[];
  anknuepfpunkt: AutomatikAnknuepfpunkt | null;
}

export interface FundusImportAntwort {
  importierte_projekte: number;
  gefundene_figuren: number;
  uebersprungen: string[];
}

export interface FundusProjektAntwort {
  gefundene_figuren: number;
  uebersprungen: boolean;
}

export interface FundusFigur {
  epoche: string;
  name: string;
  /** Insertion-geordnet: Standardfelder zuerst, dann eigene Zusatzfelder, "Geschichten" immer zuletzt. */
  felder: Record<string, string>;
}

export interface FundusFigurenAntwort {
  figuren: FundusFigur[];
  standard_felder: string[];
}

export interface ProjektBereinigenAntwort {
  geloeschte_bak: number;
  geloeschte_stand: number;
}

export interface Einstellungen {
  projects_dir: string;
  ist_standard: boolean;
  standard_projects_dir: string;
  unterordner_je_epoche: boolean;
  /** Link zu einer externen Bildgenerierungs-Weboberflaeche (z.B. Google
   * Gemini) - Schnellzugriff im Titelbild-Bereich (Stand & Export). */
  bildgenerator_url: string;
  bildgenerator_url_ist_standard: boolean;
  /** Zeit-Ueberbrueckungs-Overlay "Unnuetzes Wissen" (siehe
   * components/ZeitUeberbrueckungOverlay.tsx): komplett abschaltbar, sonst
   * konfigurierbar wann es waehrend einer KI-Wartezeit erscheint und wie
   * schnell es weiterblaettert. */
  unnuetzes_wissen_aktiv: boolean;
  unnuetzes_wissen_start_sekunden: number;
  unnuetzes_wissen_wechsel_sekunden: number;
}

// /api/auth/*
export interface Benutzer {
  id: number;
  username: string;
  ist_admin: boolean;
}

export interface LoginEingabe {
  username: string;
  password: string;
}

// /api/benutzer/* - nur fuer Admin-Benutzer erreichbar (siehe Tab "Benutzer")
export interface BenutzerEintrag {
  id: number;
  username: string;
  ist_admin: boolean;
  created_at: string;
}

export interface BenutzerAnlegenEingabe {
  username: string;
  password: string;
  ist_admin: boolean;
}

export interface WissenEintrag {
  nummer: number;
  kategorie: string;
  thema: string;
  kuriositaet: string;
  hintergrund: string;
  quelle: string | null;
}

// /api/unnuetzeswissen/naechstes - liefert Eintraege in einer serverseitig
// gemerkten, einmal gemischten Reihenfolge statt rein zufaellig, damit
// jeder Eintrag garantiert einmal drankommt bevor sich etwas wiederholt.
export interface WissenNaechstesAntwort {
  eintrag: WissenEintrag;
  position: number;
  gesamt: number;
}

// WebSocket-Nachrichten von /api/projects/{ordner}/ws/schreiben/{n}
export type SchreibenNachricht =
  | { phase: "stand_nachholen"; typ: "start" | "done"; kapitel: number }
  | { phase: "autor"; typ: "start"; modell: string; ziel_woerter: number | null }
  | { phase: "autor"; typ: "thinking" | "content"; text: string }
  | { phase: "autor"; typ: "done"; meta: Record<string, unknown> }
  | { phase: "autor"; typ: "error"; text: string }
  | {
      phase: "nachbearbeitung";
      typ: "done";
      findings: Finding[];
      gesichert_als: string | null;
      titelseite_hinzugefuegt: boolean;
    }
  | { phase: "pruefen"; typ: "start" }
  | { phase: "pruefen"; typ: "done"; befunde: BefundeAntwort }
  | { phase: "abgeschlossen"; kapitel_text: string }
  | { phase: "fehler"; typ: "error"; text: string };

// WebSocket-Nachrichten von /api/projects/{ordner}/ws/architekt
export type ArchitektNachricht =
  | { phase: "fortgesetzt"; verlauf: string[] }
  | { phase: "zurueckgesetzt"; verlauf: string[] }
  | { phase: "frage"; typ: "start" }
  | { phase: "frage"; typ: "denkt_nach" }
  | { phase: "frage"; typ: "fertig"; text: string }
  | {
      phase: "abgeschlossen";
      geruest: string;
      ausgangslage_gespeichert: boolean;
      gesichert_als: string | null;
      neuer_ordner: string;
      kapitelplan_platzhalter: string[];
    }
  | { phase: "beendet_ohne_speichern" }
  | { phase: "fehler"; typ: "error"; text: string };
