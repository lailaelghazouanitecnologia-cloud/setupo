import { create } from "zustand";
import type { DashboardView } from "@/types/dashboard";

export type Theme = "dark" | "light" | "auto";

interface Z86State {
  activeView: DashboardView;
  sidebarOpen: boolean;
  token: string | null;
  userEmail: string | null;
  userRole: string | null;
  theme: Theme;

  // Storage context
  projectId: string | null;
  bucketName: string | null;
  accessKeyId: string | null;

  setActiveView: (view: DashboardView) => void;
  toggleSidebar: () => void;
  setToken: (token: string | null) => void;
  setUser: (email: string, role: string) => void;
  setTheme: (theme: Theme) => void;
  logout: () => void;
  setProjectId: (id: string | null) => void;
  setBucketName: (name: string | null) => void;
  setAccessKeyId: (id: string | null) => void;
}

function getInitialToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("z86_token") || null;
}

function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  return (localStorage.getItem("z86_theme") as Theme) || "dark";
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

export const useZ86Store = create<Z86State>((set) => ({
  activeView: "overview",
  sidebarOpen: true,
  token: getInitialToken(),
  userEmail: typeof window !== "undefined" ? localStorage.getItem("z86_email") : null,
  userRole: typeof window !== "undefined" ? localStorage.getItem("z86_role") : null,
  theme: getInitialTheme(),

  projectId: typeof window !== "undefined" ? localStorage.getItem("z86_project_id") : null,
  bucketName: typeof window !== "undefined" ? localStorage.getItem("z86_bucket") : null,
  accessKeyId: typeof window !== "undefined" ? localStorage.getItem("z86_access_key") : null,

  setActiveView: (view) => set({ activeView: view }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setToken: (token) => {
    if (token) localStorage.setItem("z86_token", token);
    else localStorage.removeItem("z86_token");
    set({ token });
  },
  setUser: (email, role) => {
    localStorage.setItem("z86_email", email);
    localStorage.setItem("z86_role", role);
    set({ userEmail: email, userRole: role });
  },
  setTheme: (theme) => {
    localStorage.setItem("z86_theme", theme);
    applyTheme(theme);
    set({ theme });
  },
  logout: () => {
    localStorage.removeItem("z86_token");
    localStorage.removeItem("z86_email");
    localStorage.removeItem("z86_role");
    localStorage.removeItem("z86_project_id");
    localStorage.removeItem("z86_bucket");
    localStorage.removeItem("z86_access_key");
    set({ token: null, userEmail: null, userRole: null, projectId: null, bucketName: null, accessKeyId: null });
  },
  setProjectId: (id) => {
    if (id) localStorage.setItem("z86_project_id", id);
    else localStorage.removeItem("z86_project_id");
    set({ projectId: id });
  },
  setBucketName: (name) => {
    if (name) localStorage.setItem("z86_bucket", name);
    else localStorage.removeItem("z86_bucket");
    set({ bucketName: name });
  },
  setAccessKeyId: (id) => {
    if (id) localStorage.setItem("z86_access_key", id);
    else localStorage.removeItem("z86_access_key");
    set({ accessKeyId: id });
  },
}));
