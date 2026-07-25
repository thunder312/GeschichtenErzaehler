import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import type { ProjektDetail, ProjektKurz, SSHZiel } from "./api/types";
import { TabBar } from "./components/TabBar";
import { ArchitektInterviewPage } from "./pages/ArchitektInterviewPage";
import { EinstellungenPage } from "./pages/EinstellungenPage";
import { EpocheErstellenPage } from "./pages/EpocheErstellenPage";
import { GeruestPage } from "./pages/GeruestPage";
import { StatusFooter } from "./components/StatusFooter";
import { ZeitUeberbrueckungOverlay } from "./components/ZeitUeberbrueckungOverlay";
import { AktivitaetProvider } from "./context/AktivitaetContext";
import { useAuth } from "./context/AuthContext";
import { LektorierenPage } from "./pages/LektorierenPage";
import { LoginPage } from "./pages/LoginPage";
import { ProjektePage } from "./pages/ProjektePage";
import { PersonasPage } from "./pages/PersonasPage";
import { PruefenAnwendenPage } from "./pages/PruefenAnwendenPage";
import { RechtschreibungPage } from "./pages/RechtschreibungPage";
import { SchreibenPage } from "./pages/SchreibenPage";
import { SshZielePage } from "./pages/SshZielePage";
import { StandExportPage } from "./pages/StandExportPage";
import { Button, Select } from "./components/ui";

function App() {
  const { benutzer, ladend, logout } = useAuth();
  const [projekte, setProjekte] = useState<ProjektKurz[]>([]);
  const [sshZiele, setSshZiele] = useState<SSHZiel[]>([]);
  const [aktuellesProjekt, setAktuellesProjekt] = useState<string | null>(null);
  const [projektDetail, setProjektDetail] = useState<ProjektDetail | null>(null);
  const [activeTab, setActiveTab] = useState("projekte");
  const [interviewErzwungen, setInterviewErzwungen] = useState(false);
  // Geteilt ueber alle Pipeline-Schritte hinweg (Architekt, Schreiben,
  // Pruefen, Lektorieren, Stand): das gewaehlte KI-Ziel soll beim
  // Tab-Wechsel erhalten bleiben, statt bei jedem neu gemounteten Tab auf
  // "Lokal" zurueckzufallen - das fuehrte sonst dazu, dass z.B. "Pruefen"
  // versehentlich gegen ein nicht erreichbares lokales Ollama lief, obwohl
  // im Schreiben-Tab zuvor ein SSH-Ziel gewaehlt war.
  const [sshZielId, setSshZielId] = useState("");
  const favoritVorausgewaehlt = useRef(false);

  const projekteLaden = useCallback(() => {
    api.projekte().then(setProjekte);
  }, []);

  const sshZieleLaden = useCallback(() => {
    api.sshZiele().then(setSshZiele);
  }, []);

  const projektDetailLaden = useCallback(() => {
    if (aktuellesProjekt) api.projekt(aktuellesProjekt).then(setProjektDetail);
  }, [aktuellesProjekt]);

  useEffect(() => {
    // Vor dem Login (siehe useAuth() oben) macht das Laden noch keinen
    // Sinn - ist Settings.auth_aktiv im Backend an, liefen diese Aufrufe
    // sonst ins Leere (401), bevor ueberhaupt eine Session existiert.
    if (!benutzer) return;
    projekteLaden();
    sshZieleLaden();
  }, [benutzer, projekteLaden, sshZieleLaden]);

  useEffect(() => {
    projektDetailLaden();
  }, [projektDetailLaden]);

  useEffect(() => {
    // Nur EINMAL beim ersten Laden der KI-Ziele automatisch vorbelegen -
    // ein spaeter im laufenden Betrieb gesetzter/entfernter Favorit soll die
    // gerade aktive Auswahl nicht nachtraeglich unter dem Nutzer wegziehen.
    if (favoritVorausgewaehlt.current || sshZiele.length === 0) return;
    favoritVorausgewaehlt.current = true;
    const favorit = sshZiele.find((z) => z.favorit);
    if (favorit) setSshZielId(favorit.id);
  }, [sshZiele]);

  function projektAuswaehlen(ordner: string) {
    setAktuellesProjekt(ordner);
    setInterviewErzwungen(false);
    setActiveTab("geruest");
  }

  function architektAbgeschlossen(neuerOrdner: string) {
    setInterviewErzwungen(false);
    setAktuellesProjekt(neuerOrdner);
    projekteLaden();
  }

  function ordnerUmbenannt(neuerOrdner: string) {
    setAktuellesProjekt(neuerOrdner);
    projekteLaden();
  }

  if (ladend) return null;
  if (!benutzer) return <LoginPage />;

  const tabs = [
    { id: "projekte", label: "Projekte", icon: "📚" },
    ...(aktuellesProjekt
      ? [
          { id: "geruest", label: "Architekt / Gerüst", icon: "🗺️" },
          { id: "schreiben", label: "Schreiben", icon: "✍️" },
          { id: "pruefen", label: "Prüfen & Anwenden", icon: "🔍" },
          { id: "lektorieren", label: "Lektorieren", icon: "🪄" },
          { id: "rechtschreibung", label: "Rechtschreibung", icon: "📖" },
          { id: "stand", label: "Stand & Export", icon: "📦" },
          { id: "personas", label: "Personas", icon: "🎭" },
        ]
      : []),
    { id: "epoche", label: "Epoche erstellen", icon: "🏛️" },
    { id: "ssh", label: "KI-Ziele", icon: "🔌", align: "end" as const },
    { id: "einstellungen", label: "Einstellungen", icon: "⚙️", align: "end" as const },
  ];

  return (
    <AktivitaetProvider>
    <div className="flex h-screen flex-col overflow-hidden text-text">
      <header className="flex items-center justify-between gap-4 border-b border-border px-6 py-4">
        <div className="flex min-w-0 items-center gap-4">
          <h1 className="flex shrink-0 items-center gap-2">
            <span aria-hidden="true" className="text-2xl">
              📖
            </span>
            <span className="heading-flourish inline-block bg-gradient-to-r from-accent-light to-accent bg-clip-text text-3xl font-bold tracking-tight text-transparent transition-transform duration-300 hover:-rotate-1 hover:scale-105">
              Geschichten Erzähler
            </span>
          </h1>
          {aktuellesProjekt && (
            <span className="truncate whitespace-nowrap text-sm text-text-muted">
              Projekt: <span className="font-medium text-text">{projektDetail?.ordner ?? aktuellesProjekt}</span>
            </span>
          )}
        </div>
        {aktuellesProjekt && (
          <div className="shrink-0">
            {/* Ein einziges KI-Ziel pro Projekt-Sitzung statt einer eigenen
                Auswahl in jedem Pipeline-Schritt - innerhalb derselben
                Geschichte wechselt man das praktisch nie zwischen den
                Schritten. */}
            <Select
              value={sshZielId}
              onChange={(e) => setSshZielId(e.target.value)}
              className="w-56"
            >
              <option value="">Lokal / Standard-Ollama</option>
              {sshZiele.map((z) => (
                <option key={z.id} value={z.id}>
                  {z.name} ({z.host})
                </option>
              ))}
            </Select>
          </div>
        )}
        <div className="shrink-0 flex items-center gap-3">
          <span className="text-sm text-text-muted">{benutzer.username}</span>
          <Button variant="secondary" onClick={() => logout()}>
            Abmelden
          </Button>
        </div>
      </header>

      <TabBar tabs={tabs} active={activeTab} onSelect={setActiveTab} />

      {/* Jeder Tab-Inhalt bleibt dauerhaft gemountet und wird nur per CSS
          ein-/ausgeblendet (statt bedingt gerendert), solange dasselbe
          Projekt offen ist. Vorher wurde beim Tab-Wechsel die komplette
          Seite unmounted - dabei ging jeder lokale Zustand verloren
          (laufende Pruefung/Lektorat wirkte "abgebrochen", ein gerade
          geschriebenes Kapitel "verschwand"), obwohl der zugehoerige
          Server-Request oft noch lief oder laengst fertig war. Der
          key={aktuellesProjekt} sorgt weiterhin dafuer, dass beim
          Wechsel zu einem ANDEREN Projekt alles frisch neu gemountet
          wird (kein Ueberbleibsel des vorherigen Projekts). */}
      {/* h-screen + overflow-hidden am aeusseren Container (oben) sorgt
          dafuer, dass Kopfbereich, Tab-Leiste und Fussleiste immer fix
          sichtbar bleiben - nur dieser mittlere Bereich scrollt bei Bedarf,
          statt dass die ganze Seite scrollt. */}
      <main className="flex-1 overflow-y-auto pb-10">
        <div className={activeTab === "projekte" ? "" : "hidden"}>
          <ProjektePage
            projekte={projekte}
            aktuellesProjekt={aktuellesProjekt}
            onProjekteGeaendert={projekteLaden}
            onProjektAuswaehlen={projektAuswaehlen}
          />
        </div>

        {aktuellesProjekt && (
          <div key={aktuellesProjekt}>
            <div className={activeTab === "geruest" ? "" : "hidden"}>
              {interviewErzwungen || !projektDetail?.geruest ? (
                <ArchitektInterviewPage
                  ordner={aktuellesProjekt}
                  sshZielId={sshZielId}
                  onAbgeschlossen={architektAbgeschlossen}
                />
              ) : (
                <GeruestPage
                  ordner={aktuellesProjekt}
                  projekt={projektDetail}
                  onGeaendert={projektDetailLaden}
                  onOrdnerUmbenannt={ordnerUmbenannt}
                  onInterviewStarten={() => setInterviewErzwungen(true)}
                />
              )}
            </div>

            <div className={activeTab === "schreiben" ? "" : "hidden"}>
              <SchreibenPage
                ordner={aktuellesProjekt}
                projekt={projektDetail}
                sshZielId={sshZielId}
                onKapitelGeschrieben={() => {
                  projektDetailLaden();
                  projekteLaden();
                }}
              />
            </div>

            <div className={activeTab === "pruefen" ? "" : "hidden"}>
              <PruefenAnwendenPage
                ordner={aktuellesProjekt}
                projekt={projektDetail}
                sshZielId={sshZielId}
              />
            </div>

            <div className={activeTab === "lektorieren" ? "" : "hidden"}>
              <LektorierenPage
                ordner={aktuellesProjekt}
                projekt={projektDetail}
                sshZielId={sshZielId}
              />
            </div>

            <div className={activeTab === "rechtschreibung" ? "" : "hidden"}>
              <RechtschreibungPage
                ordner={aktuellesProjekt}
                projekt={projektDetail}
                sshZielId={sshZielId}
              />
            </div>

            <div className={activeTab === "stand" ? "" : "hidden"}>
              <StandExportPage
                ordner={aktuellesProjekt}
                projekt={projektDetail}
                sshZielId={sshZielId}
                onGeaendert={() => {
                  projektDetailLaden();
                  projekteLaden();
                }}
              />
            </div>

            <div className={activeTab === "personas" ? "" : "hidden"}>
              <PersonasPage ordner={aktuellesProjekt} />
            </div>
          </div>
        )}

        <div className={activeTab === "epoche" ? "" : "hidden"}>
          <EpocheErstellenPage />
        </div>

        <div className={activeTab === "ssh" ? "" : "hidden"}>
          <SshZielePage sshZiele={sshZiele} onGeaendert={sshZieleLaden} />
        </div>

        <div className={activeTab === "einstellungen" ? "" : "hidden"}>
          <EinstellungenPage />
        </div>
      </main>
      <StatusFooter />
      <ZeitUeberbrueckungOverlay />
    </div>
    </AktivitaetProvider>
  );
}

export default App;
