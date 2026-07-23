import { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import type { ProjektDetail, ProjektKurz, SSHZiel } from "./api/types";
import { TabBar } from "./components/TabBar";
import { GeruestPage } from "./pages/GeruestPage";
import { LektorierenPage } from "./pages/LektorierenPage";
import { ProjektePage } from "./pages/ProjektePage";
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
    setActiveTab("geruest");
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
        ]
      : []),
    { id: "ssh", label: "SSH-Ziele", icon: "🔌" },
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

      <main className="flex-1">
        {activeTab === "projekte" && (
          <ProjektePage
            projekte={projekte}
            aktuellesProjekt={aktuellesProjekt}
            onProjekteGeaendert={projekteLaden}
            onProjektAuswaehlen={projektAuswaehlen}
          />
        )}

        {activeTab === "geruest" && aktuellesProjekt && (
          <GeruestPage ordner={aktuellesProjekt} projekt={projektDetail} onGeaendert={projektDetailLaden} />
        )}

        {activeTab === "schreiben" && aktuellesProjekt && (
          <SchreibenPage
            ordner={aktuellesProjekt}
            projekt={projektDetail}
            sshZiele={sshZiele}
            onKapitelGeschrieben={() => {
              projektDetailLaden();
              projekteLaden();
            }}
          />
        )}

        {activeTab === "pruefen" && aktuellesProjekt && (
          <PruefenAnwendenPage ordner={aktuellesProjekt} projekt={projektDetail} sshZiele={sshZiele} />
        )}

        {activeTab === "lektorieren" && aktuellesProjekt && (
          <LektorierenPage ordner={aktuellesProjekt} projekt={projektDetail} sshZiele={sshZiele} />
        )}

        {activeTab === "stand" && aktuellesProjekt && (
          <StandExportPage
            ordner={aktuellesProjekt}
            projekt={projektDetail}
            sshZiele={sshZiele}
            onGeaendert={() => {
              projektDetailLaden();
              projekteLaden();
            }}
          />
        )}

        {activeTab === "ssh" && <SshZielePage sshZiele={sshZiele} onGeaendert={sshZieleLaden} />}
      </main>
    </div>
  );
}

export default App;
