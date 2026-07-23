import { useState } from "react";
import { api } from "../api/client";
import type { AuthMethod, SSHZiel, SSHZielEingabe } from "../api/types";
import { Badge, Button, Card, Input, Label, Select } from "../components/ui";

const LEERES_FORMULAR: SSHZielEingabe = {
  name: "",
  host: "",
  port: 22,
  username: "",
  auth_method: "password",
  password: "",
  private_key_pem: "",
  private_key_passphrase: "",
  remote_ollama_port: 11434,
};

interface SshZielePageProps {
  sshZiele: SSHZiel[];
  onGeaendert: () => void;
}

export function SshZielePage({ sshZiele, onGeaendert }: SshZielePageProps) {
  const [formular, setFormular] = useState<SSHZielEingabe>(LEERES_FORMULAR);
  const [bearbeiteId, setBearbeiteId] = useState<string | null>(null);
  const [testErgebnis, setTestErgebnis] = useState<{ ok: boolean; text: string } | null>(null);
  const [ladenTest, setLadenTest] = useState(false);
  const [ladenSpeichern, setLadenSpeichern] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  function feld<K extends keyof SSHZielEingabe>(name: K, wert: SSHZielEingabe[K]) {
    setFormular((bisher) => ({ ...bisher, [name]: wert }));
  }

  function neuesFormular() {
    setFormular(LEERES_FORMULAR);
    setBearbeiteId(null);
    setTestErgebnis(null);
  }

  function bearbeiten(z: SSHZiel) {
    setFormular({
      name: z.name,
      host: z.host,
      port: z.port,
      username: z.username,
      auth_method: z.auth_method,
      password: "",
      private_key_pem: "",
      private_key_passphrase: "",
      remote_ollama_port: z.remote_ollama_port,
    });
    setBearbeiteId(z.id);
    setTestErgebnis(null);
  }

  async function testen() {
    setLadenTest(true);
    setTestErgebnis(null);
    try {
      const antwort = await api.sshVerbindungTestenUngespeichert(formular);
      setTestErgebnis({ ok: antwort.erfolgreich, text: antwort.meldung });
    } catch (e) {
      setTestErgebnis({ ok: false, text: e instanceof Error ? e.message : String(e) });
    } finally {
      setLadenTest(false);
    }
  }

  async function speichern() {
    setLadenSpeichern(true);
    setFehler(null);
    try {
      if (bearbeiteId) {
        await api.sshZielAktualisieren(bearbeiteId, formular);
      } else {
        await api.sshZielAnlegen(formular);
      }
      neuesFormular();
      onGeaendert();
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLadenSpeichern(false);
    }
  }

  async function loeschen(id: string) {
    await api.sshZielLoeschen(id);
    onGeaendert();
  }

  return (
    <div className="grid grid-cols-1 gap-6 p-6 lg:grid-cols-[1.3fr_1fr]">
      <Card>
        <h2 className="mb-3 text-sm font-semibold text-neutral-700 dark:text-neutral-200">
          Gespeicherte SSH-Ziele
        </h2>
        {sshZiele.length === 0 ? (
          <p className="text-sm text-neutral-500">
            Noch kein SSH-Ziel angelegt. Ohne SSH-Ziel wird das lokal/per Umgebungsvariable konfigurierte
            Standard-Ollama angesprochen.
          </p>
        ) : (
          <ul className="divide-y divide-neutral-200 dark:divide-neutral-800">
            {sshZiele.map((z) => (
              <li key={z.id} className="flex items-center justify-between py-2.5">
                <div>
                  <div className="text-sm font-medium">{z.name}</div>
                  <div className="text-xs text-neutral-500">
                    {z.username}@{z.host}:{z.port} · Ollama-Port {z.remote_ollama_port} ·{" "}
                    <Badge>{z.auth_method}</Badge>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button variant="secondary" onClick={() => bearbeiten(z)}>
                    Bearbeiten
                  </Button>
                  <Button variant="danger" onClick={() => loeschen(z.id)}>
                    Löschen
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-200">
            {bearbeiteId ? "SSH-Ziel bearbeiten" : "Neues SSH-Ziel"}
          </h2>
          {bearbeiteId && (
            <button onClick={neuesFormular} className="text-xs text-purple-600 hover:underline">
              Abbrechen
            </button>
          )}
        </div>
        <div className="space-y-3">
          <div>
            <Label>Name</Label>
            <Input value={formular.name} onChange={(e) => feld("name", e.target.value)} placeholder="Mein Docker-Server" />
          </div>
          <div className="grid grid-cols-[2fr_1fr] gap-3">
            <div>
              <Label>Host</Label>
              <Input value={formular.host} onChange={(e) => feld("host", e.target.value)} placeholder="192.168.1.50" />
            </div>
            <div>
              <Label>SSH-Port</Label>
              <Input type="number" value={formular.port} onChange={(e) => feld("port", Number(e.target.value))} />
            </div>
          </div>
          <div>
            <Label>Benutzername</Label>
            <Input value={formular.username} onChange={(e) => feld("username", e.target.value)} />
          </div>
          <div>
            <Label>Authentifizierung</Label>
            <Select
              value={formular.auth_method}
              onChange={(e) => feld("auth_method", e.target.value as AuthMethod)}
            >
              <option value="password">Passwort</option>
              <option value="private_key">Privater Schlüssel</option>
              <option value="agent">SSH-Agent</option>
            </Select>
          </div>
          {formular.auth_method === "password" && (
            <div>
              <Label>Passwort</Label>
              <Input
                type="password"
                value={formular.password}
                onChange={(e) => feld("password", e.target.value)}
                placeholder={bearbeiteId ? "unverändert lassen = leer" : ""}
              />
            </div>
          )}
          {formular.auth_method === "private_key" && (
            <>
              <div>
                <Label>Privater Schlüssel (PEM)</Label>
                <textarea
                  className="w-full rounded-md border border-neutral-300 bg-white px-3 py-1.5 font-mono text-xs outline-none focus:border-purple-500 dark:border-neutral-700 dark:bg-neutral-950"
                  rows={5}
                  value={formular.private_key_pem}
                  onChange={(e) => feld("private_key_pem", e.target.value)}
                  placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
                />
              </div>
              <div>
                <Label>Passphrase (falls vorhanden)</Label>
                <Input
                  type="password"
                  value={formular.private_key_passphrase}
                  onChange={(e) => feld("private_key_passphrase", e.target.value)}
                />
              </div>
            </>
          )}
          <div>
            <Label>Ollama-Port auf dem Zielhost/-container</Label>
            <Input
              type="number"
              value={formular.remote_ollama_port}
              onChange={(e) => feld("remote_ollama_port", Number(e.target.value))}
            />
          </div>

          {testErgebnis && (
            <p className={`text-sm ${testErgebnis.ok ? "text-emerald-600" : "text-red-600"}`}>{testErgebnis.text}</p>
          )}
          {fehler && <p className="text-sm text-red-600">{fehler}</p>}

          <div className="flex gap-2">
            <Button variant="secondary" onClick={testen} disabled={ladenTest}>
              {ladenTest ? "Testet..." : "Verbindung testen"}
            </Button>
            <Button onClick={speichern} disabled={ladenSpeichern || !formular.name || !formular.host}>
              {ladenSpeichern ? "Speichert..." : bearbeiteId ? "Aktualisieren" : "Anlegen"}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
