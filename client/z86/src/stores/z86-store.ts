import { create } from "zustand";

interface Z86State {
  token: string | null;
  user: { id: string; email: string; name: string; plan: string } | null;
  view: "landing" | "login" | "register" | "dashboard";
  panel: "overview" | "buckets" | "objects" | "keys" | "usage" | "settings";
  activeBucket: string | null;
  setToken: (t: string | null) => void;
  setUser: (u: Z86State["user"]) => void;
  setView: (v: Z86State["view"]) => void;
  setPanel: (p: Z86State["panel"]) => void;
  setActiveBucket: (b: string | null) => void;
  logout: () => void;
}

function getInit<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const v = localStorage.getItem(key);
    return v ? JSON.parse(v) : fallback;
  } catch {
    return fallback;
  }
}

export const useZ86Store = create<Z86State>((set) => ({
  token: typeof window !== "undefined" ? localStorage.getItem("z86_token") : null,
  user: getInit("z86_user", null),
  view: typeof window !== "undefined" && localStorage.getItem("z86_token") ? "dashboard" : "landing",
  panel: "overview",
  activeBucket: null,

  setToken: (t) => {
    if (t) localStorage.setItem("z86_token", t);
    else localStorage.removeItem("z86_token");
    set({ token: t });
  },
  setUser: (u) => {
    if (u) localStorage.setItem("z86_user", JSON.stringify(u));
    else localStorage.removeItem("z86_user");
    set({ user: u });
  },
  setView: (v) => set({ view: v }),
  setPanel: (p) => set({ panel: p, activeBucket: p !== "objects" ? null : undefined }),
  setActiveBucket: (b) => set({ activeBucket: b, panel: "objects" }),
  logout: () => {
    localStorage.removeItem("z86_token");
    localStorage.removeItem("z86_user");
    set({ token: null, user: null, view: "landing", panel: "overview", activeBucket: null });
  },
}));
