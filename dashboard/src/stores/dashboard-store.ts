import { create } from "zustand";
import type { DashboardView } from "@/types/dashboard";

export interface Workspace {
  id: string;
  name: string;
  color: string;
}

const DEFAULT_WORKSPACES: Workspace[] = [
  { id: "default", name: "Production", color: "#4cb782" },
];

interface DashboardState {
  activeView: DashboardView;
  sidebarOpen: boolean;
  token: string | null;
  userEmail: string | null;
  userRole: string | null;
  workspaces: Workspace[];
  activeWorkspace: string;
  setActiveView: (view: DashboardView) => void;
  toggleSidebar: () => void;
  setToken: (token: string | null) => void;
  setUser: (email: string, role: string) => void;
  addWorkspace: (ws: Workspace) => void;
  removeWorkspace: (id: string) => void;
  setActiveWorkspace: (id: string) => void;
  logout: () => void;
}

function loadWorkspaces(): Workspace[] {
  if (typeof window === "undefined") return DEFAULT_WORKSPACES;
  try {
    const raw = localStorage.getItem("nso_workspaces");
    return raw ? JSON.parse(raw) : DEFAULT_WORKSPACES;
  } catch { return DEFAULT_WORKSPACES; }
}

function saveWorkspaces(ws: Workspace[]) {
  localStorage.setItem("nso_workspaces", JSON.stringify(ws));
}

export const useDashboardStore = create<DashboardState>((set, get) => ({
  activeView: "overview",
  sidebarOpen: true,
  token: typeof window !== "undefined" ? localStorage.getItem("nso_token") : null,
  userEmail: typeof window !== "undefined" ? localStorage.getItem("nso_email") : null,
  userRole: typeof window !== "undefined" ? localStorage.getItem("nso_role") : null,
  workspaces: loadWorkspaces(),
  activeWorkspace: typeof window !== "undefined"
    ? localStorage.getItem("nso_active_ws") || "default"
    : "default",
  setActiveView: (view) => set({ activeView: view }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setToken: (token) => {
    if (token) {
      localStorage.setItem("nso_token", token);
    } else {
      localStorage.removeItem("nso_token");
    }
    set({ token });
  },
  setUser: (email, role) => {
    localStorage.setItem("nso_email", email);
    localStorage.setItem("nso_role", role);
    set({ userEmail: email, userRole: role });
  },
  addWorkspace: (ws) => {
    const updated = [...get().workspaces, ws];
    saveWorkspaces(updated);
    set({ workspaces: updated });
  },
  removeWorkspace: (id) => {
    const updated = get().workspaces.filter((w) => w.id !== id);
    saveWorkspaces(updated);
    const active = get().activeWorkspace === id ? (updated[0]?.id || "default") : get().activeWorkspace;
    localStorage.setItem("nso_active_ws", active);
    set({ workspaces: updated, activeWorkspace: active });
  },
  setActiveWorkspace: (id) => {
    localStorage.setItem("nso_active_ws", id);
    set({ activeWorkspace: id });
  },
  logout: () => {
    localStorage.removeItem("nso_token");
    localStorage.removeItem("nso_email");
    localStorage.removeItem("nso_role");
    set({ token: null, userEmail: null, userRole: null });
  },
}));
