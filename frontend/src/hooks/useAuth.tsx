import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, refreshAccessToken, setAccessToken, type TokenResponse } from "../api/client";

interface AuthUser {
  id: string;
  email: string;
  fullName: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function toAuthUser(data: TokenResponse): AuthUser {
  return { id: data.user_id, email: data.email, fullName: data.full_name };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // The access token only lives in memory, so it's gone after a hard
  // refresh. The httpOnly refresh cookie survives that though — this is
  // what quietly re-establishes the session before the app renders
  // behind a login wall.
  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      const token = await refreshAccessToken();
      if (cancelled) return;

      if (token) {
        try {
          const profile = await api.get<{ id: string; email: string; full_name: string }>("/profile");
          if (!cancelled) setUser({ id: profile.id, email: profile.email, fullName: profile.full_name });
        } catch {
          setAccessToken(null);
        }
      }
      if (!cancelled) setIsLoading(false);
    }

    restoreSession();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setError(null);
    try {
      const data = await api.post<TokenResponse>("/auth/login", { email, password }, { skipAuth: true });
      setAccessToken(data.access_token);
      setUser(toAuthUser(data));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't log you in");
      throw err;
    }
  }, []);

  const register = useCallback(async (email: string, password: string, fullName: string) => {
    setError(null);
    try {
      const data = await api.post<TokenResponse>(
        "/auth/register",
        { email, password, full_name: fullName },
        { skipAuth: true },
      );
      setAccessToken(data.access_token);
      setUser(toAuthUser(data));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registration failed");
      throw err;
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      // Clear client state regardless of whether the request succeeded —
      // a network hiccup on logout shouldn't leave someone stuck "logged in."
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, isLoading, isAuthenticated: user !== null, error, login, register, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside an AuthProvider");
  return ctx;
}