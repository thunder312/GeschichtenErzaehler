import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { Button, Card, Input, Label } from "../components/ui";
import { AboutDialog } from "../components/AboutDialog";
import { EulenwerkLogo } from "../components/EulenwerkAbout";

/** Login im einheitlichen Eulenwerk-Layout (siehe Design-System, Abschnitt "Login-Seite"):
 * Logo, App-Name, Untertitel, Felder, Primärbutton, darunter der Eulenwerk-Hinweis. */
export function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [laden, setLaden] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [ueber, setUeber] = useState(false);

  async function anmelden() {
    setLaden(true);
    setFehler(null);
    try {
      await login(username, password);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    } finally {
      setLaden(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 p-4">
      <Card className="w-full max-w-sm">
        <div className="mb-4 flex flex-col items-center gap-2 text-center">
          <img src="/favicon.svg" alt="" className="h-14 w-14 rounded-2xl" />
          <h1 className="heading-flourish bg-gradient-to-r from-accent-light to-accent bg-clip-text text-2xl font-bold tracking-tight text-transparent">
            Geschichten Erzähler
          </h1>
          <p className="text-sm text-text-muted">Anmeldung erforderlich</p>
        </div>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            anmelden();
          }}
        >
          <div>
            <Label>Benutzername</Label>
            <Input
              name="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
            />
          </div>
          <div>
            <Label>Passwort</Label>
            <Input
              type="password"
              name="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {fehler && <p className="rounded-md bg-red-400/15 px-3 py-2 text-sm text-red-400">{fehler}</p>}
          <Button type="submit" className="w-full" disabled={laden || !username || !password}>
            {laden ? "Meldet an..." : "Anmelden"}
          </Button>
        </form>
      </Card>
      <div className="flex items-center gap-4 text-sm text-text-muted">
        <a className="ew-brand" href="https://daniel-ertl.de" target="_blank" rel="noopener">
          <EulenwerkLogo />
          Ein Eulenwerk-Projekt
        </a>
        <button type="button" className="hover:text-text" onClick={() => setUeber(true)}>
          Über
        </button>
      </div>
      {ueber && <AboutDialog onClose={() => setUeber(false)} />}
    </div>
  );
}
