"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Puzzle, Download, Trash2, Package,
  Loader, AlertCircle, ToggleLeft, ToggleRight,
  HardDrive, FileText, Globe, Activity,
  Clock, ChevronDown, ChevronUp, RefreshCw,
  Link2, ShoppingBag, Zap, Github,
  Cloud, MessageSquare, Database,
  HeartPulse, Shield, Timer,
  Star, Check, Server,
} from "lucide-react";
import { useDashboardStore } from "@/stores/dashboard-store";
import {
  listAddons, installAddon, uninstallAddon, updateAddon,
  testConnector,
  pluginStorageList, pluginStorageDelete,
  pluginLogsList, pluginDnsList, pluginMonitoring,
  type AddonInfo,
} from "@/lib/api/client";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import type { AddonTab } from "@/types/dashboard";

// ═══════════════════════════════════════════
//  ICON MAP
// ═══════════════════════════════════════════

const ADDON_ICONS: Record<string, typeof Puzzle> = {
  // Plugins
  storage: HardDrive,
  monitoring: Activity,
  logs: FileText,
  dns: Globe,
  cron: Clock,
  // Connectors
  github: Github,
  s3: Cloud,
  slack: MessageSquare,
  cloudflare: Globe,
  r2: Database,
  vultr: Server,
  hetzner: Server,
  runpod: Zap,
  // Marketplace
  "uptime-monitor": HeartPulse,
  "ssl-manager": Shield,
  "scheduled-tasks": Timer,
};

const TAB_CONFIG: { id: AddonTab; label: string; icon: typeof Puzzle }[] = [
  { id: "connectors", label: "Connectors", icon: Link2 },
  { id: "plugins", label: "Plugins", icon: Puzzle },
  { id: "marketplace", label: "Apps", icon: ShoppingBag },
];

const ADDON_TYPE_MAP: Record<AddonTab, string> = {
  connectors: "connector",
  plugins: "plugin",
  marketplace: "marketplace",
};

// ═══════════════════════════════════════════
//  PLUGIN DETAIL VIEW (reused from old panel)
// ═══════════════════════════════════════════

function PluginDetailView({ addonId, projectId }: { addonId: string; projectId: string }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (addonId === "storage") {
        setData(await pluginStorageList(projectId));
      } else if (addonId === "logs") {
        setData(await pluginLogsList(projectId, "", "", 50));
      } else if (addonId === "dns") {
        setData(await pluginDnsList(projectId));
      } else if (addonId === "monitoring") {
        setData(await pluginMonitoring(projectId));
      }
    } catch (e: any) {
      setError(e.message || "Failed to load");
    }
    setLoading(false);
  }, [addonId, projectId]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="plugin-detail-loading">
        <Loader className="h-3.5 w-3.5 animate-spin" />
        <span>Loading...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="plugin-detail-error">
        <span>{error}</span>
        <button className="plugin-detail-retry" onClick={load}><RefreshCw className="h-3 w-3" /> Retry</button>
      </div>
    );
  }

  if (addonId === "storage") {
    const files = data?.files || [];
    return (
      <div className="plugin-detail">
        <div className="plugin-detail-header">
          <span>{files.length} file{files.length !== 1 ? "s" : ""} in storage</span>
          <button className="plugin-detail-retry" onClick={load}><RefreshCw className="h-3 w-3" /></button>
        </div>
        {files.length === 0 ? (
          <div className="plugin-detail-empty">No files uploaded yet. Use the API to upload files.</div>
        ) : (
          <div className="plugin-detail-list">
            {files.map((f: any) => (
              <div key={f.key} className="plugin-detail-row">
                <span className="plugin-detail-row-name">{f.key}</span>
                <button
                  className="plugin-detail-row-action"
                  onClick={async () => { await pluginStorageDelete(projectId, f.key); load(); }}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  if (addonId === "logs") {
    const logs = data?.logs || [];
    return (
      <div className="plugin-detail">
        <div className="plugin-detail-header">
          <span>{logs.length} log entries</span>
          <button className="plugin-detail-retry" onClick={load}><RefreshCw className="h-3 w-3" /></button>
        </div>
        {logs.length === 0 ? (
          <div className="plugin-detail-empty">No deploy logs yet.</div>
        ) : (
          <div className="plugin-detail-logs">
            {logs.slice(0, 20).map((l: any, i: number) => (
              <div key={i} className={`plugin-log-entry ${l.level}`}>
                <span className="plugin-log-level">{l.level}</span>
                <span className="plugin-log-msg">{l.message}</span>
                <span className="plugin-log-time">{new Date(l.created_at).toLocaleString()}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  if (addonId === "dns") {
    const records = data?.records || [];
    return (
      <div className="plugin-detail">
        <div className="plugin-detail-header">
          <span>{records.length} DNS record{records.length !== 1 ? "s" : ""}</span>
          <button className="plugin-detail-retry" onClick={load}><RefreshCw className="h-3 w-3" /></button>
        </div>
        {records.length === 0 ? (
          <div className="plugin-detail-empty">No domains configured yet.</div>
        ) : (
          <div className="plugin-detail-list">
            {records.map((r: any) => (
              <div key={r.id} className="plugin-detail-row">
                <span className="plugin-detail-row-name">{r.domain}</span>
                <span className="plugin-detail-row-meta">{r.value} {r.managed ? "(managed)" : ""}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  if (addonId === "monitoring") {
    const instances = data?.instances || [];
    return (
      <div className="plugin-detail">
        <div className="plugin-detail-header">
          <span>{instances.length} instance{instances.length !== 1 ? "s" : ""}</span>
          <button className="plugin-detail-retry" onClick={load}><RefreshCw className="h-3 w-3" /></button>
        </div>
        {instances.length === 0 ? (
          <div className="plugin-detail-empty">No instances to monitor.</div>
        ) : (
          <div className="plugin-detail-list">
            {instances.map((inst: any) => (
              <div key={inst.id} className="plugin-detail-row">
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span className={`plugin-status-dot ${inst.state === "ready" || inst.state === "running" ? "green" : inst.state === "error" ? "red" : "yellow"}`} />
                  <span className="plugin-detail-row-name">{inst.label}</span>
                </div>
                <span className="plugin-detail-row-meta">
                  {inst.ip || "no ip"} | {inst.total_logs} logs | {inst.recent_errors} errors
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  if (addonId === "cron") {
    return (
      <div className="plugin-detail">
        <div className="plugin-detail-empty">
          Cron jobs are configured via the API. Use <code>POST /exec</code> with scheduled triggers.
        </div>
      </div>
    );
  }

  return null;
}

// ═══════════════════════════════════════════
//  CONNECTOR CONFIG SCHEMAS
// ═══════════════════════════════════════════

const CONNECTOR_FIELDS: Record<string, { key: string; label: string; placeholder: string; secret?: boolean }[]> = {
  github: [
    { key: "token", label: "Personal Access Token", placeholder: "ghp_xxxxxxxxxxxx", secret: true },
  ],
  s3: [
    { key: "endpoint", label: "Endpoint URL", placeholder: "https://xxx.r2.cloudflarestorage.com" },
    { key: "access_key", label: "Access Key", placeholder: "AKIA...", secret: true },
    { key: "secret_key", label: "Secret Key", placeholder: "wJalr...", secret: true },
    { key: "bucket", label: "Bucket Name", placeholder: "my-bucket" },
  ],
  slack: [
    { key: "bot_token", label: "Bot Token", placeholder: "xoxb-xxxx", secret: true },
    { key: "webhook_url", label: "Webhook URL (optional)", placeholder: "https://hooks.slack.com/services/..." },
  ],
  cloudflare: [
    { key: "api_token", label: "API Token", placeholder: "Your Cloudflare API token", secret: true },
  ],
  r2: [
    { key: "endpoint", label: "R2 Endpoint", placeholder: "https://xxx.r2.cloudflarestorage.com" },
    { key: "access_key", label: "Access Key ID", placeholder: "Your R2 access key", secret: true },
    { key: "secret_key", label: "Secret Access Key", placeholder: "Your R2 secret key", secret: true },
    { key: "bucket", label: "Bucket Name", placeholder: "my-bucket" },
  ],
  vultr: [
    { key: "api_key", label: "API Key", placeholder: "Your Vultr API key", secret: true },
  ],
  hetzner: [
    { key: "api_token", label: "API Token", placeholder: "Your Hetzner Cloud API token", secret: true },
  ],
  runpod: [
    { key: "api_key", label: "API Key", placeholder: "Your RunPod API key", secret: true },
  ],
};

function maskValue(v: string): string {
  if (v.length <= 8) return "••••••";
  return `${v.slice(0, 4)}${"•".repeat(Math.min(12, v.length - 8))}${v.slice(-4)}`;
}

// ═══════════════════════════════════════════
//  CONNECTOR CONFIG FORM
// ═══════════════════════════════════════════

function ConnectorConfigForm({
  connectorId, projectId, initialConfig, onSaved,
}: {
  connectorId: string;
  projectId: string;
  initialConfig: Record<string, any>;
  onSaved: () => void;
}) {
  const fields = CONNECTOR_FIELDS[connectorId] || [];
  const [values, setValues] = useState<Record<string, string>>(() => {
    const v: Record<string, string> = {};
    for (const f of fields) v[f.key] = "";
    return v;
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const hasExistingConfig = Object.keys(initialConfig || {}).length > 0;

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      // Merge: only send fields that have a value (don't overwrite with empty)
      const merged = { ...(initialConfig || {}) };
      for (const [k, v] of Object.entries(values)) {
        if (v.trim()) merged[k] = v.trim();
      }
      await updateAddon(projectId, connectorId, { config: merged }, "connector");
      setValues(() => {
        const v: Record<string, string> = {};
        for (const f of fields) v[f.key] = "";
        return v;
      });
      onSaved();
    } catch (e: any) {
      setError(e.message || "Failed to save");
    }
    setSaving(false);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {fields.map((f) => (
        <div key={f.key}>
          <label style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", display: "block", marginBottom: 3 }}>
            {f.label}
          </label>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input
              type={f.secret ? "password" : "text"}
              value={values[f.key]}
              onChange={(e) => setValues((p) => ({ ...p, [f.key]: e.target.value }))}
              placeholder={initialConfig?.[f.key] ? maskValue(initialConfig[f.key]) : f.placeholder}
              style={{
                flex: 1, padding: "5px 8px", fontSize: "var(--font-xs)",
                background: "var(--bg-deeper, oklch(0.12 0.01 240))", border: "1px solid var(--border)",
                borderRadius: 4, color: "var(--foreground)", fontFamily: "var(--font-mono)",
                outline: "none",
              }}
            />
            {initialConfig?.[f.key] && (
              <Check style={{ width: 12, height: 12, color: "var(--color-green)", flexShrink: 0 }} />
            )}
          </div>
        </div>
      ))}
      {error && (
        <div style={{ fontSize: "var(--font-xxs)", color: "var(--color-red)" }}>{error}</div>
      )}
      <button
        className="plugin-action"
        onClick={handleSave}
        disabled={saving || Object.values(values).every((v) => !v.trim())}
        style={{ alignSelf: "flex-start", marginTop: 4, padding: "4px 12px" }}
      >
        {saving ? <Loader className="h-3 w-3 animate-spin" /> : <>{hasExistingConfig ? "Update" : "Save"}</>}
      </button>
    </div>
  );
}

// ═══════════════════════════════════════════
//  CONNECTOR DETAIL VIEW
// ═══════════════════════════════════════════

function ConnectorDetailView({ addon, projectId, onRefresh }: { addon: AddonInfo; projectId: string; onRefresh: () => void }) {
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [editing, setEditing] = useState(false);

  const handleTest = async () => {
    setTesting(true);
    setResult(null);
    try {
      const res = await testConnector(projectId, addon.addon_id);
      setResult(res);
    } catch (e: any) {
      setResult({ ok: false, message: e.message || "Test failed" });
    }
    setTesting(false);
  };

  const configKeys = Object.keys(addon.config || {});
  const hasConfig = configKeys.length > 0;

  return (
    <div className="plugin-detail">
      <div className="plugin-detail-header">
        <span>Configuration</span>
        <div style={{ display: "flex", gap: 6 }}>
          {hasConfig && (
            <button className="plugin-detail-retry" onClick={() => setEditing(!editing)}>
              <RefreshCw className="h-3 w-3" />
              <span style={{ marginLeft: 3 }}>{editing ? "Cancel" : "Edit"}</span>
            </button>
          )}
          <button className="plugin-detail-retry" onClick={handleTest} disabled={testing || !hasConfig}>
            {testing ? <Loader className="h-3 w-3 animate-spin" /> : <Zap className="h-3 w-3" />}
            <span style={{ marginLeft: 3 }}>Test</span>
          </button>
        </div>
      </div>

      {result && (
        <div style={{
          padding: "6px 10px", fontSize: "var(--font-xs)", borderRadius: 4, marginBottom: 8,
          background: result.ok ? "rgba(52,211,153,0.08)" : "rgba(239,68,68,0.08)",
          color: result.ok ? "var(--color-green)" : "var(--color-red)",
        }}>
          {result.ok ? "✓ " : "✗ "}{result.message}
        </div>
      )}

      {!hasConfig || editing ? (
        <ConnectorConfigForm
          connectorId={addon.addon_id}
          projectId={projectId}
          initialConfig={addon.config || {}}
          onSaved={() => { setEditing(false); onRefresh(); }}
        />
      ) : (
        <div className="plugin-detail-list">
          {configKeys.map((key) => (
            <div key={key} className="plugin-detail-row">
              <span className="plugin-detail-row-name" style={{ fontFamily: "var(--font-mono)", fontSize: "var(--font-xxs)" }}>{key}</span>
              <span className="plugin-detail-row-meta" style={{ fontFamily: "var(--font-mono)", fontSize: "var(--font-xxs)" }}>
                {maskValue(String(addon.config[key] || ""))}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
//  MARKETPLACE SHOWCASE
// ═══════════════════════════════════════════

const CATEGORY_COLORS: Record<string, string> = {
  analytics: "var(--color-teal)",
  monitoring: "var(--color-green)",
  security: "var(--color-yellow)",
  tools: "var(--color-blue)",
  messaging: "var(--color-purple, #a78bfa)",
  automation: "var(--color-orange, #fb923c)",
};

function MarketplaceCard({ addon, onInstall, onUninstall, busy }: {
  addon: AddonInfo;
  onInstall: () => void;
  onUninstall: () => void;
  busy: boolean;
}) {
  const Icon = ADDON_ICONS[addon.addon_id] || Package;
  const schema = addon.config || {};
  const highlights: string[] = schema.highlights || [];
  const tagline: string = schema.tagline || "";
  const pricing: string = schema.pricing || "free";
  const featured: boolean = schema.featured || false;
  const catColor = CATEGORY_COLORS[addon.category] || "var(--color-teal)";

  return (
    <div style={{
      border: `1px solid ${featured ? "oklch(0.22 0.03 200 / 60%)" : "var(--border)"}`,
      borderRadius: 10,
      padding: 0,
      overflow: "hidden",
      transition: "all 0.12s",
      background: featured ? "oklch(0.12 0.01 200 / 30%)" : "transparent",
    }}>
      {/* Header band */}
      <div style={{
        padding: "16px 16px 12px",
        display: "flex", alignItems: "flex-start", gap: 12,
      }}>
        <div style={{
          width: 40, height: 40, borderRadius: 10,
          display: "flex", alignItems: "center", justifyContent: "center",
          background: "oklch(0.18 0.02 200 / 50%)",
          flexShrink: 0,
        }}>
          <Icon style={{ width: 20, height: 20, color: catColor }} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
            <span style={{ fontSize: "var(--font-md)", fontWeight: 600 }}>{addon.name}</span>
            {featured && <Star style={{ width: 12, height: 12, color: "var(--color-yellow)", fill: "var(--color-yellow)" }} />}
          </div>
          {tagline && (
            <div style={{ fontSize: "var(--font-xs)", color: catColor, marginBottom: 4, fontWeight: 500 }}>
              {tagline}
            </div>
          )}
          <div style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)", lineHeight: 1.45 }}>
            {addon.description}
          </div>
        </div>
      </div>

      {/* Highlights */}
      {highlights.length > 0 && (
        <div style={{
          padding: "0 16px 12px",
          display: "flex", flexWrap: "wrap", gap: 6,
        }}>
          {highlights.map((h) => (
            <span key={h} style={{
              display: "inline-flex", alignItems: "center", gap: 4,
              fontSize: "var(--font-xxs)", color: "var(--muted-foreground)",
              background: "oklch(0.18 0.01 200 / 40%)",
              padding: "2px 8px", borderRadius: 4,
            }}>
              <Check style={{ width: 9, height: 9, color: "var(--color-green)" }} />
              {h}
            </span>
          ))}
        </div>
      )}

      {/* Footer */}
      <div style={{
        padding: "10px 16px",
        borderTop: "1px solid var(--border)",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="plugin-category">{addon.category}</span>
          <span style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)" }}>
            {pricing === "free" ? "Gratis" : pricing}
          </span>
          <span style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)" }}>
            v{addon.version}
          </span>
        </div>
        {addon.installed ? (
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <span style={{ fontSize: "var(--font-xxs)", color: "var(--color-green)", display: "flex", alignItems: "center", gap: 3 }}>
              <Check style={{ width: 10, height: 10 }} /> Instalado
            </span>
            <button
              className="plugin-action"
              onClick={onUninstall}
              disabled={busy}
              style={{ fontSize: "var(--font-xxs)", padding: "3px 8px", color: "var(--color-red)" }}
            >
              {busy ? <Loader style={{ width: 10, height: 10 }} className="animate-spin" /> : <Trash2 style={{ width: 10, height: 10 }} />}
            </button>
          </div>
        ) : (
          <button
            className="plugin-action"
            onClick={onInstall}
            disabled={busy}
            style={{ fontSize: "var(--font-xxs)", padding: "3px 10px" }}
          >
            {busy ? (
              <Loader style={{ width: 10, height: 10 }} className="animate-spin" />
            ) : (
              <><Download style={{ width: 10, height: 10 }} /> Instalar</>
            )}
          </button>
        )}
      </div>
    </div>
  );
}

function MarketplaceShowcase({ addons, projectId, actionId, onInstall, onUninstall }: {
  addons: AddonInfo[];
  projectId: string;
  actionId: string | null;
  onInstall: (id: string, type: string) => void;
  onUninstall: (id: string, type: string) => void;
}) {
  const featured = addons.filter((a) => a.config?.featured);
  const rest = addons.filter((a) => !a.config?.featured);

  // Group by category
  const categories = new Map<string, AddonInfo[]>();
  for (const a of rest) {
    const cat = a.category || "other";
    if (!categories.has(cat)) categories.set(cat, []);
    categories.get(cat)!.push(a);
  }

  return (
    <div>
      {/* Featured apps */}
      {featured.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div style={{
            fontSize: "var(--font-xs)", fontWeight: 600, color: "var(--muted-foreground)",
            textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 10,
            display: "flex", alignItems: "center", gap: 6,
          }}>
            <Star style={{ width: 12, height: 12, color: "var(--color-yellow)" }} />
            Destacados
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 12 }}>
            {featured.map((a) => (
              <MarketplaceCard
                key={a.addon_id}
                addon={a}
                busy={actionId === a.addon_id}
                onInstall={() => onInstall(a.addon_id, a.addon_type)}
                onUninstall={() => onUninstall(a.addon_id, a.addon_type)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Rest by category */}
      {Array.from(categories.entries()).map(([cat, apps]) => (
        <div key={cat} style={{ marginBottom: 20 }}>
          <div style={{
            fontSize: "var(--font-xs)", fontWeight: 600, color: "var(--muted-foreground)",
            textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 10,
          }}>
            {cat}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 12 }}>
            {apps.map((a) => (
              <MarketplaceCard
                key={a.addon_id}
                addon={a}
                busy={actionId === a.addon_id}
                onInstall={() => onInstall(a.addon_id, a.addon_type)}
                onUninstall={() => onUninstall(a.addon_id, a.addon_type)}
              />
            ))}
          </div>
        </div>
      ))}

      {addons.length === 0 && (
        <div className="panel-empty">
          <ShoppingBag className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
          <div className="panel-empty-title">No hay apps disponibles</div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
//  ADDON CARD
// ═══════════════════════════════════════════

function AddonCard({
  addon, projectId, busy, expanded,
  onInstall, onUninstall, onToggle, onToggleExpand, onRefresh,
}: {
  addon: AddonInfo;
  projectId: string;
  busy: boolean;
  expanded: boolean;
  onInstall: () => void;
  onUninstall: () => void;
  onToggle: (enabled: boolean) => void;
  onToggleExpand: () => void;
  onRefresh: () => void;
}) {
  const Icon = ADDON_ICONS[addon.addon_id] || Puzzle;

  return (
    <div className={`plugin-card ${addon.installed ? "installed" : ""}`}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <div className="plugin-icon">
          <Icon className="h-5 w-5" style={{ color: addon.installed && addon.enabled ? "var(--color-teal)" : "var(--muted-foreground)" }} />
        </div>
        <div className="plugin-info">
          <div className="plugin-name">
            {addon.name}
            {addon.installed && !addon.enabled && (
              <span style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginLeft: 6 }}>disabled</span>
            )}
          </div>
          <div className="plugin-desc">{addon.description}</div>
          <div className="plugin-meta">
            <span className="plugin-version">v{addon.version}</span>
            <span className="plugin-category">{addon.category}</span>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-end", flexShrink: 0 }}>
          {addon.installed ? (
            <>
              <button
                className="plugin-action installed"
                onClick={() => onToggle(!addon.enabled)}
                disabled={busy}
              >
                {busy ? (
                  <Loader className="h-3 w-3 animate-spin" />
                ) : addon.enabled ? (
                  <><ToggleRight className="h-3 w-3" /><span>Enabled</span></>
                ) : (
                  <><ToggleLeft className="h-3 w-3" /><span>Disabled</span></>
                )}
              </button>
              <div style={{ display: "flex", gap: 4 }}>
                <button
                  className="plugin-action"
                  onClick={onToggleExpand}
                  title={expanded ? "Collapse" : "Expand"}
                >
                  {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                  <span>{expanded ? "Close" : "Open"}</span>
                </button>
                <button
                  className="plugin-action"
                  onClick={onUninstall}
                  disabled={busy}
                  style={{ color: "var(--color-red)", fontSize: 10 }}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            </>
          ) : (
            <button className="plugin-action" onClick={onInstall} disabled={busy}>
              {busy ? (
                <Loader className="h-3 w-3 animate-spin" />
              ) : (
                <><Download className="h-3 w-3" /><span>Install</span></>
              )}
            </button>
          )}
        </div>
      </div>
      {expanded && addon.installed && addon.enabled && (
        addon.addon_type === "connector" ? (
          <ConnectorDetailView addon={addon} projectId={projectId} onRefresh={onRefresh} />
        ) : (
          <PluginDetailView addonId={addon.addon_id} projectId={projectId} />
        )
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
//  MAIN ADDONS PANEL
// ═══════════════════════════════════════════

export function AddonsPanel() {
  const activeProject = useDashboardStore((s) => s.activeProject);
  const projectId = activeProject?.id || "";
  const [addons, setAddons] = useState<AddonInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionId, setActionId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<AddonTab>("connectors");

  useEffect(() => {
    if (!projectId) return;
    loadAddons();
  }, [projectId, activeTab]);

  const loadAddons = async () => {
    setLoading(true);
    setError("");
    try {
      const addonType = ADDON_TYPE_MAP[activeTab];
      const res = await listAddons(projectId, addonType);
      setAddons(res.addons || []);
    } catch (e: any) {
      setError(e.message?.includes("401") ? "Not authorized" : `Failed to load: ${e.message}`);
    }
    setLoading(false);
  };

  const handleInstall = async (addonId: string, addonType: string) => {
    setActionId(addonId);
    setError("");
    try {
      await installAddon(projectId, addonId, addonType);
      await loadAddons();
      // Auto-expand connectors so user sees the config form
      if (addonType === "connector") setExpandedId(addonId);
    } catch (e: any) {
      setError(`Install failed: ${e.message}`);
    }
    setActionId(null);
  };

  const handleUninstall = async (addonId: string, addonType: string) => {
    setActionId(addonId);
    setError("");
    try {
      await uninstallAddon(projectId, addonId, addonType);
      setExpandedId(null);
      await loadAddons();
    } catch (e: any) {
      setError(`Uninstall failed: ${e.message}`);
    }
    setActionId(null);
  };

  const handleToggle = async (addonId: string, enabled: boolean, addonType: string) => {
    setActionId(addonId);
    setError("");
    try {
      await updateAddon(projectId, addonId, { enabled }, addonType);
      setAddons((prev) =>
        prev.map((a) => (a.addon_id === addonId ? { ...a, enabled } : a))
      );
    } catch (e: any) {
      setError(`Update failed: ${e.message}`);
    }
    setActionId(null);
  };

  const installed = addons.filter((a) => a.installed);
  const available = addons.filter((a) => !a.installed);

  const emptyIcon = activeTab === "connectors" ? Link2 : activeTab === "marketplace" ? ShoppingBag : Puzzle;
  const emptyLabel = activeTab === "connectors" ? "connectors" : activeTab === "marketplace" ? "apps" : "plugins";

  return (
    <div>

      {/* Tab bar */}
      <div className="tab-bar">
        {TAB_CONFIG.map((tab) => (
          <button
            key={tab.id}
            className={`tab-item ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => { setActiveTab(tab.id); setExpandedId(null); }}
          >
            <tab.icon className="h-3.5 w-3.5" />
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div style={{ padding: "8px 12px", fontSize: "var(--font-xs)", color: "var(--color-red)", background: "rgba(239,68,68,0.08)", borderRadius: 6, marginBottom: 12, display: "flex", alignItems: "center", gap: 6 }}>
          <AlertCircle className="h-3.5 w-3.5" style={{ flexShrink: 0 }} />
          <span>{error}</span>
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 40, gap: 8, color: "var(--muted-foreground)" }}>
          <Loader className="h-4 w-4 animate-spin" />
          <span style={{ fontSize: "var(--font-xs)" }}>Loading {emptyLabel}...</span>
        </div>
      ) : activeTab === "marketplace" ? (
        /* ── Marketplace: showcase layout ── */
        <MarketplaceShowcase
          addons={addons}
          projectId={projectId}
          actionId={actionId}
          onInstall={handleInstall}
          onUninstall={handleUninstall}
        />
      ) : (
        /* ── Connectors & Plugins: install/manage layout ── */
        <>
          {installed.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: "var(--font-xs)", fontWeight: 600, color: "var(--muted-foreground)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 8 }}>
                Installed ({installed.length})
              </div>
              <div className="plugin-grid">
                {installed.map((a) => (
                  <AddonCard
                    key={a.addon_id}
                    addon={a}
                    projectId={projectId}
                    busy={actionId === a.addon_id}
                    expanded={expandedId === a.addon_id}
                    onInstall={() => handleInstall(a.addon_id, a.addon_type)}
                    onUninstall={() => handleUninstall(a.addon_id, a.addon_type)}
                    onToggle={(enabled) => handleToggle(a.addon_id, enabled, a.addon_type)}
                    onToggleExpand={() => setExpandedId(expandedId === a.addon_id ? null : a.addon_id)}
                    onRefresh={loadAddons}
                  />
                ))}
              </div>
            </div>
          )}

          <div>
            <div style={{ fontSize: "var(--font-xs)", fontWeight: 600, color: "var(--muted-foreground)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 8 }}>
              {installed.length > 0 ? "Available" : TAB_CONFIG.find((t) => t.id === activeTab)?.label || "Addons"}
            </div>
            {available.length === 0 && installed.length > 0 ? (
              <div className="panel-empty">
                <Package className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
                <div className="panel-empty-title">All installed</div>
              </div>
            ) : available.length === 0 ? (
              <div className="panel-empty">
                {(() => { const EI = emptyIcon; return <EI className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />; })()}
                <div className="panel-empty-title">No {emptyLabel} available</div>
              </div>
            ) : (
              <div className="plugin-grid">
                {available.map((a) => (
                  <AddonCard
                    key={a.addon_id}
                    addon={a}
                    projectId={projectId}
                    busy={actionId === a.addon_id}
                    expanded={false}
                    onInstall={() => handleInstall(a.addon_id, a.addon_type)}
                    onUninstall={() => handleUninstall(a.addon_id, a.addon_type)}
                    onToggle={(enabled) => handleToggle(a.addon_id, enabled, a.addon_type)}
                    onToggleExpand={() => {}}
                    onRefresh={loadAddons}
                  />
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
