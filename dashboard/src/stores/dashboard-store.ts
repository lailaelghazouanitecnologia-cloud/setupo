import { create } from "zustand";
import type { DashboardView } from "@/types/dashboard";

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
  setActiveView: (view: DashboardView) => void;
  toggleSidebar: () => void;
  setToken: (token: string | null) => void;
  setUser: (email: string, role: string) => void;
  logout: () => void;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  activeView: "inbox",
  sidebarOpen: true,
  token: typeof window !== "undefined" ? localStorage.getItem("nso_token") : null,
  userEmail: typeof window !== "undefined" ? localStorage.getItem("nso_email") : null,
  userRole: typeof window !== "undefined" ? localStorage.getItem("nso_role") : null,
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
  logout: () => {
    localStorage.removeItem("nso_token");
    localStorage.removeItem("nso_email");
    localStorage.removeItem("nso_role");
    set({ token: null, userEmail: null, userRole: null });
  },
}));
