import Editor from "@monaco-editor/react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ProjektDetail } from "../api/types";
import { CollapsibleCard } from "../components/CollapsibleCard";
import { KapitelplanEditor } from "../components/KapitelplanEditor";
import { Badge, Button, Card, CardTitle } from "../components/ui";
import {
  geruestAusKapitelplanZusammenbauen,
  kapitelPflichtfelderPruefen,
  kapitelplanAusGeruestExtrahieren,
  leeresKapitel,
  type KapitelEintrag,
  type KapitelplanFehler,
} from "../utils/kapitelplan";

// Anzeige-Mapping der intern aus dem Gerüst erkannten Content-Stufe (siehe
// backend/app/core/rollen.py: STUFE_DIREKTIVEN) auf die aus Filmen bekannten
// FSK-Alterskennzeichen - "voll" klang vorher wie "Jugendschutz voll aktiv",
// war aber genau das Gegenteil (voll explizit, keine Einschraenkung).
const JUGENDSCHUTZ_ANZEIGE: Record<string, { label: string; tone: "green" | "amber" }> = {
  jugendfrei: { label: "FSK 0 · jugendfrei", tone: "green" },
  angedeutet: { label: "FSK 12 · angedeutet", tone: "green" },
  voll: { label: "FSK 18 · voll explizit", tone: "amber" },
};

/** Kopfzeile fuer einen der drei "Haupt-Container" INNERHALB des äußeren
 * "🗺️ geruest.md"-CollapsibleCard - bewusst kein verschachteltes
 * CollapsibleCard (das wuerde eine zweite Card-Umrandung ineinander
 * schachteln), sondern derselbe Titel+Toggle-Aufbau, nur ohne eigene
 * Card-Border. */
function AbschnittKopf({ titel, offen, onToggle }: { titel: string; offen: boolean; onToggle: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 pt-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">{titel}</h3>
      <button type="button" onClick={onToggle} className="text-xs text-accent-light hover:underline">
        {offen ? "Einklappen" : "Ausklappen"}
      </button>
    </div>
  );
}

interface GeruestPageProps {
  ordner: string;
  projekt: ProjektDetail | null;
  onGeaendert: () => void;
  onOrdnerUmbenannt: (neuerOrdner: string) => void;
  onInterviewStarten: () => void;
}

/** Rohtext-Ansicht von geruest.md, fuer die manuelle Nachjustierung NACH dem
 * Architekten-Interview (siehe ArchitektInterviewPage - das ist der
 * eigentliche Weg, ein Gerüst zu erzeugen). Die Feldererkennung (Jahr,
 * Jugendschutz-Stufe, Autor-Modell, Kapitelplan, ...) laeuft serverseitig
 * exakt wie im CLI (siehe backend/app/core/geruest.py) und wird hier zur
 * Kontrolle angezeigt. Verbotsliste (fuer die Anachronismus-Pruefung)
 * liegt gleich daneben, da beide Dateien zusammen das Setting definieren. */
export function GeruestPage({ ordner, projekt, onGeaendert, onOrdnerUmbenannt, onInterviewStarten }: GeruestPageProps) {
  // Kapitelplan strukturiert (KapitelplanEditor), Rest des Gerüsts bleibt
  // Freitext in zwei Editoren links/rechts davon (siehe utils/kapitelplan.ts
  // fuer die Begruendung, warum nur der Kapitelplan formalisiert wird).
  const [vor, setVor] = useState("");
  const [kapitel, setKapitel] = useState<KapitelEintrag[]>([]);
  const [nach, setNach] = useState("");
  const [kapitelplanWarnung, setKapitelplanWarnung] = useState<string | null>(null);
  const [kapitelFehler, setKapitelFehler] = useState<KapitelplanFehler[]>([]);
  const [wirdGespeichert, setWirdGespeichert] = useState(false);
  const [gespeichertHinweis, setGespeichertHinweis] = useState<string | null>(null);
  const [geruestFehler, setGeruestFehler] = useState<string | null>(null);

  const [verbotslisteInhalt, setVerbotslisteInhalt] = useState(projekt?.verbotsliste ?? "");
  const [verbotslisteWirdGespeichert, setVerbotslisteWirdGespeichert] = useState(false);
  const [verbotslisteHinweis, setVerbotslisteHinweis] = useState<string | null>(null);

  const [stilprobenInhalt, setStilprobenInhalt] = useState(projekt?.stilproben ?? "");
  const [stilprobenWirdGespeichert, setStilprobenWirdGespeichert] = useState(false);
  const [stilprobenHinweis, setStilprobenHinweis] = useState<string | null>(null);

  const [architektenGespraech, setArchitektenGespraech] = useState<string | null>(null);

  // Einklappzustand der drei "Haupt-Container" innerhalb des geruest.md-
  // Editors (siehe ToDo.md: mehr Platz fuer den Block, an dem gerade
  // gearbeitet wird) - unabhaengig vom aeusseren "🗺️ geruest.md"-
  // CollapsibleCard und unabhaengig voneinander. Default offen, damit sich
  // fuer bestehende Nutzung nichts aendert, solange niemand aktiv einklappt.
  const [rahmenOffen, setRahmenOffen] = useState(true);
  const [kapitelplanOffen, setKapitelplanOffen] = useState(true);
  const [ausgangslageOffen, setAusgangslageOffen] = useState(true);

  useEffect(() => {
    const geteilt = kapitelplanAusGeruestExtrahieren(projekt?.geruest ?? "");
    setVor(geteilt.vor);
    // Ein Gerüst, das WIRKLICH noch keinen Kapitelplan hat (kein "kann nicht
    // geparst werden"-Fall, siehe warnung-Kommentar in kapitelplan.ts), zeigt
    // sofort ein erstes leeres Kapitel zum Ausfuellen statt der bisherigen
    // "Noch kein Kapitelplan"-Leermeldung - erspart den Klick auf "+ Kapitel"
    // bei jedem neu angelegten Projekt (z.B. frisch ueber "Gerüst selbst
    // schreiben" angelegt, siehe ProjektePage.tsx:anlegen). Rein lokaler
    // Editor-Zustand, wird erst beim Speichern validiert/persistiert - siehe
    // geruestVorlage.ts, warum das Startkapitel nicht schon im initial
    // gespeicherten Skelett steckt.
    setKapitel(geteilt.kapitel.length === 0 && !geteilt.warnung ? [leeresKapitel()] : geteilt.kapitel);
    setNach(geteilt.nach);
    setKapitelplanWarnung(geteilt.warnung);
    setKapitelFehler([]);
    setVerbotslisteInhalt(projekt?.verbotsliste ?? "");
    setStilprobenInhalt(projekt?.stilproben ?? "");
    setArchitektenGespraech(null);
    api
      .architektenGespraech(ordner)
      .then(setArchitektenGespraech)
      .catch(() => setArchitektenGespraech(null));
  }, [projekt?.geruest, projekt?.verbotsliste, projekt?.stilproben, ordner]);

  async function speichern() {
    setGespeichertHinweis(null);
    setGeruestFehler(null);

    // Pflichtfeld-Pruefung ZUERST, komplett ohne Server-Roundtrip - der
    // eigentliche Punkt von Schritt 2 (siehe utils/kapitelplan.ts). Die
    // serverseitige Pruefung (kapitelplan_pruefen()) bleibt trotzdem als
    // zweite Verteidigungslinie bestehen, siehe geruest_schreiben().
    const pflichtfeldFehler = kapitelPflichtfelderPruefen(kapitel);
    setKapitelFehler(pflichtfeldFehler);
    if (pflichtfeldFehler.length > 0) {
      setGeruestFehler(
        `Kapitelplan unvollständig:\n${pflichtfeldFehler.map((f) => f.meldung).join("\n")}`,
      );
      return;
    }

    setWirdGespeichert(true);
    try {
      const inhalt = geruestAusKapitelplanZusammenbauen(vor, kapitel, nach);
      const antwort = await api.geruestSchreiben(ordner, inhalt);
      const zusatz = antwort.stand_00_aktualisiert ? " Ausgangslage vor Kapitel eins (stand_00.md) synchronisiert." : "";
      if (antwort.neuer_ordner) {
        onOrdnerUmbenannt(antwort.neuer_ordner);
        setGespeichertHinweis(`Gespeichert - Ordner umbenannt in "${antwort.neuer_ordner}".${zusatz}`);
      } else {
        onGeaendert();
        setGespeichertHinweis(`Gespeichert.${zusatz}`);
      }
    } catch (e) {
      // Ueblicherweise die 400-Antwort von geruest_schreiben() bei einem
      // unvollstaendigen Kapitelplan (fehlende Zielwortzahl, doppelte
      // Kapitelnummer, siehe app/core/geruest.py:kapitelplan_pruefen) - der
      // alte Speicherstand bleibt dabei serverseitig unangetastet.
      setGeruestFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setWirdGespeichert(false);
    }
  }

  async function verbotslisteSpeichern() {
    setVerbotslisteWirdGespeichert(true);
    setVerbotslisteHinweis(null);
    try {
      await api.verbotslisteSchreiben(ordner, verbotslisteInhalt);
      onGeaendert();
      setVerbotslisteHinweis("Gespeichert.");
    } finally {
      setVerbotslisteWirdGespeichert(false);
    }
  }

  async function stilprobenSpeichern() {
    setStilprobenWirdGespeichert(true);
    setStilprobenHinweis(null);
    try {
      await api.stilprobenSchreiben(ordner, stilprobenInhalt);
      onGeaendert();
      setStilprobenHinweis("Gespeichert.");
    } finally {
      setStilprobenWirdGespeichert(false);
    }
  }

  return (
    <div className="grid grid-cols-1 items-start gap-6 p-4 sm:p-6 lg:grid-cols-[2fr_1fr]">
      <CollapsibleCard
        title="🗺️ geruest.md"
        aktionen={
          <>
            {gespeichertHinweis && <span className="text-xs text-accent-light">{gespeichertHinweis}</span>}
            <Button variant="secondary" onClick={onInterviewStarten}>
              Interview neu führen
            </Button>
            <Button onClick={speichern} disabled={wirdGespeichert}>
              {wirdGespeichert ? "Speichert..." : "Speichern"}
            </Button>
          </>
        }
      >
        {geruestFehler && (
          <p className="whitespace-pre-line border-b border-border bg-red-400/10 px-4 py-3 text-sm text-red-400">
            {geruestFehler}
          </p>
        )}

        <div className="border-b border-border">
          <AbschnittKopf
            titel="Rahmen, Titel, Figuren, Konflikt, Nebenstrang"
            offen={rahmenOffen}
            onToggle={() => setRahmenOffen((o) => !o)}
          />
          {rahmenOffen && (
            <div className="p-4 pt-2">
              <Editor
                height="clamp(200px, 32vh, 360px)"
                defaultLanguage="markdown"
                value={vor}
                onChange={(v) => setVor(v ?? "")}
                theme="vs-dark"
                options={{ wordWrap: "on", minimap: { enabled: false }, fontSize: 14 }}
              />
            </div>
          )}
        </div>

        <div className="border-b border-border">
          <AbschnittKopf titel="Kapitelplan" offen={kapitelplanOffen} onToggle={() => setKapitelplanOffen((o) => !o)} />
          {kapitelplanOffen && (
            <>
              {kapitelplanWarnung && (
                <p className="mx-4 mt-2 rounded-lg border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-xs text-amber-300">
                  ⚠️ {kapitelplanWarnung}
                </p>
              )}
              <KapitelplanEditor
                kapitel={kapitel}
                onChange={(neu) => {
                  // Jede Aenderung (auch Verschieben/Loeschen) macht die zuletzt
                  // berechneten Pflichtfeld-Fehler potenziell falsch - Index N
                  // zeigt nach einer Verschiebung auf ein ANDERES Kapitel als
                  // beim letzten Speicherversuch. Erst der naechste Speichern-
                  // Klick berechnet sie neu; bis dahin lieber keine (evtl.
                  // falsch zugeordnete) rote Markierung stehen lassen.
                  setKapitel(neu);
                  setKapitelFehler([]);
                }}
                fehler={kapitelFehler}
              />
            </>
          )}
        </div>

        <div>
          <AbschnittKopf
            titel="Ausgangslage vor Kapitel eins, Offene Punkte, Regeln"
            offen={ausgangslageOffen}
            onToggle={() => setAusgangslageOffen((o) => !o)}
          />
          {ausgangslageOffen && (
            <div className="p-4 pt-2">
              <Editor
                height="clamp(200px, 32vh, 360px)"
                defaultLanguage="markdown"
                value={nach}
                onChange={(v) => setNach(v ?? "")}
                theme="vs-dark"
                options={{ wordWrap: "on", minimap: { enabled: false }, fontSize: 14 }}
              />
            </div>
          )}
        </div>
      </CollapsibleCard>

      <div className="space-y-6">
        <Card>
          <CardTitle>Erkannte Felder</CardTitle>
          <dl className="space-y-2.5 text-sm">
            <div className="flex items-center justify-between">
              <dt className="text-text-muted">Jahr</dt>
              <dd>{projekt?.jahr ?? "–"}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-text-muted">Content-Stufe</dt>
              <dd>
                {projekt?.jugendschutz_stufe && JUGENDSCHUTZ_ANZEIGE[projekt.jugendschutz_stufe] ? (
                  <Badge tone={JUGENDSCHUTZ_ANZEIGE[projekt.jugendschutz_stufe].tone}>
                    {JUGENDSCHUTZ_ANZEIGE[projekt.jugendschutz_stufe].label}
                  </Badge>
                ) : (
                  <Badge>–</Badge>
                )}
              </dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-text-muted">Autor-Modell</dt>
              <dd>{projekt?.autor_modell ?? "–"}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-text-muted">Automatische Fortsetzung</dt>
              <dd>
                <Badge tone={projekt?.automatische_fortsetzung ? "amber" : "green"}>
                  {projekt?.automatische_fortsetzung ? "Ein" : "Aus"}
                </Badge>
              </dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-text-muted">Letztes geplantes Kapitel</dt>
              <dd>{projekt?.letztes_geplantes_kapitel ?? "–"}</dd>
            </div>
          </dl>

          {projekt && Object.keys(projekt.kapitelplan).length > 0 && (
            <>
              <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-text-muted">
                Kapitelplan (Zielwortzahl)
              </h3>
              <ul className="space-y-1 text-sm">
                {Object.entries(projekt.kapitelplan)
                  .sort(([a], [b]) => Number(a) - Number(b))
                  .map(([n, ziel]) => (
                    <li key={n} className="flex justify-between">
                      <span>Kapitel {n}</span>
                      <span className="text-text-muted">{ziel} Woerter</span>
                    </li>
                  ))}
              </ul>
            </>
          )}
        </Card>

        <CollapsibleCard
          title="🚫 verbotsliste.md"
          aktionen={
            <>
              {verbotslisteHinweis && <span className="text-xs text-accent-light">{verbotslisteHinweis}</span>}
              <Button onClick={verbotslisteSpeichern} disabled={verbotslisteWirdGespeichert}>
                {verbotslisteWirdGespeichert ? "Speichert..." : "Speichern"}
              </Button>
            </>
          }
        >
          <Editor
            height="clamp(220px, 40vh, 320px)"
            defaultLanguage="markdown"
            value={verbotslisteInhalt}
            onChange={(v) => setVerbotslisteInhalt(v ?? "")}
            theme="vs-dark"
            options={{ wordWrap: "on", minimap: { enabled: false }, fontSize: 13 }}
          />
        </CollapsibleCard>

        <CollapsibleCard
          title="✍️ stilproben.md"
          defaultOffen={false}
          aktionen={
            <>
              {stilprobenHinweis && <span className="text-xs text-accent-light">{stilprobenHinweis}</span>}
              <Button onClick={stilprobenSpeichern} disabled={stilprobenWirdGespeichert}>
                {stilprobenWirdGespeichert ? "Speichert..." : "Speichern"}
              </Button>
            </>
          }
        >
          <p className="mb-3 text-sm text-text-muted">
            Optional: ein bis drei kurze Ausschnitte (je etwa 100 bis 300 Wörter) aus Geschichten, deren Sprache,
            Satzrhythmus und Ton dir gefallen haben. Der Autor orientiert sich beim Schreiben daran, übernimmt aber
            NICHT die Handlung, Namen oder Figuren daraus. Leer lassen hat keinen Effekt.
          </p>
          <Editor
            height="clamp(220px, 40vh, 320px)"
            defaultLanguage="markdown"
            value={stilprobenInhalt}
            onChange={(v) => setStilprobenInhalt(v ?? "")}
            theme="vs-dark"
            options={{ wordWrap: "on", minimap: { enabled: false }, fontSize: 13 }}
          />
        </CollapsibleCard>

        {architektenGespraech && (
          <CollapsibleCard title="📜 Architekten-Gespräch" defaultOffen={false}>
            <pre className="max-h-[400px] overflow-auto whitespace-pre-wrap p-4 text-sm text-text">
              {architektenGespraech}
            </pre>
          </CollapsibleCard>
        )}
      </div>
    </div>
  );
}
