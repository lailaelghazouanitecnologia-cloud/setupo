"use client";

import React from "react";
import {
  BarChart3, Users, TrendingUp, Shield, Link2, ArrowDownUp,
  LogOut, Sun, Moon, X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAdminStore, type AdminView } from "@/stores/admin-store";
import { adminLogout } from "@/lib/api/client";
import { AdminPanel } from "./admin-panel";

const navItems: { id: AdminView; label: string; icon: React.ElementType }[] = [
  { id: "overview", label: "Overview", icon: BarChart3 },
  { id: "users", label: "Users", icon: Users },
  { id: "cashflow", label: "Cashflow", icon: ArrowDownUp },
  { id: "analytics", label: "Analytics", icon: TrendingUp },
  { id: "fraud", label: "Fraud", icon: Shield },
  { id: "ledger", label: "Ledger", icon: Link2 },
];

const viewTitles: Record<AdminView, string> = {
  overview: "Overview",
  users: "Users",
  cashflow: "Cashflow",
  analytics: "Analytics",
  fraud: "Fraud Detection",
  ledger: "Blockchain Ledger",
};

function SonfaztLogo({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" fill="currentColor">
      <path d="M1.225 61.523c-.222-.949.908-1.546 1.597-.857L39.334 97.178c.689.689.092 1.819-.857 1.597C20.052 94.452 5.548 79.949 1.225 61.523zM.002 46.889a1.073 1.073 0 01.29.761L52.35 99.709c.2.2.477.307.76.289a43.36 43.36 0 006.963-.926c.764-.157 1.03-1.096.478-1.648L2.576 39.449c-.552-.552-1.491-.287-1.648.478a43.36 43.36 0 00-.926 6.962zM4.211 29.705a.993.993 0 01.208 1.1l64.776 64.776c.29.29.726.374 1.1.208a43.1 43.1 0 005.186-2.684c.552-.328.637-1.087.183-1.541L8.436 24.337c-.454-.454-1.213-.369-1.541.183a43.1 43.1 0 00-2.684 5.186zM12.659 18.074c-.37-.37-.393-.964-.044-1.354A49.93 49.93 0 0149.952 0C77.593 0 100 22.407 100 50.048a49.93 49.93 0 01-16.72 37.338c-.39.349-.984.326-1.354-.044L12.659 18.074z" />
    </svg>
  );
}

const IC_Menu = () => (
  <svg width="16" height="14" viewBox="0 0 16 14" fill="currentColor">
    <rect y="0" width="16" height="2" rx="1" />
    <rect y="6" width="16" height="2" rx="1" />
    <rect y="12" width="16" height="2" rx="1" />
  </svg>
);

export function AdminDashboard() {
  const activeView = useAdminStore((s) => s.activeView);
  const setActiveView = useAdminStore((s) => s.setActiveView);
  const sidebarOpen = useAdminStore((s) => s.sidebarOpen);
  const toggleSidebar = useAdminStore((s) => s.toggleSidebar);
  const userEmail = useAdminStore((s) => s.userEmail);
  const theme = useAdminStore((s) => s.theme);
  const setTheme = useAdminStore((s) => s.setTheme);
  const logout = useAdminStore((s) => s.logout);

  const handleLogout = () => {
    adminLogout();
    logout();
  };

  return (
    <div style={{ height: "100vh", overflow: "hidden", position: "relative" }}>
      {/* ════ ACTIVATION STRIP ════ */}
      <div
        className={cn("activation-strip", sidebarOpen && "shifted")}
        onClick={toggleSidebar}
      >
        <IC_Menu />
      </div>

      {/* ════ HEADER ════ */}
      <header className={cn("fheader", sidebarOpen && "shifted")}>
        <div className="fheader-left">
          {!sidebarOpen && (
            <button className="ibtn" onClick={toggleSidebar} aria-label="Open sidebar">
              <IC_Menu />
            </button>
          )}
          <span className="fheader-title">{viewTitles[activeView]}</span>
        </div>
        <div className="fheader-right">
          <span style={{ fontSize: 11, color: "var(--muted-foreground)" }}>
            {userEmail}
          </span>
        </div>
      </header>

      {/* ════ SIDEBAR ════ */}
      <aside className={cn("fsidebar", sidebarOpen && "visible")}>
        <div className="fsidebar-header">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <SonfaztLogo />
            <span style={{ fontSize: 14, fontWeight: 600 }}>Sonfazt</span>
          </div>
          <button className="ibtn" onClick={toggleSidebar} aria-label="Close sidebar">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        <nav className="fsidebar-nav">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={cn("fmenu", activeView === item.id && "active")}
              onClick={() => setActiveView(item.id)}
            >
              <item.icon className="h-3.5 w-3.5" />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <div style={{ flex: 1 }} />

        {/* Bottom controls */}
        <div style={{ padding: "10px 14px", display: "flex", flexDirection: "column", gap: 4 }}>
          <button
            className="fmenu"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
            <span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>
          </button>
          <button className="fmenu" onClick={handleLogout} style={{ color: "var(--color-red)" }}>
            <LogOut className="h-3.5 w-3.5" />
            <span>Log out</span>
          </button>
        </div>
      </aside>

      {/* ════ MAIN CONTENT ════ */}
      <div className={cn("fmain", sidebarOpen && "shifted")}>
        <div className="fmain-content">
          <AdminPanel tab={activeView} />
        </div>
      </div>
    </div>
  );
}
