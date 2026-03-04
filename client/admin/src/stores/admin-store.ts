import { create } from "zustand";

export type Theme = "dark" | "light" | "auto";
export type AdminView = "overview" | "users" | "infra" | "cashflow" | "analytics" | "fraud" | "ledger";

interface AdminState {
  token: string | null;
  userEmail: string | null;
  theme: Theme;
  sidebarOpen: boolean;
  activeView: AdminView;
  setToken: (token: string | null) => void;
  setUser: (email: string) => void;
  setTheme: (theme: Theme) => void;
  toggleSidebar: () => void;
  setActiveView: (view: AdminView) => void;
  logout: () => void;
}

function getInitialToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("sonfazt_token") || null;
}

function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  return (localStorage.getItem("sonfazt_theme") as Theme) || "dark";
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

export const useAdminStore = create<AdminState>((set) => ({
  token: getInitialToken(),
  userEmail: typeof window !== "undefined" ? localStorage.getItem("sonfazt_email") : null,
  theme: getInitialTheme(),
  sidebarOpen: true,
  activeView: "overview",
  setToken: (token) => {
    if (token) {
      localStorage.setItem("sonfazt_token", token);
    } else {
      localStorage.removeItem("sonfazt_token");
    }
    set({ token });
  },
  setUser: (email) => {
    localStorage.setItem("sonfazt_email", email);
    set({ userEmail: email });
  },
  setTheme: (theme) => {
    localStorage.setItem("sonfazt_theme", theme);
    applyTheme(theme);
    set({ theme });
  },
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setActiveView: (view) => set({ activeView: view }),
  logout: () => {
    localStorage.removeItem("sonfazt_token");
    localStorage.removeItem("sonfazt_email");
    set({ token: null, userEmail: null });
  },
}));
