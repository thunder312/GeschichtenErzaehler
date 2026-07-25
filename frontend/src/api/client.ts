import type {
  AnwendenAntwort,
  BefundeAntwort,
  Benutzer,
  Einstellungen,
  EpocheKurz,
  LoginEingabe,
  ProjektDetail,
  ProjektKurz,
  RechtschreibAntwort,
  SSHTestErgebnis,
  SSHZiel,
  SSHZielEingabe,
  WissenEintrag,
} from "./types";

async function anfrage<T>(pfad: string, init?: RequestInit): Promise<T> {
  const antwort = await fetch(pfad, {
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...init,
  });
  if (!antwort.ok) {
    let detail = antwort.statusText;
    try {
      const body = await antwort.json();
      detail = body.detail ?? detail;
    } catch {
      // Antwort war kein JSON - Statustext reicht als Fehlermeldung.
    }
    throw new Error(detail);
  }
  if (antwort.status === 204) {
    return undefined as T;
  }
  const contentType = antwort.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await antwort.json()) as T;
  }
  return (await antwort.text()) as unknown as T;
}

function sshQuery(sshZielId?: string | null): string {
  return sshZielId ? `?ssh_ziel_id=${encodeURIComponent(sshZielId)}` : "";
}

export const api = {
  epochen: () => anfrage<EpocheKurz[]>("/api/projects/epochen"),

  projekte: () => anfrage<ProjektKurz[]>("/api/projects"),

  projektAnlegen: (titel: string, epoche: string) =>
    anfrage<ProjektKurz>("/api/projects", {
      method: "POST",
      // Leerer Titel ist erlaubt - das Backend legt dann einen Platzhalter-
      // Ordner "neu" an, der benannt wird, sobald das Architekten-Interview
      // einen Titel liefert.
      body: JSON.stringify({ titel, epoche }),
    }),

  projekt: (ordner: string) => anfrage<ProjektDetail>(`/api/projects/${ordner}`),

  geruestSchreiben: (ordner: string, inhalt: string) =>
    anfrage<{ gespeichert: string; gesichert_als: string | null; neuer_ordner: string | null }>(
      `/api/projects/${ordner}/geruest`,
      { method: "PUT", body: JSON.stringify({ inhalt }) },
    ),

  kapitel: (ordner: string, n: number) =>
    anfrage<string>(`/api/projects/${ordner}/kapitel/${n}`),

  kapitelSchreiben: (ordner: string, n: number, inhalt: string) =>
    anfrage<{ gesichert_als: string | null }>(
      `/api/projects/${ordner}/kapitel/${n}`,
      { method: "PUT", body: JSON.stringify({ inhalt }) },
    ),

  stand: (ordner: string, n: number) =>
    anfrage<string>(`/api/projects/${ordner}/stand/${n}`),

  befunde: (ordner: string, n: number) =>
    anfrage<string>(`/api/projects/${ordner}/befunde/${n}`),

  gesamt: (ordner: string) => anfrage<string>(`/api/projects/${ordner}/gesamt`),

  architektenGespraech: (ordner: string) =>
    anfrage<string>(`/api/projects/${ordner}/architekten-gespraech`),

  architektFortsetzbar: (ordner: string) =>
    anfrage<{ fortsetzbar: boolean }>(`/api/projects/${ordner}/architekt-fortsetzbar`),

  verbotslisteSchreiben: (ordner: string, inhalt: string) =>
    anfrage<{ gesichert_als: string | null }>(
      `/api/projects/${ordner}/verbotsliste`,
      { method: "PUT", body: JSON.stringify({ inhalt }) },
    ),

  personasAuflisten: (ordner: string) => anfrage<string[]>(`/api/projects/${ordner}/personas`),

  personaLesen: (ordner: string, name: string) =>
    anfrage<string>(`/api/projects/${ordner}/personas/${name}`),

  personaSchreiben: (ordner: string, name: string, inhalt: string) =>
    anfrage<{ gesichert_als: string | null }>(
      `/api/projects/${ordner}/personas/${name}`,
      { method: "PUT", body: JSON.stringify({ inhalt }) },
    ),

  pruefen: (ordner: string, n: number, sshZielId?: string | null) =>
    anfrage<BefundeAntwort>(
      `/api/projects/${ordner}/pruefen/${n}${sshQuery(sshZielId)}`,
      { method: "POST" },
    ),

  anwenden: (ordner: string, n: number, sshZielId?: string | null) =>
    anfrage<AnwendenAntwort>(
      `/api/projects/${ordner}/anwenden/${n}${sshQuery(sshZielId)}`,
      { method: "POST" },
    ),

  lektorieren: (ordner: string, n: number, sshZielId?: string | null) =>
    anfrage<AnwendenAntwort>(
      `/api/projects/${ordner}/lektorieren/${n}${sshQuery(sshZielId)}`,
      { method: "POST" },
    ),

  standErzeugen: (ordner: string, n: number, sshZielId?: string | null) =>
    anfrage<{ stand: string; auto_export: boolean }>(
      `/api/projects/${ordner}/stand/${n}${sshQuery(sshZielId)}`,
      { method: "POST" },
    ),

  exportieren: (ordner: string) =>
    anfrage<{ gesamt: string; dateiname: string }>(`/api/projects/${ordner}/export`, { method: "POST" }),

  exportPdfUrl: (ordner: string) => `/api/projects/${ordner}/export/pdf`,

  zusammenfassen: (ordner: string, von?: number, bis?: number) => {
    const params = new URLSearchParams();
    if (von !== undefined) params.set("von", String(von));
    if (bis !== undefined) params.set("bis", String(bis));
    const query = params.toString() ? `?${params.toString()}` : "";
    return anfrage<{ datei?: string; gesamt?: string; dateiname?: string; inhalt?: string }>(
      `/api/projects/${ordner}/zusammenfassen${query}`,
      { method: "POST" },
    );
  },

  rechtschreibung: (ordner: string, n: number, sshZielId?: string | null) =>
    anfrage<RechtschreibAntwort>(
      `/api/projects/${ordner}/rechtschreibung/${n}${sshQuery(sshZielId)}`,
    ),

  sshZiele: () => anfrage<SSHZiel[]>("/api/ssh-targets"),

  sshZielAnlegen: (daten: SSHZielEingabe) =>
    anfrage<SSHZiel>("/api/ssh-targets", {
      method: "POST",
      body: JSON.stringify(daten),
    }),

  sshZielAktualisieren: (id: string, daten: SSHZielEingabe) =>
    anfrage<SSHZiel>(`/api/ssh-targets/${id}`, {
      method: "PUT",
      body: JSON.stringify(daten),
    }),

  sshZielLoeschen: (id: string) =>
    anfrage<void>(`/api/ssh-targets/${id}`, { method: "DELETE" }),

  sshZielFavoritSetzen: (id: string, favorit: boolean) =>
    anfrage<SSHZiel>(`/api/ssh-targets/${id}/favorit`, {
      method: "PUT",
      body: JSON.stringify({ favorit }),
    }),

  sshZielTesten: (id: string) =>
    anfrage<SSHTestErgebnis>(`/api/ssh-targets/${id}/test`, { method: "POST" }),

  sshVerbindungTestenUngespeichert: (daten: SSHZielEingabe) =>
    anfrage<SSHTestErgebnis>("/api/ssh-targets/test", {
      method: "POST",
      body: JSON.stringify(daten),
    }),

  einstellungen: () => anfrage<Einstellungen>("/api/einstellungen"),

  einstellungenSchreiben: (projectsDir: string, unterordnerJeEpoche: boolean) =>
    anfrage<Einstellungen>("/api/einstellungen", {
      method: "PUT",
      body: JSON.stringify({ projects_dir: projectsDir, unterordner_je_epoche: unterordnerJeEpoche }),
    }),

  unnuetzesWissen: () => anfrage<WissenEintrag[]>("/api/unnuetzeswissen"),

  login: (eingabe: LoginEingabe) =>
    anfrage<Benutzer>("/api/auth/login", { method: "POST", body: JSON.stringify(eingabe) }),

  logout: () => anfrage<void>("/api/auth/logout", { method: "POST" }),

  me: () => anfrage<Benutzer>("/api/auth/me"),
};

export function schreibenWebSocketUrl(
  ordner: string,
  n: number,
  zusatzhinweis: string,
  sshZielId?: string | null,
): string {
  const protokoll = window.location.protocol === "https:" ? "wss" : "ws";
  const params = new URLSearchParams();
  if (zusatzhinweis) params.set("zusatzhinweis", zusatzhinweis);
  if (sshZielId) params.set("ssh_ziel_id", sshZielId);
  const query = params.toString() ? `?${params.toString()}` : "";
  return `${protokoll}://${window.location.host}/api/projects/${ordner}/ws/schreiben/${n}${query}`;
}

export function architektWebSocketUrl(ordner: string, sshZielId?: string | null): string {
  const protokoll = window.location.protocol === "https:" ? "wss" : "ws";
  const params = new URLSearchParams();
  if (sshZielId) params.set("ssh_ziel_id", sshZielId);
  const query = params.toString() ? `?${params.toString()}` : "";
  return `${protokoll}://${window.location.host}/api/projects/${ordner}/ws/architekt${query}`;
}
