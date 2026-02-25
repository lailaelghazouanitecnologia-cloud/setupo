"use client";

import { useState, useEffect } from "react";
import {
  FolderOpen, Plus, RefreshCw, Terminal, FileText,
  Trash2, ExternalLink, FolderTree,
} from "lucide-react";
import { execCommand, listFiles } from "@/lib/api/client";

const WORKSPACES_ROOT = "/opt/setupo/workspaces";

interface WorkspaceInfo {
  name: string;
  path: string;
  files: number;
}

export function ProjectsPanel() {
  const [workspaces, setWorkspaces] = useState<WorkspaceInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [selected, setSelected] = useState<WorkspaceInfo | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<any[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);

  const fetchWorkspaces = async () => {
    setLoading(true);
    try {
      const res = await execCommand(`ls -1 ${WORKSPACES_ROOT} 2>/dev/null || echo ""`, WORKSPACES_ROOT, 10);
      const dirs = res.stdout.trim().split("\n").filter(Boolean);
      const ws: WorkspaceInfo[] = [];
      for (const dir of dirs) {
        const count = await execCommand(`find ${WORKSPACES_ROOT}/${dir} -maxdepth 1 -type f | wc -l`, WORKSPACES_ROOT, 5);
        ws.push({
          name: dir,
          path: `${WORKSPACES_ROOT}/${dir}`,
          files: parseInt(count.stdout.trim()) || 0,
        });
      }
      setWorkspaces(ws);
    } catch {
      setWorkspaces([]);
    }
    setLoading(false);
  };

  useEffect(() => { fetchWorkspaces(); }, []);

  const createWorkspace = async () => {
    const name = newName.trim().replace(/[^a-zA-Z0-9_-]/g, "-");
    if (!name) return;
    try {
      await execCommand(`mkdir -p ${WORKSPACES_ROOT}/${name}`, WORKSPACES_ROOT, 5);
      setNewName("");
      setCreating(false);
      fetchWorkspaces();
    } catch {}
  };

  const deleteWorkspace = async (ws: WorkspaceInfo) => {
    if (!confirm(`Delete workspace "${ws.name}"? This will remove the directory and all its contents.`)) return;
    try {
      await execCommand(`rm -rf ${ws.path}`, WORKSPACES_ROOT, 10);
      if (selected?.name === ws.name) {
        setSelected(null);
        setSelectedFiles([]);
      }
      fetchWorkspaces();
    } catch {}
  };

  const selectWorkspace = async (ws: WorkspaceInfo) => {
    setSelected(ws);
    setFilesLoading(true);
    try {
      const res = await listFiles(ws.path);
      setSelectedFiles(res.items || []);
    } catch {
      setSelectedFiles([]);
    }
    setFilesLoading(false);
  };

  return (
    <div>
      {/* Header */}
      <div className="panel-header-row">
        <span className="panel-count">{workspaces.length} workspace{workspaces.length !== 1 ? "s" : ""}</span>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="panel-btn-sm" onClick={fetchWorkspaces} disabled={loading}>
            <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button className="panel-btn-sm" onClick={() => setCreating(true)}>
            <Plus className="h-3 w-3" />
            <span>New</span>
          </button>
        </div>
      </div>

      {/* Create workspace */}
      {creating && (
        <div className="proj-create">
          <input
            className="proj-input"
            type="text"
            placeholder="Workspace name (e.g. my-app)"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") createWorkspace();
              if (e.key === "Escape") { setCreating(false); setNewName(""); }
            }}
            autoFocus
          />
          <button className="panel-btn-sm" onClick={createWorkspace} disabled={!newName.trim()}>
            Create
          </button>
          <button className="panel-btn-sm" onClick={() => { setCreating(false); setNewName(""); }}>
            Cancel
          </button>
        </div>
      )}

      {workspaces.length === 0 && !loading ? (
        <div className="panel-empty">
          <FolderTree className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
          <div className="panel-empty-title">No workspaces</div>
          <div className="panel-empty-sub">Create a workspace to get started. Each workspace is a directory on your VPS.</div>
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
                  <div className="proj-card-meta">{ws.files} files</div>
                </div>
                <div className="proj-card-actions">
                  <button
                    className="svc-btn red"
                    title="Delete"
                    onClick={(e) => { e.stopPropagation(); deleteWorkspace(ws); }}
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
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
