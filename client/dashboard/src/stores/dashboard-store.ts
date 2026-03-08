import { create } from "zustand";
import type { DashboardView } from "@/types/dashboard";

export type Theme = "dark" | "light" | "auto";

export interface ProjectInfo {
  id: string;
  name: string;
  api_key_hash?: string;
  owner?: string;
  created_at?: string;
}

export interface WorkspaceInfo {
  id: string;
  name: string;
  path: string;
  description: string;
  instance_id?: string | null;
  ws_type?: string;
  stack?: string;
  exists?: boolean;
  deployed?: boolean;
  deploy_url?: string | null;
  instance_label?: string | null;
  instance_ip?: string | null;
  instance_state?: string | null;
}

interface DashboardState {
  activeView: DashboardView;
  sidebarOpen: boolean;
  token: string | null;
  userEmail: string | null;
  userRole: string | null;
  theme: Theme;

  // Project & workspace context
  projects: ProjectInfo[];
  activeProject: ProjectInfo | null;
  workspaces: WorkspaceInfo[];
  activeWorkspace: WorkspaceInfo | null;
  projectLoading: boolean;

  setActiveView: (view: DashboardView) => void;
  toggleSidebar: () => void;
  setToken: (token: string | null) => void;
  setUser: (email: string, role: string) => void;
  setTheme: (theme: Theme) => void;
  logout: () => void;

  setProjects: (projects: ProjectInfo[]) => void;
  setActiveProject: (project: ProjectInfo | null) => void;
  setWorkspaces: (workspaces: WorkspaceInfo[]) => void;
  setActiveWorkspace: (workspace: WorkspaceInfo | null) => void;
  setProjectLoading: (loading: boolean) => void;
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

export const useDashboardStore = create<DashboardState>((set, get) => ({
  activeView: "inbox",
  sidebarOpen: true,
  token: getInitialToken(),
  userEmail: typeof window !== "undefined" ? localStorage.getItem("nso_email") : null,
  userRole: typeof window !== "undefined" ? localStorage.getItem("nso_role") : null,
  theme: getInitialTheme(),

  projects: [],
  activeProject: null,
  workspaces: [],
  activeWorkspace: null,
  projectLoading: true,

  setActiveView: (view) => set({ activeView: view }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setToken: (token) => {
    if (token) {
      localStorage.setItem("nso_api_token", token);
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
    set({ token: null, userEmail: null, userRole: null, projects: [], activeProject: null, workspaces: [], activeWorkspace: null });
  },

  setProjects: (projects) => set({ projects }),
  setActiveProject: (project) => {
    if (project) localStorage.setItem("nso_active_project", project.id);
    else localStorage.removeItem("nso_active_project");
    set({ activeProject: project });
  },
  setWorkspaces: (workspaces) => set({ workspaces }),
  setActiveWorkspace: (workspace) => {
    if (workspace) localStorage.setItem("nso_active_workspace", workspace.id);
    else localStorage.removeItem("nso_active_workspace");
    set({ activeWorkspace: workspace });
  },
  setProjectLoading: (loading) => set({ projectLoading: loading }),
}));

// Listen for session expiry from API client — triggers clean logout without page reload
if (typeof window !== "undefined") {
  window.addEventListener("nso:session-expired", () => {
    useDashboardStore.getState().logout();
  });
}

/** Restore active project/workspace from localStorage after projects are loaded */
export function restoreActiveSelections(projects: ProjectInfo[], workspaces: WorkspaceInfo[]) {
  const store = useDashboardStore.getState();
  const savedProjectId = localStorage.getItem("nso_active_project");
  if (savedProjectId && !store.activeProject) {
    const match = projects.find((p) => p.id === savedProjectId);
    if (match) store.setActiveProject(match);
    else localStorage.removeItem("nso_active_project");
  }
  const savedWorkspaceId = localStorage.getItem("nso_active_workspace");
  if (savedWorkspaceId && !store.activeWorkspace) {
    const match = workspaces.find((w) => w.id === savedWorkspaceId);
    if (match) store.setActiveWorkspace(match);
    else localStorage.removeItem("nso_active_workspace");
  }
}
