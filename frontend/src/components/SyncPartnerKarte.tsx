import { useEffect, useState } from "react";
import { api } from "../api/client";
import { CollapsibleCard } from "./CollapsibleCard";
import { Button, Input, Label } from "./ui";

/** Einstellungen für den Projekt-Abgleich: Adresse und Zugang der
 * Gegenstelle (typisch am lokalen PC: der Produktiv-Server). Leer lassen,
 * wenn diese Instanz selbst die Gegenstelle ist (Server). */
export function SyncPartnerKarte() {
  const [url, setUrl] = useState("");
  const [benutzer, setBenutzer] = useState("");
  const [passwort, setPasswort] = useState("");
  const [passwortGesetzt, setPasswortGesetzt] = useState(false);
  const [beschaeftigt, setBeschaeftigt] = useState(false);
  const [meldung, setMeldung] = useState<{ text: string; fehler: boolean } | null>(null);

  useEffect(() => {
    api.syncPartner().then(
      (p) => {
        setUrl(p.url);
        setBenutzer(p.username);
        setPasswortGesetzt(p.passwort_gesetzt);
      },
      () => undefined,
    );
  }, []);

  async function ausfuehren(aktion: () => Promise<string>) {
    setBeschaeftigt(true);
    setMeldung(null);
    try {
      setMeldung({ text: await aktion(), fehler: false });
    } catch (e) {
      setMeldung({ text: e instanceof Error ? e.message : String(e), fehler: true });
    } finally {
      setBeschaeftigt(false);
    }
  }

  const speichern = () =>
    ausfuehren(async () => {
      const p = await api.syncPartnerSchreiben(url, benutzer, passwort ? passwort : null);
      setPasswort("");
      setPasswortGesetzt(p.passwort_gesetzt);
      return "Gespeichert.";
    });

  const testen = () =>
    ausfuehren(async () => {
      const r = await api.syncPartnerTesten();
      return `Verbindung steht – ${r.projekte} Projekt(e) auf der Gegenstelle.`;
    });

  const entfernen = () =>
    ausfuehren(async () => {
      await api.syncPartnerLoeschen();
      setUrl("");
      setBenutzer("");
      setPasswort("");
      setPasswortGesetzt(false);
      return "Gegenstelle entfernt.";
    });

  return (
    <CollapsibleCard title="🔄 Abgleich mit Server" defaultOffen={false}>
      <div className="space-y-3 p-4">
        <p className="text-sm text-text-muted">
          Projekte lassen sich zwischen diesem PC und dem Server hin- und herkopieren (Tab „Projekte" → „Abgleich
          mit Server"). Trage hier die Adresse des Servers und dein Login dort ein. Am Server selbst bleibt das
          leer. Das Passwort wird verschlüsselt gespeichert.
        </p>
        <div>
          <Label>Adresse der Gegenstelle</Label>
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://geschichten.daniel-ertl.de"
            autoComplete="off"
            disabled={beschaeftigt}
          />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <Label>Benutzername</Label>
            <Input
              value={benutzer}
              onChange={(e) => setBenutzer(e.target.value)}
              autoComplete="off"
              disabled={beschaeftigt}
            />
          </div>
          <div>
            <Label>Passwort</Label>
            <Input
              type="password"
              value={passwort}
              onChange={(e) => setPasswort(e.target.value)}
              placeholder={passwortGesetzt ? "(gespeichert – leer lassen zum Beibehalten)" : ""}
              autoComplete="new-password"
              disabled={beschaeftigt}
            />
          </div>
        </div>
        {meldung && <p className={`text-sm ${meldung.fehler ? "text-red-400" : "text-accent-light"}`}>{meldung.text}</p>}
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => void speichern()} disabled={beschaeftigt || !url.trim() || !benutzer.trim()}>
            Speichern
          </Button>
          <Button variant="secondary" onClick={() => void testen()} disabled={beschaeftigt || !url.trim()}>
            Verbindung testen
          </Button>
          <Button variant="secondary" onClick={() => void entfernen()} disabled={beschaeftigt || !url.trim()}>
            Entfernen
          </Button>
        </div>
      </div>
    </CollapsibleCard>
  );
}
