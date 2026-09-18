import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, loadTokens, saveTokens, setAuthFailureHandler } from "./api";
import type { AuthResponse, Provider, User } from "./types";

interface AuthState {
  user: User | null;
  provider: Provider | null;
  loading: boolean;
  login: (identifier: string, password: string) => Promise<User>;
  register: (payload: RegisterPayload) => Promise<User>;
  logout: () => void;
  refreshUser: () => Promise<void>;
  becomeProvider: (payload: { provider_type: "INDIVIDUAL" | "SOCIETY"; organization_name?: string }) => Promise<void>;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
  phone?: string;
  role?: "RENTER" | "PROVIDER";
  provider_type?: "INDIVIDUAL" | "SOCIETY";
  organization_name?: string;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [provider, setProvider] = useState<Provider | null>(null);
  const [loading, setLoading] = useState(true);

  const loadProvider = useCallback(async (current: User | null) => {
    if (!current || current.role === "RENTER") {
      setProvider(null);
      return;
    }
    try {
      setProvider(await api.get<Provider>("/providers/me"));
    } catch {
      // An admin (or a provider whose profile was removed) simply has none.
      setProvider(null);
    }
  }, []);

  const loadUser = useCallback(async () => {
    if (!loadTokens()?.access_token) {
      setUser(null);
      setProvider(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.get<User>("/me");
      setUser(me);
      await loadProvider(me);
    } catch {
      saveTokens(null);
      setUser(null);
      setProvider(null);
    } finally {
      setLoading(false);
    }
  }, [loadProvider]);

  useEffect(() => {
    // A refresh failure anywhere in the app drops us back to signed-out state.
    setAuthFailureHandler(() => {
      setUser(null);
      setProvider(null);
    });
    void loadUser();
  }, [loadUser]);

  const applyAuth = useCallback(
    async (response: AuthResponse) => {
      saveTokens({ access_token: response.access_token, refresh_token: response.refresh_token });
      setUser(response.user);
      await loadProvider(response.user);
      return response.user;
    },
    [loadProvider],
  );

  const login = useCallback(
    async (identifier: string, password: string) =>
      applyAuth(await api.post<AuthResponse>("/auth/login", { identifier, password })),
    [applyAuth],
  );

  const register = useCallback(
    async (payload: RegisterPayload) =>
      applyAuth(await api.post<AuthResponse>("/auth/register", payload)),
    [applyAuth],
  );

  const logout = useCallback(() => {
    saveTokens(null);
    setUser(null);
    setProvider(null);
  }, []);

  const becomeProvider = useCallback(
    async (payload: { provider_type: "INDIVIDUAL" | "SOCIETY"; organization_name?: string }) => {
      await api.post<Provider>("/providers", payload);
      await loadUser();
    },
    [loadUser],
  );

  const value = useMemo<AuthState>(
    () => ({ user, provider, loading, login, register, logout, refreshUser: loadUser, becomeProvider }),
    [user, provider, loading, login, register, logout, loadUser, becomeProvider],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
