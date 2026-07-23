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
    { id: "projekte", label: "Projekte" },
    ...(aktuellesProjekt
      ? [
          { id: "geruest", label: "Architekt / Gerüst" },
          { id: "schreiben", label: "Schreiben" },
          { id: "pruefen", label: "Prüfen & Anwenden" },
          { id: "lektorieren", label: "Lektorieren" },
          { id: "stand", label: "Stand & Export" },
        ]
      : []),
    { id: "ssh", label: "SSH-Ziele" },
  ];

  return (
    <div className="flex min-h-screen flex-col bg-neutral-50 text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
      <header className="flex items-center justify-between border-b border-neutral-200 px-6 py-3 dark:border-neutral-800">
        <h1 className="text-base font-semibold">Novellen-GUI</h1>
        {aktuellesProjekt && (
          <span className="text-sm text-neutral-500">
            Projekt: <span className="font-medium text-neutral-800 dark:text-neutral-200">{projektDetail?.ordner ?? aktuellesProjekt}</span>
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
