import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { BenutzerEintrag } from "../api/types";
import { useAuth } from "../context/AuthContext";
import { Badge, Button, Card, CardTitle, Input, Label } from "../components/ui";

const LEERES_FORMULAR = { username: "", password: "", passwortWiederholung: "", ist_admin: false };

export function BenutzerPage() {
  const { benutzer: angemeldeter } = useAuth();
  const [benutzerListe, setBenutzerListe] = useState<BenutzerEintrag[]>([]);
  const [formular, setFormular] = useState(LEERES_FORMULAR);
  const [ladenListe, setLadenListe] = useState(true);
  const [ladenAnlegen, setLadenAnlegen] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  const listeLaden = useCallback(() => {
    setLadenListe(true);
    api
      .benutzerListe()
      .then(setBenutzerListe)
      .finally(() => setLadenListe(false));
  }, []);

  useEffect(() => {
    listeLaden();
  }, [listeLaden]);

  function feld<K extends keyof typeof LEERES_FORMULAR>(name: K, wert: (typeof LEERES_FORMULAR)[K]) {
    setFormular((bisher) => ({ ...bisher, [name]: wert }));
  }

  const formularGueltig =
    formular.username.trim() !== "" &&
    formular.password.length >= 8 &&
    formular.password === formular.passwortWiederholung;

  async function anlegen() {
    setLadenAnlegen(true);
    setFehler(null);
    try {
      await api.benutzerAnlegen({
        username: formular.username.trim(),
        password: formular.password,
        ist_admin: formular.ist_admin,
      });
      setFormular(LEERES_FORMULAR);
      listeLaden();
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLadenAnlegen(false);
    }
  }

  async function loeschen(b: BenutzerEintrag) {
    if (
      !window.confirm(
        `Benutzer "${b.username}" wirklich löschen? Bereits vorhandene Geschichten/Projekte werden zu "${angemeldeter?.username}" verschoben.`,
      )
    ) {
      return;
    }
    try {
      await api.benutzerLoeschen(b.id);
      listeLaden();
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 p-6 lg:grid-cols-[1.3fr_1fr]">
      <Card>
        <CardTitle>👤 Benutzer</CardTitle>
        {ladenListe ? (
          <p className="text-sm text-text-muted">Lädt...</p>
        ) : (
          <ul className="divide-y divide-border">
            {benutzerListe.map((b) => (
              <li key={b.id} className="flex items-center justify-between py-2.5">
                <div>
                  <div className="text-sm font-medium text-text">{b.username}</div>
                  <div className="text-xs text-text-muted">
                    {b.ist_admin ? <Badge tone="green">Admin</Badge> : <Badge>Benutzer</Badge>}
                  </div>
                </div>
                <Button
                  variant="danger"
                  onClick={() => loeschen(b)}
                  disabled={b.id === angemeldeter?.id}
                  title={b.id === angemeldeter?.id ? "Der eigene Account kann nicht gelöscht werden." : undefined}
                >
                  Löschen
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <h2 className="font-heading mb-3 text-lg font-semibold tracking-wide text-text">Neuer Benutzer</h2>
        <div className="space-y-3">
          <div>
            <Label>Benutzername</Label>
            <Input value={formular.username} onChange={(e) => feld("username", e.target.value)} />
          </div>
          <div>
            <Label>Passwort</Label>
            <Input
              type="password"
              value={formular.password}
              onChange={(e) => feld("password", e.target.value)}
              placeholder="mindestens 8 Zeichen"
            />
          </div>
          <div>
            <Label>Passwort (Wiederholung)</Label>
            <Input
              type="password"
              value={formular.passwortWiederholung}
              onChange={(e) => feld("passwortWiederholung", e.target.value)}
            />
          </div>
          {formular.password &&
            formular.passwortWiederholung &&
            formular.password !== formular.passwortWiederholung && (
              <p className="text-sm text-red-400">Die Passwörter stimmen nicht überein.</p>
            )}
          <label className="flex items-center gap-2 text-sm text-text">
            <input
              type="checkbox"
              checked={formular.ist_admin}
              onChange={(e) => feld("ist_admin", e.target.checked)}
            />
            Admin-Rechte (Zugriff auf KI-Ziele, Einstellungen und Benutzerverwaltung)
          </label>
          {fehler && <p className="text-sm text-red-400">{fehler}</p>}
          <Button onClick={anlegen} disabled={ladenAnlegen || !formularGueltig}>
            {ladenAnlegen ? "Legt an..." : "Anlegen"}
          </Button>
        </div>
      </Card>
    </div>
  );
}
