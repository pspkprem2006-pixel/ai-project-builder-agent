"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearStoredToken, getStoredToken, setStoredToken, setUnauthorizedHandler } from "@/lib/api";
import type { TokenResponse, User } from "@/lib/types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string, redirectTo?: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const refreshUser = useCallback(async () => {
    const token = getStoredToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.get<User>("/auth/me");
      setUser(me);
    } catch {
      clearStoredToken();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  // Any 401 from the API means the session expired or was invalidated.
  // Clear the user, drop the token, and send the user to the login screen,
  // preserving the page they were trying to reach.
  useEffect(() => {
    setUnauthorizedHandler((destination) => {
      setUser(null);
      setLoading(false);
      router.replace(`/login?next=${encodeURIComponent(destination)}`);
    });
    return () => setUnauthorizedHandler(null);
  }, [router]);

  const login = useCallback(
    async (email: string, password: string, redirectTo?: string) => {
      const data = await api.post<TokenResponse>("/auth/login", { email, password });
      setStoredToken(data.access_token);
      setUser(data.user);
      router.push(redirectTo && redirectTo !== "/" ? redirectTo : "/dashboard");
    },
    [router]
  );

  const register = useCallback(
    async (email: string, password: string, fullName: string) => {
      const data = await api.post<TokenResponse>("/auth/register", {
        email,
        password,
        full_name: fullName,
      });
      setStoredToken(data.access_token);
      setUser(data.user);
      router.push("/dashboard");
    },
    [router]
  );

  const logout = useCallback(() => {
    clearStoredToken();
    setUser(null);
    router.push("/login");
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
