import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { BefundeAntwort, ProjektDetail } from "../api/types";
import { BefundEditor } from "../components/BefundEditor";
import { Button, Card, CardTitle, Input, Label } from "../components/ui";
import { useAktivitaet } from "../context/AktivitaetContext";
import { useLetztesKapitelSync } from "../utils/useLetztesKapitelSync";

interface PruefenAnwendenPageProps {
  ordner: string;
  projekt: ProjektDetail | null;
  sshZielId: string;
}

export function PruefenAnwendenPage({
  ordner,
  projekt,
  sshZielId,
}: PruefenAnwendenPageProps) {
  const [n, setN] = useState(projekt?.kapitel.at(-1) ?? 1);
  const [kapiteltext, setKapiteltext] = useState("");
  const [bearbeitet, setBearbeitet] = useState("");
  const [kapitelGeladen, setKapitelGeladen] = useState(false);
  const [befunde, setBefunde] = useState<BefundeAntwort | null>(null);
  const [ladenPruefen, setLadenPruefen] = useState(false);
  const [gespeichertHinweis, setGespeichertHinweis] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const { starten, beenden } = useAktivitaet();
  useLetztesKapitelSync(projekt, setN);

  // Beim Wechsel auf ein anderes Kapitel den bereits vorhandenen Kapiteltext
  // und die zuletzt automatisch (nach dem Schreiben) erzeugten Befunde
  // gleich mitladen, statt eine erneute, teure KI-Pruefung zu erzwingen, nur
  // um sie wieder anzuzeigen.
  useEffect(() => {
    setGespeichertHinweis(null);
    setFehler(null);
    setKapitelGeladen(false);
    let abgebrochen = false;
    api
      .kapitel(ordner, n)
      .then((text) => {
        if (abgebrochen) return;
        setKapiteltext(text);
        setBearbeitet(text);
      })
      .catch((e) => {
        if (abgebrochen) return;
        setKapiteltext("");
        setBearbeitet("");
        setFehler(`Kapiteltext konnte nicht geladen werden: ${e instanceof Error ? e.message : String(e)}`);
      })
      .finally(() => {
        if (!abgebrochen) setKapitelGeladen(true);
      });
    api
      .befunde(ordner, n)
      .then((antwort) => {
        if (!abgebrochen) setBefunde(antwort);
      })
      .catch(() => {
        if (!abgebrochen) setBefunde(null);
      });
    return () => {
      abgebrochen = true;
    };
  }, [ordner, n]);

  async function pruefen() {
    setLadenPruefen(true);
    setFehler(null);
    starten(`Prüft Kapitel ${n} auf Anachronismen, Stimmigkeit, Kontinuität & Lektorat...`);
    try {
      const antwort = await api.pruefen(ordner, n, sshZielId || null);
      setBefunde(antwort);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLadenPruefen(false);
      beenden();
    }
  }

  async function speichern() {
    await api.kapitelSchreiben(ordner, n, bearbeitet);
    setKapiteltext(bearbeitet);
    setGespeichertHinweis("Gespeichert.");
  }

  const offeneAenderungen = bearbeitet !== kapiteltext;

  return (
    <div className="space-y-6 p-6">
      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <Label>Kapitelnummer</Label>
            <Input type="number" min={1} value={n} onChange={(e) => setN(Number(e.target.value))} className="w-28" />
          </div>
          <Button onClick={pruefen} disabled={ladenPruefen} variant="secondary">
            {ladenPruefen ? "Prüft..." : "Erneut prüfen"}
          </Button>
          <div className="ml-auto flex items-center gap-3">
            {offeneAenderungen && <span className="text-xs text-text-muted">Noch nicht gespeicherte Änderungen</span>}
            {gespeichertHinweis && <span className="text-xs text-accent-light">{gespeichertHinweis}</span>}
            <Button onClick={speichern} disabled={!offeneAenderungen}>
              Speichern
            </Button>
          </div>
        </div>
        <p className="mt-2 text-xs text-text-muted">
          Anachronismus/Stimmigkeit, Kontinuität und Lektorat laufen automatisch parallel direkt nach dem
          Schreiben eines Kapitels (Tab "Schreiben"). Jeder Fund ist im Text farbig markiert (Amber:
          Anachronismus, Violett: Stimmigkeit, Sky: Kontinuität, Grün: Lektorat, Türkis: von mehreren Prüfern
          gemeldet, Rot: widersprüchliche Vorschläge - hier manuell entscheiden). Text direkt im Editor
          bearbeiten, dann speichern.
        </p>
        {fehler && <p className="mt-2 text-sm text-red-400">{fehler}</p>}
      </Card>

      <Card>
        <CardTitle>🔍 Befunde &amp; Kapiteltext</CardTitle>
        {befunde?.veraltet && (
          <p className="mt-2 text-sm text-amber-400">
            Diese Befunde wurden gegen eine ältere Fassung des Kapiteltexts ermittelt und können falsch
            positioniert sein (nicht mehr zutreffende Funde werden automatisch als "nicht mehr vorhanden"
            markiert). Bitte "Erneut prüfen" klicken.
          </p>
        )}
        {befunde && kapitelGeladen ? (
          <BefundEditor
            key={n}
            kapiteltext={bearbeitet}
            befunde={befunde.befunde}
            onKapiteltextChange={setBearbeitet}
          />
        ) : befunde ? (
          <p className="text-sm text-text-muted">Lädt Kapiteltext...</p>
        ) : (
          <p className="text-sm text-text-muted">
            Noch keine Befunde für dieses Kapitel - "Erneut prüfen" klicken oder zuerst im Tab "Schreiben" ein
            Kapitel erzeugen.
          </p>
        )}
      </Card>
    </div>
  );
}
