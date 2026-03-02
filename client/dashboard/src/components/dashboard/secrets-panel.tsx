"use client";

import { useState, useEffect } from "react";
import {
  Key, Plus, Eye, EyeOff, Trash2, RefreshCw, Copy, Check,
  Shield, ChevronDown, ChevronRight, FolderKey, Folder,
} from "lucide-react";
import {
  listSecrets, addSecret as apiAddSecret, deleteSecret as apiDeleteSecret,
  type AgentSecret,
} from "@/lib/api/client";

interface Bucket {
  name: string;
  label: string;
  icon: "system" | "storage" | "auth" | "provider" | "custom";
}

const BUCKET_META: Record<string, Bucket> = {
  auth: { name: "auth", label: "Authentication", icon: "auth" },
  providers: { name: "providers", label: "Providers", icon: "provider" },
  storage: { name: "storage", label: "Storage (R2)", icon: "storage" },
  system: { name: "system", label: "System", icon: "system" },
  custom: { name: "custom", label: "Custom", icon: "custom" },
};

const BUCKET_ORDER = ["auth", "providers", "storage", "system", "custom"];

export function SecretsPanel() {
  const [secrets, setSecrets] = useState<AgentSecret[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [copied, setCopied] = useState<string | null>(null);

  const fetchSecrets = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listSecrets();
      setSecrets(res.secrets || []);
    } catch (err: any) {
      setError(err.message || "Failed to load secrets");
      setSecrets([]);
    }
    setLoading(false);
  };

  useEffect(() => { fetchSecrets(); }, []);

  const handleAdd = async () => {
    const k = newKey.trim().toUpperCase().replace(/[^A-Z0-9_]/g, "_");
    const v = newValue.trim();
    if (!k || !v) return;
    try {
      await apiAddSecret(k, v);
      setNewKey("");
      setNewValue("");
      setAdding(false);
      fetchSecrets();
    } catch (err: any) {
      setError(err.message || "Failed to add secret");
    }
  };

  const handleDelete = async (key: string) => {
    if (!confirm(`Remove ${key}?`)) return;
    try {
      await apiDeleteSecret(key);
      fetchSecrets();
    } catch (err: any) {
      setError(err.message || "Failed to delete secret");
    }
  };

  const toggleReveal = (key: string) => {
    setRevealed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const toggleCollapse = (bucket: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(bucket)) next.delete(bucket); else next.add(bucket);
      return next;
    });
  };

  const copyValue = (key: string, value: string) => {
    navigator.clipboard.writeText(value);
    setCopied(key);
    setTimeout(() => setCopied(null), 2000);
  };

  const maskValue = (value: string) => {
    if (value.length <= 4) return "****";
    return value.slice(0, 2) + "*".repeat(Math.min(value.length - 4, 20)) + value.slice(-2);
  };

  // Group by bucket
  const grouped: Record<string, AgentSecret[]> = {};
  for (const s of secrets) {
    const b = s.bucket || "custom";
    if (!grouped[b]) grouped[b] = [];
    grouped[b].push(s);
  }

  const activeBuckets = BUCKET_ORDER.filter((b) => grouped[b]?.length);

  const bucketIcon = (icon: string) => {
    switch (icon) {
      case "auth": return <Key className="h-3.5 w-3.5" style={{ color: "var(--color-yellow)" }} />;
      case "provider": return <FolderKey className="h-3.5 w-3.5" style={{ color: "var(--color-blue)" }} />;
      case "storage": return <Folder className="h-3.5 w-3.5" style={{ color: "var(--color-teal)" }} />;
      case "system": return <Shield className="h-3.5 w-3.5" style={{ color: "var(--color-purple)" }} />;
      default: return <Folder className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)" }} />;
    }
  };

  return (
    <div>
      <div className="panel-header-row">
        <span className="panel-count">{secrets.length} secret{secrets.length !== 1 ? "s" : ""} in {activeBuckets.length} group{activeBuckets.length !== 1 ? "s" : ""}</span>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="panel-btn-sm" onClick={fetchSecrets} disabled={loading}>
            <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button className="panel-btn-sm" onClick={() => setAdding(true)}>
            <Plus className="h-3 w-3" />
            <span>Add</span>
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: "8px 12px", marginBottom: 12, borderRadius: 6, background: "rgba(239,68,68,0.1)", color: "var(--color-red)", fontSize: "var(--font-xs)" }}>
          {error}
        </div>
      )}

      {adding && (
        <div className="secret-add">
          <div className="secret-add-row">
            <input
              className="secret-input"
              type="text"
              placeholder="KEY_NAME"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value.toUpperCase())}
              autoFocus
            />
            <input
              className="secret-input"
              type="text"
              placeholder="value"
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleAdd(); }}
              style={{ flex: 2 }}
            />
          </div>
          <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
            <button className="panel-btn-sm" onClick={handleAdd} disabled={!newKey.trim() || !newValue.trim()}>
              Save
            </button>
            <button className="panel-btn-sm" onClick={() => { setAdding(false); setNewKey(""); setNewValue(""); }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {secrets.length === 0 && !loading ? (
        <div className="panel-empty">
          <Shield className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
          <div className="panel-empty-title">No secrets</div>
          <div className="panel-empty-sub">Environment variables managed by the agent</div>
          <button className="panel-btn" onClick={() => setAdding(true)}>
            <Plus className="h-3.5 w-3.5" />
            <span>Add secret</span>
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {activeBuckets.map((bucketName) => {
            const meta = BUCKET_META[bucketName] || BUCKET_META.custom;
            const items = grouped[bucketName] || [];
            const isCollapsed = collapsed.has(bucketName);
            return (
              <div key={bucketName} style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
                {/* Bucket header */}
                <button
                  onClick={() => toggleCollapse(bucketName)}
                  style={{
                    width: "100%", display: "flex", alignItems: "center", gap: 8,
                    padding: "8px 14px", background: "var(--sidebar-bg)",
                    border: "none", borderBottom: isCollapsed ? "none" : "1px solid var(--border)",
                    cursor: "pointer", color: "var(--foreground)",
                  }}
                >
                  {isCollapsed
                    ? <ChevronRight className="h-3 w-3" style={{ color: "var(--muted-foreground)" }} />
                    : <ChevronDown className="h-3 w-3" style={{ color: "var(--muted-foreground)" }} />
                  }
                  {bucketIcon(meta.icon)}
                  <span style={{ fontSize: "var(--font-xs)", fontWeight: 600 }}>{meta.label}</span>
                  <span style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginLeft: "auto" }}>
                    {items.length}
                  </span>
                </button>

                {/* Bucket contents */}
                {!isCollapsed && (
                  <div className="secret-list" style={{ padding: "4px" }}>
                    {items.map((v) => (
                      <div key={v.key} className="secret-row" style={{ border: "none", borderRadius: 4, padding: "8px 10px" }}>
                        <div className="secret-key">
                          <Key className="h-3 w-3" style={{ color: "var(--color-yellow)", opacity: 0.6 }} />
                          <span>{v.key}</span>
                        </div>
                        <div className="secret-value fs-mono">
                          {revealed.has(v.key) ? v.value : maskValue(v.value)}
                        </div>
                        <div className="secret-actions">
                          <button className="svc-btn" title={revealed.has(v.key) ? "Hide" : "Reveal"} onClick={() => toggleReveal(v.key)}>
                            {revealed.has(v.key) ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                          </button>
                          <button className="svc-btn" title="Copy" onClick={() => copyValue(v.key, v.value)}>
                            {copied === v.key ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                          </button>
                          <button className="svc-btn red" title="Remove" onClick={() => handleDelete(v.key)}>
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
