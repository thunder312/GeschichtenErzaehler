import { useState } from "react";
import { api } from "../api/client";
import type { ProjektDetail, RechtschreibWort } from "../api/types";
import { Button, Card, CardTitle, Input, Label } from "../components/ui";
import { useAktivitaet } from "../context/AktivitaetContext";
import { useLetztesKapitelSync } from "../utils/useLetztesKapitelSync";

interface RechtschreibungPageProps {
  ordner: string;
  projekt: ProjektDetail | null;
  sshZielId: string;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Hebt das gefundene Wort innerhalb seines Satzkontexts hervor, damit man
 * es nicht erst im Fliesstext suchen muss. */
function satzMitHervorhebung(satz: string, wort: string) {
  const teile = satz.split(new RegExp(`(\\b${escapeRegExp(wort)}\\b)`, "gi"));
  return teile.map((teil, i) =>
    teil.toLowerCase() === wort.toLowerCase() ? (
      <mark key={i} className="rounded bg-violet-400/30 px-0.5 text-violet-100">
        {teil}
      </mark>
    ) : (
      <span key={i}>{teil}</span>
    ),
  );
}

export function RechtschreibungPage({
  ordner,
  projekt,
  sshZielId,
}: RechtschreibungPageProps) {
  const [n, setN] = useState(projekt?.kapitel.at(-1) ?? 1);
  const [woerter, setWoerter] = useState<RechtschreibWort[] | null>(null);
  const [hunspellVerfuegbar, setHunspellVerfuegbar] = useState(true);
  const [ersatzWerte, setErsatzWerte] = useState<Record<string, string>>({});
  const [laedt, setLaedt] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const { starten, beenden } = useAktivitaet();
  useLetztesKapitelSync(projekt, setN);

  async function rechtschreibungPruefen() {
    setLaedt(true);
    setFehler(null);
    starten(`Prüft Kapitel ${n} per hunspell auf unbekannte Wörter...`);
    try {
      const antwort = await api.rechtschreibung(ordner, n, sshZielId || null);
      setWoerter(antwort.unbekannte_woerter);
      setHunspellVerfuegbar(antwort.hunspell_verfuegbar);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLaedt(false);
      beenden();
    }
  }

  async function ersetzenUndSpeichern() {
    const eintraege = Object.entries(ersatzWerte).filter(([, ersatz]) => ersatz.trim() !== "");
    if (eintraege.length === 0) return;
    let text = await api.kapitel(ordner, n);
    for (const [wort, ersatz] of eintraege) {
      text = text.replace(new RegExp(`\\b${wort}\\b`, "g"), ersatz);
    }
    await api.kapitelSchreiben(ordner, n, text);
    setErsatzWerte({});
    setWoerter(null);
  }

  return (
    <div className="space-y-6 p-6">
      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <Label>Kapitelnummer</Label>
            <Input type="number" min={1} value={n} onChange={(e) => setN(Number(e.target.value))} className="w-28" />
          </div>
          <Button onClick={rechtschreibungPruefen} disabled={laedt}>
            {laedt ? "Prüft..." : "Wörterbuch-Prüfung (hunspell)"}
          </Button>
        </div>
        {fehler && <p className="mt-2 text-sm text-red-400">{fehler}</p>}
      </Card>

      {woerter && (
        <Card>
          <CardTitle>📖 Unbekannte Wörter</CardTitle>
          {!hunspellVerfuegbar && (
            <p className="mb-2 text-sm text-amber-300">
              hunspell ist auf dem angesprochenen Ziel nicht verfügbar - für lokale Windows-Entwicklung ein
              SSH-Ziel mit installiertem hunspell auswählen.
            </p>
          )}
          {woerter.length === 0 ? (
            <p className="text-sm text-text-muted">Keine unbekannten Wörter gefunden.</p>
          ) : (
            <div className="space-y-2">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="text-xs font-medium uppercase tracking-wider text-text-muted">
                    <th className="pb-2 pr-[50px] text-left">Wort</th>
                    <th className="pb-2 pr-4 text-left">Satzkontext</th>
                    <th className="w-64 pb-2 text-left">Ersatzwort</th>
                  </tr>
                </thead>
                <tbody>
                  {woerter.map((w) => (
                    <tr key={w.wort} className="border-b border-border last:border-0">
                      <td className="whitespace-nowrap py-2 pr-[50px] align-middle font-mono text-sm">{w.wort}</td>
                      <td className="py-2 pr-4 align-middle text-sm leading-relaxed text-text-muted">
                        {w.satz ? satzMitHervorhebung(w.satz, w.wort) : "(kein Satzkontext gefunden)"}
                      </td>
                      <td className="w-64 py-2 align-middle">
                        <Input
                          placeholder="leer = behalten"
                          value={ersatzWerte[w.wort] ?? ""}
                          onChange={(e) => setErsatzWerte((bisher) => ({ ...bisher, [w.wort]: e.target.value }))}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Button onClick={ersetzenUndSpeichern} className="mt-2">
                Ersetzungen übernehmen &amp; speichern
              </Button>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}