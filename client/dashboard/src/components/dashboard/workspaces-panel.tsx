"use client";

import { useState, useEffect, useCallback } from "react";
import {
  FolderOpen, Plus, RefreshCw, Trash2,
  File, Folder, ChevronRight, ChevronDown,
  ArrowLeft, FileText, Code, Image,
  GitBranch, Package,
} from "lucide-react";
import {
  listWorkspaces, createWorkspace, deleteWorkspace as apiDeleteWorkspace,
  getWorkspaceFiles, readWorkspaceFile, zarVersions,
} from "@/lib/api/client";
import { useDashboardStore } from "@/stores/dashboard-store";
import { formatSize } from "@/lib/format";

interface Workspace {
  id: string;
  name: string;
  path: string;
  ws_type: string;
  stack: string;
  description: string;
  created_at: string;
  exists: boolean;
}

interface FileItem {
  name: string;
  path: string;
  type: "file" | "dir";
  size?: number;
  modified?: number;
}



function fileIcon(name: string) {
  const ext = name.split(".").pop()?.toLowerCase() || "";
  if (["ts", "tsx", "js", "jsx", "py", "rs", "go", "java", "c", "cpp", "h"].includes(ext))
    return <Code className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} />;
  if (["png", "jpg", "jpeg", "gif", "svg", "ico", "webp"].includes(ext))
    return <Image className="h-3.5 w-3.5" style={{ color: "#e879a0" }} />;
  if (["md", "txt", "toml", "yaml", "yml", "json", "xml", "html", "css"].includes(ext))
    return <FileText className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)" }} />;
  return <File className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)" }} />;
}

export function WorkspacesPanel() {
  const activeProject = useDashboardStore((s) => s.activeProject);
  const workspaces = useDashboardStore((s) => s.workspaces);
  const setWorkspaces = useDashboardStore((s) => s.setWorkspaces);
  const activeWorkspace = useDashboardStore((s) => s.activeWorkspace);
  const setActiveWorkspace = useDashboardStore((s) => s.setActiveWorkspace);

  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newStack, setNewStack] = useState("node");

  // Tab state
  const [tab, setTab] = useState<"files" | "versions">("files");

  // File browser state
  const [browsePath, setBrowsePath] = useState(".");
  const [files, setFiles] = useState<FileItem[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [viewingFile, setViewingFile] = useState<string | null>(null);

  // Versions state
  const [versions, setVersions] = useState<string[]>([]);
  const [branches, setBranches] = useState<Record<string, string>>({});
  const [versionsLoading, setVersionsLoading] = useState(false);

  const fetchWorkspaces = useCallback(async () => {
    if (!activeProject) return;
    setLoading(true);
    try {
      const res = await listWorkspaces(activeProject.id);
      setWorkspaces(res.workspaces || []);
    } catch {
      setWorkspaces([]);
    }
    setLoading(false);
  }, [activeProject, setWorkspaces]);

  useEffect(() => {
    fetchWorkspaces();
  }, [fetchWorkspaces]);

  // Load files when workspace or path changes
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
    } catch {
      setFiles([]);
    }
    setFilesLoading(false);
  }, [activeProject, activeWorkspace, browsePath]);

  useEffect(() => {
    if (tab === "files") fetchFiles();
  }, [fetchFiles, tab]);

  // Load versions when workspace changes or versions tab selected
  const fetchVersions = useCallback(async () => {
    if (!activeProject || !activeWorkspace) return;
    setVersionsLoading(true);
    try {
      const res = await zarVersions(activeProject.id, activeWorkspace.name);
      setVersions(res.versions || []);
      setBranches(res.branches || {});
    } catch {
      setVersions([]);
      setBranches({});
    }
    setVersionsLoading(false);
  }, [activeProject, activeWorkspace]);

  useEffect(() => {
    if (tab === "versions") fetchVersions();
  }, [fetchVersions, tab]);

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name || !activeProject) return;
    try {
      await createWorkspace(activeProject.id, name, newStack);
      setNewName("");
      setCreating(false);
      fetchWorkspaces();
    } catch (e: any) {
      alert(e.message || "Failed to create workspace");
    }
  };

  const handleDelete = async (ws: Workspace) => {
    if (!activeProject || !confirm(`Delete workspace "${ws.name}"?`)) return;
    try {
      await apiDeleteWorkspace(activeProject.id, ws.name);
      if (activeWorkspace?.id === ws.id) setActiveWorkspace(null);
      fetchWorkspaces();
    } catch (e: any) {
      alert(e.message || "Failed to delete workspace");
    }
  };

  const handleOpenFile = async (item: FileItem) => {
    if (item.type === "dir") {
      setBrowsePath(item.path);
      return;
    }
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

  if (!activeProject) {
    return (
      <div className="panel-empty">
        <FolderOpen className="h-8 w-8" style={{ opacity: 0.3 }} />
        <p>Select a project to view workspaces</p>
      </div>
    );
  }

  return (
    <div style={{
      display: "flex", gap: 0,
      height: "calc(100vh - 100px)",
      border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden",
      background: "var(--card)",
    }}>
      {/* Sidebar: workspace list */}
      <div style={{
        width: 220, minWidth: 220, borderRight: "1px solid var(--border)",
        display: "flex", flexDirection: "column", overflow: "hidden",
      }}>
        <div style={{
          padding: "12px 12px 8px", display: "flex", alignItems: "center",
          justifyContent: "space-between", borderBottom: "1px solid var(--border)",
        }}>
          <span style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", opacity: 0.6 }}>Workspaces</span>
          <div style={{ display: "flex", gap: 4 }}>
            <button className="ibtn" onClick={fetchWorkspaces} title="Refresh">
              <RefreshCw className="h-3 w-3" />
            </button>
            <button className="ibtn" onClick={() => setCreating(!creating)} title="New workspace">
              <Plus className="h-3 w-3" />
            </button>
          </div>
        </div>

        {creating && (
          <div style={{ padding: 8, borderBottom: "1px solid var(--border)" }}>
            <input
              style={{
                width: "100%", padding: "4px 8px", fontSize: 12,
                background: "var(--input)", border: "1px solid var(--border)",
                borderRadius: 4, color: "var(--foreground)", marginBottom: 4,
              }}
              placeholder="Name..."
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              autoFocus
            />
            <select
              value={newStack}
              onChange={(e) => setNewStack(e.target.value)}
              style={{
                width: "100%", padding: "4px 8px", fontSize: 11,
                background: "var(--input)", border: "1px solid var(--border)",
                borderRadius: 4, color: "var(--foreground)", marginBottom: 4,
              }}
            >
              <option value="node">Node.js</option>
              <option value="python">Python</option>
              <option value="static">Static</option>
              <option value="custom">Custom</option>
            </select>
            <div style={{ display: "flex", gap: 4 }}>
              <button className="btn btn-sm" onClick={handleCreate}>Create</button>
              <button className="btn btn-sm btn-ghost" onClick={() => setCreating(false)}>Cancel</button>
            </div>
          </div>
        )}

        <div style={{ flex: 1, overflow: "auto" }}>
          {loading ? (
            <div style={{ padding: 16, textAlign: "center", fontSize: 12, opacity: 0.5 }}>Loading...</div>
          ) : workspaces.length === 0 ? (
            <div style={{ padding: 16, textAlign: "center", fontSize: 12, opacity: 0.5 }}>No workspaces</div>
          ) : (
            workspaces.map((ws: any) => (
              <button
                key={ws.id}
                onClick={() => { setActiveWorkspace(ws); setBrowsePath("."); }}
                style={{
                  display: "flex", alignItems: "center", gap: 8, width: "100%",
                  padding: "8px 12px", border: "none", cursor: "pointer",
                  background: activeWorkspace?.id === ws.id ? "var(--accent)" : "transparent",
                  color: "var(--foreground)", fontSize: 12, textAlign: "left",
                  borderBottom: "1px solid var(--border)",
                }}
              >
                <FolderOpen className="h-3.5 w-3.5" style={{ opacity: 0.6, flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{ws.name}</div>
                  <div style={{ fontSize: 10, opacity: 0.5 }}>{ws.stack || ws.ws_type || "custom"}</div>
                </div>
                <button
                  className="ibtn"
                  onClick={(e) => { e.stopPropagation(); handleDelete(ws); }}
                  title="Delete"
                  style={{ opacity: 0.3 }}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Main: file browser + versions */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {!activeWorkspace ? (
          <div className="panel-empty">
            <FolderOpen className="h-8 w-8" style={{ opacity: 0.3 }} />
            <p>Select a workspace to browse files</p>
          </div>
        ) : (
          <>
            {/* Tabs: Files | Versions */}
            <div style={{
              display: "flex", borderBottom: "1px solid var(--border)",
              gap: 0,
            }}>
              {(["files", "versions"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  style={{
                    padding: "8px 16px", border: "none", cursor: "pointer",
                    background: "transparent", color: "var(--foreground)",
                    fontSize: 12, fontWeight: tab === t ? 600 : 400,
                    borderBottom: tab === t ? "2px solid var(--accent)" : "2px solid transparent",
                    opacity: tab === t ? 1 : 0.5,
                    display: "flex", alignItems: "center", gap: 6,
                  }}
                >
                  {t === "files" ? <FolderOpen className="h-3 w-3" /> : <Package className="h-3 w-3" />}
                  {t === "files" ? "Files" : "Versions"}
                </button>
              ))}
            </div>

            {tab === "files" && viewingFile ? (
              /* File viewer */
              <>
                <div style={{
                  padding: "8px 12px", borderBottom: "1px solid var(--border)",
                  display: "flex", alignItems: "center", gap: 8, fontSize: 12,
                }}>
                  <button className="ibtn" onClick={() => { setViewingFile(null); setFileContent(null); }}>
                    <ArrowLeft className="h-3.5 w-3.5" />
                  </button>
                  <span style={{ opacity: 0.5 }}>{activeWorkspace.name} /</span>
                  <span style={{ fontWeight: 500 }}>{viewingFile}</span>
                </div>
                <pre style={{
                  flex: 1, overflow: "auto", padding: 16, margin: 0,
                  fontSize: 12, lineHeight: 1.6, fontFamily: "var(--font-mono, monospace)",
                  whiteSpace: "pre-wrap", wordBreak: "break-all",
                  background: "var(--card)", color: "var(--foreground)",
                }}>
                  {fileContent}
                </pre>
              </>
            ) : tab === "files" ? (
              /* Directory listing */
              <>
                <div style={{
                  padding: "8px 12px", borderBottom: "1px solid var(--border)",
                  display: "flex", alignItems: "center", gap: 8, fontSize: 12,
                }}>
                  {browsePath !== "." && (
                    <button className="ibtn" onClick={navigateUp}>
                      <ArrowLeft className="h-3.5 w-3.5" />
                    </button>
                  )}
                  <span style={{ fontWeight: 500 }}>{activeWorkspace.name}</span>
                  {browsePath !== "." && (
                    <span style={{ opacity: 0.5 }}>/ {browsePath}</span>
                  )}
                  <div style={{ marginLeft: "auto" }}>
                    <button className="ibtn" onClick={fetchFiles} title="Refresh">
                      <RefreshCw className="h-3 w-3" />
                    </button>
                  </div>
                </div>

                <div style={{ flex: 1, overflow: "auto" }}>
                  {filesLoading ? (
                    <div style={{ padding: 16, textAlign: "center", fontSize: 12, opacity: 0.5 }}>Loading...</div>
                  ) : files.length === 0 ? (
                    <div style={{ padding: 16, textAlign: "center", fontSize: 12, opacity: 0.5 }}>Empty directory</div>
                  ) : (
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                      <tbody>
                        {files.map((item) => (
                          <tr
                            key={item.path}
                            onClick={() => handleOpenFile(item)}
                            style={{
                              cursor: "pointer",
                              borderBottom: "1px solid var(--border)",
                            }}
                            className="file-row"
                          >
                            <td style={{ padding: "6px 12px", display: "flex", alignItems: "center", gap: 8 }}>
                              {item.type === "dir"
                                ? <Folder className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} />
                                : fileIcon(item.name)
                              }
                              <span style={{ fontWeight: item.type === "dir" ? 500 : 400 }}>{item.name}</span>
                            </td>
                            <td style={{ padding: "6px 12px", textAlign: "right", opacity: 0.4, whiteSpace: "nowrap" }}>
                              {item.type === "file" ? formatSize(item.size) : ""}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </>
            ) : (
              /* Versions tab */
              <div style={{ flex: 1, overflow: "auto" }}>
                {/* Branches */}
                {Object.keys(branches).length > 0 && (
                  <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)" }}>
                    <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", opacity: 0.5, marginBottom: 8 }}>Branches</div>
                    {Object.entries(branches).map(([branch, latest]) => (
                      <div key={branch} style={{
                        display: "flex", alignItems: "center", gap: 8, padding: "6px 0",
                        fontSize: 12,
                      }}>
                        <GitBranch className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} />
                        <span style={{ fontWeight: 500 }}>{branch}</span>
                        <span style={{ opacity: 0.4, marginLeft: "auto", fontFamily: "var(--font-mono, monospace)", fontSize: 11 }}>
                          {latest}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Versions list */}
                <div style={{ padding: "12px 16px" }}>
                  <div style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8,
                  }}>
                    <span style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", opacity: 0.5 }}>
                      Versions ({versions.length})
                    </span>
                    <button className="ibtn" onClick={fetchVersions} title="Refresh">
                      <RefreshCw className="h-3 w-3" />
                    </button>
                  </div>
                  {versionsLoading ? (
                    <div style={{ padding: 16, textAlign: "center", fontSize: 12, opacity: 0.5 }}>Loading...</div>
                  ) : versions.length === 0 ? (
                    <div style={{ padding: 16, textAlign: "center", fontSize: 12, opacity: 0.5 }}>
                      No versions deployed yet
                    </div>
                  ) : (
                    versions.map((v, i) => (
                      <div key={v} style={{
                        display: "flex", alignItems: "center", gap: 8, padding: "8px 0",
                        borderBottom: "1px solid var(--border)", fontSize: 12,
                      }}>
                        <Package className="h-3.5 w-3.5" style={{ opacity: 0.4 }} />
                        <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11 }}>{v}</span>
                        {i === 0 && (
                          <span style={{
                            marginLeft: "auto", fontSize: 10, padding: "1px 6px",
                            background: "var(--accent)", borderRadius: 3, fontWeight: 500,
                          }}>
                            latest
                          </span>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
