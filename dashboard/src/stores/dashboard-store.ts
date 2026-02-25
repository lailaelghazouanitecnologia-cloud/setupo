import { create } from "zustand";
import type { DashboardView } from "@/types/dashboard";

interface DashboardState {
  activeView: DashboardView;
  sidebarOpen: boolean;
  token: string | null;
  setActiveView: (view: DashboardView) => void;
  toggleSidebar: () => void;
  setToken: (token: string | null) => void;
  logout: () => void;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  activeView: "overview",
  sidebarOpen: true,
  token: typeof window !== "undefined" ? localStorage.getItem("setupo_token") : null,
  setActiveView: (view) => set({ activeView: view }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setToken: (token) => {
    if (token) {
      localStorage.setItem("setupo_token", token);
    } else {
      localStorage.removeItem("setupo_token");
    }
    set({ token });
  },
  logout: () => {
    localStorage.removeItem("setupo_token");
    set({ token: null });
  },
}));
