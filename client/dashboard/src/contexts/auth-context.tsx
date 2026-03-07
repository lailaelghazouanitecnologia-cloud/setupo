"use client";

import React, { createContext, useContext, useCallback, useEffect, useState, type ReactNode } from "react";
import { login as apiLogin, register as apiRegister, getMe } from "@/lib/api/client";

// ── Types ──────────────────────────────────────────────────

export interface AuthUser {
  email: string;
  role: string;
  name?: string;
  id?: string;
}

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  loading: boolean;
  initialized: boolean;
}

interface AuthActions {
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

type AuthContextValue = AuthState & AuthActions;

// ── Context ────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}

// ── Helpers ────────────────────────────────────────────────

function loadToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("nso_api_token") || localStorage.getItem("nso_token") || null;
}

function loadUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const email = localStorage.getItem("nso_email");
  const role = localStorage.getItem("nso_role");
  if (email && role) return { email, role };
  return null;
}

function persistAuth(token: string, user: AuthUser) {
  localStorage.setItem("nso_api_token", token);
  localStorage.setItem("nso_email", user.email);
  localStorage.setItem("nso_role", user.role);
}

function clearAuth() {
  localStorage.removeItem("nso_token");
  localStorage.removeItem("nso_api_token");
  localStorage.removeItem("nso_email");
  localStorage.removeItem("nso_role");
}

// ── Provider ───────────────────────────────────────────────

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    token: null,
    loading: false,
    initialized: false,
  });

  // Restore from localStorage on mount
  useEffect(() => {
    const token = loadToken();
    const user = loadUser();
    setState({ token, user, loading: false, initialized: true });
  }, []);

  // Listen for session expiry from API client
  useEffect(() => {
    function handleExpired() {
      clearAuth();
      setState((s) => ({ ...s, user: null, token: null }));
    }
    window.addEventListener("nso:session-expired", handleExpired);
    return () => window.removeEventListener("nso:session-expired", handleExpired);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setState((s) => ({ ...s, loading: true }));
    try {
      const res = await apiLogin(email, password);
      const user: AuthUser = { email: res.email, role: res.role };
      persistAuth(res.token, user);
      setState((s) => ({ ...s, user, token: res.token, loading: false }));
    } catch (err) {
      setState((s) => ({ ...s, loading: false }));
      throw err;
    }
  }, []);

  const register = useCallback(async (email: string, password: string, name?: string) => {
    setState((s) => ({ ...s, loading: true }));
    try {
      const res = await apiRegister(email, password, name);
      const user: AuthUser = { email: res.email, role: res.role };
      persistAuth(res.token, user);
      setState((s) => ({ ...s, user, token: res.token, loading: false }));
    } catch (err) {
      setState((s) => ({ ...s, loading: false }));
      throw err;
    }
  }, []);

  const logout = useCallback(() => {
    clearAuth();
    setState((s) => ({ ...s, user: null, token: null }));
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const me = await getMe();
      const user: AuthUser = { email: me.email, role: me.role, name: me.name, id: me.id };
      setState((s) => ({ ...s, user }));
    } catch {
      // If token is invalid, logout
      clearAuth();
      setState((s) => ({ ...s, user: null, token: null }));
    }
  }, []);

  const value: AuthContextValue = {
    ...state,
    login,
    register,
    logout,
    refreshUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
