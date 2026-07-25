import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { Button, Card, CardTitle, Input, Label } from "../components/ui";

export function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [laden, setLaden] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

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
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardTitle>📖 Anmelden</CardTitle>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            anmelden();
          }}
        >
          <div>
            <Label>Benutzername</Label>
            <Input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
          </div>
          <div>
            <Label>Passwort</Label>
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          {fehler && <p className="text-sm text-red-400">{fehler}</p>}
          <Button type="submit" disabled={laden || !username || !password}>
            {laden ? "Meldet an..." : "Anmelden"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
