"use client";

import { useState, useEffect, useRef } from "react";
import {
  Package, Download, Upload, Trash2, Search,
  Loader, AlertCircle, Eye, Tag, HardDrive,
  ChevronRight, ArrowLeft, FileArchive,
} from "lucide-react";
import {
  listModules, publishModule, uploadModuleZar, listModuleVersions,
  removeModule, updateModule,
  type ModuleInfo,
} from "@/lib/api/client";

const CATEGORIES = ["server", "frontend", "agent", "core", "library", "template", "other"];

export function ModulesPanel() {
  const [modules, setModules] = useState<ModuleInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [selectedModule, setSelectedModule] = useState<ModuleInfo | null>(null);
  const [showPublish, setShowPublish] = useState(false);

  useEffect(() => { loadModules(); }, []);

  const loadModules = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await listModules();
      setModules(res.modules || []);
    } catch (e: any) {
      setError(e.message?.includes("401") ? "Not authorized" : `Failed to load modules: ${e.message}`);
    }
    setLoading(false);
  };

  const filtered = modules.filter((m) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return m.name.toLowerCase().includes(q) || m.display_name?.toLowerCase().includes(q) || m.description?.toLowerCase().includes(q);
  });

  if (selectedModule) {
    return <ModuleDetail module={selectedModule} onBack={() => { setSelectedModule(null); loadModules(); }} />;
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
        <div style={{ flex: 1, position: "relative" }}>
          <Search className="h-3.5 w-3.5" style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--muted-foreground)" }} />
          <input
            className="deploy-select"
            placeholder="Search modules..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ paddingLeft: 30, width: "100%" }}
          />
        </div>
        <button className="btn-primary" onClick={() => setShowPublish(true)} style={{ whiteSpace: "nowrap" }}>
          <Upload className="h-3.5 w-3.5" />
          <span>Publish</span>
        </button>
      </div>

      {error && (
        <div style={{ padding: "8px 12px", fontSize: "var(--font-xs)", color: "var(--color-red)", background: "rgba(239,68,68,0.08)", borderRadius: 6, marginBottom: 12, display: "flex", alignItems: "center", gap: 6 }}>
          <AlertCircle className="h-3.5 w-3.5" style={{ flexShrink: 0 }} />
          <span>{error}</span>
        </div>
      )}

      {showPublish && (
        <PublishForm
          onClose={() => setShowPublish(false)}
          onPublished={() => { setShowPublish(false); loadModules(); }}
        />
      )}

      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 40, gap: 8, color: "var(--muted-foreground)" }}>
          <Loader className="h-4 w-4 animate-spin" />
          <span style={{ fontSize: "var(--font-xs)" }}>Loading modules...</span>
        </div>
      ) : filtered.length === 0 ? (
        <div className="panel-empty">
          <Package className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
          <div className="panel-empty-title">{search ? "No matches" : "No modules yet"}</div>
          <div className="panel-empty-sub">{search ? "Try a different search" : "Publish your first .zar module"}</div>
        </div>
      ) : (
        <div className="plugin-grid">
          {filtered.map((m) => (
            <ModuleCard key={m.id || m.name} module={m} onClick={() => setSelectedModule(m)} />
          ))}
        </div>
      )}
    </div>
  );
}

function ModuleCard({ module: m, onClick }: { module: ModuleInfo; onClick: () => void }) {
  const sizeKB = m.size ? Math.round(m.size / 1024) : 0;

  return (
    <div className="plugin-card" onClick={onClick} style={{ cursor: "pointer" }}>
      <div className="plugin-icon">
        <Package className="h-5 w-5" style={{ color: m.published ? "var(--color-teal)" : "var(--muted-foreground)" }} />
      </div>
      <div className="plugin-info">
        <div className="plugin-name">
          {m.display_name || m.name}
          {!m.published && (
            <span style={{ fontSize: "var(--font-xxs)", color: "var(--color-yellow)", marginLeft: 6 }}>draft</span>
          )}
        </div>
        <div className="plugin-desc">{m.description || "No description"}</div>
        <div className="plugin-meta">
          <span className="plugin-version">v{m.version || "0.0.0"}</span>
          <span className="plugin-category">{m.category || "other"}</span>
          {sizeKB > 0 && <span style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)" }}>{sizeKB}KB</span>}
        </div>
      </div>
      <ChevronRight className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)", opacity: 0.5 }} />
    </div>
  );
}

function ModuleDetail({ module: m, onBack }: { module: ModuleInfo; onBack: () => void }) {
  const [versions, setVersions] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const [uploadVersion, setUploadVersion] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await listModuleVersions(m.name);
        setVersions(res.versions || []);
      } catch {}
    })();
  }, [m.name]);

  const handleUpload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      await uploadModuleZar(m.name, file, uploadVersion);
      const res = await listModuleVersions(m.name);
      setVersions(res.versions || []);
      setUploadVersion("");
      if (fileRef.current) fileRef.current.value = "";
    } catch (e: any) {
      setError(`Upload failed: ${e.message}`);
    }
    setUploading(false);
  };

  const handleDelete = async () => {
    if (!confirm(`Delete module "${m.name}"? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await removeModule(m.name);
      onBack();
    } catch (e: any) {
      setError(`Delete failed: ${e.message}`);
      setDeleting(false);
    }
  };

  const sizeKB = m.size ? Math.round(m.size / 1024) : 0;

  return (
    <div>
      <button
        onClick={onBack}
        style={{ display: "flex", alignItems: "center", gap: 4, fontSize: "var(--font-xs)", color: "var(--muted-foreground)", background: "none", border: "none", cursor: "pointer", marginBottom: 16, padding: 0 }}
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        <span>Back to modules</span>
      </button>

      {error && (
        <div style={{ padding: "8px 12px", fontSize: "var(--font-xs)", color: "var(--color-red)", background: "rgba(239,68,68,0.08)", borderRadius: 6, marginBottom: 12, display: "flex", alignItems: "center", gap: 6 }}>
          <AlertCircle className="h-3.5 w-3.5" style={{ flexShrink: 0 }} />
          <span>{error}</span>
        </div>
      )}

      <div style={{ display: "flex", gap: 16, marginBottom: 20 }}>
        <div style={{ width: 48, height: 48, borderRadius: 10, background: "var(--sidebar-bg)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Package className="h-6 w-6" style={{ color: "var(--color-teal)" }} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 16, fontWeight: 600 }}>{m.display_name || m.name}</div>
          <div style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)", marginTop: 2 }}>{m.description || "No description"}</div>
          <div style={{ display: "flex", gap: 12, marginTop: 8, fontSize: "var(--font-xxs)", color: "var(--muted-foreground)" }}>
            <span style={{ display: "flex", alignItems: "center", gap: 3 }}><Tag className="h-3 w-3" />v{m.version || "0.0.0"}</span>
            <span style={{ display: "flex", alignItems: "center", gap: 3 }}><Package className="h-3 w-3" />{m.category || "other"}</span>
            {sizeKB > 0 && <span style={{ display: "flex", alignItems: "center", gap: 3 }}><HardDrive className="h-3 w-3" />{sizeKB}KB</span>}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 16 }}>
        <div style={{ flex: 1 }}>
          <div className="settings-section">
            <div className="settings-section-title">Upload .zar</div>
            <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
              <div style={{ flex: 1 }}>
                <label style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginBottom: 4, display: "block" }}>Version (optional)</label>
                <input
                  className="deploy-select"
                  placeholder="e.g. 1.2.0"
                  value={uploadVersion}
                  onChange={(e) => setUploadVersion(e.target.value)}
                  style={{ width: "100%" }}
                />
              </div>
              <input ref={fileRef} type="file" accept=".zar,.tar.gz" style={{ display: "none" }} onChange={handleUpload} />
              <button
                className="btn-primary"
                onClick={() => fileRef.current?.click()}
                disabled={uploading}
                style={{ whiteSpace: "nowrap" }}
              >
                {uploading ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
                <span>{uploading ? "Uploading..." : "Upload .zar"}</span>
              </button>
            </div>
          </div>

          <div className="settings-section" style={{ marginTop: 16 }}>
            <div className="settings-section-title">Versions ({versions.length})</div>
            {versions.length === 0 ? (
              <div style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)", padding: "12px 0" }}>No versions uploaded yet</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {versions.map((v) => (
                  <div key={v} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", background: "var(--sidebar-bg)", borderRadius: 6, fontSize: "var(--font-xs)" }}>
                    <FileArchive className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)" }} />
                    <span style={{ flex: 1 }}>{v}</span>
                    {v === `v${m.version}` && (
                      <span style={{ fontSize: "var(--font-xxs)", color: "var(--color-teal)", background: "rgba(20,184,166,0.1)", padding: "1px 6px", borderRadius: 4 }}>latest</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div style={{ width: 200 }}>
          <div className="settings-section">
            <div className="settings-section-title">Actions</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <button
                className="btn-primary"
                onClick={handleDelete}
                disabled={deleting}
                style={{ width: "100%", background: "rgba(239,68,68,0.1)", color: "var(--color-red)", justifyContent: "center" }}
              >
                {deleting ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                <span>{deleting ? "Deleting..." : "Delete Module"}</span>
              </button>
            </div>
          </div>

          {m.r2_key && (
            <div className="settings-section" style={{ marginTop: 16 }}>
              <div className="settings-section-title">R2 Key</div>
              <div style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", wordBreak: "break-all", padding: "6px 10px", background: "var(--sidebar-bg)", borderRadius: 6 }}>
                {m.r2_key}
              </div>
            </div>
          )}

          {m.hash && (
            <div className="settings-section" style={{ marginTop: 12 }}>
              <div className="settings-section-title">SHA256</div>
              <div style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", wordBreak: "break-all", padding: "6px 10px", background: "var(--sidebar-bg)", borderRadius: 6, fontFamily: "monospace" }}>
                {m.hash.slice(0, 16)}...
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function PublishForm({ onClose, onPublished }: { onClose: () => void; onPublished: () => void }) {
  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("other");
  const [version, setVersion] = useState("0.1.0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    if (!name.trim()) { setError("Name is required"); return; }
    setBusy(true);
    setError("");
    try {
      await publishModule({
        name: name.trim().toLowerCase().replace(/[^a-z0-9-]/g, "-"),
        display_name: displayName.trim() || name.trim(),
        description: description.trim(),
        category,
        version: version.trim() || "0.1.0",
      });
      onPublished();
    } catch (e: any) {
      setError(e.message);
    }
    setBusy(false);
  };

  return (
    <div style={{ padding: 16, background: "var(--sidebar-bg)", borderRadius: 8, marginBottom: 16, border: "1px solid var(--border)" }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Publish New Module</div>

      {error && (
        <div style={{ padding: "6px 10px", fontSize: "var(--font-xs)", color: "var(--color-red)", background: "rgba(239,68,68,0.08)", borderRadius: 6, marginBottom: 10 }}>
          {error}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
        <div>
          <label style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginBottom: 3, display: "block" }}>Name *</label>
          <input className="deploy-select" placeholder="my-module" value={name} onChange={(e) => setName(e.target.value)} style={{ width: "100%" }} />
        </div>
        <div>
          <label style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginBottom: 3, display: "block" }}>Display Name</label>
          <input className="deploy-select" placeholder="My Module" value={displayName} onChange={(e) => setDisplayName(e.target.value)} style={{ width: "100%" }} />
        </div>
        <div>
          <label style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginBottom: 3, display: "block" }}>Category</label>
          <select className="deploy-select" value={category} onChange={(e) => setCategory(e.target.value)} style={{ width: "100%" }}>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <label style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginBottom: 3, display: "block" }}>Version</label>
          <input className="deploy-select" placeholder="0.1.0" value={version} onChange={(e) => setVersion(e.target.value)} style={{ width: "100%" }} />
        </div>
      </div>

      <div style={{ marginBottom: 12 }}>
        <label style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginBottom: 3, display: "block" }}>Description</label>
        <input className="deploy-select" placeholder="What does this module do?" value={description} onChange={(e) => setDescription(e.target.value)} style={{ width: "100%" }} />
      </div>

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" onClick={handleSubmit} disabled={busy}>
          {busy ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Package className="h-3.5 w-3.5" />}
          <span>{busy ? "Publishing..." : "Publish"}</span>
        </button>
      </div>
    </div>
  );
}
