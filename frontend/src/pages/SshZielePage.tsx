import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { AuthMethod, OllamaModellInfo, PersonaModell, SSHZiel, SSHZielEingabe } from "../api/types";
import { Badge, Button, Card, CardTitle, Label, Input, Select } from "../components/ui";

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
  bildki_port: null,
};

interface SshZielePageProps {
  sshZiele: SSHZiel[];
  onGeaendert: () => void;
}

export function SshZielePage({ sshZiele, onGeaendert }: SshZielePageProps) {
  const [formular, setFormular] = useState<SSHZielEingabe>(LEERES_FORMULAR);
  const [bearbeiteId, setBearbeiteId] = useState<string | null>(null);
  const [bearbeiteUrsprungAuthMethod, setBearbeiteUrsprungAuthMethod] = useState<AuthMethod | null>(null);
  const [testErgebnis, setTestErgebnis] = useState<{ ok: boolean; text: string } | null>(null);
  const [ladenTest, setLadenTest] = useState(false);
  const [ladenSpeichern, setLadenSpeichern] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const dateiEingabeRef = useRef<HTMLInputElement>(null);

  const istDirekt = formular.auth_method === "direct";

  function feld<K extends keyof SSHZielEingabe>(name: K, wert: SSHZielEingabe[K]) {
    setFormular((bisher) => ({ ...bisher, [name]: wert }));
  }

  function neuesFormular() {
    setFormular(LEERES_FORMULAR);
    setBearbeiteId(null);
    setBearbeiteUrsprungAuthMethod(null);
    setTestErgebnis(null);
    setFehler(null);
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
      bildki_port: z.bildki_port,
    });
    setBearbeiteId(z.id);
    setBearbeiteUrsprungAuthMethod(z.auth_method);
    setTestErgebnis(null);
    setFehler(null);
  }

  // Beim Bearbeiten bleiben Passwort/Schluessel-Felder leer (siehe
  // bearbeiten()), damit ein gespeichertes Geheimnis nicht im Klartext
  // angezeigt werden muss. "Unveraendert" heisst deshalb: nichts Neues
  // eingetippt UND Auth-Methode nicht gewechselt - dann sollen Test und
  // Speichern die bereits hinterlegten Zugangsdaten weiterverwenden statt
  // faelschlich mit leeren Feldern zu arbeiten.
  const geheimnisUnveraendert =
    !!bearbeiteId &&
    !formular.password &&
    !formular.private_key_pem &&
    formular.auth_method === bearbeiteUrsprungAuthMethod;

  const formularGueltig =
    formular.name.trim() !== "" &&
    (istDirekt
      ? /^https?:\/\/.+/.test(formular.host.trim())
      : formular.host.trim() !== "" &&
        formular.username.trim() !== "" &&
        (formular.auth_method === "agent" ||
          geheimnisUnveraendert ||
          (formular.auth_method === "password" && !!formular.password) ||
          (formular.auth_method === "private_key" && !!formular.private_key_pem)));

  async function testen() {
    setLadenTest(true);
    setTestErgebnis(null);
    try {
      const antwort = geheimnisUnveraendert
        ? await api.sshZielTesten(bearbeiteId!)
        : await api.sshVerbindungTestenUngespeichert(formular);
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

  async function loeschen(z: SSHZiel) {
    if (!window.confirm(`KI-Ziel "${z.name}" wirklich löschen?`)) return;
    await api.sshZielLoeschen(z.id);
    if (bearbeiteId === z.id) neuesFormular();
    onGeaendert();
  }

  async function favoritUmschalten(z: SSHZiel) {
    await api.sshZielFavoritSetzen(z.id, !z.favorit);
    onGeaendert();
  }

  function schluesseldateiWaehlen(datei: File | undefined) {
    if (!datei) return;
    const reader = new FileReader();
    reader.onload = () => feld("private_key_pem", String(reader.result ?? ""));
    reader.readAsText(datei);
  }

  return (
    <div className="grid grid-cols-1 gap-6 p-6 lg:grid-cols-[1.3fr_1fr]">
      <Card>
        <CardTitle>🔌 Gespeicherte KI-Ziele</CardTitle>
        {sshZiele.length === 0 ? (
          <p className="text-sm text-text-muted">
            Noch kein KI-Ziel angelegt. Ohne Auswahl wird das lokal/per Umgebungsvariable konfigurierte
            Standard-Ollama angesprochen.
          </p>
        ) : (
          <>
            <p className="mb-2 text-xs text-text-muted">
              ⭐ markiert das Ziel, das im Kopfbereich-Dropdown automatisch vorausgewählt wird (statt "Lokal /
              Standard-Ollama"). Es kann immer nur ein Favorit gleichzeitig gesetzt sein.
            </p>
            <ul className="divide-y divide-border">
              {sshZiele.map((z) => (
                <li key={z.id} className="flex items-center justify-between py-2.5">
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => favoritUmschalten(z)}
                      title={z.favorit ? "Favorit entfernen" : "Als Favorit im Kopfbereich vorauswählen"}
                      className={`text-lg leading-none ${z.favorit ? "text-amber-300" : "text-text-muted hover:text-amber-300"}`}
                    >
                      {z.favorit ? "★" : "☆"}
                    </button>
                    <div>
                      <div className="text-sm font-medium text-text">{z.name}</div>
                      <div className="text-xs text-text-muted">
                        {z.auth_method === "direct" ? (
                          <>{z.host}</>
                        ) : (
                          <>
                            {z.username}@{z.host}:{z.port} · Ollama-Port {z.remote_ollama_port}{" "}
                          </>
                        )}{" "}
                        · <Badge>{z.auth_method === "direct" ? "direkt, kein SSH" : z.auth_method}</Badge>
                        {z.bildki_port != null && <Badge>🎨 Bild-Port {z.bildki_port}</Badge>}
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="secondary" onClick={() => bearbeiten(z)}>
                      Bearbeiten
                    </Button>
                    <Button variant="danger" onClick={() => loeschen(z)}>
                      Löschen
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      <Card>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-heading text-lg font-semibold tracking-wide text-text">
            {bearbeiteId ? "KI-Ziel bearbeiten" : "Neues KI-Ziel"}
          </h2>
          {bearbeiteId && (
            <button onClick={neuesFormular} className="text-xs text-accent-light hover:underline">
              Abbrechen
            </button>
          )}
        </div>
        <div className="space-y-3">
          <div>
            <Label>Name</Label>
            <Input value={formular.name} onChange={(e) => feld("name", e.target.value)} placeholder="Mein Docker-Server" />
          </div>

          <div>
            <Label>Verbindungsart</Label>
            <Select
              value={formular.auth_method}
              onChange={(e) => {
                feld("auth_method", e.target.value as AuthMethod);
                feld("password", "");
                feld("private_key_pem", "");
                feld("private_key_passphrase", "");
              }}
            >
              <option value="password">SSH mit Passwort</option>
              <option value="private_key">SSH mit privatem Schlüssel</option>
              <option value="agent">SSH mit SSH-Agent</option>
              <option value="direct">Direkt, kein SSH (lokal oder im LAN erreichbar)</option>
            </Select>
          </div>

          {istDirekt ? (
            <div>
              <Label>Basis-URL von Ollama</Label>
              <Input
                value={formular.host}
                onChange={(e) => feld("host", e.target.value)}
                placeholder="http://192.168.1.50:11434"
              />
              <p className="mt-1 text-xs text-text-muted">
                Vollstaendige Adresse inkl. Port, z.B. für ein zweites Ollama im lokalen Netz oder auf einer
                anderen Windows-Maschine - ohne SSH-Tunnel.
              </p>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-[2fr_1fr] gap-3">
                <div>
                  <Label>Host</Label>
                  <Input
                    autoComplete="off"
                    value={formular.host}
                    onChange={(e) => feld("host", e.target.value)}
                    placeholder="192.168.1.50"
                  />
                </div>
                <div>
                  <Label>SSH-Port</Label>
                  <Input
                    type="number"
                    min={1}
                    max={65535}
                    value={formular.port}
                    onChange={(e) => feld("port", Number(e.target.value))}
                  />
                </div>
              </div>
              <div>
                <Label>Benutzername</Label>
                <Input autoComplete="off" value={formular.username} onChange={(e) => feld("username", e.target.value)} />
              </div>
            </>
          )}

          {formular.auth_method === "password" && (
            <div>
              <Label>Passwort</Label>
              <Input
                type="password"
                autoComplete="off"
                value={formular.password}
                onChange={(e) => feld("password", e.target.value)}
                placeholder={geheimnisUnveraendert || bearbeiteId ? "unverändert lassen = leer" : ""}
              />
            </div>
          )}
          {formular.auth_method === "private_key" && (
            <>
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <Label>Privater Schlüssel (PEM)</Label>
                  <button
                    type="button"
                    onClick={() => dateiEingabeRef.current?.click()}
                    className="text-xs text-accent-light hover:underline"
                  >
                    Aus Datei laden...
                  </button>
                  <input
                    ref={dateiEingabeRef}
                    type="file"
                    className="hidden"
                    onChange={(e) => schluesseldateiWaehlen(e.target.files?.[0])}
                  />
                </div>
                <textarea
                  className="w-full rounded-lg border border-border bg-bg px-3 py-1.5 font-mono text-xs text-text outline-none transition-colors focus:border-accent"
                  rows={5}
                  value={formular.private_key_pem}
                  onChange={(e) => feld("private_key_pem", e.target.value)}
                  placeholder={
                    bearbeiteId ? "unverändert lassen = leer" : "-----BEGIN OPENSSH PRIVATE KEY-----"
                  }
                />
              </div>
              <div>
                <Label>Passphrase (falls vorhanden)</Label>
                <Input
                  type="password"
                  autoComplete="off"
                  value={formular.private_key_passphrase}
                  onChange={(e) => feld("private_key_passphrase", e.target.value)}
                />
              </div>
            </>
          )}
          {!istDirekt && (
            <div>
              <Label>Ollama-Port auf dem Zielhost/-container</Label>
              <Input
                type="number"
                min={1}
                max={65535}
                value={formular.remote_ollama_port}
                onChange={(e) => feld("remote_ollama_port", Number(e.target.value))}
              />
            </div>
          )}

          <div>
            <Label>Bild-Generierung Port (optional, sd-server)</Label>
            <Input
              type="number"
              min={1}
              max={65535}
              value={formular.bildki_port ?? ""}
              placeholder="leer = keine Bildgenerierung auf diesem Ziel"
              onChange={(e) => feld("bildki_port", e.target.value ? Number(e.target.value) : null)}
            />
          </div>

          {geheimnisUnveraendert && (
            <p className="text-xs text-text-muted">
              Test/Speichern verwenden die bereits hinterlegten Zugangsdaten, da hier nichts Neues
              eingegeben wurde.
            </p>
          )}
          {testErgebnis && (
            <p className={`text-sm ${testErgebnis.ok ? "text-accent-light" : "text-red-400"}`}>{testErgebnis.text}</p>
          )}
          {fehler && <p className="text-sm text-red-400">{fehler}</p>}

          <div className="flex gap-2">
            <Button variant="secondary" onClick={testen} disabled={ladenTest || !formularGueltig}>
              {ladenTest ? "Testet..." : "Verbindung testen"}
            </Button>
            <Button onClick={speichern} disabled={ladenSpeichern || !formularGueltig}>
              {ladenSpeichern ? "Speichert..." : bearbeiteId ? "Aktualisieren" : "Anlegen"}
            </Button>
          </div>
        </div>
      </Card>

      <PersonaModellZuordnung sshZiele={sshZiele} />
    </div>
  );
}

const PERSONA_LABELS: Record<string, string> = {
  architekt: "Architekt",
  autor: "Autor",
  autor_qwen: "Autor (Qwen3-Variante)",
  autor_mistral: "Autor (Mistral-Variante)",
  chronist: "Chronist",
  anachronismus: "Prüfer: Anachronismus",
  kontinuitaet: "Prüfer: Kontinuität",
  fundus_pfleger: "Fundus-Pfleger",
  lektor: "Lektor",
  satzbau: "Prüfer: Satzbau (Verb-Letzt)",
};

interface PersonaModellZuordnungProps {
  sshZiele: SSHZiel[];
}

function PersonaModellZuordnung({ sshZiele }: PersonaModellZuordnungProps) {
  const [personaModelle, setPersonaModelle] = useState<PersonaModell[]>([]);
  const [modelleZielId, setModelleZielId] = useState<string>("");
  const [verfuegbareModelle, setVerfuegbareModelle] = useState<OllamaModellInfo[]>([]);
  const [auswahl, setAuswahl] = useState<Record<string, string>>({});
  const [ladenModelle, setLadenModelle] = useState(false);
  const [fehlerModelle, setFehlerModelle] = useState<string | null>(null);
  const [speichertPersona, setSpeichertPersona] = useState<string | null>(null);
  const zielVorbelegt = useRef(false);

  useEffect(() => {
    api.personaModelle().then(setPersonaModelle).catch(() => {});
  }, []);

  useEffect(() => {
    if (zielVorbelegt.current || sshZiele.length === 0) return;
    zielVorbelegt.current = true;
    const favorit = sshZiele.find((z) => z.favorit) ?? sshZiele[0];
    setModelleZielId(favorit.id);
  }, [sshZiele]);

  useEffect(() => {
    if (!modelleZielId) return;
    setLadenModelle(true);
    setFehlerModelle(null);
    api
      .sshZielModelle(modelleZielId)
      .then(setVerfuegbareModelle)
      .catch((e) => setFehlerModelle(e instanceof Error ? e.message : String(e)))
      .finally(() => setLadenModelle(false));
  }, [modelleZielId]);

  // Ollama akzeptiert einen Modellnamen ohne Tag (z.B. "gemma4") als Alias
  // fuer "gemma4:latest" - ohne diese Normalisierung wuerde die
  // Verfuegbarkeits-Warnung faelschlich bei jedem in rollen.py ohne
  // Tag-Suffix eingetragenen Modell auschlagen, obwohl der eigentliche
  // Ollama-Aufruf einwandfrei funktioniert.
  const ohneLatestTag = (name: string) => name.replace(/:latest$/, "");
  const verfuegbareNamen = new Set(verfuegbareModelle.map((m) => ohneLatestTag(m.name)));

  async function speichern(persona: string, modell: string | null) {
    setSpeichertPersona(persona);
    try {
      const aktualisiert = await api.personaModellSetzen(persona, modell);
      setPersonaModelle((bisher) => bisher.map((p) => (p.persona === persona ? aktualisiert : p)));
      setAuswahl((bisher) => {
        const kopie = { ...bisher };
        delete kopie[persona];
        return kopie;
      });
    } finally {
      setSpeichertPersona(null);
    }
  }

  return (
    <Card className="lg:col-span-2">
      <CardTitle>🧭 Persona-Modell-Zuordnung</CardTitle>
      <p className="mb-3 text-xs text-text-muted">
        Legt fest, welches Ollama-Modell hinter jeder Persona steckt - global für alle Benutzer und Projekte.
        Überschreibt nur das Modell, alle sonstigen Parameter bleiben wie im Code hinterlegt. Unabhängig vom
        projektspezifischen "Autor-Modell: Qwen3"-Vermerk im Gerüst.
      </p>

      <div className="mb-3 max-w-sm">
        <Label>Modell-Liste abfragen von KI-Ziel</Label>
        <Select value={modelleZielId} onChange={(e) => setModelleZielId(e.target.value)}>
          {sshZiele.length === 0 && <option value="">Kein KI-Ziel angelegt</option>}
          {sshZiele.map((z) => (
            <option key={z.id} value={z.id}>
              {z.name}
            </option>
          ))}
        </Select>
        {ladenModelle && <p className="mt-1 text-xs text-text-muted">Fragt verfügbare Modelle ab...</p>}
        {fehlerModelle && <p className="mt-1 text-xs text-red-400">{fehlerModelle}</p>}
      </div>

      <ul className="divide-y divide-border">
        {personaModelle.map((p) => {
          const nichtVerfuegbar =
            verfuegbareModelle.length > 0 && !verfuegbareNamen.has(ohneLatestTag(p.effektives_modell));
          const pendingWert = auswahl[p.persona] ?? p.effektives_modell;
          return (
            <li key={p.persona} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
              <div>
                <div className="text-sm font-medium text-text">{PERSONA_LABELS[p.persona] ?? p.persona}</div>
                <div className="text-xs text-text-muted">
                  Default: {p.default_modell}
                  {p.override_modell && <> · Override: {p.override_modell}</>}
                  {nichtVerfuegbar && (
                    <>
                      {" "}
                      · <Badge tone="amber">⚠️ nicht auf gewähltem Ziel gefunden</Badge>
                    </>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Select
                  className="w-56"
                  value={pendingWert}
                  onChange={(e) => setAuswahl((bisher) => ({ ...bisher, [p.persona]: e.target.value }))}
                >
                  <option value={p.effektives_modell}>{p.effektives_modell}</option>
                  {verfuegbareModelle
                    .filter((m) => m.name !== p.effektives_modell)
                    .map((m) => (
                      <option key={m.name} value={m.name}>
                        {m.name}
                      </option>
                    ))}
                </Select>
                <Button
                  variant="secondary"
                  disabled={speichertPersona === p.persona || pendingWert === p.effektives_modell}
                  onClick={() => speichern(p.persona, pendingWert)}
                >
                  Speichern
                </Button>
                {p.override_modell && (
                  <Button
                    variant="secondary"
                    disabled={speichertPersona === p.persona}
                    onClick={() => speichern(p.persona, null)}
                  >
                    Default
                  </Button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
