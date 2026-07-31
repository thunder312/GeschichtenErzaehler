// Spiegelt backend/app/schemas.py - bei Aenderungen dort bitte hier nachziehen.

export interface EpocheKurz {
  name: string;
  genre?: string | null;
}

export interface ProjektKurz {
  ordner: string;
  titel: string | null;
  epoche: string | null;
  anzahl_kapitel: number;
  letztes_geplantes_kapitel: number | null;
}

export interface ProjektDetail {
  ordner: string;
  epoche: string | null;
  geruest: string | null;
  verbotsliste: string | null;
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
// (Tab "KI-Ziele" -> Persona-Modell-Zuordnung), unabhaengig vom Projekt-
// Override "Autor-Modell: Qwen3" im Gerüst (siehe ProjektDetail.autor_modell).
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
}

export interface RechtschreibAntwort {
  unbekannte_woerter: RechtschreibWort[];
  hunspell_verfuegbar: boolean;
}

export interface FundusImportAntwort {
  importierte_projekte: number;
  gefundene_figuren: number;
  uebersprungen: string[];
}

export interface Einstellungen {
  projects_dir: string;
  ist_standard: boolean;
  standard_projects_dir: string;
  unterordner_je_epoche: boolean;
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
  | { phase: "frage"; typ: "start" }
  | { phase: "frage"; typ: "denkt_nach" }
  | { phase: "frage"; typ: "fertig"; text: string }
  | {
      phase: "abgeschlossen";
      geruest: string;
      ausgangslage_gespeichert: boolean;
      gesichert_als: string | null;
      neuer_ordner: string;
    }
  | { phase: "beendet_ohne_speichern" }
  | { phase: "fehler"; typ: "error"; text: string };
