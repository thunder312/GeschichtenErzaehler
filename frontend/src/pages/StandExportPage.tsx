import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ProjektDetail, SSHZiel } from "../api/types";
import { Badge, Button, Card, CardTitle, Input, Label, Select } from "../components/ui";
import { useAktivitaet } from "../context/AktivitaetContext";
import { alsDateiHerunterladen } from "../utils/download";
import { useLetztesKapitelSync } from "../utils/useLetztesKapitelSync";

interface StandExportPageProps {
  ordner: string;
  projekt: ProjektDetail | null;
  sshZielId: string;
  sshZiele: SSHZiel[];
  onGeaendert: () => void;
}

export function StandExportPage({
  ordner,
  projekt,
  sshZielId,
  sshZiele,
  onGeaendert,
}: StandExportPageProps) {
  const [n, setN] = useState(projekt?.kapitel.at(-1) ?? 1);
  const [standText, setStandText] = useState<string | null>(null);
  const [autoExport, setAutoExport] = useState(false);
  const [ladenStand, setLadenStand] = useState(false);

  const [ladenStandNeu, setLadenStandNeu] = useState(false);

  const [von, setVon] = useState<number | undefined>(undefined);
  const [bis, setBis] = useState<number | undefined>(undefined);
  const [gesamtText, setGesamtText] = useState<string | null>(null);
  const [gesamtDateiname, setGesamtDateiname] = useState("");
  const [ladenExport, setLadenExport] = useState(false);
  // Merkt sich, welche der beiden Export-Aktionen zuletzt lief, damit
  // "🔄 Neu laden" (siehe standNeuLaden/exportNeuLaden unten) dieselbe
  // Aktion wiederholen kann, statt zu raten.
  const [letzteExportArt, setLetzteExportArt] = useState<"gesamt" | "zwischenstand" | null>(null);

  const bildZiele = sshZiele.filter((z) => z.bildki_port != null);
  const [bildZielId, setBildZielId] = useState("");
  const [coverPrompt, setCoverPrompt] = useState("");
  const [coverVorhanden, setCoverVorhanden] = useState(false);
  const [coverVersion, setCoverVersion] = useState(0);
  const [ladenCoverPrompt, setLadenCoverPrompt] = useState(false);
  const [ladenCoverBild, setLadenCoverBild] = useState(false);
  const [ladenCoverUpload, setLadenCoverUpload] = useState(false);
  const [coverFehler, setCoverFehler] = useState<string | null>(null);
  const [bildgeneratorUrl, setBildgeneratorUrl] = useState<string | null>(null);

  const [fehler, setFehler] = useState<string | null>(null);
  const { starten, beenden } = useAktivitaet();
  useLetztesKapitelSync(projekt, setN);

  useEffect(() => {
    if (bildZiele.length > 0 && !bildZielId) {
      setBildZielId(bildZiele[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sshZiele]);

  useEffect(() => {
    api.einstellungen().then((e) => setBildgeneratorUrl(e.bildgenerator_url)).catch(() => {});
  }, []);

  useEffect(() => {
    setCoverVorhanden(false);
    fetch(api.coverUrl(ordner), { credentials: "same-origin" })
      .then((r) => setCoverVorhanden(r.ok))
      .catch(() => setCoverVorhanden(false));
  }, [ordner, coverVersion]);

  async function coverPromptVorschlagen() {
    setLadenCoverPrompt(true);
    setCoverFehler(null);
    starten("Fasst Gerüst zu einem Bildprompt zusammen...");
    try {
      const antwort = await api.coverPromptVorschlagen(ordner, sshZielId || null);
      setCoverPrompt(antwort.prompt);
    } catch (e) {
      setCoverFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLadenCoverPrompt(false);
      beenden();
    }
  }

  async function coverGenerieren() {
    if (!bildZielId || !coverPrompt.trim()) return;
    setLadenCoverBild(true);
    setCoverFehler(null);
    starten("Generiert Titelbild (kann bis zu 3 Minuten dauern)...");
    try {
      await api.coverGenerieren(ordner, coverPrompt.trim(), bildZielId, sshZielId || null);
      setCoverVersion((v) => v + 1);
    } catch (e) {
      setCoverFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLadenCoverBild(false);
      beenden();
    }
  }

  async function coverHochladen(datei: File) {
    setLadenCoverUpload(true);
    setCoverFehler(null);
    starten("Lädt Titelbild hoch...");
    try {
      await api.coverHochladen(ordner, datei);
      setCoverVersion((v) => v + 1);
    } catch (e) {
      setCoverFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLadenCoverUpload(false);
      beenden();
    }
  }

  async function standErzeugen() {
    setLadenStand(true);
    setFehler(null);
    starten(`Erzeugt Stand nach Kapitel ${n} (Chronist)...`);
    try {
      const antwort = await api.standErzeugen(ordner, n, sshZielId || null);
      setStandText(antwort.stand);
      setAutoExport(antwort.auto_export);
      onGeaendert();
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLadenStand(false);
      beenden();
    }
  }

  // Liest nur die bereits gespeicherte stand_NN.md neu ein (kein Chronist-
  // Aufruf, also kein Ollama-Roundtrip) - fuer den Fall, dass sich Kapitel
  // NACH dem letzten "Stand erzeugen" noch geaendert haben (z.B. im Tab
  // "Rechtschreibung") und die hier angezeigte Vorschau veraltet ist, ohne
  // dass man dafuer gleich eine komplette Neu-Zusammenfassung bezahlen will.
  async function standNeuLaden() {
    setLadenStandNeu(true);
    setFehler(null);
    try {
      setStandText(await api.stand(ordner, n));
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLadenStandNeu(false);
    }
  }

  async function exportieren() {
    setLadenExport(true);
    setFehler(null);
    try {
      const antwort = await api.exportieren(ordner);
      setGesamtText(antwort.gesamt);
      setGesamtDateiname(antwort.dateiname);
      setLetzteExportArt("gesamt");
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLadenExport(false);
    }
  }

  async function zusammenfassen() {
    setLadenExport(true);
    setFehler(null);
    try {
      const antwort = await api.zusammenfassen(ordner, von, bis);
      setGesamtText(antwort.inhalt ?? antwort.gesamt ?? null);
      setGesamtDateiname(antwort.datei ?? antwort.dateiname ?? "gesamt.md");
      setLetzteExportArt("zwischenstand");
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLadenExport(false);
    }
  }

  // Wiederholt die zuletzt genutzte der beiden Export-Aktionen (beide lesen
  // die Kapitel-Dateien ohnehin bei jedem Aufruf frisch von der Platte, kein
  // Ollama-Aufruf - "neu laden" ist hier also einfach derselbe Klick nochmal,
  // nur unter einem Namen, der den Zweck klarer macht).
  function exportNeuLaden() {
    if (letzteExportArt === "zwischenstand") zusammenfassen();
    else exportieren();
  }

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <Card>
        <CardTitle>📦 Zustand nach Kapitel festhalten (Chronist)</CardTitle>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <Label>Kapitelnummer</Label>
            <Input type="number" min={1} value={n} onChange={(e) => setN(Number(e.target.value))} className="w-28" />
          </div>
          <Button onClick={standErzeugen} disabled={ladenStand}>
            {ladenStand ? "Erzeugt..." : "Stand erzeugen"}
          </Button>
          <Button variant="secondary" onClick={standNeuLaden} disabled={ladenStandNeu || ladenStand}>
            {ladenStandNeu ? "Lädt..." : "🔄 Neu laden"}
          </Button>
        </div>
        <p className="mt-1 text-xs text-text-muted">
          „Stand erzeugen" lässt den Chronisten neu zusammenfassen (KI-Aufruf). „Neu laden" zeigt nur den zuletzt
          gespeicherten Stand erneut an - z.B. falls du seitdem im Tab „Rechtschreibung" etwas am Kapiteltext
          geändert hast.
        </p>
        {fehler && <p className="mt-2 text-sm text-red-400">{fehler}</p>}
        {standText && (
          <div className="mt-4">
            {autoExport && (
              <div className="mb-2">
                <Badge tone="green">
                  Letztes geplantes Kapitel erreicht - alle Kapitel wurden automatisch zu gesamt.md
                  zusammengefügt.
                </Badge>
              </div>
            )}
            <div className="mb-1 flex justify-end">
              <button
                onClick={() => alsDateiHerunterladen(`stand_${String(n).padStart(2, "0")}.md`, standText)}
                className="text-xs text-accent-light hover:underline"
              >
                ⬇️ Herunterladen
              </button>
            </div>
            <pre className="max-h-[360px] overflow-auto whitespace-pre-wrap rounded-lg bg-bg p-3 text-sm text-text">
              {standText}
            </pre>
          </div>
        )}
      </Card>

      <Card>
        <CardTitle>🎨 Titelbild</CardTitle>

        {bildZiele.length === 0 ? (
          <p className="text-sm text-text-muted">
            Kein KI-Ziel mit konfigurierter Bildgenerierung vorhanden. Unter "KI-Ziele" bei einem
            Ziel den Bild-Port hinterlegen, um diese Funktion zu nutzen - oder unten direkt ein
            fertiges Bild hochladen.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-end gap-4">
              <div>
                <Label>Bild-KI-Ziel</Label>
                <Select value={bildZielId} onChange={(e) => setBildZielId(e.target.value)} className="w-56">
                  {bildZiele.map((z) => (
                    <option key={z.id} value={z.id}>
                      {z.name}
                    </option>
                  ))}
                </Select>
              </div>
              <Button onClick={coverPromptVorschlagen} variant="secondary" disabled={ladenCoverPrompt}>
                {ladenCoverPrompt ? "Erzeugt Vorschlag..." : "Prompt vorschlagen"}
              </Button>
            </div>
            <div className="mt-4">
              <Label>Bildprompt (Deutsch, editierbar - wird vor der Generierung automatisch übersetzt)</Label>
              <textarea
                value={coverPrompt}
                onChange={(e) => setCoverPrompt(e.target.value)}
                rows={3}
                className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text outline-none transition-colors focus:border-accent"
                placeholder="Erst 'Prompt vorschlagen' klicken oder direkt selbst einen Bildprompt auf Deutsch eingeben..."
              />
            </div>
            <div className="mt-3 flex items-center gap-4">
              <Button onClick={coverGenerieren} disabled={ladenCoverBild || !coverPrompt.trim()}>
                {ladenCoverBild ? "Generiert Bild..." : coverVorhanden ? "Bild neu generieren" : "Bild generieren"}
              </Button>
            </div>
          </>
        )}

        <div className={bildZiele.length === 0 ? "mt-2" : "mt-6 border-t border-border pt-4"}>
          <Label>Oder eigenes Bild hochladen</Label>
          <p className="mb-2 text-xs text-text-muted">
            Z. B. von Hand{" "}
            {bildgeneratorUrl && (
              <>
                über{" "}
                <a href={bildgeneratorUrl} target="_blank" rel="noopener noreferrer" className="text-accent-light hover:underline">
                  einen externen Bildgenerator ↗
                </a>{" "}
              </>
            )}
            erzeugt und heruntergeladen - PNG, JPEG oder WEBP, wird automatisch zu PNG umgewandelt.
            Der Link lässt sich unter "Einstellungen" anpassen.
          </p>
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            disabled={ladenCoverUpload}
            onChange={(e) => {
              const datei = e.target.files?.[0];
              e.target.value = "";
              if (datei) coverHochladen(datei);
            }}
            className="text-sm text-text-muted file:mr-3 file:rounded-full file:border-0 file:bg-accent file:px-4 file:py-2 file:text-sm file:font-medium file:text-[#0c1712] hover:file:bg-accent-hover"
          />
          {ladenCoverUpload && <p className="mt-1 text-xs text-text-muted">Lädt hoch...</p>}
        </div>

        {coverVorhanden && (
          <div className="mt-4 max-w-xs">
            <a href={`${api.coverUrl(ordner)}?v=${coverVersion}`} target="_blank" rel="noopener noreferrer">
              <img
                key={coverVersion}
                src={`${api.coverUrl(ordner)}?v=${coverVersion}`}
                alt="Titelbild"
                className="w-full cursor-zoom-in rounded-lg border border-border transition-opacity hover:opacity-90"
              />
            </a>
          </div>
        )}
        {coverFehler && <p className="mt-2 text-sm text-red-400">{coverFehler}</p>}
      </Card>

      <Card>
        <CardTitle>🗂️ Export / Zwischenstand</CardTitle>
        <div className="flex flex-wrap items-end gap-4">
          <Button onClick={exportieren} variant="secondary" disabled={ladenExport}>
            Alle Kapitel zusammenfassen
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => window.open(api.exportPdfUrl(ordner), "_blank")}
          >
            📖 Als PDF-Buch herunterladen
          </Button>
          <div>
            <Label>von Kapitel</Label>
            <Input type="number" min={1} className="w-24" value={von ?? ""} onChange={(e) => setVon(e.target.value ? Number(e.target.value) : undefined)} />
          </div>
          <div>
            <Label>bis Kapitel</Label>
            <Input type="number" min={1} className="w-24" value={bis ?? ""} onChange={(e) => setBis(e.target.value ? Number(e.target.value) : undefined)} />
          </div>
          <Button onClick={zusammenfassen} variant="secondary" disabled={ladenExport}>
            Zwischenstand zusammenfassen
          </Button>
        </div>
        {gesamtText && (
          <div className="mt-4">
            <div className="mb-1 flex justify-end gap-3">
              <button
                onClick={exportNeuLaden}
                disabled={ladenExport}
                className="text-xs text-accent-light hover:underline disabled:opacity-40"
              >
                {ladenExport ? "Lädt..." : "🔄 Neu laden"}
              </button>
              <button
                onClick={() => alsDateiHerunterladen(gesamtDateiname, gesamtText)}
                className="text-xs text-accent-light hover:underline"
              >
                ⬇️ Herunterladen
              </button>
            </div>
            <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap rounded-lg bg-bg p-3 text-sm text-text">
              {gesamtText}
            </pre>
          </div>
        )}
      </Card>
    </div>
  );
}
