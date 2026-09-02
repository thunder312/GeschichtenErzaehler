import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { AutomatikStatus, Befund, ProjektDetail } from "../api/types";
import { KATEGORIE_CHIP, KATEGORIE_LABEL } from "../components/BefundListe";
import { Button, Card, CardTitle, Textarea } from "../components/ui";
import { useAktivitaet } from "../context/AktivitaetContext";
import { automatikAktionsText } from "../utils/automatik";

interface MobilPageProps {
  ordner: string;
  projekt: ProjektDetail | null;
  sshZielId: string;
  onGeaendert: () => void;
}

interface OffenerFund {
  kapitel: number;
  befund: Befund;
}

/** Schlanke Ansicht fuer schmale (Handy-)Bildschirmbreiten - ersetzt dort die
 * volle Tab-Navigation (siehe App.tsx: "md:hidden"-Zweig), weil fuer aktives
 * Schreiben oder den Volltext-Editor aus "Prüfen & Anwenden" (Monaco) auf
 * einem Handy schlicht zu wenig Platz ist. Fokus liegt stattdessen auf:
 * 1) den laufenden Automatikmodus ueberwachen (derselbe Status wie im
 *    Schreiben-Tab, per Polling), 2) Pruefer-Vorschlaege ueber alle bereits
 *    geschriebenen Kapitel hinweg mit einem Antippen uebernehmen/ablehnen,
 *    optional vorher leicht abaendern, 3) eine kleine Handkorrektur direkt im
 *    aktuellen Kapiteltext (einfaches Textfeld statt Monaco).
 *
 * Uebernehmen laeuft NICHT ueber den Monaco-Editor (der existiert hier gar
 * nicht), sondern ueber den dedizierten Server-Endpunkt POST .../befunde/
 * {n}/uebernehmen (siehe app/api/projects.py:befund_uebernehmen) - der
 * spleisst den Vorschlag serverseitig in die Kapiteldatei und verankert die
 * uebrigen offenen Funde neu. */
export function MobilPage({ ordner, projekt, sshZielId, onGeaendert }: MobilPageProps) {
  const { starten: aktivitaetStarten, beenden: aktivitaetBeenden } = useAktivitaet();
  const automatikAktivitaetTextRef = useRef<string | null>(null);

  const [automatikStatus, setAutomatikStatus] = useState<AutomatikStatus | null>(null);
  const [automatikFehler, setAutomatikFehler] = useState<string | null>(null);

  const [funde, setFunde] = useState<OffenerFund[]>([]);
  const [fundeLaden, setFundeLaden] = useState(false);
  const [fundeFehler, setFundeFehler] = useState<string | null>(null);
  const [veralteteKapitel, setVeralteteKapitel] = useState<number[]>([]);
  const [pruefenLaeuftKapitel, setPruefenLaeuftKapitel] = useState<Set<number>>(new Set());
  const [bearbeiteId, setBearbeiteId] = useState<string | null>(null);
  const [bearbeiteText, setBearbeiteText] = useState("");
  const [aktionLaeuftId, setAktionLaeuftId] = useState<string | null>(null);

  const geschriebeneKapitel = projekt?.kapitel ?? [];
  const [kapitelNummer, setKapitelNummer] = useState<number | null>(null);
  const [kapitelText, setKapitelText] = useState("");
  const [kapitelGeladenFuer, setKapitelGeladenFuer] = useState<number | null>(null);
  const [kapitelSpeichern, setKapitelSpeichern] = useState(false);
  const [kapitelFehler, setKapitelFehler] = useState<string | null>(null);
  const [kapitelGespeichert, setKapitelGespeichert] = useState(false);

  // Automatik-Status pollen, solange dieser Screen offen ist - derselbe
  // Hintergrund-Job wie im Schreiben-Tab (SchreibenPage.tsx), nur ohne die
  // dort zusaetzlich vorhandene interaktive WebSocket-Steuerung.
  useEffect(() => {
    let abgebrochen = false;
    function laden() {
      api
        .automatikStatus(ordner)
        .then((status) => {
          if (abgebrochen) return;
          setAutomatikStatus(status);
          if (status.laeuft) {
            const text = automatikAktionsText(status);
            if (automatikAktivitaetTextRef.current !== text) {
              automatikAktivitaetTextRef.current = text;
              aktivitaetStarten(text);
            }
          } else if (automatikAktivitaetTextRef.current !== null) {
            automatikAktivitaetTextRef.current = null;
            aktivitaetBeenden();
          }
        })
        .catch(() => {});
    }
    laden();
    const intervall = setInterval(laden, 4000);
    return () => {
      abgebrochen = true;
      clearInterval(intervall);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ordner]);

  // Offene Funde ueber ALLE bereits geschriebenen Kapitel hinweg laden -
  // jedes 404 (noch nie geprueft) wird stillschweigend uebersprungen, kein
  // Fehlerfall.
  //
  // "veraltet" (siehe befunde_lesen() in app/api/projects.py: Hash-Vergleich
  // gegen den AKTUELLEN Kapiteltext) wird hier bewusst ausgewertet, statt die
  // Funde einfach anzuzeigen: Wird ein Fund am DESKTOP im Tab "Prüfen &
  // Anwenden" übernommen, merkt sich das nur der Monaco-Editor im Browser-Tab
  // - die gespeicherte befunde_NN.json wird dabei NIE aktualisiert. Ein
  // zweites, unabhaengiges Geraet (Handy) haette sonst weiterhin die alte,
  // laengst erledigte Liste angezeigt (Live-Fund 2026-09-02: "Handy zeigt
  // offene Punkte, PC-Browser nicht" - beide Ansichten waren technisch
  // korrekt, nur eine kannte den Desktop-Fortschritt nicht). Veraltete
  // Kapitel werden deshalb NICHT in der Funde-Liste angezeigt (koennten
  // laengst erledigt sein), sondern separat mit einer "Jetzt erneut
  // prüfen"-Option markiert.
  const kapitelSchluessel = geschriebeneKapitel.join(",");
  async function fundeLadenAusfuehren() {
    setFundeLaden(true);
    setFundeFehler(null);
    try {
      const ergebnisse = await Promise.all(
        geschriebeneKapitel.map((n) =>
          api
            .befunde(ordner, n)
            .then((antwort) => ({
              kapitel: n,
              veraltet: antwort.veraltet,
              funde: antwort.befunde.map((befund) => ({ kapitel: n, befund })),
            }))
            .catch(() => null),
        ),
      );
      const gueltig = ergebnisse.filter((e): e is NonNullable<typeof e> => e !== null);
      setFunde(gueltig.filter((e) => !e.veraltet).flatMap((e) => e.funde));
      setVeralteteKapitel(gueltig.filter((e) => e.veraltet).map((e) => e.kapitel));
    } catch (e) {
      setFundeFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setFundeLaden(false);
    }
  }
  useEffect(() => {
    fundeLadenAusfuehren();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ordner, kapitelSchluessel]);

  async function kapitelErneutPruefen(n: number) {
    setPruefenLaeuftKapitel((bisher) => new Set(bisher).add(n));
    setFundeFehler(null);
    try {
      await api.pruefen(ordner, n, sshZielId || null);
      await fundeLadenAusfuehren();
    } catch (e) {
      setFundeFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setPruefenLaeuftKapitel((bisher) => {
        const kopie = new Set(bisher);
        kopie.delete(n);
        return kopie;
      });
    }
  }

  // Kapitelnummer fuer "kleine Verbesserungen" vorbelegen: das zuletzt
  // geschriebene Kapitel, sobald die Liste erstmals bekannt ist - danach
  // nicht mehr automatisch eingreifen, damit eine manuelle Auswahl bestehen
  // bleibt.
  const vorbelegtRef = useRef(false);
  useEffect(() => {
    if (vorbelegtRef.current || geschriebeneKapitel.length === 0) return;
    vorbelegtRef.current = true;
    setKapitelNummer(Math.max(...geschriebeneKapitel));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kapitelSchluessel]);

  useEffect(() => {
    if (kapitelNummer == null || kapitelGeladenFuer === kapitelNummer) return;
    let abgebrochen = false;
    setKapitelFehler(null);
    api
      .kapitel(ordner, kapitelNummer)
      .then((text) => {
        if (abgebrochen) return;
        setKapitelText(text);
        setKapitelGeladenFuer(kapitelNummer);
      })
      .catch((e) => {
        if (abgebrochen) return;
        setKapitelFehler(e instanceof Error ? e.message : String(e));
      });
    return () => {
      abgebrochen = true;
    };
  }, [ordner, kapitelNummer, kapitelGeladenFuer]);

  async function automatikStarten(fortsetzen: boolean) {
    setAutomatikFehler(null);
    try {
      await api.automatikStarten(ordner, 3, sshZielId || null, fortsetzen);
      setAutomatikStatus(await api.automatikStatus(ordner));
    } catch (e) {
      setAutomatikFehler(e instanceof Error ? e.message : String(e));
    }
  }

  async function automatikStoppen() {
    try {
      await api.automatikStoppen(ordner);
      setAutomatikStatus(await api.automatikStatus(ordner));
    } catch (e) {
      setAutomatikFehler(e instanceof Error ? e.message : String(e));
    }
  }

  async function fundUebernehmen(fund: OffenerFund, vorschlagOverride?: string) {
    setAktionLaeuftId(fund.befund.id);
    setFundeFehler(null);
    try {
      await api.befundUebernehmen(ordner, fund.kapitel, fund.befund.id, vorschlagOverride);
      setBearbeiteId(null);
      await fundeLadenAusfuehren();
      if (kapitelGeladenFuer === fund.kapitel) setKapitelGeladenFuer(null); // im Editor-Feld unten neu laden
      onGeaendert();
    } catch (e) {
      setFundeFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setAktionLaeuftId(null);
    }
  }

  async function fundAblehnen(fund: OffenerFund) {
    setAktionLaeuftId(fund.befund.id);
    setFundeFehler(null);
    try {
      await api.befundAblehnen(ordner, fund.kapitel, fund.befund.id);
      await fundeLadenAusfuehren();
    } catch (e) {
      setFundeFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setAktionLaeuftId(null);
    }
  }

  async function kapitelSpeichernAusfuehren() {
    if (kapitelNummer == null) return;
    setKapitelSpeichern(true);
    setKapitelFehler(null);
    setKapitelGespeichert(false);
    try {
      await api.kapitelSchreiben(ordner, kapitelNummer, kapitelText);
      setKapitelGespeichert(true);
      // Ein manueller Textwechsel kann Fund-Positionen verschieben - Liste
      // sicherheitshalber neu laden (Server erkennt "veraltet" ueber den
      // Hash, siehe befunde_lesen()).
      fundeLadenAusfuehren();
    } catch (e) {
      setKapitelFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setKapitelSpeichern(false);
    }
  }

  if (!projekt) {
    return (
      <div className="p-4">
        <p className="text-sm text-text-muted">Lädt...</p>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4">
      <Card>
        <CardTitle>🤖 Automatikmodus</CardTitle>
        {automatikStatus?.laeuft ? (
          <div className="space-y-2">
            <p className="text-sm text-text">
              Phase: <strong>{automatikStatus.phase}</strong>
              {automatikStatus.aktuelles_kapitel != null && (
                <>
                  {" "}
                  · Kapitel {automatikStatus.aktuelles_kapitel}
                  {automatikStatus.gesamt_kapitel != null && <>/{automatikStatus.gesamt_kapitel}</>}
                </>
              )}
              {automatikStatus.aktueller_durchlauf != null && <> · Durchlauf {automatikStatus.aktueller_durchlauf}</>}
            </p>
            <div className="max-h-32 overflow-auto rounded-lg bg-bg p-2 font-mono text-xs text-text-muted">
              {automatikStatus.log.slice(-8).map((zeile, i) => (
                <div key={i}>{zeile}</div>
              ))}
            </div>
            <Button variant="danger" onClick={automatikStoppen} disabled={automatikStatus.stop_angefordert}>
              {automatikStatus.stop_angefordert ? "Wird gestoppt..." : "Stoppen"}
            </Button>
          </div>
        ) : (
          <div className="space-y-2">
            {automatikStatus?.abgeschlossen && (
              <p className="text-sm text-text-muted">Letzter Lauf abgeschlossen.</p>
            )}
            {automatikStatus?.fehler && <p className="text-sm text-red-400">Fehler: {automatikStatus.fehler}</p>}
            <div className="flex flex-wrap gap-2">
              {automatikStatus?.fortsetzbar && (
                <Button onClick={() => automatikStarten(true)}>Fortsetzen</Button>
              )}
              <Button
                variant={automatikStatus?.fortsetzbar ? "secondary" : "primary"}
                onClick={() => automatikStarten(false)}
              >
                Automatikmodus starten
              </Button>
            </div>
          </div>
        )}
        {automatikFehler && <p className="mt-2 text-sm text-red-400">{automatikFehler}</p>}
      </Card>

      <Card>
        <div className="mb-3 flex items-center justify-between">
          <CardTitle className="mb-0">🔍 Offene Prüfer-Funde</CardTitle>
          <button
            onClick={fundeLadenAusfuehren}
            disabled={fundeLaden}
            className="text-xs text-accent-light hover:underline disabled:opacity-50"
          >
            {fundeLaden ? "Lädt..." : "Neu laden"}
          </button>
        </div>
        {fundeFehler && <p className="mb-2 text-sm text-red-400">{fundeFehler}</p>}
        {veralteteKapitel.length > 0 && (
          <div className="mb-3 space-y-1.5 rounded-lg border border-amber-400/40 bg-amber-400/10 p-2">
            <p className="text-xs text-amber-200">
              ⚠ {veralteteKapitel.length === 1 ? "Kapitel wurde" : "Diese Kapitel wurden"} seit der letzten Prüfung
              verändert (z.B. am Desktop bearbeitet) - die dortige Funde-Liste könnte veraltet sein und wird deshalb
              hier nicht angezeigt.
            </p>
            <div className="flex flex-wrap gap-2">
              {veralteteKapitel.map((n) => (
                <Button
                  key={n}
                  variant="secondary"
                  className="!px-3 !py-1 text-xs"
                  disabled={pruefenLaeuftKapitel.has(n)}
                  onClick={() => kapitelErneutPruefen(n)}
                >
                  {pruefenLaeuftKapitel.has(n) ? "Prüft..." : `Kapitel ${n} jetzt erneut prüfen`}
                </Button>
              ))}
            </div>
          </div>
        )}
        {funde.length === 0 ? (
          <p className="text-sm text-text-muted">
            {fundeLaden ? "Lädt..." : "Keine offenen Funde."}
          </p>
        ) : (
          <ul className="space-y-2">
            {funde.map((fund) => {
              const { befund, kapitel } = fund;
              const laeuft = aktionLaeuftId === befund.id;
              const bearbeitetGerade = bearbeiteId === befund.id;
              const kannUebernehmen = befund.gefunden && !befund.konflikt;
              return (
                <li key={`${kapitel}-${befund.id}`} className="rounded-lg border border-border bg-surface px-3 py-2 text-sm">
                  <div className="mb-1 flex flex-wrap items-center gap-1.5">
                    <span className="rounded-full border border-border px-2 py-0.5 text-xs font-medium text-text-muted">
                      Kapitel {kapitel}
                    </span>
                    {befund.kategorien.map((k) => (
                      <span key={k} className={`rounded-full border px-2 py-0.5 text-xs font-medium ${KATEGORIE_CHIP[k]}`}>
                        {KATEGORIE_LABEL[k]}
                      </span>
                    ))}
                    {befund.konflikt && (
                      <span className="rounded-full border border-red-400/40 bg-red-400/15 px-2 py-0.5 text-xs font-medium text-red-200">
                        Konflikt - nur am Desktop lösbar
                      </span>
                    )}
                    {!befund.gefunden && (
                      <span className="rounded-full border border-border px-2 py-0.5 text-xs text-text-muted">
                        Stelle nicht gefunden
                      </span>
                    )}
                  </div>
                  <p className="mb-1 text-xs">
                    <span className="text-text-muted">Stelle:</span>{" "}
                    <span className="font-mono text-text-muted">„{befund.fundstelle}"</span>
                  </p>
                  {befund.beschreibungen.map((b, i) => (
                    <p key={i} className="text-text">
                      {b.text}
                    </p>
                  ))}
                  {befund.vorschlag && !bearbeitetGerade && (
                    <p className="mt-1 text-xs">
                      <span className="text-text-muted">Vorschlag:</span> „{befund.vorschlag}"
                    </p>
                  )}
                  {bearbeitetGerade && (
                    <Textarea
                      className="mt-1"
                      rows={3}
                      value={bearbeiteText}
                      onChange={(e) => setBearbeiteText(e.target.value)}
                    />
                  )}
                  {kannUebernehmen && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {bearbeitetGerade ? (
                        <>
                          <Button
                            variant="primary"
                            className="!px-3 !py-1 text-xs"
                            disabled={laeuft || !bearbeiteText.trim()}
                            onClick={() => fundUebernehmen(fund, bearbeiteText)}
                          >
                            {laeuft ? "..." : "Geändert übernehmen"}
                          </Button>
                          <Button
                            variant="secondary"
                            className="!px-3 !py-1 text-xs"
                            onClick={() => setBearbeiteId(null)}
                          >
                            Abbrechen
                          </Button>
                        </>
                      ) : (
                        <>
                          {befund.vorschlag && (
                            <Button
                              variant="primary"
                              className="!px-3 !py-1 text-xs"
                              disabled={laeuft}
                              onClick={() => fundUebernehmen(fund)}
                            >
                              {laeuft ? "..." : "Übernehmen"}
                            </Button>
                          )}
                          <Button
                            variant="secondary"
                            className="!px-3 !py-1 text-xs"
                            disabled={laeuft}
                            onClick={() => {
                              setBearbeiteId(befund.id);
                              setBearbeiteText(befund.vorschlag ?? "");
                            }}
                          >
                            Abändern
                          </Button>
                        </>
                      )}
                      <Button
                        variant="secondary"
                        className="!px-3 !py-1 text-xs"
                        disabled={laeuft}
                        onClick={() => fundAblehnen(fund)}
                      >
                        Ablehnen
                      </Button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Card>
        <CardTitle>✏️ Kleine Verbesserung im Kapiteltext</CardTitle>
        <p className="mb-2 text-xs text-text-muted">
          Einfaches Textfeld ohne Editor-Komfort - für größere Überarbeitungen besser am Desktop im Tab
          "Prüfen &amp; Anwenden" arbeiten.
        </p>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <label className="text-xs text-text-muted">Kapitel:</label>
          <select
            value={kapitelNummer ?? ""}
            onChange={(e) => setKapitelNummer(Number(e.target.value))}
            className="rounded-lg border border-border bg-bg px-2 py-1 text-sm text-text"
          >
            {geschriebeneKapitel.map((n) => (
              <option key={n} value={n}>
                Kapitel {n}
              </option>
            ))}
          </select>
          {automatikStatus?.laeuft && automatikStatus.aktuelles_kapitel === kapitelNummer && (
            <span className="text-xs text-amber-300">⚠ Automatikmodus bearbeitet dieses Kapitel gerade</span>
          )}
        </div>
        {kapitelFehler && <p className="mb-2 text-sm text-red-400">{kapitelFehler}</p>}
        {kapitelNummer != null && (
          <>
            <Textarea rows={10} value={kapitelText} onChange={(e) => setKapitelText(e.target.value)} />
            <div className="mt-2 flex items-center gap-2">
              <Button onClick={kapitelSpeichernAusfuehren} disabled={kapitelSpeichern}>
                {kapitelSpeichern ? "Speichert..." : "Speichern"}
              </Button>
              {kapitelGespeichert && <span className="text-xs text-accent-light">Gespeichert.</span>}
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
