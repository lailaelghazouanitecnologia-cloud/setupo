"use client";

import { useState, useEffect } from "react";
import {
  Layers, Plus, RefreshCw, Trash2, Key, Copy, Check,
  RotateCw, ChevronRight, FolderOpen, Server, Clock,
} from "lucide-react";
import {
  listProjects, createProject as apiCreateProject,
  deleteProject as apiDeleteProject, rotateProjectKey,
  listWorkspaces, listInstances,
} from "@/lib/api/client";
import { useDashboardStore } from "@/stores/dashboard-store";

interface Project {
  id: string;
  name: string;
  owner?: string;
  created_at?: string;
  settings?: Record<string, any>;
  role?: string;
}

export function ProjectsPanel() {
  const activeProject = useDashboardStore((s) => s.activeProject);
  const setActiveProject = useDashboardStore((s) => s.setActiveProject);
  const storeProjects = useDashboardStore((s) => s.projects);
  const setProjects = useDashboardStore((s) => s.setProjects);
  const setWorkspaces = useDashboardStore((s) => s.setWorkspaces);
  const setActiveWorkspace = useDashboardStore((s) => s.setActiveWorkspace);
  const setActiveView = useDashboardStore((s) => s.setActiveView);

  const [projects, setLocalProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [error, setError] = useState("");

  // Selected project detail
  const [selected, setSelected] = useState<Project | null>(null);
  const [wsCount, setWsCount] = useState(0);
  const [instCount, setInstCount] = useState(0);
  const [detailLoading, setDetailLoading] = useState(false);

  // API key
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [keyVisible, setKeyVisible] = useState(false);
  const [copied, setCopied] = useState(false);
  const [rotating, setRotating] = useState(false);

  const fetchProjects = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await listProjects();
      const projs = res.projects || [];
      setLocalProjects(projs);
      setProjects(projs);
    } catch (e: any) {
      setError("Failed to load projects");
    }
    setLoading(false);
  };

  useEffect(() => { fetchProjects(); }, []);

  // Auto-select active project
  useEffect(() => {
    if (activeProject && !selected) {
      const p = projects.find((pr) => pr.id === activeProject.id);
      if (p) selectProject(p);
    }
  }, [projects, activeProject]);

  const selectProject = async (proj: Project) => {
    setSelected(proj);
    setApiKey(null);
    setKeyVisible(false);
    setDetailLoading(true);
    try {
      const [wsRes, instRes] = await Promise.all([
        listWorkspaces(proj.id).catch(() => ({ workspaces: [] })),
        listInstances(proj.id).catch(() => ({ instances: [] })),
      ]);
      setWsCount((wsRes.workspaces || []).length);
      setInstCount((instRes.instances || []).length);
    } catch {
      setWsCount(0);
      setInstCount(0);
    }
    setDetailLoading(false);
  };

  const handleCreate = async () => {
    const name = newName.trim().replace(/[^a-zA-Z0-9_-]/g, "-");
    if (!name) return;
    setError("");
    try {
      const res = await apiCreateProject(name);
      setNewName("");
      setCreating(false);
      // Show API key for new project
      if (res.api_key) {
        setApiKey(res.api_key);
        setKeyVisible(true);
      }
      await fetchProjects();
      // Select the new project
      const newProj = { id: res.project.id, name: res.project.name, ...res.project };
      setSelected(newProj);
      setActiveProject(newProj);
    } catch (e: any) {
      setError(e.message || "Failed to create project");
    }
  };

  const handleDelete = async (proj: Project) => {
    if (!confirm(`Delete project "${proj.name}"?\n\nThis will permanently remove the project and all associated data.`)) return;
    setError("");
    try {
      await apiDeleteProject(proj.id);
      if (selected?.id === proj.id) {
        setSelected(null);
        setApiKey(null);
      }
      if (activeProject?.id === proj.id) {
        setActiveProject(null);
        setWorkspaces([]);
        setActiveWorkspace(null);
      }
      await fetchProjects();
    } catch (e: any) {
      setError(e.message || "Failed to delete project");
    }
  };

  const handleRotateKey = async () => {
    if (!selected) return;
    if (!confirm("Rotate API key? The current key will stop working immediately.")) return;
    setRotating(true);
    try {
      const res = await rotateProjectKey(selected.id);
      setApiKey(res.api_key);
      setKeyVisible(true);
    } catch (e: any) {
      setError(e.message || "Failed to rotate key");
    }
    setRotating(false);
  };

  const handleCopyKey = () => {
    if (!apiKey) return;
    navigator.clipboard.writeText(apiKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSwitchTo = (proj: Project) => {
    setActiveProject(proj);
    // Load workspaces for this project
    listWorkspaces(proj.id)
      .then((res) => {
        const wsList = res.workspaces || [];
        setWorkspaces(wsList);
        setActiveWorkspace(wsList[0] || null);
      })
      .catch(() => { setWorkspaces([]); });
  };

  return (
    <div>
      {/* Header */}
      <div className="panel-header-row">
        <span className="panel-count">
          {projects.length} project{projects.length !== 1 ? "s" : ""}
        </span>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="panel-btn-sm" onClick={fetchProjects} disabled={loading}>
            <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
          </button>
          {activeProject?.role === "admin" && (
            <button className="panel-btn-sm" onClick={() => setCreating(true)}>
              <Plus className="h-3 w-3" />
              <span>New</span>
            </button>
          )}
        </div>
      </div>

      {error && (
        <div style={{ padding: "8px 12px", fontSize: "var(--font-xs)", color: "var(--color-red)", background: "rgba(239,68,68,0.08)", borderRadius: 6, margin: "8px 0" }}>
          {error}
        </div>
      )}

      {/* Create project form */}
      {creating && (
        <div className="proj-create" style={{ margin: "8px 0" }}>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              className="proj-input"
              type="text"
              placeholder="Project name (e.g. my-app)"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleCreate();
                if (e.key === "Escape") { setCreating(false); setNewName(""); }
              }}
              style={{ flex: 1 }}
              autoFocus
            />
            <button className="panel-btn-sm" onClick={handleCreate} disabled={!newName.trim()}>
              Create
            </button>
            <button className="panel-btn-sm" onClick={() => { setCreating(false); setNewName(""); }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* API key alert (shown after create or rotate) */}
      {apiKey && keyVisible && (
        <div style={{
          margin: "8px 0", padding: "10px 12px", borderRadius: 6,
          background: "rgba(16,185,129,0.08)", border: "1px solid rgba(16,185,129,0.2)",
        }}>
          <div style={{ fontSize: "var(--font-xs)", fontWeight: 600, color: "var(--color-teal)", marginBottom: 6 }}>
            API Key — save it now, it won't be shown again
          </div>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <code style={{
              flex: 1, padding: "6px 8px", fontSize: 11, fontFamily: "var(--font-mono, monospace)",
              background: "var(--card)", border: "1px solid var(--border)", borderRadius: 4,
              wordBreak: "break-all", color: "var(--foreground)",
            }}>
              {apiKey}
            </code>
            <button className="panel-btn-sm" onClick={handleCopyKey} title="Copy">
              {copied ? <Check className="h-3 w-3" style={{ color: "var(--color-teal)" }} /> : <Copy className="h-3 w-3" />}
            </button>
            <button className="panel-btn-sm" onClick={() => setKeyVisible(false)} title="Dismiss">
              &times;
            </button>
          </div>
        </div>
      )}

      {projects.length === 0 && !loading ? (
        <div className="panel-empty">
          <Layers className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
          <div className="panel-empty-title">No projects</div>
          <div className="panel-empty-sub">Create a project to get started.</div>
          <button className="panel-btn" onClick={() => setCreating(true)}>
            <Plus className="h-3.5 w-3.5" />
            <span>Create project</span>
          </button>
        </div>
      ) : (
        <div className="proj-layout">
          {/* Project list */}
          <div className="proj-list">
            {projects.map((proj) => (
              <div
                key={proj.id}
                className={`proj-card ${selected?.id === proj.id ? "active" : ""}`}
                onClick={() => selectProject(proj)}
              >
                <div className="proj-card-icon">
                  <Layers className="h-4 w-4" style={{ color: "var(--color-teal)" }} />
                </div>
                <div className="proj-card-info">
                  <div className="proj-card-name">{proj.name}</div>
                  <div className="proj-card-meta">
                    {proj.id}
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  {activeProject?.id === proj.id && (
                    <span className="inst-badge green" style={{ fontSize: 9 }}>active</span>
                  )}
                  {proj.role === "admin" && (
                  <div className="proj-card-actions">
                    <button
                      className="svc-btn red"
                      title="Delete project"
                      onClick={(e) => { e.stopPropagation(); handleDelete(proj); }}
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                )}
                </div>
              </div>
            ))}
          </div>

          {/* Project detail */}
          {selected && (
            <div className="proj-detail">
              <div className="proj-detail-header">
                <Layers className="h-4 w-4" style={{ color: "var(--color-teal)" }} />
                <span className="proj-detail-name">{selected.name}</span>
                <span className="proj-detail-path">{selected.id}</span>
              </div>

              {/* Stats row */}
              <div style={{
                display: "flex", gap: 16, padding: "12px 14px",
                borderBottom: "1px solid var(--border)",
              }}>
                <div
                  style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: "var(--font-xs)" }}
                  onClick={() => setActiveView("workspaces")}
                >
                  <FolderOpen className="h-3.5 w-3.5" style={{ color: "var(--color-blue)" }} />
                  <span>{detailLoading ? "..." : wsCount} workspaces</span>
                  <ChevronRight className="h-3 w-3" style={{ opacity: 0.3 }} />
                </div>
                <div
                  style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: "var(--font-xs)" }}
                  onClick={() => setActiveView("infrastructure")}
                >
                  <Server className="h-3.5 w-3.5" style={{ color: "var(--color-purple)" }} />
                  <span>{detailLoading ? "..." : instCount} instances</span>
                  <ChevronRight className="h-3 w-3" style={{ opacity: 0.3 }} />
                </div>
                {selected.created_at && (
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "var(--font-xs)", color: "var(--muted-foreground)" }}>
                    <Clock className="h-3.5 w-3.5" />
                    <span>{new Date(selected.created_at).toLocaleDateString()}</span>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 8 }}>
                {/* Switch active project */}
                {activeProject?.id !== selected.id && (
                  <button
                    className="deploy-action-btn teal"
                    style={{ padding: "6px 12px", fontSize: "var(--font-xs)", width: "fit-content" }}
                    onClick={() => handleSwitchTo(selected)}
                  >
                    <Check className="h-3 w-3" />
                    <span>Set as active project</span>
                  </button>
                )}

                {/* API Key section */}
                {selected.role === "admin" && (
                  <div style={{ fontSize: "var(--font-xs)" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                      <Key className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)" }} />
                      <span style={{ fontWeight: 500 }}>API Key</span>
                    </div>
                    <div style={{ display: "flex", gap: 6 }}>
                      <button
                        className="panel-btn-sm"
                        onClick={handleRotateKey}
                        disabled={rotating}
                      >
                        <RotateCw className={`h-3 w-3 ${rotating ? "animate-spin" : ""}`} />
                        <span>Rotate key</span>
                      </button>
                    </div>
                    <div style={{ marginTop: 4, fontSize: 10, color: "var(--muted-foreground)" }}>
                      Rotating generates a new key. The old key stops working immediately.
                    </div>
                  </div>
                )}
              </div>

              {/* Quick actions */}
              <div style={{ padding: "12px 14px", display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  className="panel-btn-sm"
                  onClick={() => setActiveView("workspaces")}
                >
                  <FolderOpen className="h-3 w-3" />
                  <span>Workspaces</span>
                </button>
                <button
                  className="panel-btn-sm"
                  onClick={() => setActiveView("deploy")}
                >
                  <ChevronRight className="h-3 w-3" />
                  <span>Deploy</span>
                </button>
                <button
                  className="panel-btn-sm"
                  onClick={() => setActiveView("secrets")}
                >
                  <Key className="h-3 w-3" />
                  <span>Secrets</span>
                </button>
                {selected.role === "admin" && (
                  <button
                    className="svc-btn red"
                    style={{ marginLeft: "auto" }}
                    onClick={() => handleDelete(selected)}
                    title="Delete project"
                  >
                    <Trash2 className="h-3 w-3" />
                    <span style={{ fontSize: 11 }}>Delete</span>
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
