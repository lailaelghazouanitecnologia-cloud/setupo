"use client";

import React, { createContext, useContext, useCallback, useEffect, useState, type ReactNode } from "react";
import { adminLogin as apiLogin, adminLogout as apiLogout } from "@/lib/api/client";

// ── Types ──────────────────────────────────────────────────

export interface AdminUser {
  email: string;
  role: string;
}

interface AdminAuthState {
  user: AdminUser | null;
  token: string | null;
  loading: boolean;
  initialized: boolean;
}

interface AdminAuthActions {
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

type AdminAuthContextValue = AdminAuthState & AdminAuthActions;

// ── Context ────────────────────────────────────────────────

const AdminAuthContext = createContext<AdminAuthContextValue | null>(null);

export function useAdminAuth(): AdminAuthContextValue {
  const ctx = useContext(AdminAuthContext);
  if (!ctx) throw new Error("useAdminAuth must be used within <AdminAuthProvider>");
  return ctx;
}

// ── Helpers ────────────────────────────────────────────────

function loadToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("sonfazt_token") || null;
}

function loadUser(): AdminUser | null {
  if (typeof window === "undefined") return null;
  const email = localStorage.getItem("sonfazt_email");
  if (email) return { email, role: "admin" };
  return null;
}

function persistAuth(token: string, email: string) {
  localStorage.setItem("sonfazt_token", token);
  localStorage.setItem("sonfazt_email", email);
}

function clearAuth() {
  localStorage.removeItem("sonfazt_token");
  localStorage.removeItem("sonfazt_email");
  localStorage.removeItem("sonfazt_role");
}

// ── Provider ───────────────────────────────────────────────

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AdminAuthState>({
    user: null,
    token: null,
    loading: false,
    initialized: false,
  });

  useEffect(() => {
    const token = loadToken();
    const user = loadUser();
    setState({ token, user, loading: false, initialized: true });
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setState((s) => ({ ...s, loading: true }));
    try {
      const res = await apiLogin(email, password);
      const user: AdminUser = { email: res.email, role: "admin" };
      persistAuth(res.token, res.email);
      setState((s) => ({ ...s, user, token: res.token, loading: false }));
    } catch (err) {
      setState((s) => ({ ...s, loading: false }));
      throw err;
    }
  }, []);

  const logout = useCallback(() => {
    apiLogout();
    clearAuth();
    setState((s) => ({ ...s, user: null, token: null }));
  }, []);

  const value: AdminAuthContextValue = { ...state, login, logout };

  return <AdminAuthContext.Provider value={value}>{children}</AdminAuthContext.Provider>;
}
