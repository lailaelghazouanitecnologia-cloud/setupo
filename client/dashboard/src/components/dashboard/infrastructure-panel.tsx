"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  Server, Database, HardDrive, Plus, Trash2,
  RefreshCw, Play, Terminal, Copy, CheckCircle,
  XCircle, Upload, Download, FolderOpen, File,
  ChevronRight, Eye, EyeOff, AlertTriangle, Activity,
} from "lucide-react";
import { InstancesTab, ServicesTab } from "./instances-panel";
import { useDashboardStore } from "@/stores/dashboard-store";
import {
  listDatabases, createDatabase, deleteDatabase,
  queryDatabase, getDatabaseStatus,
  listBuckets, createBucket, deleteBucket,
  listBucketObjects, uploadObject, downloadObject, deleteObject,
} from "@/lib/api/client";

type InfraTab = "instances" | "services" | "database" | "storage";

export function InfrastructurePanel() {
  const [tab, setTab] = useState<InfraTab>("instances");

  const tabs: { id: InfraTab; label: string; icon: React.ElementType }[] = [
    { id: "instances", label: "Machines", icon: Server },
    { id: "services", label: "Services", icon: Activity },
    { id: "database", label: "Database", icon: Database },
    { id: "storage", label: "Storage", icon: HardDrive },
  ];

  return (
    <div>
      <div className="tab-bar">
        {tabs.map((t) => (
          <button
            key={t.id}
            className={`tab-item ${tab === t.id ? "active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            <t.icon className="h-3.5 w-3.5" />
            <span>{t.label}</span>
          </button>
        ))}
      </div>
      {tab === "instances" && <InstancesTab />}
      {tab === "services" && <ServicesTab />}
      {tab === "database" && <DatabaseTab />}
      {tab === "storage" && <StorageTab />}
    </div>
  );
}

/* ═══════════════════════════════════════════
   DATABASE TAB
   ═══════════════════════════════════════════ */

interface ManagedDatabase {
  id: string;
  project_id: string;
  instance_id: string;
  name: string;
  engine: string;
  version: string;
  host: string;
  port: number;
  db_user: string;
  password_encrypted: string;
  state: string;
  size_mb: number;
  error: string;
  created_at: string;
  ready_at: string;
}

interface DbStatus {
  state: string;
  size_bytes?: number;
  size_mb?: number;
  connections?: number;
  error?: string;
}

function DatabaseTab() {
  const activeProject = useDashboardStore((s) => s.activeProject);
  const [databases, setDatabases] = useState<ManagedDatabase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [selected, setSelected] = useState<ManagedDatabase | null>(null);

  const projectId = activeProject?.id;

  const refresh = useCallback(async () => {
    if (!projectId) return;
    try {
      const data = await listDatabases(projectId);
      setDatabases(data.databases || []);
      setError("");
    } catch (e: any) {
      setError(e.message || "Failed to load databases");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { refresh(); }, [refresh]);

  if (!projectId) return <div className="empty-state">Select a project first</div>;

  return (
    <div className="panel-content">
      <div className="panel-header">
        <div className="panel-actions">
          <button className="btn-sm" onClick={refresh}><RefreshCw className="h-3.5 w-3.5" /></button>
          <button className="btn-sm btn-primary" onClick={() => setShowCreate(true)}>
            <Plus className="h-3.5 w-3.5" /><span>Create Database</span>
          </button>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {showCreate && (
        <CreateDatabaseForm
          projectId={projectId}
          onCreated={() => { setShowCreate(false); refresh(); }}
          onCancel={() => setShowCreate(false)}
        />
      )}

      {selected ? (
        <DatabaseDetail db={selected} projectId={projectId} onBack={() => { setSelected(null); refresh(); }} />
      ) : (
        <>
          {loading ? (
            <div className="loading-state">Loading databases...</div>
          ) : databases.length === 0 ? (
            <div className="empty-state">
              <Database className="h-8 w-8 opacity-30" />
              <p>No databases yet</p>
              <p className="text-xs opacity-50">Create a managed PostgreSQL database on any of your instances</p>
            </div>
          ) : (
            <div className="card-grid">
              {databases.map((db) => (
                <div key={db.id} className="card card-interactive" onClick={() => setSelected(db)}>
                  <div className="card-header">
                    <Database className="h-4 w-4" />
                    <span className="card-title">{db.name}</span>
                    <span className={`badge ${db.state === "running" ? "badge-success" : db.state === "error" ? "badge-error" : "badge-warning"}`}>
                      {db.state}
                    </span>
                  </div>
                  <div className="card-meta">
                    <span>{db.engine} {db.version}</span>
                    <span>{db.host}:{db.port}</span>
                    {db.size_mb > 0 && <span>{db.size_mb} MB</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ── Create Database Form ── */

function CreateDatabaseForm({ projectId, onCreated, onCancel }: {
  projectId: string;
  onCreated: () => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!name.trim()) return;
    setCreating(true);
    setError("");
    try {
      await createDatabase(projectId, { name: name.trim(), instance_id: "" });
      onCreated();
    } catch (e: any) {
      setError(e.message || "Failed to create database");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="form-card">
      <h3>Create Managed Database</h3>
      {error && <div className="error-banner">{error}</div>}
      <div className="form-group">
        <label>Database Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="my-database" className="input" />
        <span className="text-xs opacity-50">Letters, numbers, hyphens, underscores.</span>
      </div>
      <div className="form-group">
        <label>Engine</label>
        <input value="PostgreSQL 16 — Managed by NSO" disabled className="input opacity-50" />
      </div>
      <div style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", padding: "4px 0" }}>
        Hosted on NSO infrastructure. Connection details will be provided after creation.
      </div>
      <div className="form-actions">
        <button className="btn-sm" onClick={onCancel}>Cancel</button>
        <button className="btn-sm btn-primary" onClick={submit} disabled={creating || !name.trim()}>
          {creating ? "Creating..." : "Create"}
        </button>
      </div>
    </div>
  );
}

/* ── Database Detail ── */

function DatabaseDetail({ db, projectId, onBack }: {
  db: ManagedDatabase;
  projectId: string;
  onBack: () => void;
}) {
  const [showPassword, setShowPassword] = useState(false);
  const [sql, setSql] = useState("");
  const [queryResult, setQueryResult] = useState<any>(null);
  const [querying, setQuerying] = useState(false);
  const [status, setStatus] = useState<DbStatus | null>(null);
  const [copied, setCopied] = useState("");
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (db.state === "running") {
      getDatabaseStatus(projectId, db.id).then(setStatus).catch((e) => console.error(e));
    }
  }, [projectId, db.id, db.state]);

  const runQuery = async () => {
    if (!sql.trim()) return;
    setQuerying(true);
    try {
      const result = await queryDatabase(projectId, db.id, sql);
      setQueryResult(result);
    } catch (e: any) {
      setQueryResult({ ok: false, error: e.message });
    } finally {
      setQuerying(false);
    }
  };

  const copyText = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(""), 2000);
  };

  const connString = `postgresql://${db.db_user}:${db.password_encrypted}@${db.host}:${db.port}/${db.name}`;

  const handleDelete = async () => {
    if (!confirm(`Delete database "${db.name}"? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await deleteDatabase(projectId, db.id);
      onBack();
    } catch (e: any) {
      alert(e.message || "Failed to delete");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="detail-panel">
      <div className="detail-header">
        <button className="btn-sm" onClick={onBack}>← Back</button>
        <h3><Database className="h-4 w-4 inline" /> {db.name}</h3>
        <span className={`badge ${db.state === "running" ? "badge-success" : "badge-error"}`}>{db.state}</span>
      </div>

      {db.error && <div className="error-banner">{db.error}</div>}

      {/* Connection Info */}
      <div className="info-section">
        <h4>Connection</h4>
        <div className="info-grid">
          <div className="info-row">
            <span className="info-label">Host</span>
            <span className="info-value">{db.host}</span>
            <button className="btn-icon" onClick={() => copyText(db.host, "host")} title="Copy">
              {copied === "host" ? <CheckCircle className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
            </button>
          </div>
          <div className="info-row">
            <span className="info-label">Port</span>
            <span className="info-value">{db.port}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Database</span>
            <span className="info-value">{db.name}</span>
          </div>
          <div className="info-row">
            <span className="info-label">User</span>
            <span className="info-value">{db.db_user}</span>
            <button className="btn-icon" onClick={() => copyText(db.db_user, "user")} title="Copy">
              {copied === "user" ? <CheckCircle className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
            </button>
          </div>
          <div className="info-row">
            <span className="info-label">Password</span>
            <span className="info-value mono">{showPassword ? db.password_encrypted : "••••••••••••"}</span>
            <button className="btn-icon" onClick={() => setShowPassword(!showPassword)}>
              {showPassword ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
            </button>
            <button className="btn-icon" onClick={() => copyText(db.password_encrypted, "pw")} title="Copy">
              {copied === "pw" ? <CheckCircle className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
            </button>
          </div>
          <div className="info-row">
            <span className="info-label">Connection String</span>
            <button className="btn-sm" onClick={() => copyText(connString, "conn")}>
              {copied === "conn" ? "Copied!" : "Copy"}
            </button>
          </div>
        </div>
      </div>

      {/* Status */}
      {status && (
        <div className="info-section">
          <h4>Status</h4>
          <div className="info-grid">
            <div className="info-row"><span className="info-label">Size</span><span className="info-value">{status.size_mb ?? 0} MB</span></div>
            <div className="info-row"><span className="info-label">Connections</span><span className="info-value">{status.connections ?? 0}</span></div>
          </div>
        </div>
      )}

      {/* SQL Editor */}
      {db.state === "running" && (
        <div className="info-section">
          <h4><Terminal className="h-3.5 w-3.5 inline" /> SQL Editor</h4>
          <textarea
            className="code-editor"
            value={sql}
            onChange={(e) => setSql(e.target.value)}
            placeholder="SELECT * FROM ..."
            rows={4}
          />
          <div className="form-actions" style={{ marginTop: 8 }}>
            <button className="btn-sm btn-primary" onClick={runQuery} disabled={querying || !sql.trim()}>
              <Play className="h-3 w-3" /> {querying ? "Running..." : "Run Query"}
            </button>
          </div>

          {queryResult && (
            <div className="query-result" style={{ marginTop: 12 }}>
              {queryResult.ok === false ? (
                <div className="error-banner">{queryResult.error}</div>
              ) : (
                <>
                  <div className="text-xs opacity-50">{queryResult.row_count} row(s)</div>
                  {queryResult.rows?.length > 0 && (
                    <div className="table-wrap">
                      <table className="data-table">
                        <thead>
                          <tr>
                            {Object.keys(queryResult.rows[0]).map((col) => (
                              <th key={col}>{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {queryResult.rows.map((row: any, i: number) => (
                            <tr key={i}>
                              {Object.values(row).map((val: any, j: number) => (
                                <td key={j}>{String(val)}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Delete */}
      <div className="danger-zone">
        <button className="btn-sm btn-danger" onClick={handleDelete} disabled={deleting}>
          <Trash2 className="h-3 w-3" /> {deleting ? "Deleting..." : "Delete Database"}
        </button>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   STORAGE TAB
   ═══════════════════════════════════════════ */

interface Bucket {
  id: string;
  project_id: string;
  name: string;
  r2_prefix: string;
  size_bytes: number;
  object_count: number;
  public_access: number;
  created_at: string;
}

interface StorageObject {
  key: string;
  full_key: string;
}

function StorageTab() {
  const activeProject = useDashboardStore((s) => s.activeProject);
  const [buckets, setBuckets] = useState<Bucket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [selected, setSelected] = useState<Bucket | null>(null);

  const projectId = activeProject?.id;

  const refresh = useCallback(async () => {
    if (!projectId) return;
    try {
      const data = await listBuckets(projectId);
      setBuckets(data.buckets || []);
      setError("");
    } catch (e: any) {
      setError(e.message || "Failed to load buckets");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { refresh(); }, [refresh]);

  if (!projectId) return <div className="empty-state">Select a project first</div>;

  return (
    <div className="panel-content">
      <div className="panel-header">
        <div className="panel-actions">
          <button className="btn-sm" onClick={refresh}><RefreshCw className="h-3.5 w-3.5" /></button>
          <button className="btn-sm btn-primary" onClick={() => setShowCreate(true)}>
            <Plus className="h-3.5 w-3.5" /><span>Create Bucket</span>
          </button>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {showCreate && (
        <CreateBucketForm
          projectId={projectId}
          onCreated={() => { setShowCreate(false); refresh(); }}
          onCancel={() => setShowCreate(false)}
        />
      )}

      {selected ? (
        <BucketDetail bucket={selected} projectId={projectId} onBack={() => { setSelected(null); refresh(); }} />
      ) : (
        <>
          {loading ? (
            <div className="loading-state">Loading buckets...</div>
          ) : buckets.length === 0 ? (
            <div className="empty-state">
              <HardDrive className="h-8 w-8 opacity-30" />
              <p>No storage buckets yet</p>
              <p className="text-xs opacity-50">Create an S3-compatible storage bucket for your project</p>
            </div>
          ) : (
            <div className="card-grid">
              {buckets.map((b) => (
                <div key={b.id} className="card card-interactive" onClick={() => setSelected(b)}>
                  <div className="card-header">
                    <HardDrive className="h-4 w-4" />
                    <span className="card-title">{b.name}</span>
                    {b.public_access ? <span className="badge badge-warning">public</span> : null}
                  </div>
                  <div className="card-meta">
                    <span>{b.object_count} objects</span>
                    <span>{formatBytes(b.size_bytes)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ── Create Bucket Form ── */

function CreateBucketForm({ projectId, onCreated, onCancel }: {
  projectId: string;
  onCreated: () => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!name.trim()) return;
    setCreating(true);
    setError("");
    try {
      await createBucket(projectId, name.trim());
      onCreated();
    } catch (e: any) {
      setError(e.message || "Failed to create bucket");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="form-card">
      <h3>Create Bucket</h3>
      {error && <div className="error-banner">{error}</div>}
      <div className="form-group">
        <label>Bucket Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="my-bucket" className="input" />
        <span className="text-xs opacity-50">Letters, numbers, hyphens, underscores. 2-63 chars.</span>
      </div>
      <div className="form-actions">
        <button className="btn-sm" onClick={onCancel}>Cancel</button>
        <button className="btn-sm btn-primary" onClick={submit} disabled={creating || !name.trim()}>
          {creating ? "Creating..." : "Create"}
        </button>
      </div>
    </div>
  );
}

/* ── Bucket Detail (File Browser) ── */

const MAX_UPLOAD_GB = 5;
const MAX_UPLOAD_BYTES = MAX_UPLOAD_GB * 1024 * 1024 * 1024;
const BLOCKED_EXTENSIONS = new Set([
  ".iso", ".img", ".vmdk", ".vhd", ".vhdx", ".qcow2", ".ova", ".ovf",
  ".dmg", ".sparseimage", ".raw",
  ".exe", ".msi", ".dll", ".sys", ".com", ".bat", ".cmd", ".scr", ".pif",
  ".app", ".deb", ".rpm", ".appimage", ".snap", ".flatpak",
  ".hta", ".vbs", ".vbe", ".wsf", ".wsh", ".ps1", ".psm1",
  ".cab", ".wim", ".swm",
]);

function validateUploadFile(file: File): string | null {
  if (file.size > MAX_UPLOAD_BYTES) {
    return `File too large (${(file.size / (1024 * 1024 * 1024)).toFixed(2)}GB). Max is ${MAX_UPLOAD_GB}GB.`;
  }
  const name = file.name.toLowerCase();
  const ext = name.includes(".") ? "." + name.split(".").pop() : "";
  if (BLOCKED_EXTENSIONS.has(ext)) {
    return `File type "${ext}" is not allowed. Disk images, executables, and installers cannot be uploaded.`;
  }
  return null;
}

function BucketDetail({ bucket, projectId, onBack }: {
  bucket: Bucket;
  projectId: string;
  onBack: () => void;
}) {
  const [objects, setObjects] = useState<StorageObject[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await listBucketObjects(projectId, bucket.id);
      setObjects(data.objects || []);
    } catch { }
    finally { setLoading(false); }
  }, [projectId, bucket.id]);

  useEffect(() => { refresh(); }, [refresh]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError("");

    const error = validateUploadFile(file);
    if (error) {
      setUploadError(error);
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    setUploading(true);
    try {
      await uploadObject(projectId, bucket.id, file);
      refresh();
    } catch (err: any) {
      setUploadError(err.message || "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDownload = async (key: string) => {
    try {
      const blob = await downloadObject(projectId, bucket.id, key);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = key.split("/").pop() || key;
      a.click();
      URL.revokeObjectURL(url);
    } catch { }
  };

  const handleDeleteObj = async (key: string) => {
    if (!confirm(`Delete "${key}"?`)) return;
    try {
      await deleteObject(projectId, bucket.id, key);
      refresh();
    } catch { }
  };

  const handleDeleteBucket = async () => {
    if (!confirm(`Delete bucket "${bucket.name}" and all its objects? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await deleteBucket(projectId, bucket.id);
      onBack();
    } catch (e: any) {
      alert(e.message || "Failed to delete");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="detail-panel">
      <div className="detail-header">
        <button className="btn-sm" onClick={onBack}>← Back</button>
        <h3><HardDrive className="h-4 w-4 inline" /> {bucket.name}</h3>
        <span className="text-xs opacity-50">{objects.length} objects</span>
      </div>

      {uploadError && <div className="error-banner"><AlertTriangle className="h-3.5 w-3.5 inline" /> {uploadError}</div>}

      <div className="panel-actions" style={{ marginBottom: 12 }}>
        <button className="btn-sm" onClick={refresh}><RefreshCw className="h-3.5 w-3.5" /></button>
        <button className="btn-sm btn-primary" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
          <Upload className="h-3.5 w-3.5" /> {uploading ? "Uploading..." : "Upload"}
        </button>
        <span className="text-xs opacity-50">Max {MAX_UPLOAD_GB}GB per file (large files upload direct to R2)</span>
        <input ref={fileInputRef} type="file" className="hidden" onChange={handleUpload} />
      </div>

      {loading ? (
        <div className="loading-state">Loading objects...</div>
      ) : objects.length === 0 ? (
        <div className="empty-state">
          <FolderOpen className="h-6 w-6 opacity-30" />
          <p>Empty bucket</p>
        </div>
      ) : (
        <div className="file-list">
          {objects.map((obj) => (
            <div key={obj.key} className="file-row">
              <File className="h-3.5 w-3.5 opacity-50" />
              <span className="file-name">{obj.key}</span>
              <div className="file-actions">
                <button className="btn-icon" onClick={() => handleDownload(obj.key)} title="Download">
                  <Download className="h-3 w-3" />
                </button>
                <button className="btn-icon btn-danger-icon" onClick={() => handleDeleteObj(obj.key)} title="Delete">
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="danger-zone">
        <button className="btn-sm btn-danger" onClick={handleDeleteBucket} disabled={deleting}>
          <Trash2 className="h-3 w-3" /> {deleting ? "Deleting..." : "Delete Bucket"}
        </button>
      </div>
    </div>
  );
}

/* ── Helpers ── */

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}
