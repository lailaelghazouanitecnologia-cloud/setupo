"use client";

import React, { useEffect, useState } from "react";
import {
  LayoutDashboard, Server, FolderOpen, Terminal, Settings,
  Plus, Search, ChevronUp, ChevronDown, X, LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useDashboardStore } from "@/stores/dashboard-store";
import { getApiHealth, getAgentHealth } from "@/lib/api/client";
import { OverviewPanel } from "./overview-panel";
import { InstancesPanel } from "./instances-panel";
import { FilesPanel } from "./files-panel";
import { TerminalPanel } from "./terminal-panel";
import { SettingsPanel } from "./settings-panel";
import type { DashboardView } from "@/types/dashboard";

const IC_Menu = () => (
  <svg width="16" height="14" viewBox="0 0 16 14" fill="currentColor">
    <rect y="0" width="16" height="2" rx="1" />
    <rect y="6" width="16" height="2" rx="1" />
    <rect y="12" width="16" height="2" rx="1" />
  </svg>
);

function SetupLogo() {
  return (
    <svg width="13" height="13" viewBox="0 0 100 100" fill="currentColor">
      <path d="M1.225 61.523c-.222-.949.908-1.546 1.597-.857L39.334 97.178c.689.689.092 1.819-.857 1.597C20.052 94.452 5.548 79.949 1.225 61.523zM.002 46.889a1.073 1.073 0 01.29.761L52.35 99.709c.2.2.477.307.76.289a43.36 43.36 0 006.963-.926c.764-.157 1.03-1.096.478-1.648L2.576 39.449c-.552-.552-1.491-.287-1.648.478a43.36 43.36 0 00-.926 6.962zM4.211 29.705a.993.993 0 01.208 1.1l64.776 64.776c.29.29.726.374 1.1.208a43.1 43.1 0 005.186-2.684c.552-.328.637-1.087.183-1.541L8.436 24.337c-.454-.454-1.213-.369-1.541.183a43.1 43.1 0 00-2.684 5.186zM12.659 18.074c-.37-.37-.393-.964-.044-1.354A49.93 49.93 0 0149.952 0C77.593 0 100 22.407 100 50.048a49.93 49.93 0 01-16.72 37.338c-.39.349-.984.326-1.354-.044L12.659 18.074z" />
    </svg>
  );
}

const GRADIENTS = [
  "linear-gradient(135deg, #3b82f6, #2563eb)",
  "linear-gradient(135deg, #4cb782, #36946a)",
  "linear-gradient(135deg, #f2c94c, #e6b800)",
  "linear-gradient(135deg, #e74c3c, #c0392b)",
  "linear-gradient(135deg, #8b5cf6, #7c3aed)",
];

function Avatar({ name, size = 14 }: { name: string; size?: number }) {
  const idx = [...(name || "")].reduce((a, c) => a + c.charCodeAt(0), 0) % GRADIENTS.length;
  return (
    <div className="fav" style={{ width: size, height: size, background: GRADIENTS[idx], fontSize: size * 0.48 }}>
      {(name || "?")[0].toUpperCase()}
    </div>
  );
}

const navItems: { id: DashboardView; label: string; icon: React.ElementType }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "instances", label: "Instances", icon: Server },
  { id: "files", label: "Files", icon: FolderOpen },
  { id: "terminal", label: "Terminal", icon: Terminal },
  { id: "settings", label: "Settings", icon: Settings },
];

const viewTitles: Record<DashboardView, string> = {
  overview: "Overview",
  instances: "Instances",
  files: "Files",
  terminal: "Terminal",
  settings: "Settings",
};

const viewDescriptions: Record<DashboardView, string> = {
  overview: "System overview — API status, services, and infrastructure health.",
  instances: "VPS instances — create, manage, and monitor your servers.",
  files: "Browse and edit files on your VPS remotely.",
  terminal: "Execute commands on your VPS via the agent.",
  settings: "System configuration and service management.",
};

export function DashboardLayout() {
  const activeView = useDashboardStore((s) => s.activeView);
  const setActiveView = useDashboardStore((s) => s.setActiveView);
  const sidebarOpen = useDashboardStore((s) => s.sidebarOpen);
  const toggleSidebar = useDashboardStore((s) => s.toggleSidebar);
  const logout = useDashboardStore((s) => s.logout);

  const [apiHealth, setApiHealth] = useState<any>(null);
  const [agentHealth, setAgentHealth] = useState<any>(null);

  useEffect(() => {
    getApiHealth().then(setApiHealth).catch(() => {});
    getAgentHealth().then(setAgentHealth).catch(() => {});
  }, []);

  const viewKeys = navItems.map((n) => n.id);
  const currentIdx = viewKeys.indexOf(activeView);

  return (
    <div style={{ height: "100vh", overflow: "hidden", position: "relative" }}>
      {/* Header */}
      <header className={cn("fheader", sidebarOpen && "shifted")}>
        <div className="fheader-left">
          {!sidebarOpen && (
            <button className="ibtn" onClick={toggleSidebar}><IC_Menu /></button>
          )}
          <span style={{ fontSize: 13, fontWeight: 600 }}>{viewTitles[activeView]}</span>
          <span style={{ fontSize: "var(--font-sm)", color: "var(--muted-foreground)" }}>
            setupo dashboard
          </span>
        </div>
        <div className="fheader-right">
          <span style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)" }}>
            <span style={{ color: "var(--foreground)" }}>{String(currentIdx + 1).padStart(2, "0")}</span>
            {" / "}{viewKeys.length}
          </span>
          <div className="fheader-sep" />
          <button className="ibtn" onClick={() => {
            const prev = currentIdx > 0 ? currentIdx - 1 : viewKeys.length - 1;
            setActiveView(viewKeys[prev]);
          }}><ChevronUp className="h-3.5 w-3.5" /></button>
          <button className="ibtn" onClick={() => {
            const next = currentIdx < viewKeys.length - 1 ? currentIdx + 1 : 0;
            setActiveView(viewKeys[next]);
          }}><ChevronDown className="h-3.5 w-3.5" /></button>
          <div className="fheader-sep" />
          <button className="ibtn"><Search className="h-3.5 w-3.5" /></button>
          <Avatar name="admin" size={21} />
        </div>
      </header>

      {/* Sidebar */}
      <aside className={cn("fsidebar", sidebarOpen && "visible")}>
        <div className="fsidebar-header">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <SetupLogo />
            <span style={{ fontSize: 14, fontWeight: 600 }}>setupo</span>
          </div>
          <button className="ibtn" onClick={toggleSidebar}><X className="h-3.5 w-3.5" /></button>
        </div>
        <div className="fsidebar-content">
          <button className="task-btn" onClick={() => setActiveView("instances")}>
            <Plus className="h-3.5 w-3.5" /><span>New instance</span>
          </button>

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

          {/* Status */}
          <div style={{ marginTop: "auto", paddingTop: 12, borderTop: "1px solid var(--sidebar-border)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 8px" }}>
              <div style={{
                width: 6, height: 6, borderRadius: "50%",
                background: apiHealth ? "var(--color-green)" : "var(--color-red)",
              }} />
              <span style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)" }}>
                API {apiHealth ? "online" : "offline"}
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 8px" }}>
              <div style={{
                width: 6, height: 6, borderRadius: "50%",
                background: agentHealth ? "var(--color-green)" : "var(--color-red)",
              }} />
              <span style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)" }}>
                Agent {agentHealth ? "online" : "offline"}
              </span>
            </div>
            <button className="fmenu" onClick={logout} style={{ marginTop: 8 }}>
              <LogOut className="h-3.5 w-3.5" /><span>Sign out</span>
            </button>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className={cn("fmain", sidebarOpen && "shifted")}>
        <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
          <div className="issue-body">
            <div style={{ fontSize: "var(--font-xl)", fontWeight: 500, marginBottom: 4 }}>
              {viewTitles[activeView]}
            </div>
            <div style={{ fontSize: "var(--font-md)", color: "var(--muted-foreground)", maxWidth: 600, lineHeight: 1.65, marginBottom: 22 }}>
              {viewDescriptions[activeView]}
            </div>

            {activeView === "overview" && <OverviewPanel apiHealth={apiHealth} agentHealth={agentHealth} />}
            {activeView === "instances" && <InstancesPanel />}
            {activeView === "files" && <FilesPanel />}
            {activeView === "terminal" && <TerminalPanel />}
            {activeView === "settings" && <SettingsPanel />}
          </div>
        </div>
      </div>
    </div>
  );
}
