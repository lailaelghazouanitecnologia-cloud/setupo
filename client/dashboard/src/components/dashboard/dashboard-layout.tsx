"use client";

import React, { useEffect, useState, useRef, useCallback, Component, type ErrorInfo, type ReactNode } from "react";
import {
  Mail, Server, Key, Blocks,
  X, LogOut, ChevronDown, Settings, Rocket,
  Bell, Wallet, CreditCard, Sun, Moon,
  FolderOpen, Plus, Check, Layers, Shield, Cpu,
  Users, Copy, Link, Trash2, Crown, Eye,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useDashboardStore } from "@/stores/dashboard-store";
import type { ProjectInfo, WorkspaceInfo } from "@/stores/dashboard-store";
import { InboxPanel } from "./inbox-panel";
import { InfrastructurePanel } from "./infrastructure-panel";
import { ProjectsPanel } from "./projects-panel";
import { SecretsPanel } from "./secrets-panel";
import { AddonsPanel } from "./addons-panel";
import { DeployPanel } from "./deploy-panel";
import { BillingPanel } from "./billing-panel";
import { SettingsPanel } from "./settings-panel";
import { WorkspacesPanel } from "./workspaces-panel";
import { AdminPanel } from "./admin-panel";
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
   ERROR BOUNDARY
   ═══════════════════════════════════════════ */
class PanelErrorBoundary extends Component<
  { name: string; children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[${this.props.name}] Panel crashed:`, error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="error-boundary">
          <div className="error-boundary-icon">&#9888;</div>
          <div className="error-boundary-title">Something went wrong</div>
          <div className="error-boundary-msg">
            There was a problem loading this section. Try again or reload the page.
          </div>
          <button className="error-boundary-retry" onClick={() => this.setState({ error: null })}>
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

/* ═══════════════════════════════════════════
   NAV CONFIG
   ═══════════════════════════════════════════ */
const navItems: { id: DashboardView; label: string; icon: React.ElementType }[] = [
  { id: "inbox", label: "Inbox", icon: Mail },
  { id: "infrastructure", label: "Infrastructure", icon: Server },
  { id: "workspaces", label: "Workspaces", icon: FolderOpen },
  { id: "deploy", label: "Deploy", icon: Rocket },
  { id: "secrets", label: "Secrets", icon: Key },
  { id: "addons", label: "Apps", icon: Blocks },
];

const viewTitles: Record<DashboardView, string> = {
  inbox: "Inbox",
  infrastructure: "Infrastructure",
  projects: "Projects",
  workspaces: "Workspaces",
  deploy: "Deploy",
  secrets: "Secrets",
  addons: "Apps",
  billing: "Billing",
  settings: "Settings",
  admin: "Admin",
};

/* ═══════════════════════════════════════════
   PROJECT / WORKSPACE SWITCHER (dropdown only)
   ═══════════════════════════════════════════ */
function ProjectSwitcher() {
  const projects = useDashboardStore((s) => s.projects);
  const activeProject = useDashboardStore((s) => s.activeProject);
  const setActiveProject = useDashboardStore((s) => s.setActiveProject);
  const setWorkspaces = useDashboardStore((s) => s.setWorkspaces);
  const setActiveWorkspace = useDashboardStore((s) => s.setActiveWorkspace);
  const projectLoading = useDashboardStore((s) => s.projectLoading);
  const setActiveView = useDashboardStore((s) => s.setActiveView);

  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const dropRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [dropPos, setDropPos] = useState({ top: 0, left: 0 });

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropRef.current && !dropRef.current.contains(e.target as Node)) {
        setOpen(false);
        setCreating(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const handleCreateProject = async () => {
    const name = newName.trim();
    if (!name) return;
    try {
      const { createProject } = await import("@/lib/api/client");
      const res = await createProject(name);
      const proj: ProjectInfo = res.project;
      useDashboardStore.getState().setProjects([...projects, proj]);
      setActiveProject(proj);
      setWorkspaces([]);
      setActiveWorkspace(null);
      // Load workspaces for new project
      try {
        const { listWorkspaces } = await import("@/lib/api/client");
        const wsRes = await listWorkspaces(proj.id);
        setWorkspaces(wsRes.workspaces || []);
      } catch {}
      setNewName("");
      setCreating(false);
      setOpen(false);
    } catch (e: any) {
      alert(e.message || "Failed to create project");
    }
  };

  const handleSelectProject = async (proj: ProjectInfo) => {
    if (proj.id === activeProject?.id) {
      setOpen(false);
      return;
    }
    setActiveProject(proj);
    setWorkspaces([]);
    setActiveWorkspace(null);
    setOpen(false);
    try {
      const { listWorkspaces } = await import("@/lib/api/client");
      const res = await listWorkspaces(proj.id);
      const wsList: WorkspaceInfo[] = res.workspaces || [];
      setWorkspaces(wsList);
      setActiveWorkspace(wsList[0] || null);
    } catch {
      setWorkspaces([]);
    }
  };

  if (projectLoading) {
    return (
      <div className="proj-switcher">
        <div className="proj-trigger" style={{ opacity: 0.5, cursor: "default" }}>
          <Layers className="h-3.5 w-3.5" style={{ opacity: 0.4 }} />
          <span style={{ fontSize: 13 }}>Loading...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="proj-switcher" ref={dropRef}>
      <button
        className="proj-trigger"
        ref={triggerRef}
        onClick={() => {
          if (!open && triggerRef.current) {
            const rect = triggerRef.current.getBoundingClientRect();
            setDropPos({ top: rect.bottom + 4, left: rect.left });
          }
          setOpen(!open);
        }}
      >
        <Layers className="h-3.5 w-3.5" style={{ opacity: 0.6 }} />
        <span className="proj-trigger-name">{activeProject?.name || "Select project"}</span>
        <ChevronDown
          className="h-3 w-3"
          style={{
            opacity: 0.4, marginLeft: "auto", flexShrink: 0,
            transform: open ? "rotate(180deg)" : "rotate(0)",
            transition: "transform 0.15s ease",
          }}
        />
      </button>

      {open && (
        <div className="proj-dropdown" style={{ top: dropPos.top, left: dropPos.left }}>
          <div className="proj-dropdown-label">Project</div>
          {projects.map((p) => (
            <button
              key={p.id}
              className={cn("proj-dropdown-item", activeProject?.id === p.id && "active")}
              onClick={() => handleSelectProject(p)}
            >
              <Layers className="h-3 w-3" />
              <span>{p.name}</span>
              {activeProject?.id === p.id && <Check className="h-3 w-3" style={{ marginLeft: "auto", opacity: 0.5 }} />}
            </button>
          ))}
          {!creating ? (
            <button className="proj-dropdown-item create" onClick={() => setCreating(true)}>
              <Plus className="h-3 w-3" />
              <span>New project</span>
            </button>
          ) : (
            <div className="proj-create-form" style={{ margin: "4px 6px" }}>
              <input
                className="proj-create-input"
                placeholder="Name..."
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreateProject()}
                autoFocus
              />
              <button className="proj-create-ok" onClick={handleCreateProject}>
                <Check className="h-3 w-3" />
              </button>
            </div>
          )}
          <div className="proj-dropdown-sep" />
          <button
            className="proj-dropdown-item"
            onClick={() => { setActiveView("projects"); setOpen(false); }}
          >
            <Settings className="h-3 w-3" />
            <span>Manage</span>
          </button>
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
  const theme = useDashboardStore((s) => s.theme);
  const setTheme = useDashboardStore((s) => s.setTheme);
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

  const menuNav = (view: DashboardView) => {
    setActiveView(view);
    setMenuOpen(false);
  };

  return (
    <div className="user-profile-wrapper" ref={menuRef}>
      {menuOpen && (
        <div className="user-profile-menu">
          <div className="user-profile-menu-header">
            <div className="user-profile-avatar">{initial}</div>
            <div style={{ minWidth: 0 }}>
              <div className="user-profile-email">{userEmail || "User"}</div>
              <div className="user-profile-role">{userRole || "user"}</div>
            </div>
          </div>
          <div className="user-profile-menu-sep" />
          <button className="user-profile-menu-item" onClick={() => menuNav("secrets")}>
            <Key className="h-3.5 w-3.5" />
            <span>API Keys & Secrets</span>
          </button>
          <button className="user-profile-menu-item" onClick={() => menuNav("inbox")}>
            <Bell className="h-3.5 w-3.5" />
            <span>Notifications</span>
          </button>
          <button className="user-profile-menu-item" onClick={() => menuNav("billing")}>
            <CreditCard className="h-3.5 w-3.5" />
            <span>Billing</span>
          </button>
          <button className="user-profile-menu-item" onClick={() => menuNav("settings")}>
            <Settings className="h-3.5 w-3.5" />
            <span>Settings</span>
          </button>
          <button
            className="user-profile-menu-item"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
            <span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>
          </button>
          <div className="user-profile-menu-sep" />
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
          <div className="user-profile-role">{userRole || "user"}</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
          <div
            role="button"
            tabIndex={0}
            className="add-node-btn"
            title="Add node"
            onClick={(e) => {
              e.stopPropagation();
              setActiveView("infrastructure");
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.stopPropagation();
                setActiveView("infrastructure");
              }
            }}
            style={{
              width: 28, height: 28, borderRadius: 6,
              display: "flex", alignItems: "center", justifyContent: "center",
              border: "0.5px solid var(--border)",
              background: "transparent",
              cursor: "pointer",
              transition: "all 0.1s ease",
              color: "var(--muted-foreground)",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "var(--accent)";
              e.currentTarget.style.color = "var(--color-teal)";
              e.currentTarget.style.borderColor = "transparent";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.color = "var(--muted-foreground)";
              e.currentTarget.style.borderColor = "var(--border)";
            }}
          >
            <Cpu className="h-3.5 w-3.5" />
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
        </div>
      </button>
    </div>
  );
}

/* ═══════════════════════════════════════════
   MEMBERS POPOVER
   ═══════════════════════════════════════════ */
import type { ProjectMember, ProjectInvite } from "@/lib/api/client";

function MembersPopover() {
  const activeProject = useDashboardStore((s) => s.activeProject);
  const [open, setOpen] = useState(false);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [invites, setInvites] = useState<ProjectInvite[]>([]);
  const [loading, setLoading] = useState(false);
  const [showInvite, setShowInvite] = useState(false);
  const [inviteRole, setInviteRole] = useState("member");
  const [inviteLink, setInviteLink] = useState("");
  const [copied, setCopied] = useState(false);
  const [creating, setCreating] = useState(false);
  const popRef = useRef<HTMLDivElement>(null);

  const projectId = activeProject?.id;

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (popRef.current && !popRef.current.contains(e.target as Node)) {
        setOpen(false);
        setShowInvite(false);
        setInviteLink("");
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const { listProjectMembers, listProjectInvites } = await import("@/lib/api/client");
      const [mRes, iRes] = await Promise.all([
        listProjectMembers(projectId),
        listProjectInvites(projectId).catch(() => ({ invites: [] })),
      ]);
      setMembers(mRes.members || []);
      setInvites(iRes.invites || []);
    } catch { }
    setLoading(false);
  }, [projectId]);

  const handleOpen = () => {
    if (!open) refresh();
    setOpen(!open);
    setShowInvite(false);
    setInviteLink("");
  };

  const handleCreateInvite = async () => {
    if (!projectId) return;
    setCreating(true);
    try {
      const { createProjectInvite } = await import("@/lib/api/client");
      const res = await createProjectInvite(projectId, { role: inviteRole });
      const code = res.invite.join_code;
      const link = `${window.location.origin}/api/join/project/${code}`;
      setInviteLink(link);
      refresh();
    } catch (e: any) {
      alert(e.message || "Failed to create invite");
    }
    setCreating(false);
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(inviteLink);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRevokeInvite = async (inviteId: string) => {
    if (!projectId) return;
    try {
      const { revokeProjectInvite } = await import("@/lib/api/client");
      await revokeProjectInvite(projectId, inviteId);
      refresh();
    } catch { }
  };

  const handleRemoveMember = async (userId: string) => {
    if (!projectId) return;
    if (!confirm("Remove this member from the project?")) return;
    try {
      const { removeProjectMember } = await import("@/lib/api/client");
      await removeProjectMember(projectId, userId);
      refresh();
    } catch (e: any) {
      alert(e.message || "Failed to remove member");
    }
  };

  const handleChangeRole = async (userId: string, newRole: string) => {
    if (!projectId) return;
    try {
      const { updateMemberRole } = await import("@/lib/api/client");
      await updateMemberRole(projectId, userId, newRole);
      refresh();
    } catch (e: any) {
      alert(e.message || "Failed to update role");
    }
  };

  const roleIcon = (role: string) => {
    if (role === "admin") return <Crown className="h-3 w-3" style={{ color: "var(--color-amber, #f59e0b)" }} />;
    return <Eye className="h-3 w-3" style={{ color: "var(--muted-foreground)" }} />;
  };

  return (
    <div ref={popRef} style={{ position: "relative" }}>
      <button
        className="header-action-btn"
        title="Project members"
        onClick={handleOpen}
        style={{ position: "relative" }}
      >
        <Users className="h-3.5 w-3.5" />
        {members.length > 0 && (
          <span style={{
            fontSize: 9, fontWeight: 600,
            background: "var(--color-teal, #14b8a6)", color: "#fff",
            borderRadius: 6, padding: "0 4px", minWidth: 14,
            height: 14, display: "flex", alignItems: "center", justifyContent: "center",
            position: "absolute", top: -2, right: -4,
          }}>
            {members.length}
          </span>
        )}
      </button>

      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 8px)", right: 0,
          width: 320, maxHeight: 440, overflowY: "auto",
          background: "var(--popover)", border: "1px solid var(--border)",
          borderRadius: 10, boxShadow: "0 8px 32px rgba(0,0,0,0.25)",
          zIndex: 100, padding: "8px 0",
        }}>
          {/* Header */}
          <div style={{ padding: "6px 14px 10px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 12, fontWeight: 600 }}>Members</span>
            <button
              onClick={() => { setShowInvite(!showInvite); setInviteLink(""); }}
              style={{
                fontSize: 11, padding: "3px 10px", borderRadius: 6,
                background: "var(--accent)", border: "1px solid var(--border)",
                color: "var(--foreground)", cursor: "pointer",
                display: "flex", alignItems: "center", gap: 4,
              }}
            >
              <Plus className="h-3 w-3" /> Invite
            </button>
          </div>

          {/* Invite form */}
          {showInvite && (
            <div style={{ padding: "0 14px 10px", borderBottom: "1px solid var(--border)" }}>
              {!inviteLink ? (
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <select
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value)}
                    style={{
                      fontSize: 11, padding: "4px 8px", borderRadius: 6,
                      background: "var(--input)", border: "1px solid var(--border)",
                      color: "var(--foreground)", flex: 1,
                    }}
                  >
                    <option value="member">Member</option>
                    <option value="admin">Admin</option>
                  </select>
                  <button
                    onClick={handleCreateInvite}
                    disabled={creating}
                    style={{
                      fontSize: 11, padding: "4px 12px", borderRadius: 6,
                      background: "var(--color-teal, #14b8a6)", border: "none",
                      color: "#fff", cursor: "pointer", whiteSpace: "nowrap",
                    }}
                  >
                    <Link className="h-3 w-3" style={{ display: "inline", verticalAlign: "-2px", marginRight: 4 }} />
                    {creating ? "..." : "Generate link"}
                  </button>
                </div>
              ) : (
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <input
                    readOnly
                    value={inviteLink}
                    style={{
                      fontSize: 10, padding: "4px 8px", borderRadius: 6,
                      background: "var(--input)", border: "1px solid var(--border)",
                      color: "var(--foreground)", flex: 1, fontFamily: "monospace",
                    }}
                  />
                  <button
                    onClick={handleCopy}
                    style={{
                      fontSize: 11, padding: "4px 8px", borderRadius: 6,
                      background: copied ? "var(--color-teal, #14b8a6)" : "var(--accent)",
                      border: "1px solid var(--border)", color: copied ? "#fff" : "var(--foreground)",
                      cursor: "pointer",
                    }}
                  >
                    <Copy className="h-3 w-3" />
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Members list */}
          {loading ? (
            <div style={{ padding: "16px 14px", fontSize: 11, opacity: 0.5, textAlign: "center" }}>Loading...</div>
          ) : members.length === 0 ? (
            <div style={{ padding: "16px 14px", fontSize: 11, opacity: 0.5, textAlign: "center" }}>No members yet</div>
          ) : (
            <div style={{ padding: "4px 0" }}>
              {members.map((m) => (
                <div
                  key={m.id}
                  style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "6px 14px", fontSize: 12,
                  }}
                >
                  <div style={{
                    width: 26, height: 26, borderRadius: "50%",
                    background: "var(--accent)", display: "flex",
                    alignItems: "center", justifyContent: "center",
                    fontSize: 11, fontWeight: 600, flexShrink: 0,
                  }}>
                    {(m.name || m.email || "?")[0].toUpperCase()}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {m.name || m.email}
                    </div>
                    <div style={{ fontSize: 10, opacity: 0.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {m.email}
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
                    {roleIcon(m.role)}
                    <span style={{ fontSize: 10, opacity: 0.6 }}>{m.role}</span>
                    {m.role !== "admin" && (
                      <div style={{ display: "flex", gap: 2, marginLeft: 4 }}>
                        <button
                          onClick={() => handleChangeRole(m.user_id, m.role === "member" ? "admin" : "member")}
                          title={m.role === "member" ? "Promote to admin" : "Demote to member"}
                          style={{
                            width: 20, height: 20, borderRadius: 4,
                            background: "transparent", border: "none",
                            cursor: "pointer", display: "flex",
                            alignItems: "center", justifyContent: "center",
                            color: "var(--muted-foreground)",
                          }}
                        >
                          {m.role === "member" ? <Crown className="h-2.5 w-2.5" /> : <Eye className="h-2.5 w-2.5" />}
                        </button>
                        <button
                          onClick={() => handleRemoveMember(m.user_id)}
                          title="Remove member"
                          style={{
                            width: 20, height: 20, borderRadius: 4,
                            background: "transparent", border: "none",
                            cursor: "pointer", display: "flex",
                            alignItems: "center", justifyContent: "center",
                            color: "var(--destructive, #ef4444)",
                          }}
                        >
                          <X className="h-2.5 w-2.5" />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Active invites */}
          {invites.length > 0 && (
            <>
              <div style={{ height: 1, background: "var(--border)", margin: "4px 14px", opacity: 0.3 }} />
              <div style={{ padding: "6px 14px 4px" }}>
                <span style={{ fontSize: 10, fontWeight: 600, opacity: 0.5, textTransform: "uppercase", letterSpacing: "0.5px" }}>
                  Active invites
                </span>
              </div>
              {invites.map((inv) => (
                <div
                  key={inv.id}
                  style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "4px 14px", fontSize: 11,
                  }}
                >
                  <Link className="h-3 w-3" style={{ opacity: 0.4, flexShrink: 0 }} />
                  <span style={{ flex: 1, opacity: 0.6 }}>
                    {inv.role} &middot; {inv.uses}/{inv.max_uses || "\u221E"} uses
                  </span>
                  <button
                    onClick={() => handleRevokeInvite(inv.id)}
                    title="Revoke invite"
                    style={{
                      width: 20, height: 20, borderRadius: 4,
                      background: "transparent", border: "none",
                      cursor: "pointer", display: "flex",
                      alignItems: "center", justifyContent: "center",
                      color: "var(--destructive, #ef4444)",
                    }}
                  >
                    <Trash2 className="h-2.5 w-2.5" />
                  </button>
                </div>
              ))}
            </>
          )}
        </div>
      )}
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
  const setProjects = useDashboardStore((s) => s.setProjects);
  const setActiveProject = useDashboardStore((s) => s.setActiveProject);
  const setWorkspaces = useDashboardStore((s) => s.setWorkspaces);
  const setActiveWorkspace = useDashboardStore((s) => s.setActiveWorkspace);
  const setProjectLoading = useDashboardStore((s) => s.setProjectLoading);
  const userRole = useDashboardStore((s) => s.userRole);

  const [balance, setBalance] = useState(0);
  const [unread, setUnread] = useState(0);

  // Load projects + workspaces on mount
  const loadProjects = useCallback(async () => {
    setProjectLoading(true);
    try {
      const { listProjects, createProject, listWorkspaces } = await import("@/lib/api/client");
      let res = await listProjects();
      let projs = res.projects || [];

      // Auto-create if no projects
      if (projs.length === 0) {
        try {
          const created = await createProject("main");
          projs = [created.project];
        } catch { /* ignore */ }
      }

      setProjects(projs);

      if (projs.length > 0) {
        // Restore last active project or pick first
        const savedProjId = localStorage.getItem("nso_active_project");
        const restored = projs.find((p: ProjectInfo) => p.id === savedProjId);
        const active = restored || projs[0];
        setActiveProject(active);

        // Load workspaces
        try {
          const wsRes = await listWorkspaces(active.id);
          const wsList = wsRes.workspaces || [];
          setWorkspaces(wsList);

          const savedWsId = localStorage.getItem("nso_active_workspace");
          const restoredWs = wsList.find((w: WorkspaceInfo) => w.id === savedWsId);
          setActiveWorkspace(restoredWs || wsList[0] || null);
        } catch {
          setWorkspaces([]);
        }
      }
    } catch {
      setProjects([]);
    }
    setProjectLoading(false);
  }, [setProjects, setActiveProject, setWorkspaces, setActiveWorkspace, setProjectLoading]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    import("@/lib/api/client").then(({ getMe, listNotifications }) => {
      getMe().then((me) => setBalance(me.balance)).catch(() => {});
      listNotifications().then((n) => setUnread(n.unread)).catch(() => {});
    });
  }, [activeView]);

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
          {/* Members */}
          <MembersPopover />

          {/* Balance */}
          <button
            className="header-action-btn"
            title="Account balance"
            onClick={() => setActiveView("billing")}
          >
            <Wallet className="h-3.5 w-3.5" />
            <span className="header-balance">${balance.toFixed(2)}</span>
          </button>

          {/* Notifications */}
          <button
            className="header-action-btn"
            title="Notifications"
            onClick={() => setActiveView("inbox")}
            style={{ position: "relative" }}
          >
            <Bell className="h-3.5 w-3.5" />
            {unread > 0 && <span className="header-notif-badge">{unread}</span>}
          </button>
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

        {/* Project + Workspace Switcher */}
        <ProjectSwitcher />

        {/* Separator */}
        <div style={{ height: 1, background: "var(--border)", margin: "4px 12px", opacity: 0.5 }} />

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
          {userRole === "admin" && typeof window !== "undefined" && window.location.hostname === "sonfazt.nso.dev" && (
            <>
              <div style={{ height: 1, background: "var(--border)", margin: "6px 0", opacity: 0.3 }} />
              <button
                className={cn("fmenu", activeView === "admin" && "active")}
                onClick={() => setActiveView("admin")}
              >
                <Shield className="h-3.5 w-3.5" />
                <span>Admin</span>
              </button>
            </>
          )}
        </nav>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* User profile */}
        <UserProfile />
      </aside>

      {/* ════ MAIN CONTENT ════ */}
      <div className={cn("fmain", sidebarOpen && "shifted")}>
        <div className={cn("fmain-content", (activeView === "deploy" || activeView === "workspaces") && "fmain-full")}>
          {activeView === "inbox" && <PanelErrorBoundary name="Inbox"><InboxPanel /></PanelErrorBoundary>}
          {activeView === "infrastructure" && <PanelErrorBoundary name="Infrastructure"><InfrastructurePanel /></PanelErrorBoundary>}
          {activeView === "projects" && <PanelErrorBoundary name="Projects"><ProjectsPanel /></PanelErrorBoundary>}
          {activeView === "workspaces" && <PanelErrorBoundary name="Workspaces"><WorkspacesPanel /></PanelErrorBoundary>}
          {activeView === "deploy" && <PanelErrorBoundary name="Deploy"><DeployPanel /></PanelErrorBoundary>}
          {activeView === "secrets" && <PanelErrorBoundary name="Secrets"><SecretsPanel /></PanelErrorBoundary>}
          {activeView === "addons" && <PanelErrorBoundary name="Apps"><AddonsPanel /></PanelErrorBoundary>}
          {activeView === "billing" && <PanelErrorBoundary name="Billing"><BillingPanel /></PanelErrorBoundary>}
          {activeView === "settings" && <PanelErrorBoundary name="Settings"><SettingsPanel /></PanelErrorBoundary>}
          {activeView === "admin" && <PanelErrorBoundary name="Admin"><AdminPanel /></PanelErrorBoundary>}
        </div>
      </div>
    </div>
  );
}
