import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { defaultApiClient, ApiClient } from "../../shared/api/client";
import type { SessionResponse, LoginRequest } from "../../shared/api/types";

export interface AuthContextValue {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: SessionResponse | null;
  login: (data: LoginRequest) => Promise<void>;
  logout: () => Promise<void>;
  checkSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({
  children,
  client = defaultApiClient,
}: {
  children: ReactNode;
  client?: ApiClient;
}) {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [user, setUser] = useState<SessionResponse | null>(null);

  const checkSession = useCallback(async () => {
    try {
      setIsLoading(true);
      const session = await client.auth.session();
      setUser(session);
      setIsAuthenticated(session.authenticated);
    } catch {
      setUser(null);
      setIsAuthenticated(false);
    } finally {
      setIsLoading(false);
    }
  }, [client]);

  useEffect(() => {
    client.setOnUnauthorized(() => {
      setIsAuthenticated(false);
      setUser(null);
    });
    checkSession();
  }, [client, checkSession]);

  const login = useCallback(
    async (data: LoginRequest) => {
      await client.auth.login(data);
      await checkSession();
    },
    [client, checkSession],
  );

  const logout = useCallback(async () => {
    try {
      await client.auth.logout();
    } finally {
      setUser(null);
      setIsAuthenticated(false);
    }
  }, [client]);

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        isLoading,
        user,
        login,
        logout,
        checkSession,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
