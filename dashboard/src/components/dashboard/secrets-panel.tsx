"use client";

import { useState, useEffect } from "react";
import {
  Key, Plus, Eye, EyeOff, Trash2, RefreshCw, Copy, Check,
  Shield, ChevronDown, ChevronRight, FolderKey, Folder,
} from "lucide-react";
import { execCommand } from "@/lib/api/client";

const ENV_FILE = "/opt/setupo/.env";

interface EnvVar {
  key: string;
  value: string;
}

interface Bucket {
  name: string;
  label: string;
  icon: "system" | "storage" | "auth" | "provider" | "custom";
  prefixes: string[];
}

// Auto-grouping rules: secrets matching these prefixes go into their bucket
const BUCKETS: Bucket[] = [
  { name: "auth", label: "Authentication", icon: "auth", prefixes: ["SETUPO_ADMIN", "AGENT_ADMIN", "JWT_", "SECRET_"] },
  { name: "providers", label: "Providers", icon: "provider", prefixes: ["VULTR_", "CF_"] },
  { name: "storage", label: "Storage (R2)", icon: "storage", prefixes: ["R2_"] },
  { name: "system", label: "System", icon: "system", prefixes: ["HOST", "PORT", "DB_", "LOG_", "CORS_", "SETUPO_SERVE"] },
];

function classifyVar(key: string): string {
  for (const bucket of BUCKETS) {
    if (bucket.prefixes.some((p) => key.startsWith(p))) return bucket.name;
  }
  return "custom";
}

export function SecretsPanel() {
  const [vars, setVars] = useState<EnvVar[]>([]);
  const [loading, setLoading] = useState(false);
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);
  const [addBucket, setAddBucket] = useState("custom");
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [copied, setCopied] = useState<string | null>(null);

  const fetchSecrets = async () => {
    setLoading(true);
    try {
      const res = await execCommand(`cat ${ENV_FILE} 2>/dev/null || echo ""`, "/opt/setupo", 5);
      const lines = res.stdout.trim().split("\n").filter((l: string) => l && !l.startsWith("#") && l.includes("="));
      setVars(lines.map((line: string) => {
        const idx = line.indexOf("=");
        return { key: line.slice(0, idx), value: line.slice(idx + 1) };
      }));
    } catch {
      setVars([]);
    }
    setLoading(false);
  };

  useEffect(() => { fetchSecrets(); }, []);

  const addSecret = async () => {
    const k = newKey.trim().toUpperCase().replace(/[^A-Z0-9_]/g, "_");
    const v = newValue.trim();
    if (!k || !v) return;
    try {
      await execCommand(`echo '${k}=${v}' >> ${ENV_FILE}`, "/opt/setupo", 5);
      setNewKey("");
      setNewValue("");
      setAdding(false);
      fetchSecrets();
    } catch {}
  };

  const removeSecret = async (key: string) => {
    if (!confirm(`Remove ${key}?`)) return;
    try {
      await execCommand(`sed -i '/^${key}=/d' ${ENV_FILE}`, "/opt/setupo", 5);
      fetchSecrets();
    } catch {}
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

  // Group vars by bucket
  const grouped: Record<string, EnvVar[]> = {};
  for (const v of vars) {
    const bucket = classifyVar(v.key);
    if (!grouped[bucket]) grouped[bucket] = [];
    grouped[bucket].push(v);
  }

  // Build ordered bucket list (defined buckets first, then custom)
  const allBuckets = [
    ...BUCKETS.filter((b) => grouped[b.name]?.length),
    ...(grouped["custom"]?.length ? [{ name: "custom", label: "Custom", icon: "custom" as const, prefixes: [] }] : []),
  ];

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
        <span className="panel-count">{vars.length} secret{vars.length !== 1 ? "s" : ""} in {allBuckets.length} group{allBuckets.length !== 1 ? "s" : ""}</span>
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

      {adding && (
        <div className="secret-add">
          <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}>
            <select
              className="deploy-select"
              value={addBucket}
              onChange={(e) => setAddBucket(e.target.value)}
              style={{ minWidth: 130, fontSize: "var(--font-xs)" }}
            >
              {BUCKETS.map((b) => <option key={b.name} value={b.name}>{b.label}</option>)}
              <option value="custom">Custom</option>
            </select>
          </div>
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
              onKeyDown={(e) => { if (e.key === "Enter") addSecret(); }}
              style={{ flex: 2 }}
            />
          </div>
          <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
            <button className="panel-btn-sm" onClick={addSecret} disabled={!newKey.trim() || !newValue.trim()}>
              Save
            </button>
            <button className="panel-btn-sm" onClick={() => { setAdding(false); setNewKey(""); setNewValue(""); }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {vars.length === 0 && !loading ? (
        <div className="panel-empty">
          <Shield className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
          <div className="panel-empty-title">No secrets</div>
          <div className="panel-empty-sub">Environment variables from {ENV_FILE}</div>
          <button className="panel-btn" onClick={() => setAdding(true)}>
            <Plus className="h-3.5 w-3.5" />
            <span>Add secret</span>
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {allBuckets.map((bucket) => {
            const items = grouped[bucket.name] || [];
            const isCollapsed = collapsed.has(bucket.name);
            return (
              <div key={bucket.name} style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
                {/* Bucket header */}
                <button
                  onClick={() => toggleCollapse(bucket.name)}
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
                  {bucketIcon(bucket.icon)}
                  <span style={{ fontSize: "var(--font-xs)", fontWeight: 600 }}>{bucket.label}</span>
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
                          <button className="svc-btn red" title="Remove" onClick={() => removeSecret(v.key)}>
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
