"use client";

import React, { useEffect, useState, useRef } from "react";
import {
  LayoutDashboard, Server, FolderOpen, Terminal, Settings,
  X, LogOut, ChevronDown, Plus, Circle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useDashboardStore, type Workspace } from "@/stores/dashboard-store";
import { getApiHealth, getAgentHealth } from "@/lib/api/client";
import { OverviewPanel } from "./overview-panel";
import { InstancesPanel } from "./instances-panel";
import { FilesPanel } from "./files-panel";
import { TerminalPanel } from "./terminal-panel";
import { SettingsPanel } from "./settings-panel";
import type { DashboardView } from "@/types/dashboard";

/* ═══════════════════════════════════════════
   ICONS
   ═══════════════════════════════════════════ */
function NsoLogo({ size = 16 }: { size?: number }) {
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

/* ═══════════════════════════════════════════
   NAV CONFIG
   ═══════════════════════════════════════════ */
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

const WS_COLORS = ["#4cb782", "#3b82f6", "#f2c94c", "#a78bfa", "#02b8cc", "#e5484d", "#f59e0b"];

/* ═══════════════════════════════════════════
   WORKSPACE SWITCHER
   ═══════════════════════════════════════════ */
function WorkspaceSection() {
  const workspaces = useDashboardStore((s) => s.workspaces);
  const activeWorkspace = useDashboardStore((s) => s.activeWorkspace);
  const setActiveWorkspace = useDashboardStore((s) => s.setActiveWorkspace);
  const addWorkspace = useDashboardStore((s) => s.addWorkspace);
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (adding && inputRef.current) inputRef.current.focus();
  }, [adding]);

  function handleAdd() {
    const name = newName.trim();
    if (!name) { setAdding(false); return; }
    const id = name.toLowerCase().replace(/\s+/g, "-") + "-" + Date.now().toString(36);
    const color = WS_COLORS[workspaces.length % WS_COLORS.length];
    addWorkspace({ id, name, color });
    setNewName("");
    setAdding(false);
  }

  return (
    <div className="fsidebar-section">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 8px 6px" }}>
        <span className="fsidebar-section-title" style={{ padding: 0, marginBottom: 0 }}>Workspaces</span>
        <button
          className="ibtn"
          style={{ width: 18, height: 18 }}
          onClick={() => setAdding(true)}
          aria-label="Add workspace"
        >
          <Plus className="h-3 w-3" />
        </button>
      </div>
      {workspaces.map((ws) => (
        <button
          key={ws.id}
          className={cn("fmenu", activeWorkspace === ws.id && "active")}
          onClick={() => setActiveWorkspace(ws.id)}
        >
          <Circle className="h-2.5 w-2.5" style={{ color: ws.color, fill: ws.color }} />
          <span>{ws.name}</span>
        </button>
      ))}
      {adding && (
        <div style={{ padding: "2px 8px" }}>
          <input
            ref={inputRef}
            className="ws-input"
            type="text"
            placeholder="Workspace name..."
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleAdd(); if (e.key === "Escape") { setAdding(false); setNewName(""); } }}
            onBlur={handleAdd}
          />
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════
   USER PROFILE (bottom of sidebar)
   ═══════════════════════════════════════════ */
function UserProfile() {
  const userEmail = useDashboardStore((s) => s.userEmail);
  const userRole = useDashboardStore((s) => s.userRole);
  const logout = useDashboardStore((s) => s.logout);
  const setActiveView = useDashboardStore((s) => s.setActiveView);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  const initial = (userEmail || "U")[0].toUpperCase();

  return (
    <div className="user-profile-wrapper" ref={menuRef}>
      {menuOpen && (
        <div className="user-profile-menu">
          <div className="user-profile-menu-header">
            <div className="user-profile-avatar">{initial}</div>
            <div style={{ minWidth: 0 }}>
              <div className="user-profile-email">{userEmail || "User"}</div>
              <div className="user-profile-role">{userRole || "admin"}</div>
            </div>
          </div>
          <div className="user-profile-menu-sep" />
          <button className="user-profile-menu-item" onClick={() => { setMenuOpen(false); setActiveView("settings"); }}>
            <Settings className="h-3.5 w-3.5" />
            <span>Settings</span>
          </button>
          <button className="user-profile-menu-item destructive" onClick={logout}>
            <LogOut className="h-3.5 w-3.5" />
            <span>Log out</span>
          </button>
        </div>
      )}

      <button
        className="user-profile-trigger"
        onClick={() => setMenuOpen(!menuOpen)}
      >
        <div className="user-profile-avatar">{initial}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="user-profile-email">{userEmail || "User"}</div>
          <div className="user-profile-role">{userRole || "admin"}</div>
        </div>
        <ChevronDown
          className="h-3 w-3"
          style={{
            color: "var(--muted-foreground)",
            opacity: 0.6,
            transform: menuOpen ? "rotate(180deg)" : "rotate(0)",
            transition: "transform 0.15s ease",
          }}
        />
      </button>
    </div>
  );
}

/* ═══════════════════════════════════════════
   MAIN LAYOUT
   ═══════════════════════════════════════════ */
export function DashboardLayout() {
  const activeView = useDashboardStore((s) => s.activeView);
  const setActiveView = useDashboardStore((s) => s.setActiveView);
  const sidebarOpen = useDashboardStore((s) => s.sidebarOpen);
  const toggleSidebar = useDashboardStore((s) => s.toggleSidebar);

  const [apiHealth, setApiHealth] = useState<any>(null);
  const [agentHealth, setAgentHealth] = useState<any>(null);

  useEffect(() => {
    getApiHealth().then(setApiHealth).catch(() => {});
    getAgentHealth().then(setAgentHealth).catch(() => {});
  }, []);

  const apiUp = !!apiHealth;
  const agentUp = !!agentHealth;

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
          <div className="fheader-status">
            <div className="status-dot" style={{ background: apiUp && agentUp ? "var(--color-green)" : apiUp ? "var(--color-yellow)" : "var(--color-red)" }} />
            <span>{apiUp && agentUp ? "All systems online" : apiUp ? "Partially online" : "Offline"}</span>
          </div>
        </div>
      </header>

      {/* ════ SIDEBAR ════ */}
      <aside className={cn("fsidebar", sidebarOpen && "visible")}>
        {/* Header */}
        <div className="fsidebar-header">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <NsoLogo />
            <span style={{ fontSize: 14, fontWeight: 600 }}>NSO</span>
          </div>
          <button className="ibtn" onClick={toggleSidebar} aria-label="Close sidebar">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Navigation */}
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

        <div className="fsidebar-sep" />

        {/* Workspaces */}
        <WorkspaceSection />

        <div className="fsidebar-sep" />

        {/* Services */}
        <div className="fsidebar-section">
          <div className="fsidebar-section-title">Services</div>
          {[
            { name: "NSO API", status: apiUp },
            { name: "NSO Agent", status: agentUp },
            { name: "nginx", status: true },
          ].map((svc, i) => (
            <div
              key={i}
              className="fsidebar-service"
              onClick={() => setActiveView("settings")}
            >
              <div className="status-dot" style={{ background: svc.status ? "var(--color-green)" : "var(--color-red)" }} />
              <span>{svc.name}</span>
              <span className="fsidebar-service-status">{svc.status ? "running" : "down"}</span>
            </div>
          ))}
        </div>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* User profile */}
        <UserProfile />
      </aside>

      {/* ════ MAIN CONTENT ════ */}
      <div className={cn("fmain", sidebarOpen && "shifted")}>
        <div className={cn("fmain-content", activeView === "terminal" && "no-pad")}>
          {activeView === "overview" && <OverviewPanel apiHealth={apiHealth} agentHealth={agentHealth} />}
          {activeView === "instances" && <InstancesPanel />}
          {activeView === "files" && <FilesPanel />}
          {activeView === "terminal" && <TerminalPanel />}
          {activeView === "settings" && <SettingsPanel />}
        </div>
      </div>
    </div>
  );
}
