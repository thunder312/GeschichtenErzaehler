import type {
  AnalyseEintrag,
  AnalysatorStatus,
  AutomatikStatus,
  AutomatikVerlaufEintrag,
  Befund,
  BefundeAntwort,
  Benutzer,
  BenutzerAnlegenEingabe,
  BenutzerEintrag,
  Einstellungen,
  EpocheErstellenAntwort,
  EpocheKurz,
  EpocheUmbenennenAntwort,
  EpocheVorschlagAntwort,
  FundusFigur,
  FundusFigurenAntwort,
  FundusImportAntwort,
  FundusProjektAntwort,
  LoginEingabe,
  OllamaModellInfo,
  PersonaModell,
  ProjektBereinigenAntwort,
  ProjektDetail,
  ProjektKurz,
  RechtschreibAntwort,
  SSHTestErgebnis,
  SSHZiel,
  SSHZielEingabe,
  WissenEintrag,
  WissenNaechstesAntwort,
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

  epocheLoeschen: (ordner: string) =>
    anfrage<void>(`/api/epochen/${encodeURIComponent(ordner)}`, { method: "DELETE" }),

  epocheDateienAuflisten: (ordner: string) =>
    anfrage<string[]>(`/api/epochen/${encodeURIComponent(ordner)}/dateien`),

  epocheDateiLesen: (ordner: string, name: string) =>
    anfrage<string>(`/api/epochen/${encodeURIComponent(ordner)}/dateien/${name}`),

  epocheDateiSchreiben: (ordner: string, name: string, inhalt: string) =>
    anfrage<{ gespeichert: boolean }>(
      `/api/epochen/${encodeURIComponent(ordner)}/dateien/${name}`,
      { method: "PUT", body: JSON.stringify({ inhalt }) },
    ),

  epocheGenreSchreiben: (ordner: string, genre: string) =>
    anfrage<{ genre: string | null }>(
      `/api/epochen/${encodeURIComponent(ordner)}/genre`,
      { method: "PUT", body: JSON.stringify({ genre }) },
    ),

  epocheFarbeSchreiben: (ordner: string, farbe: string) =>
    anfrage<{ farbe: string | null }>(
      `/api/epochen/${encodeURIComponent(ordner)}/farbe`,
      { method: "PUT", body: JSON.stringify({ farbe }) },
    ),

  projekte: () => anfrage<ProjektKurz[]>("/api/projects"),

  projektAnlegen: (titel: string, epoche: string, zweiteEpoche?: string | null) =>
    anfrage<ProjektKurz>("/api/projects", {
      method: "POST",
      // Leerer Titel ist erlaubt - das Backend legt dann einen Platzhalter-
      // Ordner "neu" an, der benannt wird, sobald das Architekten-Interview
      // einen Titel liefert. zweite_epoche ist optional (Zeitsprung-Projekt,
      // siehe app/core/epoche.py:zeitsprung_dateien_zusammenfuehren).
      body: JSON.stringify({ titel, epoche, zweite_epoche: zweiteEpoche || null }),
    }),

  projekt: (ordner: string) => anfrage<ProjektDetail>(`/api/projects/${ordner}`),

  analysatorStarten: (
    titel: string, epoche: string, text: string, zweiteEpoche?: string | null, sshZielId?: string | null,
  ) =>
    anfrage<{ ordner: string }>(`/api/analysator/starten${sshQuery(sshZielId)}`, {
      method: "POST",
      body: JSON.stringify({ titel, epoche, zweite_epoche: zweiteEpoche || null, text }),
    }),

  analysatorStatus: (ordner: string) =>
    anfrage<AnalysatorStatus>(`/api/projects/${ordner}/analysator-status`),

  analysenAuflisten: () => anfrage<AnalyseEintrag[]>("/api/analysator/analysen"),

  analyseLesen: (dateiname: string) =>
    anfrage<string>(`/api/analysator/analysen/${encodeURIComponent(dateiname)}`),

  analyseLoeschen: (dateiname: string) =>
    anfrage<void>(`/api/analysator/analysen/${encodeURIComponent(dateiname)}`, { method: "DELETE" }),

  analysatorEpocheVorschlagen: (text: string, sshZielId?: string | null) =>
    anfrage<EpocheVorschlagAntwort>(`/api/analysator/epoche-vorschlagen${sshQuery(sshZielId)}`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),

  // EpocheErstellenPage.tsx legt Epochen bisher per Roh-fetch an (siehe
  // dortiger anlegen()) - dieser Wrapper ist NUR fuer AnalysatorPage.tsx
  // (Epoche-Ableiten-Weg), der denselben Endpunkt braucht, aber ueber das
  // einheitliche anfrage<T>()-Fehlerhandling laufen soll.
  epocheErstellen: (werte: EpocheVorschlagAntwort) =>
    anfrage<EpocheErstellenAntwort>("/api/epochen", {
      method: "POST",
      body: JSON.stringify(werte),
    }),

  projektLoeschen: (ordner: string) =>
    anfrage<void>(`/api/projects/${ordner}`, { method: "DELETE" }),

  projektEpocheAendern: (ordner: string, epoche: string) =>
    anfrage<ProjektKurz>(`/api/projects/${ordner}/epoche`, {
      method: "PUT",
      body: JSON.stringify({ epoche }),
    }),

  epocheUmbenennen: (ordner: string, name: string) =>
    anfrage<EpocheUmbenennenAntwort>(`/api/epochen/${encodeURIComponent(ordner)}/name`, {
      method: "PUT",
      body: JSON.stringify({ name }),
    }),

  projektNeuSchreiben: (ordner: string) =>
    anfrage<ProjektKurz>(`/api/projects/${ordner}/neu-schreiben`, { method: "POST" }),

  projektBereinigen: (ordner: string) =>
    anfrage<ProjektBereinigenAntwort>(`/api/projects/${ordner}/bereinigen`, { method: "POST" }),

  geruestSchreiben: (ordner: string, inhalt: string) =>
    anfrage<{
      gespeichert: string;
      gesichert_als: string | null;
      neuer_ordner: string | null;
      stand_00_aktualisiert: boolean;
    }>(`/api/projects/${ordner}/geruest`, { method: "PUT", body: JSON.stringify({ inhalt }) }),

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
    anfrage<BefundeAntwort>(`/api/projects/${ordner}/befunde/${n}`),

  befundAblehnen: (ordner: string, n: number, befundId: string) =>
    anfrage<{ abgelehnt: boolean }>(
      `/api/projects/${ordner}/befunde/${n}/ablehnen`,
      { method: "POST", body: JSON.stringify({ befund_id: befundId }) },
    ),

  /** Konflikt-Fund (mehrere Prüfer mit sich widersprechenden Vorschlägen für
   * dieselbe Stelle, siehe BefundListe.tsx) per gezieltem LLM-Aufruf zu einem
   * gemeinsamen, übernehmbaren Vorschlag zusammenführen. */
  befundSynthese: (ordner: string, n: number, befundId: string, sshZielId?: string | null) =>
    anfrage<Befund>(
      `/api/projects/${ordner}/befunde/${n}/${befundId}/synthese${sshQuery(sshZielId)}`,
      { method: "POST" },
    ),

  gesamt: (ordner: string) => anfrage<string>(`/api/projects/${ordner}/gesamt`),

  architektenGespraech: (ordner: string) =>
    anfrage<string>(`/api/projects/${ordner}/architekten-gespraech`),

  architektFortsetzbar: (ordner: string) =>
    anfrage<{ fortsetzbar: boolean }>(`/api/projects/${ordner}/architekt-fortsetzbar`),

  architektVorlage: (ordner: string) =>
    anfrage<{ vorlage: string }>(`/api/projects/${ordner}/architekt-vorlage`),

  architektExtraktion: (ordner: string, handlungstext: string, sshZielId?: string | null) =>
    anfrage<{ vorlage: string }>(
      `/api/projects/${ordner}/architekt-extraktion${sshQuery(sshZielId)}`,
      { method: "POST", body: JSON.stringify({ handlungstext }) },
    ),

  verbotslisteSchreiben: (ordner: string, inhalt: string) =>
    anfrage<{ gesichert_als: string | null }>(
      `/api/projects/${ordner}/verbotsliste`,
      { method: "PUT", body: JSON.stringify({ inhalt }) },
    ),

  stilprobenSchreiben: (ordner: string, inhalt: string) =>
    anfrage<{ gesichert_als: string | null }>(
      `/api/projects/${ordner}/stilproben`,
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

  standErzeugen: (ordner: string, n: number, sshZielId?: string | null) =>
    anfrage<{ stand: string; auto_export: boolean }>(
      `/api/projects/${ordner}/stand/${n}${sshQuery(sshZielId)}`,
      { method: "POST" },
    ),

  exportieren: (ordner: string) =>
    anfrage<{ gesamt: string; dateiname: string }>(`/api/projects/${ordner}/export`, { method: "POST" }),

  exportPdfUrl: (ordner: string) => `/api/projects/${ordner}/export/pdf`,

  storyFrage: (ordner: string, frage: string, sshZielId?: string | null) =>
    anfrage<{ antwort: string }>(
      `/api/projects/${ordner}/frage${sshQuery(sshZielId)}`,
      { method: "POST", body: JSON.stringify({ frage }) },
    ),

  coverPromptVorschlagen: (ordner: string, sshZielId?: string | null) =>
    anfrage<{ prompt: string }>(
      `/api/projects/${ordner}/cover/prompt-vorschlagen${sshQuery(sshZielId)}`,
      { method: "POST" },
    ),

  coverGenerieren: (ordner: string, prompt: string, bildZielId: string, sshZielId?: string | null) => {
    const params = new URLSearchParams({ bild_ziel_id: bildZielId });
    if (sshZielId) params.set("ssh_ziel_id", sshZielId);
    return anfrage<{ gespeichert: boolean }>(
      `/api/projects/${ordner}/cover/generieren?${params.toString()}`,
      { method: "POST", body: JSON.stringify({ prompt }) },
    );
  },

  coverHochladen: (ordner: string, datei: File) => {
    const formular = new FormData();
    formular.append("datei", datei);
    // Kein "Content-Type": application/json wie im Default von anfrage() -
    // der Browser setzt bei FormData selbst den korrekten
    // multipart/form-data-Header inkl. Boundary, ein erzwungener JSON-Header
    // wuerde die Anfrage serverseitig unlesbar machen.
    return anfrage<{ gespeichert: boolean }>(
      `/api/projects/${ordner}/cover/hochladen`,
      { method: "POST", headers: {}, body: formular },
    );
  },

  coverUrl: (ordner: string) => `/api/projects/${ordner}/cover`,

  anleitungUrl: () => "/api/docs/anleitung",

  hilfeUrl: () => "/api/docs/hilfe",

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

  automatikStarten: (
    ordner: string,
    maxDurchlaeufe: number,
    sshZielId?: string | null,
    fortsetzen = false,
    automatischBestaetigen = false,
  ) =>
    anfrage<{ gestartet: boolean }>(
      `/api/projects/${ordner}/automatik/start${sshQuery(sshZielId)}`,
      {
        method: "POST",
        body: JSON.stringify({
          max_durchlaeufe: maxDurchlaeufe,
          fortsetzen,
          automatisch_bestaetigen: automatischBestaetigen,
        }),
      },
    ),

  automatikStatus: (ordner: string) =>
    anfrage<AutomatikStatus>(`/api/projects/${ordner}/automatik/status`),

  automatikStoppen: (ordner: string) =>
    anfrage<{ stop_angefordert: boolean }>(`/api/projects/${ordner}/automatik/stop`, { method: "POST" }),

  automatikVerlauf: (ordner: string) =>
    anfrage<AutomatikVerlaufEintrag[]>(`/api/projects/${ordner}/automatik/verlauf`),

  automatikResteBestaetigen: (ordner: string) =>
    anfrage<{ resten_bestaetigt: boolean }>(`/api/projects/${ordner}/automatik/resten-bestaetigen`, { method: "POST" }),

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

  sshZielModelle: (id: string) => anfrage<OllamaModellInfo[]>(`/api/ssh-targets/${id}/modelle`),

  personaModelle: () => anfrage<PersonaModell[]>("/api/persona-modelle"),

  personaModellSetzen: (persona: string, modell: string | null) =>
    anfrage<PersonaModell>(`/api/persona-modelle/${encodeURIComponent(persona)}`, {
      method: "PUT",
      body: JSON.stringify({ modell }),
    }),

  einstellungen: () => anfrage<Einstellungen>("/api/einstellungen"),

  einstellungenSchreiben: (projectsDir: string, unterordnerJeEpoche: boolean, bildgeneratorUrl?: string) =>
    anfrage<Einstellungen>("/api/einstellungen", {
      method: "PUT",
      body: JSON.stringify({
        projects_dir: projectsDir,
        unterordner_je_epoche: unterordnerJeEpoche,
        bildgenerator_url: bildgeneratorUrl,
      }),
    }),

  unnuetzesWissen: () => anfrage<WissenEintrag[]>("/api/unnuetzeswissen"),

  unnuetzesWissenNaechstes: () => anfrage<WissenNaechstesAntwort>("/api/unnuetzeswissen/naechstes"),

  login: (eingabe: LoginEingabe) =>
    anfrage<Benutzer>("/api/auth/login", { method: "POST", body: JSON.stringify(eingabe) }),

  logout: () => anfrage<void>("/api/auth/logout", { method: "POST" }),

  me: () => anfrage<Benutzer>("/api/auth/me"),

  benutzerListe: () => anfrage<BenutzerEintrag[]>("/api/benutzer"),

  benutzerAnlegen: (daten: BenutzerAnlegenEingabe) =>
    anfrage<BenutzerEintrag>("/api/benutzer", { method: "POST", body: JSON.stringify(daten) }),

  benutzerLoeschen: (id: number) =>
    anfrage<void>(`/api/benutzer/${id}`, { method: "DELETE" }),

  fundusLesen: () => anfrage<string>("/api/fundus"),

  fundusSchreiben: (inhalt: string) =>
    anfrage<{ gesichert_als: string | null }>("/api/fundus", {
      method: "PUT",
      body: JSON.stringify({ inhalt }),
    }),

  fundusImportieren: (sshZielId?: string | null) =>
    anfrage<FundusImportAntwort>(`/api/fundus/import${sshQuery(sshZielId)}`, { method: "POST" }),

  fundusProjektAktualisieren: (ordner: string, sshZielId?: string | null) =>
    anfrage<FundusProjektAntwort>(`/api/fundus/projekt/${ordner}${sshQuery(sshZielId)}`, { method: "POST" }),

  fundusFigurenLesen: () => anfrage<FundusFigurenAntwort>("/api/fundus/figuren"),

  fundusFigurAnlegen: (epoche: string, name: string, felder: Record<string, string>) =>
    anfrage<FundusFigur>("/api/fundus/figuren", {
      method: "POST",
      body: JSON.stringify({ epoche, name, felder }),
    }),

  fundusFigurAktualisieren: (
    epoche: string,
    name: string,
    felder: Record<string, string>,
    neuerName?: string,
    neueEpoche?: string,
  ) =>
    anfrage<FundusFigur>("/api/fundus/figuren", {
      method: "PUT",
      body: JSON.stringify({ epoche, name, neuer_name: neuerName ?? null, neue_epoche: neueEpoche ?? null, felder }),
    }),

  fundusFigurLoeschen: (epoche: string, name: string) =>
    anfrage<{ gelöscht: boolean }>(
      `/api/fundus/figuren?${new URLSearchParams({ epoche, name })}`,
      { method: "DELETE" },
    ),

  fundusFigurKopieren: (epoche: string, name: string, zielEpoche: string, neuerName?: string) =>
    anfrage<FundusFigur>("/api/fundus/figuren/kopieren", {
      method: "POST",
      body: JSON.stringify({ epoche, name, ziel_epoche: zielEpoche, neuer_name: neuerName ?? null }),
    }),

  fundusFeldHinzufuegen: (epoche: string, name: string, feldName: string, wert: string, fuerAlle: boolean) =>
    anfrage<FundusFigur>("/api/fundus/felder", {
      method: "POST",
      body: JSON.stringify({ epoche, name, feld_name: feldName, wert, fuer_alle: fuerAlle }),
    }),
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
