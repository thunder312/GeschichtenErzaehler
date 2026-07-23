// Spiegelt backend/app/schemas.py - bei Aenderungen dort bitte hier nachziehen.

export interface EpocheKurz {
  name: string;
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

export interface Finding {
  code: string;
  meldung: string;
  schwere: "warnung" | "info";
}

export interface BefundeAntwort {
  kapitel: number;
  inhalt: string;
}

export interface AnwendenAntwort {
  alt: string;
  neu: string;
  gesichert_als: string | null;
}

export interface RechtschreibWort {
  wort: string;
  satz: string | null;
}

export interface RechtschreibAntwort {
  unbekannte_woerter: RechtschreibWort[];
  hunspell_verfuegbar: boolean;
}

export interface Einstellungen {
  projects_dir: string;
  ist_standard: boolean;
  standard_projects_dir: string;
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
  | { phase: "pruefen"; typ: "done"; text: string }
  | { phase: "abgeschlossen"; kapitel_text: string }
  | { phase: "fehler"; typ: "error"; text: string };

// WebSocket-Nachrichten von /api/projects/{ordner}/ws/architekt
export type ArchitektNachricht =
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
