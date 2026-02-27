"use client";

import { useState, useEffect } from "react";
import {
  FolderOpen, Plus, RefreshCw, FileText,
  Trash2, FolderTree, Rocket, GitBranch,
  Package, Upload, RotateCcw,
} from "lucide-react";
import {
  listProjects, listWorkspaces, createWorkspace,
  deleteWorkspace as apiDeleteWorkspace, getWorkspaceFiles,
  zarVersions,
} from "@/lib/api/client";
import { useDashboardStore } from "@/stores/dashboard-store";

interface Project {
  id: string;
  name: string;
}

interface Workspace {
  id: string;
  name: string;
  path: string;
  ws_type: string;
  stack: string;
  description: string;
  branch: string;
  created_at: string;
  exists: boolean;
  is_git: boolean;
  instance_id: string;
}

export function ProjectsPanel() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newStack, setNewStack] = useState("node");
  const [selected, setSelected] = useState<Workspace | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<any[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [error, setError] = useState("");
  const [wsVersions, setWsVersions] = useState<string[]>([]);
  const [wsBranches, setWsBranches] = useState<string[]>([]);
  const setActiveView = useDashboardStore((s) => s.setActiveView);

  const fetchProjects = async () => {
    try {
      const res = await listProjects();
      setProjects(res.projects || []);
      if (res.projects?.length && !selectedProject) {
        setSelectedProject(res.projects[0]);
      }
    } catch {
      setProjects([]);
    }
  };

  const fetchWorkspaces = async (projectId?: string) => {
    const pid = projectId || selectedProject?.id;
    if (!pid) return;
    setLoading(true);
    setError("");
    try {
      const res = await listWorkspaces(pid);
      setWorkspaces(res.workspaces || []);
    } catch (e: any) {
      setWorkspaces([]);
      setError(e.message?.includes("401") ? "Not authorized — log out and log back in" : "Failed to load workspaces");
    }
    setLoading(false);
  };

  useEffect(() => { fetchProjects(); }, []);
  useEffect(() => {
    if (selectedProject) {
      fetchWorkspaces(selectedProject.id);
      setSelected(null);
      setSelectedFiles([]);
    }
  }, [selectedProject?.id]);

  const handleCreate = async () => {
    const name = newName.trim().replace(/[^a-zA-Z0-9_-]/g, "-");
    if (!name || !selectedProject) return;
    try {
      await createWorkspace(selectedProject.id, name, newStack);
      setNewName("");
      setNewStack("node");
      setCreating(false);
      fetchWorkspaces();
    } catch (e: any) {
      setError(e.message || "Create failed");
    }
  };

  const handleDelete = async (ws: Workspace) => {
    if (!selectedProject) return;
    if (!confirm(`Delete workspace "${ws.name}"? This will remove the directory and all its contents.`)) return;
    try {
      await apiDeleteWorkspace(selectedProject.id, ws.name);
      if (selected?.name === ws.name) {
        setSelected(null);
        setSelectedFiles([]);
      }
      fetchWorkspaces();
    } catch {}
  };

  const selectWorkspace = async (ws: Workspace) => {
    setSelected(ws);
    if (!selectedProject) return;
    setFilesLoading(true);
    try {
      const res = await getWorkspaceFiles(selectedProject.id, ws.name);
      setSelectedFiles(res.items || []);
    } catch {
      setSelectedFiles([]);
    }
    setFilesLoading(false);
    // Fetch versions info
    zarVersions(selectedProject.id, ws.name, ws.branch || "main")
      .then((r) => { setWsVersions(r.versions || []); setWsBranches(r.branches || []); })
      .catch(() => { setWsVersions([]); setWsBranches([]); });
  };

  return (
    <div>
      {/* Project selector */}
      {projects.length > 1 && (
        <div className="panel-header-row" style={{ marginBottom: 8 }}>
          <select
            className="proj-input"
            value={selectedProject?.id || ""}
            onChange={(e) => {
              const p = projects.find((pr) => pr.id === e.target.value);
              if (p) setSelectedProject(p);
            }}
            style={{ maxWidth: 240 }}
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
      )}

      {/* Header */}
      <div className="panel-header-row">
        <span className="panel-count">
          {selectedProject ? `${selectedProject.name} — ` : ""}
          {workspaces.length} workspace{workspaces.length !== 1 ? "s" : ""}
        </span>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="panel-btn-sm" onClick={() => fetchWorkspaces()} disabled={loading}>
            <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button className="panel-btn-sm" onClick={() => setCreating(true)}>
            <Plus className="h-3 w-3" />
            <span>New</span>
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: "8px 12px", fontSize: "var(--font-xs)", color: "var(--color-red)", background: "rgba(239,68,68,0.08)", borderRadius: 6, margin: "8px 0" }}>
          {error}
        </div>
      )}

      {/* Create workspace */}
      {creating && (
        <div className="proj-create">
          <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
            <input
              className="proj-input"
              type="text"
              placeholder="Workspace name (e.g. my-app)"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleCreate();
                if (e.key === "Escape") { setCreating(false); setNewName(""); }
              }}
              style={{ flex: 1 }}
              autoFocus
            />
            <select className="deploy-select" value={newStack} onChange={(e) => setNewStack(e.target.value)} style={{ border: "1px solid var(--border)", borderRadius: 6, padding: "4px 8px", minWidth: 90 }}>
              <option value="node">Node</option>
              <option value="python">Python</option>
              <option value="static">Static</option>
              <option value="custom">Custom</option>
            </select>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button className="panel-btn-sm" onClick={handleCreate} disabled={!newName.trim()}>
              Create
            </button>
            <button className="panel-btn-sm" onClick={() => { setCreating(false); setNewName(""); }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {!selectedProject && !loading ? (
        <div className="panel-empty">
          <FolderTree className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
          <div className="panel-empty-title">No projects</div>
          <div className="panel-empty-sub">Create a project first via the API or CLI.</div>
        </div>
      ) : workspaces.length === 0 && !loading ? (
        <div className="panel-empty">
          <FolderTree className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
          <div className="panel-empty-title">No workspaces</div>
          <div className="panel-empty-sub">Create a workspace to get started.</div>
          <button className="panel-btn" onClick={() => setCreating(true)}>
            <Plus className="h-3.5 w-3.5" />
            <span>Create workspace</span>
          </button>
        </div>
      ) : (
        <div className="proj-layout">
          {/* Workspace list */}
          <div className="proj-list">
            {workspaces.map((ws) => (
              <div
                key={ws.name}
                className={`proj-card ${selected?.name === ws.name ? "active" : ""}`}
                onClick={() => selectWorkspace(ws)}
              >
                <div className="proj-card-icon">
                  <FolderOpen className="h-4 w-4" style={{ color: "var(--color-teal)" }} />
                </div>
                <div className="proj-card-info">
                  <div className="proj-card-name">{ws.name}</div>
                  <div className="proj-card-meta">
                    {ws.stack || ws.ws_type}{ws.branch ? ` / ${ws.branch}` : ""}
                    {ws.is_git && " (git)"}
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <span className={`inst-badge ${ws.exists ? "green" : "yellow"}`}>
                    {ws.exists ? "ready" : "missing"}
                  </span>
                  <div className="proj-card-actions">
                    <button
                      className="svc-btn red"
                      title="Delete"
                      onClick={(e) => { e.stopPropagation(); handleDelete(ws); }}
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Workspace detail */}
          {selected && (
            <div className="proj-detail">
              <div className="proj-detail-header">
                <FolderOpen className="h-4 w-4" style={{ color: "var(--color-teal)" }} />
                <span className="proj-detail-name">{selected.name}</span>
                <span className="proj-detail-path">{selected.path}</span>
              </div>
              {/* Info bar: branch, versions, deploy button */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 14px", borderBottom: "1px solid var(--border)", flexWrap: "wrap" }}>
                <div className="pill">
                  <GitBranch className="h-3 w-3" style={{ color: "var(--color-purple)" }} />
                  <span>{selected.branch || "main"}</span>
                </div>
                {wsBranches.length > 0 && (
                  <span style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)" }}>
                    {wsBranches.length} branch{wsBranches.length !== 1 ? "es" : ""}
                  </span>
                )}
                {wsVersions.length > 0 && (
                  <div className="pill">
                    <Package className="h-3 w-3" style={{ color: "var(--color-blue)" }} />
                    <span>{wsVersions.length} version{wsVersions.length !== 1 ? "s" : ""}</span>
                  </div>
                )}
                <div style={{ marginLeft: "auto" }}>
                  <button
                    className="deploy-action-btn teal"
                    style={{ padding: "3px 10px", fontSize: "var(--font-xs)" }}
                    onClick={() => setActiveView("deploy")}
                  >
                    <Rocket className="h-3 w-3" />
                    <span>Deploy</span>
                  </button>
                </div>
              </div>
              {selected.description && (
                <div style={{ padding: "4px 12px", fontSize: "var(--font-xs)", color: "var(--muted-foreground)" }}>
                  {selected.description}
                </div>
              )}
              <div className="proj-detail-files">
                {filesLoading ? (
                  <div style={{ padding: 20, textAlign: "center", color: "var(--muted-foreground)", fontSize: "var(--font-xs)" }}>
                    Loading...
                  </div>
                ) : selectedFiles.length === 0 ? (
                  <div style={{ padding: 20, textAlign: "center", color: "var(--muted-foreground)", fontSize: "var(--font-xs)" }}>
                    Empty workspace
                  </div>
                ) : (
                  selectedFiles.map((f: any) => (
                    <div key={f.name} className="proj-file-row">
                      {f.type === "dir"
                        ? <FolderOpen className="h-3.5 w-3.5" style={{ color: "var(--color-blue)" }} />
                        : <FileText className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)" }} />}
                      <span className="proj-file-name">{f.name}</span>
                      {f.size != null && (
                        <span className="proj-file-size">{formatSize(f.size)}</span>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
