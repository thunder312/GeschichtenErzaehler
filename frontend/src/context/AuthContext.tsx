import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { Benutzer } from "../api/types";

interface AuthApi {
  benutzer: Benutzer | null;
  ladend: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthApi | null>(null);

/** Haelt den aktuell eingeloggten Benutzer. Fragt beim Laden einmalig
 * /api/auth/me ab - solange Settings.auth_aktiv im Backend False ist
 * (Entwicklungs-/Testbetrieb), liefert das immer den impliziten
 * Default-Benutzer zurueck (kein 401), die LoginPage erscheint also
 * praktisch nie. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [benutzer, setBenutzer] = useState<Benutzer | null>(null);
  const [ladend, setLadend] = useState(true);

  useEffect(() => {
    api
      .me()
      .then(setBenutzer)
      .catch(() => setBenutzer(null))
      .finally(() => setLadend(false));
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const eingeloggter = await api.login({ username, password });
    setBenutzer(eingeloggter);
  }, []);

  const logout = useCallback(async () => {
    await api.logout();
    setBenutzer(null);
  }, []);

  const value = useMemo(() => ({ benutzer, ladend, login, logout }), [benutzer, ladend, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthApi {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth() muss innerhalb von <AuthProvider> verwendet werden.");
  return ctx;
}
