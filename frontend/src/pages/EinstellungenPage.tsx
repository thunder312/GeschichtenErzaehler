import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api/client";
import type {
  AuthMethod,
  Einstellungen,
  OllamaModellInfo,
  PersonaModell,
  SSHZiel,
  SSHZielEingabe,
} from "../api/types";
import { Badge, Button, Card, CardTitle, Input, Label, Select } from "../components/ui";

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

interface EinstellungenPageProps {
  sshZiele: SSHZiel[];
  onSshZieleGeaendert: () => void;
}

// Standardmaessig eingeklappt, damit alle Karten-Ueberschriften ohne Scrollen
// sichtbar sind - die meisten davon werden ohnehin nur selten geoeffnet.
function EinklappbareKarte({ titel, children }: { titel: string; children: ReactNode }) {
  const [offen, setOffen] = useState(false);
  return (
    <Card>
      <button
        onClick={() => setOffen((bisher) => !bisher)}
        className="flex w-full items-center justify-between text-left"
      >
        <h2 className="font-heading text-lg font-semibold tracking-wide text-text">{titel}</h2>
        <span className={`text-text-muted transition-transform duration-150 ${offen ? "rotate-180" : ""}`}>
          ▾
        </span>
      </button>
      {offen && <div className="mt-3">{children}</div>}
    </Card>
  );
}

export function EinstellungenPage({ sshZiele, onSshZieleGeaendert }: EinstellungenPageProps) {
  const [einstellungen, setEinstellungen] = useState<Einstellungen | null>(null);
  const [pfad, setPfad] = useState("");
  const [unterordnerJeEpoche, setUnterordnerJeEpoche] = useState(false);
  const [bildgeneratorUrl, setBildgeneratorUrl] = useState("");
  // "Unnützes Wissen"-Overlay: Startzeit im UI in Minuten (der Server rechnet
  // in Sekunden), Wechsel-Intervall in Sekunden.
  const [wissenAktiv, setWissenAktiv] = useState(true);
  const [wissenStartMinuten, setWissenStartMinuten] = useState(String(20 / 60));
  const [wissenWechselSekunden, setWissenWechselSekunden] = useState("20");
  const [laden, setLaden] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [gespeichert, setGespeichert] = useState(false);

  function uebernehmen(e: Einstellungen) {
    setEinstellungen(e);
    setPfad(e.projects_dir);
    setUnterordnerJeEpoche(e.unterordner_je_epoche);
    setBildgeneratorUrl(e.bildgenerator_url);
    setWissenAktiv(e.unnuetzes_wissen_aktiv);
    setWissenStartMinuten(String(Math.round((e.unnuetzes_wissen_start_sekunden / 60) * 100) / 100));
    setWissenWechselSekunden(String(e.unnuetzes_wissen_wechsel_sekunden));
  }

  useEffect(() => {
    api.einstellungen().then(uebernehmen);
  }, []);

  interface WissenWerte {
    aktiv: boolean;
    startMinuten: string;
    wechselSekunden: string;
  }

  async function speichern(
    neuerPfad: string,
    neuUnterordnerJeEpoche: boolean,
    neueBildgeneratorUrl: string,
    wissen?: WissenWerte,
  ) {
    const w = wissen ?? { aktiv: wissenAktiv, startMinuten: wissenStartMinuten, wechselSekunden: wissenWechselSekunden };
    setLaden(true);
    setFehler(null);
    setGespeichert(false);
    try {
      const antwort = await api.einstellungenSchreiben({
        projectsDir: neuerPfad,
        unterordnerJeEpoche: neuUnterordnerJeEpoche,
        bildgeneratorUrl: neueBildgeneratorUrl,
        unnuetzesWissenAktiv: w.aktiv,
        unnuetzesWissenStartSekunden: Math.max(0, Math.round((Number(w.startMinuten) || 0) * 60)),
        unnuetzesWissenWechselSekunden: Math.max(3, Math.round(Number(w.wechselSekunden) || 0)),
      });
      uebernehmen(antwort);
      setGespeichert(true);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLaden(false);
    }
  }

  async function unterordnerUmschalten(checked: boolean) {
    setUnterordnerJeEpoche(checked);
    await speichern(pfad, checked, bildgeneratorUrl);
  }

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div className="space-y-6">
          <EinklappbareKarte titel="🗂️ Speicherort der Geschichten">
            <p className="mb-3 text-sm text-text-muted">
              Hier legen alle Projekte ihre Dateien ab (Gerüst, Kapitel, Personas, ...) - unabhängig vom
              gewählten KI-Ziel. Athene &amp; Co. bekommen den Text nur zum Schreiben/Prüfen geschickt, die
              Ergebnisse landen ausschließlich hier auf dieser Festplatte.
            </p>
            {einstellungen && (
              <div className="space-y-3">
                <div>
                  <Label>Ordner für Projekte</Label>
                  <Input value={pfad} onChange={(e) => setPfad(e.target.value)} placeholder={einstellungen.standard_projects_dir} />
                </div>
                <div className="flex items-center gap-2 text-xs text-text-muted">
                  {einstellungen.ist_standard ? (
                    <Badge>Standardpfad</Badge>
                  ) : (
                    <Badge tone="green">Angepasster Pfad</Badge>
                  )}
                  <span>Standard: {einstellungen.standard_projects_dir}</span>
                </div>
                {fehler && <p className="text-sm text-red-400">{fehler}</p>}
                {gespeichert && !fehler && <p className="text-sm text-accent-light">Gespeichert.</p>}
                <div className="flex gap-2">
                  <Button
                    onClick={() => speichern(pfad, unterordnerJeEpoche, bildgeneratorUrl)}
                    disabled={laden || pfad.trim() === ""}
                  >
                    {laden ? "Speichert..." : "Speichern"}
                  </Button>
                  {!einstellungen.ist_standard && (
                    <Button
                      variant="secondary"
                      onClick={() => speichern("", unterordnerJeEpoche, bildgeneratorUrl)}
                      disabled={laden}
                    >
                      Zurück auf Standard
                    </Button>
                  )}
                </div>
                <p className="text-xs text-text-muted">
                  Bereits angelegte Projekte bleiben an ihrem bisherigen Ort - die Änderung gilt für neu
                  angelegte Projekte und dafür, wo die Projektliste nachschaut.
                </p>

                <label className="flex items-start gap-2 border-t border-border pt-3 text-sm text-text">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={unterordnerJeEpoche}
                    onChange={(e) => unterordnerUmschalten(e.target.checked)}
                    disabled={laden}
                  />
                  <span>
                    Automatisch Unterordner je Epoche anlegen und benutzen
                    <span className="mt-0.5 block text-xs text-text-muted">
                      Ein neues Projekt landet dann in "Ordner für Projekte/&lt;Epoche&gt;/&lt;Geschichte&gt;" statt
                      direkt in "Ordner für Projekte/&lt;Geschichte&gt;" - erspart das manuelle Umstellen des
                      Speicherorts beim Wechsel zwischen Epochen. Gilt nur für neu angelegte Projekte.
                    </span>
                  </span>
                </label>
              </div>
            )}
          </EinklappbareKarte>

          <EinklappbareKarte titel="🎨 Externer Bildgenerator">
            <p className="mb-3 text-sm text-text-muted">
              Link zu einer Web-Oberfläche, mit der sich von Hand (z. B. kostenlos) ein Titelbild
              erzeugen lässt - erscheint als Schnellzugriff im Titelbild-Bereich unter "Stand &amp;
              Export", neben dem Hochladen eines fertigen Bildes.
            </p>
            {einstellungen && (
              <div className="space-y-3">
                <div>
                  <Label>Link zum Bildgenerator</Label>
                  <Input
                    value={bildgeneratorUrl}
                    onChange={(e) => setBildgeneratorUrl(e.target.value)}
                    placeholder={einstellungen.bildgenerator_url}
                  />
                </div>
                <div className="flex items-center gap-2 text-xs text-text-muted">
                  {einstellungen.bildgenerator_url_ist_standard ? (
                    <Badge>Standard-Link</Badge>
                  ) : (
                    <Badge tone="green">Angepasster Link</Badge>
                  )}
                </div>
                <div className="flex gap-2">
                  <Button
                    onClick={() => speichern(pfad, unterordnerJeEpoche, bildgeneratorUrl)}
                    disabled={laden || bildgeneratorUrl.trim() === ""}
                  >
                    {laden ? "Speichert..." : "Speichern"}
                  </Button>
                  {!einstellungen.bildgenerator_url_ist_standard && (
                    <Button
                      variant="secondary"
                      onClick={() => speichern(pfad, unterordnerJeEpoche, "")}
                      disabled={laden}
                    >
                      Zurück auf Standard
                    </Button>
                  )}
                </div>
              </div>
            )}
          </EinklappbareKarte>

          <EinklappbareKarte titel="🎛️ Benutzer-Einstellungen">
            <p className="mb-3 text-sm text-text-muted">
              Persönliche Vorlieben für die Bedienung. Weitere Optionen folgen hier nach und nach.
            </p>
            {einstellungen && (
              <div className="space-y-3 border-t border-border pt-3">
                <label className="flex items-start gap-2 text-sm text-text">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={wissenAktiv}
                    onChange={(e) => setWissenAktiv(e.target.checked)}
                    disabled={laden}
                  />
                  <span>
                    „Unnützes Wissen" während längerer KI-Wartezeiten einblenden
                    <span className="mt-0.5 block text-xs text-text-muted">
                      Das zentrale Overlay mit Buch-/Autoren-Kuriositäten, das erscheint, während die KI
                      schreibt oder prüft. Ausgeschaltet bleibt es komplett aus.
                    </span>
                  </span>
                </label>

                {wissenAktiv && (
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div>
                      <Label>Einblenden nach (Minuten)</Label>
                      <Input
                        type="number"
                        min={0}
                        step={0.5}
                        value={wissenStartMinuten}
                        onChange={(e) => setWissenStartMinuten(e.target.value)}
                        disabled={laden}
                      />
                      <p className="mt-1 text-xs text-text-muted">0 = sofort. Standard: {Math.round((20 / 60) * 100) / 100}.</p>
                    </div>
                    <div>
                      <Label>Nächster Fakt nach (Sekunden)</Label>
                      <Input
                        type="number"
                        min={3}
                        step={1}
                        value={wissenWechselSekunden}
                        onChange={(e) => setWissenWechselSekunden(e.target.value)}
                        disabled={laden}
                      />
                      <p className="mt-1 text-xs text-text-muted">Mindestens 3. Standard: 20.</p>
                    </div>
                  </div>
                )}

                {fehler && <p className="text-sm text-red-400">{fehler}</p>}
                {gespeichert && !fehler && <p className="text-sm text-accent-light">Gespeichert.</p>}
                <Button
                  onClick={() =>
                    speichern(pfad, unterordnerJeEpoche, bildgeneratorUrl, {
                      aktiv: wissenAktiv,
                      startMinuten: wissenStartMinuten,
                      wechselSekunden: wissenWechselSekunden,
                    })
                  }
                  disabled={laden}
                >
                  {laden ? "Speichert..." : "Speichern"}
                </Button>
              </div>
            )}
          </EinklappbareKarte>
        </div>

        <div className="space-y-6">
          <KiZieleCard sshZiele={sshZiele} onGeaendert={onSshZieleGeaendert} />
        </div>
      </div>

      <EinklappbareKarte titel="🧭 Persona-Modell-Zuordnung">
        <PersonaModellZuordnung sshZiele={sshZiele} />
      </EinklappbareKarte>
    </div>
  );
}

interface KiZieleCardProps {
  sshZiele: SSHZiel[];
  onGeaendert: () => void;
}

function KiZieleCard({ sshZiele, onGeaendert }: KiZieleCardProps) {
  const [formularOffen, setFormularOffen] = useState(false);
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

  function hinzufuegenOeffnen() {
    neuesFormular();
    setFormularOffen(true);
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
    setFormularOffen(true);
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
      setFormularOffen(false);
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
    if (bearbeiteId === z.id) {
      neuesFormular();
      setFormularOffen(false);
    }
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
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <CardTitle className="mb-0">🔌 KI-Ziele</CardTitle>
        {!formularOffen && (
          <Button variant="secondary" onClick={hinzufuegenOeffnen}>
            + Neues KI-Ziel
          </Button>
        )}
      </div>

      {sshZiele.length === 0 ? (
        <p className="text-sm text-text-muted">
          Noch kein KI-Ziel angelegt. Ohne Auswahl wird das lokal/per Umgebungsvariable konfigurierte
          Standard-Ollama angesprochen.
        </p>
      ) : (
        <ul className="mb-1 divide-y divide-border">
          {sshZiele.map((z) => (
            <li key={z.id} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
              <div className="flex min-w-0 items-center gap-2">
                <button
                  onClick={() => favoritUmschalten(z)}
                  title={z.favorit ? "Favorit entfernen" : "Als Favorit im Kopfbereich vorauswählen"}
                  className={`shrink-0 text-base leading-none ${z.favorit ? "text-amber-300" : "text-text-muted hover:text-amber-300"}`}
                >
                  {z.favorit ? "★" : "☆"}
                </button>
                <span className="truncate text-sm font-medium text-text">{z.name}</span>
                <span className="truncate text-xs text-text-muted">
                  {z.auth_method === "direct" ? z.host : `${z.username}@${z.host}:${z.port}`}
                </span>
                {z.bildki_port != null && <Badge>🎨</Badge>}
              </div>
              <div className="flex shrink-0 gap-1.5">
                <button
                  onClick={() => bearbeiten(z)}
                  className="text-xs text-accent-light hover:underline"
                >
                  Bearbeiten
                </button>
                <button
                  onClick={() => loeschen(z)}
                  className="text-xs text-red-400 hover:underline"
                >
                  Löschen
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {sshZiele.length > 0 && (
        <p className="mb-2 text-xs text-text-muted">
          ⭐ markiert das Ziel, das im Kopfbereich-Dropdown automatisch vorausgewählt wird.
        </p>
      )}

      {formularOffen && (
        <div className="mt-3 space-y-3 border-t border-border pt-3">
          <div className="flex items-center justify-between">
            <h3 className="font-heading text-sm font-semibold tracking-wide text-text">
              {bearbeiteId ? "KI-Ziel bearbeiten" : "Neues KI-Ziel"}
            </h3>
            <button
              onClick={() => {
                neuesFormular();
                setFormularOffen(false);
              }}
              className="text-xs text-accent-light hover:underline"
            >
              Abbrechen
            </button>
          </div>

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
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-[2fr_1fr]">
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
      )}
    </Card>
  );
}

const PERSONA_LABELS: Record<string, string> = {
  architekt: "Architekt",
  autor: "Autor",
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
    <>
      <p className="mb-3 text-xs text-text-muted">
        Legt fest, welches Ollama-Modell hinter jeder Persona steckt - global für alle Benutzer und Projekte.
        Überschreibt nur das Modell, alle sonstigen Parameter bleiben wie im Code hinterlegt.
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
    </>
  );
}
