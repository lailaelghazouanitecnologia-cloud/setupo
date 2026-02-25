"use client";

import React, { useEffect, useState } from "react";
import {
  LayoutDashboard, Server, FolderOpen, Terminal, Settings,
  Plus, Search, ChevronUp, ChevronDown, X, Inbox, Zap, LogOut,
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

/* ═══════════════════════════════════════════
   ICONS — minimal inline SVGs
   ═══════════════════════════════════════════ */
function SetupoLogo() {
  return (
    <svg width="13" height="13" viewBox="0 0 100 100" fill="currentColor">
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
   PRIMITIVES
   ═══════════════════════════════════════════ */
const GRADIENTS = [
  "linear-gradient(135deg, #e74c3c, #c0392b)",
  "linear-gradient(135deg, #3b82f6, #2563eb)",
  "linear-gradient(135deg, #f2c94c, #e6b800)",
  "linear-gradient(135deg, #4cb782, #36946a)",
  "linear-gradient(135deg, #8b5cf6, #7c3aed)",
  "linear-gradient(135deg, #02b8cc, #0891b2)",
  "linear-gradient(135deg, #f59e0b, #d97706)",
];

function DashAvatar({ name, size = 14 }: { name: string; size?: number }) {
  const idx = [...(name || "")].reduce((a, c) => a + c.charCodeAt(0), 0) % GRADIENTS.length;
  return (
    <div
      className="fav"
      style={{ width: size, height: size, background: GRADIENTS[idx], fontSize: size * 0.48 }}
    >
      {(name || "?")[0].toUpperCase()}
    </div>
  );
}

function StatusRing({ color = "var(--color-teal)", progress = 0.25, size = 14 }: { color?: string; progress?: number; size?: number }) {
  const r = (size / 2) - 1;
  const cx = size / 2;
  const circ = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={cx} cy={cx} r={r} stroke={color} strokeWidth={1.5} fill="none" opacity={0.3} />
      <circle cx={cx} cy={cx} r={r} stroke={color} strokeWidth={1.5} fill="none"
        strokeDasharray={`${circ * progress} ${circ}`} strokeDashoffset={circ * 0.25} strokeLinecap="round" />
    </svg>
  );
}

function Collapsible({ label, defaultOpen = true, children }: { label: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button className="fcollapse-trigger" onClick={() => setOpen(!open)}>
        <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor"
          style={{ transform: open ? "rotate(90deg)" : "rotate(0)", transition: "transform 120ms" }}>
          <path d="M7 10.624c-.334.194-.75-.046-.75-.432V5.808c0-.386.416-.626.752-.432l3.758 2.192c.33.193.33.671 0 .864L7 10.624z" />
        </svg>
        {label}
      </button>
      <div className="fcollapse-content" style={{ maxHeight: open ? 500 : 0, padding: open ? "2px 0" : 0 }}>
        {children}
      </div>
    </div>
  );
}

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

const viewDescriptions: Record<DashboardView, string> = {
  overview: "System overview — API status, services, and infrastructure health.",
  instances: "VPS instances managed via Vultr API. Monitor and control your fleet.",
  files: "Browse and edit files on your VPS remotely via the agent.",
  terminal: "Execute commands on your VPS. Like SSH but via HTTP.",
  settings: "Service management — start, stop, restart, and system info.",
};

/* ═══════════════════════════════════════════
   MAIN LAYOUT
   ═══════════════════════════════════════════ */
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

  /* Quick stats for right sidebar */
  const apiUp = !!apiHealth;
  const agentUp = !!agentHealth;
  const featureCount = agentHealth?.features?.length || 0;
  const uptime = apiHealth ? Math.round(apiHealth.uptime_seconds / 60) : 0;

  return (
    <div style={{ height: "100vh", overflow: "hidden", position: "relative" }}>
      {/* ════ ACTIVATION STRIP ════ */}
      <div
        className={cn("activation-strip", sidebarOpen && "shifted")}
        onClick={toggleSidebar}
      >
        ≡
      </div>

      {/* ════ HEADER (35px compact) ════ */}
      <header className={cn("fheader", sidebarOpen && "shifted")}>
        <div className="fheader-left">
          {!sidebarOpen && (
            <button className="ibtn" onClick={toggleSidebar} aria-label="Toggle sidebar">
              <IC_Menu />
            </button>
          )}
          <span className="fheader-company">{viewTitles[activeView]}</span>
          <span style={{ fontSize: "var(--font-sm)", color: "var(--muted-foreground)" }}>
            setupo dashboard
          </span>
        </div>
        <div className="fheader-right">
          <span style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)" }}>
            <span style={{ color: "var(--foreground)" }}>
              {String(currentIdx + 1).padStart(2, "0")}
            </span>{" "}
            / {viewKeys.length}
          </span>
          <div className="fheader-sep" />
          <button
            className="ibtn"
            onClick={() => {
              const prev = currentIdx > 0 ? currentIdx - 1 : viewKeys.length - 1;
              setActiveView(viewKeys[prev]);
            }}
          >
            <ChevronUp className="h-3.5 w-3.5" />
          </button>
          <button
            className="ibtn"
            onClick={() => {
              const next = currentIdx < viewKeys.length - 1 ? currentIdx + 1 : 0;
              setActiveView(viewKeys[next]);
            }}
          >
            <ChevronDown className="h-3.5 w-3.5" />
          </button>
          <div className="fheader-sep" />
          <button className="ibtn">
            <Search className="h-3.5 w-3.5" />
          </button>
          <DashAvatar name="setupo" size={21} />
        </div>
      </header>

      {/* ════ SIDEBAR (Linear-style) ════ */}
      <aside className={cn("fsidebar", sidebarOpen && "visible")}>
        <div className="fsidebar-header">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <SetupoLogo />
            <span style={{ fontSize: 14, fontWeight: 600 }}>setupo</span>
          </div>
          <button className="ibtn" onClick={toggleSidebar} aria-label="Close sidebar">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="fsidebar-content">
          {/* New instance button */}
          <button className="task-btn" onClick={() => setActiveView("instances")}>
            <Plus className="h-3.5 w-3.5" />
            <span>New instance</span>
          </button>

          {/* Main nav */}
          <button className={cn("fmenu")}><Inbox className="h-3.5 w-3.5" /><span>Inbox</span></button>
          <button className={cn("fmenu")} onClick={() => setActiveView("terminal")}><Zap className="h-3.5 w-3.5" /><span>Pulse</span></button>
          <button className={cn("fmenu")} onClick={() => setActiveView("files")}><FolderOpen className="h-3.5 w-3.5" /><span>Projects</span></button>

          <div style={{ height: 8 }} />

          {/* Views — collapsible section */}
          <Collapsible label="Views">
            {navItems.map((item) => (
              <button
                key={item.id}
                className={cn("fmenu", activeView === item.id && "active")}
                onClick={() => setActiveView(item.id)}
              >
                {item.id === "overview" ? (
                  <StatusRing progress={apiUp && agentUp ? 1.0 : apiUp ? 0.5 : 0} color="var(--color-teal)" />
                ) : item.id === "instances" ? (
                  <StatusRing progress={0.25} color="var(--color-yellow)" />
                ) : (
                  <item.icon className="h-3.5 w-3.5" />
                )}
                <span>{item.label}</span>
              </button>
            ))}
          </Collapsible>

          {/* Services section */}
          <div className="chat-section">
            <div className="chat-section-title">Services</div>
            <div className="chat-scroll">
              {[
                { name: "setupo API", status: apiUp },
                { name: "setupo Agent", status: agentUp },
                { name: "nginx", status: true },
              ].map((svc, i) => (
                <div
                  key={i}
                  className={cn("chat-row", i === 0 && "active")}
                  onClick={() => setActiveView("settings")}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 6, flex: 1, minWidth: 0 }}>
                    <div style={{
                      width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
                      background: svc.status ? "var(--color-green)" : "var(--color-red)",
                    }} />
                    <span className="chat-name">{svc.name}</span>
                  </div>
                  <span className="chat-time">{svc.status ? "up" : "down"}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Footer — sign out */}
          <div style={{ flexShrink: 0, paddingTop: 8, borderTop: "1px solid var(--sidebar-border)" }}>
            <button className="fmenu" onClick={logout}>
              <LogOut className="h-3.5 w-3.5" /><span>Sign out</span>
            </button>
          </div>
        </div>
      </aside>

      {/* ════ MAIN CONTENT ════ */}
      <div className={cn("fmain", sidebarOpen && "shifted")}>
        <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
          {/* ─── Content Body ─── */}
          <div className="issue-body">
            {/* View title */}
            <div style={{ fontSize: "var(--font-xl)", fontWeight: 500, marginBottom: 4 }}>
              {viewTitles[activeView]}
            </div>
            <div style={{
              fontSize: "var(--font-md)",
              color: "var(--muted-foreground)",
              maxWidth: 600,
              lineHeight: 1.65,
              marginBottom: 22,
            }}>
              {viewDescriptions[activeView]}
            </div>

            {/* View content */}
            {activeView === "overview" && <OverviewPanel apiHealth={apiHealth} agentHealth={agentHealth} />}
            {activeView === "instances" && <InstancesPanel />}
            {activeView === "files" && <FilesPanel />}
            {activeView === "terminal" && <TerminalPanel />}
            {activeView === "settings" && <SettingsPanel />}
          </div>

          {/* ─── Right Sidebar (metadata) ─── */}
          <div className="rsidebar">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <span style={{ fontSize: "var(--font-sm)", color: "var(--muted-foreground)" }}>
                {viewTitles[activeView]}
              </span>
            </div>

            {/* Status */}
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, height: 26 }}>
                <StatusRing progress={apiUp && agentUp ? 1.0 : apiUp ? 0.5 : 0} color="var(--color-green)" />
                <span style={{ fontSize: "var(--font-sm)" }}>
                  {apiUp && agentUp ? "100% Online" : apiUp ? "50% Online" : "Offline"}
                </span>
              </div>

              {/* Tier / Priority */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, height: 26 }}>
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" opacity="0.5">
                  <rect x="1.5" y="8" width="3" height="6" rx="1" />
                  <rect x="6.5" y="5" width="3" height="9" rx="1" />
                  <rect x="11.5" y="2" width="3" height="12" rx="1" />
                </svg>
                <span style={{ fontSize: "var(--font-sm)" }}>Production</span>
              </div>

              {/* Agent */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, height: 26 }}>
                <DashAvatar name="setupo" size={16} />
                <span style={{ fontSize: "var(--font-sm)" }}>setupo agent</span>
              </div>
            </div>

            <div style={{ height: 20 }} />
            <div className="rsidebar-label">Stats</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <span className="pill">
                <span className="pill-dot" style={{ background: "var(--color-blue)" }} />
                {featureCount} features
              </span>
              <span className="pill">
                <span className="pill-dot" style={{ background: "var(--color-purple)" }} />
                {uptime}m uptime
              </span>
            </div>

            <div style={{ height: 20 }} />
            <div className="rsidebar-label">Services</div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Server className="h-3.5 w-3.5" style={{ color: "var(--color-teal)" }} />
              <span style={{ fontSize: "var(--font-sm)" }}>
                {(apiUp ? 1 : 0) + (agentUp ? 1 : 0)} / 2 online
              </span>
            </div>

            <div style={{ height: 20 }} />
            <div className="rsidebar-label">Version</div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="var(--color-teal)">
                <path d="M9 1.5L4 9h3.5L6.5 14.5 12 7H8.5L9 1.5z" />
              </svg>
              <span style={{ fontSize: "var(--font-sm)", color: "var(--color-teal)" }}>
                v{apiHealth?.version || "0.2.0"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
