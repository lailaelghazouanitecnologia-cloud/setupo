"use client";

import { useState, useEffect, useCallback } from "react";
import {
  FolderOpen, Plus, RefreshCw, Trash2,
  File, Folder, ChevronRight,
  ArrowLeft, FileText, Code, Image,
  GitBranch, Package, Copy, Check,
  Lock, Globe, Settings, Link,
} from "lucide-react";
import {
  listWorkspaces, createWorkspace, deleteWorkspace as apiDeleteWorkspace,
  getWorkspaceFiles, readWorkspaceFile, zarVersions,
} from "@/lib/api/client";
import { useDashboardStore } from "@/stores/dashboard-store";
import { tokenizeFile, estimateTokens } from "@/components/dashboard/file-token-view";
import { formatSize, timeAgo } from "@/lib/format";

/* ═══════════════════════════════════════════
   TYPES
   ═══════════════════════════════════════════ */

interface Workspace {
  id: string;
  name: string;
  path: string;
  ws_type: string;
  stack: string;
  description: string;
  created_at: string;
  exists: boolean;
  deployed?: boolean;
  deploy_url?: string | null;
  instance_label?: string | null;
  instance_ip?: string | null;
  instance_state?: string | null;
}

interface FileItem {
  name: string;
  path: string;
  type: "file" | "dir";
  size?: number;
  modified?: number;
}

/* ═══════════════════════════════════════════
   FILE ICON HELPER
   ═══════════════════════════════════════════ */

const EXT_COLORS: Record<string, string> = {
  ts: "#3b82f6", tsx: "#3b82f6", js: "#eab308", jsx: "#eab308",
  py: "#22c55e", rs: "#f97316", go: "#06b6d4",
  java: "#ef4444", c: "#8b5cf6", cpp: "#8b5cf6", h: "#8b5cf6",
};
const IMG_EXTS = new Set(["png", "jpg", "jpeg", "gif", "svg", "webp", "ico"]);
const TEXT_EXTS = new Set(["md", "txt", "toml", "yaml", "yml", "json", "xml", "html", "css"]);

function FileIcon({ name }: { name: string }) {
  const ext = name.split(".").pop()?.toLowerCase() || "";
  if (EXT_COLORS[ext]) return <Code className="ws-file-icon" style={{ color: EXT_COLORS[ext] }} />;
  if (IMG_EXTS.has(ext)) return <Image className="ws-file-icon" style={{ color: "#e879a0" }} />;
  if (TEXT_EXTS.has(ext)) return <FileText className="ws-file-icon" style={{ color: "var(--muted-foreground)" }} />;
  return <File className="ws-file-icon" style={{ color: "var(--muted-foreground)" }} />;
}

const STACK_LABELS: Record<string, { label: string; color: string }> = {
  node: { label: "Node.js", color: "#22c55e" },
  python: { label: "Python", color: "#3b82f6" },
  static: { label: "Static", color: "#8b5cf6" },
  go: { label: "Go", color: "#06b6d4" },
  rust: { label: "Rust", color: "#f97316" },
  docker: { label: "Docker", color: "#2496ed" },
  custom: { label: "Custom", color: "var(--muted-foreground)" },
};

/* ═══════════════════════════════════════════
   MAIN PANEL
   ═══════════════════════════════════════════ */

export function WorkspacesPanel() {
  const activeProject = useDashboardStore((s) => s.activeProject);
  const workspaces = useDashboardStore((s) => s.workspaces);
  const setWorkspaces = useDashboardStore((s) => s.setWorkspaces);
  const activeWorkspace = useDashboardStore((s) => s.activeWorkspace);
  const setActiveWorkspace = useDashboardStore((s) => s.setActiveWorkspace);

  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newStack, setNewStack] = useState("custom");
  const [newDesc, setNewDesc] = useState("");
  const [newGitUrl, setNewGitUrl] = useState("");
  const [newReadonly, setNewReadonly] = useState(false);

  const [tab, setTab] = useState<"files" | "versions">("files");

  // File browser
  const [browsePath, setBrowsePath] = useState(".");
  const [files, setFiles] = useState<FileItem[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [viewingFile, setViewingFile] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Versions
  const [versions, setVersions] = useState<string[]>([]);
  const [branches, setBranches] = useState<Record<string, string>>({});
  const [versionsLoading, setVersionsLoading] = useState(false);

  const fetchWorkspaces = useCallback(async () => {
    if (!activeProject) return;
    setLoading(true);
    try {
      const res = await listWorkspaces(activeProject.id);
      setWorkspaces(res.workspaces || []);
    } catch { setWorkspaces([]); }
    setLoading(false);
  }, [activeProject, setWorkspaces]);

  useEffect(() => { fetchWorkspaces(); }, [fetchWorkspaces]);

  const fetchFiles = useCallback(async () => {
    if (!activeProject || !activeWorkspace) return;
    setFilesLoading(true);
    setFileContent(null);
    setViewingFile(null);
    try {
      const res = await getWorkspaceFiles(activeProject.id, activeWorkspace.name, browsePath);
      const items: FileItem[] = (res.items || []).sort((a: FileItem, b: FileItem) => {
        if (a.type !== b.type) return a.type === "dir" ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
      setFiles(items);
    } catch { setFiles([]); }
    setFilesLoading(false);
  }, [activeProject, activeWorkspace, browsePath]);

  useEffect(() => {
    if (tab === "files") fetchFiles();
  }, [fetchFiles, tab]);

  const fetchVersions = useCallback(async () => {
    if (!activeProject || !activeWorkspace) return;
    setVersionsLoading(true);
    try {
      const res = await zarVersions(activeProject.id, activeWorkspace.name);
      setVersions(res.versions || []);
      setBranches(res.branches || {});
    } catch { setVersions([]); setBranches({}); }
    setVersionsLoading(false);
  }, [activeProject, activeWorkspace]);

  useEffect(() => {
    if (tab === "versions") fetchVersions();
  }, [fetchVersions, tab]);

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name || !activeProject) return;
    try {
      await createWorkspace(activeProject.id, name, newStack, newDesc, newGitUrl);
      setNewName("");
      setNewStack("custom");
      setNewDesc("");
      setNewGitUrl("");
      setNewReadonly(false);
      setCreating(false);
      fetchWorkspaces();
    } catch (e: any) { alert(e.message || "Failed to create workspace"); }
  };

  const handleDelete = async (ws: Workspace) => {
    if (!activeProject || !confirm(`Delete workspace "${ws.name}"?`)) return;
    try {
      await apiDeleteWorkspace(activeProject.id, ws.name);
      if (activeWorkspace?.id === ws.id) setActiveWorkspace(null);
      fetchWorkspaces();
    } catch (e: any) { alert(e.message || "Failed to delete workspace"); }
  };

  const handleOpenFile = async (item: FileItem) => {
    if (item.type === "dir") { setBrowsePath(item.path); return; }
    if (!activeProject || !activeWorkspace) return;
    try {
      const res = await readWorkspaceFile(activeProject.id, activeWorkspace.name, item.path);
      setFileContent(res.content);
      setViewingFile(item.path);
    } catch {
      setFileContent("// Failed to read file");
      setViewingFile(item.path);
    }
  };

  const navigateUp = () => {
    if (browsePath === ".") return;
    const parts = browsePath.split("/");
    parts.pop();
    setBrowsePath(parts.length === 0 ? "." : parts.join("/"));
  };

  const copyFileContent = () => {
    if (fileContent) {
      navigator.clipboard.writeText(fileContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (!activeProject) {
    return (
      <div className="ws-empty-root">
        <FolderOpen className="ws-empty-icon" />
        <p className="ws-empty-title">Select a project</p>
        <p className="ws-empty-sub">Choose a project from the sidebar to view workspaces</p>
      </div>
    );
  }

  return (
    <div className="ws-layout">
      {/* ── Sidebar: workspace list ── */}
      <aside className="ws-sidebar">
        <div className="ws-sidebar-header">
          <span className="ws-sidebar-label">Workspaces</span>
          <div className="ws-sidebar-actions">
            <button className="ws-icon-btn" onClick={fetchWorkspaces} title="Refresh">
              <RefreshCw className="h-3 w-3" />
            </button>
            <button className="ws-icon-btn" onClick={() => setCreating(!creating)} title="New workspace">
              <Plus className="h-3 w-3" />
            </button>
          </div>
        </div>

        {creating && (
          <div className="ws-create-form">
            <input
              className="ws-create-input"
              placeholder="workspace-name"
              value={newName}
              onChange={(e) => setNewName(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""))}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              autoFocus
            />

            {/* Stack selector */}
            <div className="ws-create-stacks">
              {(["python", "node", "static", "custom"] as const).map((s) => {
                const info = STACK_LABELS[s];
                return (
                  <button
                    key={s}
                    className={`ws-stack-chip ${newStack === s ? "active" : ""}`}
                    onClick={() => setNewStack(s)}
                    style={newStack === s ? { borderColor: info.color, color: info.color } : {}}
                  >
                    <span className="ws-stack-dot" style={{ background: info.color }} />
                    {info.label}
                  </button>
                );
              })}
            </div>

            {/* Git URL (optional) */}
            <input
              className="ws-create-input"
              placeholder="Git URL (optional) — user/repo or https://..."
              value={newGitUrl}
              onChange={(e) => setNewGitUrl(e.target.value)}
            />

            {/* Description (optional) */}
            <input
              className="ws-create-input"
              placeholder="Description (optional)"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
            />

            {/* Readonly toggle */}
            <label className="ws-create-toggle">
              <input
                type="checkbox"
                checked={newReadonly}
                onChange={(e) => setNewReadonly(e.target.checked)}
              />
              <Lock className="h-3 w-3" />
              <span>Read-only (protect config files)</span>
            </label>

            <div className="ws-create-actions">
              <button className="ws-btn ws-btn-primary" onClick={handleCreate}>Create</button>
              <button className="ws-btn ws-btn-ghost" onClick={() => setCreating(false)}>Cancel</button>
            </div>
          </div>
        )}

        <div className="ws-sidebar-list">
          {loading ? (
            <div className="ws-sidebar-loading">Loading...</div>
          ) : workspaces.length === 0 ? (
            <div className="ws-sidebar-empty">
              <FolderOpen className="h-5 w-5" style={{ opacity: 0.2 }} />
              <p>No workspaces yet</p>
            </div>
          ) : (
            workspaces.map((ws: any) => {
              const stack = STACK_LABELS[ws.stack || ws.ws_type] || STACK_LABELS.custom;
              const isDeployed = ws.deployed === true;
              return (
                <button
                  key={ws.id}
                  className={`ws-sidebar-item ${activeWorkspace?.id === ws.id ? "active" : ""}`}
                  onClick={() => { setActiveWorkspace(ws); setBrowsePath("."); }}
                >
                  <div className="ws-sidebar-item-icon">
                    <FolderOpen className="h-3.5 w-3.5" />
                  </div>
                  <div className="ws-sidebar-item-info">
                    <span className="ws-sidebar-item-name">{ws.name}</span>
                  </div>
                  <button
                    className="ws-sidebar-item-delete"
                    onClick={(e) => { e.stopPropagation(); handleDelete(ws); }}
                    title="Delete"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </button>
              );
            })
          )}
        </div>
      </aside>

      {/* ── Main: file browser + versions ── */}
      <main className="ws-main">
        {!activeWorkspace ? (
          <div className="ws-empty-root">
            <FolderOpen className="ws-empty-icon" />
            <p className="ws-empty-title">Select a workspace</p>
            <p className="ws-empty-sub">Choose a workspace to browse files and versions</p>
          </div>
        ) : (
          <>
            {/* Tab bar */}
            <div className="ws-tabs">
              <button className={`ws-tab ${tab === "files" ? "active" : ""}`} onClick={() => setTab("files")}>
                <FolderOpen className="h-3.5 w-3.5" /> Files
              </button>
              <button className={`ws-tab ${tab === "versions" ? "active" : ""}`} onClick={() => setTab("versions")}>
                <Package className="h-3.5 w-3.5" /> Versions
              </button>
            </div>

            {tab === "files" && viewingFile ? (
              /* ── File viewer — inline tokenized ── */
              <div className="ws-file-viewer ws-file-viewer-full">
                <div className="ws-file-viewer-header">
                  <button className="ws-icon-btn" onClick={() => { setViewingFile(null); setFileContent(null); }}>
                    <ArrowLeft className="h-3.5 w-3.5" />
                  </button>
                  <div className="ws-breadcrumb">
                    <span className="ws-breadcrumb-muted">{activeWorkspace.name} /</span>
                    <span className="ws-breadcrumb-current">{viewingFile}</span>
                  </div>
                  <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "10px" }}>
                    {fileContent !== null && (
                      <span className="ws-file-stats">
                        {estimateTokens(fileContent).toLocaleString()} tokens · {fileContent.split("\n").length} lines
                      </span>
                    )}
                    <button className="ws-icon-btn" onClick={copyFileContent} title="Copy content">
                      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                </div>
                <div className="ws-file-viewer-code">
                  {fileContent !== null && (
                    <pre className="ftv-code">
                      {tokenizeFile(fileContent, viewingFile).map((line) => (
                        <div key={line.lineNumber} className="ftv-line">
                          <span className="ftv-line-num">{line.lineNumber}</span>
                          <span className="ftv-line-content">
                            {line.tokens.map((tok, ti) => (
                              <span key={ti} className={`ftv-tok ftv-tok-${tok.kind}`}>
                                {tok.text}
                              </span>
                            ))}
                          </span>
                        </div>
                      ))}
                    </pre>
                  )}
                </div>
              </div>
            ) : tab === "files" ? (
              /* ── Directory listing ── */
              <div className="ws-files">
                <div className="ws-files-header">
                  {browsePath !== "." && (
                    <button className="ws-icon-btn" onClick={navigateUp}>
                      <ArrowLeft className="h-3.5 w-3.5" />
                    </button>
                  )}
                  <div className="ws-breadcrumb">
                    <span className="ws-breadcrumb-current">{activeWorkspace.name}</span>
                    {browsePath !== "." && <span className="ws-breadcrumb-muted">/ {browsePath}</span>}
                  </div>
                  <button className="ws-icon-btn" onClick={fetchFiles} title="Refresh" style={{ marginLeft: "auto" }}>
                    <RefreshCw className="h-3 w-3" />
                  </button>
                </div>

                <div className="ws-files-body">
                  {filesLoading ? (
                    <div className="ws-files-empty">Loading...</div>
                  ) : files.length === 0 ? (
                    <div className="ws-files-empty">
                      <Folder className="h-5 w-5" style={{ opacity: 0.2 }} />
                      <p>Empty directory</p>
                    </div>
                  ) : (
                    <table className="ws-file-table">
                      <thead>
                        <tr>
                          <th className="ws-ft-name">Name</th>
                          <th className="ws-ft-size">Size</th>
                          <th className="ws-ft-modified">Modified</th>
                        </tr>
                      </thead>
                      <tbody>
                        {files.map((item) => (
                          <tr key={item.path} className="ws-file-row" onClick={() => handleOpenFile(item)}>
                            <td className="ws-ft-name">
                              <div className="ws-file-name-cell">
                                {item.type === "dir"
                                  ? <Folder className="ws-file-icon" style={{ color: "#60a5fa" }} />
                                  : <FileIcon name={item.name} />
                                }
                                <span className={item.type === "dir" ? "ws-dir-name" : ""}>{item.name}</span>
                                {item.type === "dir" && <ChevronRight className="ws-dir-chevron" />}
                              </div>
                            </td>
                            <td className="ws-ft-size">
                              {item.type === "file" ? formatSize(item.size) : "\u2014"}
                            </td>
                            <td className="ws-ft-modified">
                              {item.modified ? timeAgo(new Date(item.modified * 1000).toISOString()) : "\u2014"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            ) : (
              /* ── Versions tab ── */
              <div className="ws-versions">
                {Object.keys(branches).length > 0 && (
                  <div className="ws-versions-section">
                    <div className="ws-section-header">
                      <GitBranch className="h-3.5 w-3.5" style={{ opacity: 0.5 }} />
                      <span>Branches</span>
                    </div>
                    {Object.entries(branches).map(([branch, latest]) => (
                      <div key={branch} className="ws-branch-row">
                        <GitBranch className="h-3.5 w-3.5 ws-branch-icon" />
                        <span className="ws-branch-name">{branch}</span>
                        <code className="ws-branch-version">{latest}</code>
                      </div>
                    ))}
                  </div>
                )}

                <div className="ws-versions-section">
                  <div className="ws-section-header">
                    <Package className="h-3.5 w-3.5" style={{ opacity: 0.5 }} />
                    <span>Versions ({versions.length})</span>
                    <button className="ws-icon-btn" onClick={fetchVersions} title="Refresh" style={{ marginLeft: "auto" }}>
                      <RefreshCw className="h-3 w-3" />
                    </button>
                  </div>
                  {versionsLoading ? (
                    <div className="ws-files-empty">Loading...</div>
                  ) : versions.length === 0 ? (
                    <div className="ws-files-empty">
                      <Package className="h-5 w-5" style={{ opacity: 0.2 }} />
                      <p>No versions deployed yet</p>
                    </div>
                  ) : (
                    <div className="ws-version-list">
                      {versions.map((v, i) => (
                        <div key={v} className="ws-version-row">
                          <Package className="h-3.5 w-3.5" style={{ opacity: 0.35 }} />
                          <code className="ws-version-name">{v}</code>
                          {i === 0 && <span className="ws-version-badge">latest</span>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
