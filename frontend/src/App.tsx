import { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import type { ProjektDetail, ProjektKurz, SSHZiel } from "./api/types";
import { TabBar } from "./components/TabBar";
import { ArchitektInterviewPage } from "./pages/ArchitektInterviewPage";
import { EinstellungenPage } from "./pages/EinstellungenPage";
import { EpocheErstellenPage } from "./pages/EpocheErstellenPage";
import { GeruestPage } from "./pages/GeruestPage";
import { LektorierenPage } from "./pages/LektorierenPage";
import { ProjektePage } from "./pages/ProjektePage";
import { PersonasPage } from "./pages/PersonasPage";
import { PruefenAnwendenPage } from "./pages/PruefenAnwendenPage";
import { SchreibenPage } from "./pages/SchreibenPage";
import { SshZielePage } from "./pages/SshZielePage";
import { StandExportPage } from "./pages/StandExportPage";

function App() {
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
    projekteLaden();
    sshZieleLaden();
  }, [projekteLaden, sshZieleLaden]);

  useEffect(() => {
    projektDetailLaden();
  }, [projektDetailLaden]);

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

  const tabs = [
    { id: "projekte", label: "Projekte", icon: "📚" },
    ...(aktuellesProjekt
      ? [
          { id: "geruest", label: "Architekt / Gerüst", icon: "🗺️" },
          { id: "schreiben", label: "Schreiben", icon: "✍️" },
          { id: "pruefen", label: "Prüfen & Anwenden", icon: "🔍" },
          { id: "lektorieren", label: "Lektorieren", icon: "🪄" },
          { id: "stand", label: "Stand & Export", icon: "📦" },
          { id: "personas", label: "Personas", icon: "🎭" },
        ]
      : []),
    { id: "epoche", label: "Epoche erstellen", icon: "🏛️" },
    { id: "ssh", label: "KI-Ziele", icon: "🔌" },
    { id: "einstellungen", label: "Einstellungen", icon: "⚙️" },
  ];

  return (
    <div className="flex min-h-screen flex-col text-text">
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <h1 className="flex items-center gap-2">
          <span aria-hidden="true" className="text-2xl">
            📖
          </span>
          <span className="heading-flourish inline-block bg-gradient-to-r from-accent-light to-accent bg-clip-text text-3xl font-bold tracking-tight text-transparent transition-transform duration-300 hover:-rotate-1 hover:scale-105">
            Geschichten Erzähler
          </span>
        </h1>
        {aktuellesProjekt && (
          <span className="text-sm text-text-muted">
            Projekt: <span className="font-medium text-text">{projektDetail?.ordner ?? aktuellesProjekt}</span>
          </span>
        )}
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
      <main className="flex-1">
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
                  sshZiele={sshZiele}
                  sshZielId={sshZielId}
                  onSshZielIdChange={setSshZielId}
                  onAbgeschlossen={architektAbgeschlossen}
                />
              ) : (
                <GeruestPage
                  ordner={aktuellesProjekt}
                  projekt={projektDetail}
                  onGeaendert={projektDetailLaden}
                  onInterviewStarten={() => setInterviewErzwungen(true)}
                />
              )}
            </div>

            <div className={activeTab === "schreiben" ? "" : "hidden"}>
              <SchreibenPage
                ordner={aktuellesProjekt}
                projekt={projektDetail}
                sshZiele={sshZiele}
                sshZielId={sshZielId}
                onSshZielIdChange={setSshZielId}
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
                sshZiele={sshZiele}
                sshZielId={sshZielId}
                onSshZielIdChange={setSshZielId}
              />
            </div>

            <div className={activeTab === "lektorieren" ? "" : "hidden"}>
              <LektorierenPage
                ordner={aktuellesProjekt}
                projekt={projektDetail}
                sshZiele={sshZiele}
                sshZielId={sshZielId}
                onSshZielIdChange={setSshZielId}
              />
            </div>

            <div className={activeTab === "stand" ? "" : "hidden"}>
              <StandExportPage
                ordner={aktuellesProjekt}
                projekt={projektDetail}
                sshZiele={sshZiele}
                sshZielId={sshZielId}
                onSshZielIdChange={setSshZielId}
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
    </div>
  );
}

export default App;
