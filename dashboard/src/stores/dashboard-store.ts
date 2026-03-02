import { create } from "zustand";
import type { DashboardView } from "@/types/dashboard";

export type Theme = "dark" | "light" | "auto";

export interface Workspace {
  id: string;
  name: string;
  color: string;
}

interface DashboardState {
  activeView: DashboardView;
  sidebarOpen: boolean;
  token: string | null;
  userEmail: string | null;
  userRole: string | null;
  theme: Theme;
  setActiveView: (view: DashboardView) => void;
  toggleSidebar: () => void;
  setToken: (token: string | null) => void;
  setUser: (email: string, role: string) => void;
  setTheme: (theme: Theme) => void;
  logout: () => void;
}

function getInitialToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("nso_api_token") || localStorage.getItem("nso_token") || null;
}

function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  return (localStorage.getItem("nso_theme") as Theme) || "dark";
}

function applyTheme(theme: Theme) {
  if (typeof window === "undefined") return;
  const root = document.documentElement;
  if (theme === "auto") {
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    root.classList.toggle("dark", prefersDark);
  } else {
    root.classList.toggle("dark", theme === "dark");
  }
}

export const useDashboardStore = create<DashboardState>((set) => ({
  activeView: "inbox",
  sidebarOpen: true,
  token: getInitialToken(),
  userEmail: typeof window !== "undefined" ? localStorage.getItem("nso_email") : null,
  userRole: typeof window !== "undefined" ? localStorage.getItem("nso_role") : null,
  theme: getInitialTheme(),
  setActiveView: (view) => set({ activeView: view }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setToken: (token) => {
    if (token) {
      localStorage.setItem("nso_api_token", token);
      // Don't overwrite nso_token (agent JWT) — it's set separately by login()
    } else {
      localStorage.removeItem("nso_api_token");
      localStorage.removeItem("nso_token");
    }
    set({ token });
  },
  setUser: (email, role) => {
    localStorage.setItem("nso_email", email);
    localStorage.setItem("nso_role", role);
    set({ userEmail: email, userRole: role });
  },
  setTheme: (theme) => {
    localStorage.setItem("nso_theme", theme);
    applyTheme(theme);
    set({ theme });
  },
  logout: () => {
    localStorage.removeItem("nso_token");
    localStorage.removeItem("nso_api_token");
    localStorage.removeItem("nso_email");
    localStorage.removeItem("nso_role");
    set({ token: null, userEmail: null, userRole: null });
  },
}));
