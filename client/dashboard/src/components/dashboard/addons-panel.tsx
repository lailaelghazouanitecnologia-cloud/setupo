"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Puzzle, Download, Trash2, Package,
  Loader, AlertCircle, ToggleLeft, ToggleRight,
  HardDrive, FileText, Globe, Activity, Archive,
  Clock, ChevronDown, ChevronUp, RefreshCw,
  Link2, ShoppingBag, Zap, Github, Database,
  Cloud, MessageSquare, Container, BarChart3,
  HeartPulse, Shield, Table,
} from "lucide-react";
import {
  listProjects, listAddons, installAddon, uninstallAddon, updateAddon,
  testConnector,
  pluginStorageList, pluginStorageDelete,
  pluginLogsList, pluginDnsList, pluginMonitoring, pluginBackupsList,
  type AddonInfo,
} from "@/lib/api/client";
import type { AddonTab } from "@/types/dashboard";

// ═══════════════════════════════════════════
//  ICON MAP
// ═══════════════════════════════════════════

const ADDON_ICONS: Record<string, typeof Puzzle> = {
  // Plugins
  storage: HardDrive,
  monitoring: Activity,
  backups: Archive,
  logs: FileText,
  dns: Globe,
  cron: Clock,
  // Connectors
  github: Github,
  supabase: Database,
  s3: Cloud,
  slack: MessageSquare,
  "docker-registry": Container,
  // Marketplace
  "analytics-dashboard": BarChart3,
  "uptime-monitor": HeartPulse,
  "ssl-manager": Shield,
  "database-viewer": Table,
};

const TAB_CONFIG: { id: AddonTab; label: string; icon: typeof Puzzle }[] = [
  { id: "connectors", label: "Connectors", icon: Link2 },
  { id: "plugins", label: "Plugins", icon: Puzzle },
  { id: "marketplace", label: "Marketplace", icon: ShoppingBag },
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
      } else if (addonId === "backups") {
        setData(await pluginBackupsList(projectId));
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

  if (addonId === "backups") {
    const backups = data?.backups || [];
    return (
      <div className="plugin-detail">
        <div className="plugin-detail-header">
          <span>{backups.length} backup{backups.length !== 1 ? "s" : ""} in R2</span>
          <button className="plugin-detail-retry" onClick={load}><RefreshCw className="h-3 w-3" /></button>
        </div>
        {backups.length === 0 ? (
          <div className="plugin-detail-empty">No backups yet. Deploy a workspace to create .zar backups.</div>
        ) : (
          <div className="plugin-detail-list">
            {backups.map((b: any, i: number) => (
              <div key={i} className="plugin-detail-row">
                <span className="plugin-detail-row-name">{b.workspace}/{b.branch}/{b.file}</span>
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
//  CONNECTOR DETAIL VIEW
// ═══════════════════════════════════════════

function ConnectorDetailView({ addon, projectId }: { addon: AddonInfo; projectId: string }) {
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

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

  return (
    <div className="plugin-detail">
      <div className="plugin-detail-header">
        <span>Configuration</span>
        <button className="plugin-detail-retry" onClick={handleTest} disabled={testing}>
          {testing ? <Loader className="h-3 w-3 animate-spin" /> : <Zap className="h-3 w-3" />}
          <span style={{ marginLeft: 4 }}>Test</span>
        </button>
      </div>

      {result && (
        <div style={{
          padding: "6px 10px", fontSize: "var(--font-xs)", borderRadius: 4, marginBottom: 8,
          background: result.ok ? "rgba(52,211,153,0.08)" : "rgba(239,68,68,0.08)",
          color: result.ok ? "var(--color-green)" : "var(--color-red)",
        }}>
          {result.message}
        </div>
      )}

      {configKeys.length === 0 ? (
        <div className="plugin-detail-empty">
          No credentials configured yet. Use the API to set connector config.
        </div>
      ) : (
        <div className="plugin-detail-list">
          {configKeys.map((key) => (
            <div key={key} className="plugin-detail-row">
              <span className="plugin-detail-row-name" style={{ fontFamily: "var(--font-mono)" }}>{key}</span>
              <span className="plugin-detail-row-meta">configured</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
//  MARKETPLACE DETAIL VIEW
// ═══════════════════════════════════════════

function MarketplaceDetailView({ addon }: { addon: AddonInfo }) {
  return (
    <div className="plugin-detail">
      <div className="plugin-detail-header">
        <span>App Details</span>
      </div>
      <div className="plugin-detail-list">
        <div className="plugin-detail-row">
          <span className="plugin-detail-row-name">Version</span>
          <span className="plugin-detail-row-meta">{addon.version}</span>
        </div>
        <div className="plugin-detail-row">
          <span className="plugin-detail-row-name">Author</span>
          <span className="plugin-detail-row-meta">{addon.author}</span>
        </div>
        <div className="plugin-detail-row">
          <span className="plugin-detail-row-name">Category</span>
          <span className="plugin-detail-row-meta">{addon.category}</span>
        </div>
        {addon.installed_at && (
          <div className="plugin-detail-row">
            <span className="plugin-detail-row-name">Installed</span>
            <span className="plugin-detail-row-meta">{new Date(addon.installed_at).toLocaleDateString()}</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════
//  ADDON CARD
// ═══════════════════════════════════════════

function AddonCard({
  addon, projectId, busy, expanded,
  onInstall, onUninstall, onToggle, onToggleExpand,
}: {
  addon: AddonInfo;
  projectId: string;
  busy: boolean;
  expanded: boolean;
  onInstall: () => void;
  onUninstall: () => void;
  onToggle: (enabled: boolean) => void;
  onToggleExpand: () => void;
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
          <ConnectorDetailView addon={addon} projectId={projectId} />
        ) : addon.addon_type === "marketplace" ? (
          <MarketplaceDetailView addon={addon} />
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
  const [projectId, setProjectId] = useState("");
  const [projects, setProjects] = useState<any[]>([]);
  const [addons, setAddons] = useState<AddonInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionId, setActionId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<AddonTab>("connectors");

  useEffect(() => {
    (async () => {
      try {
        const res = await listProjects();
        const projs = res.projects || [];
        setProjects(projs);
        if (projs.length > 0) setProjectId(projs[0].id);
      } catch (e: any) {
        setError(e.message?.includes("401") ? "Not authorized — check your login" : "Failed to load projects");
        setLoading(false);
      }
    })();
  }, []);

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
      {/* Project selector */}
      {projects.length > 1 && (
        <div style={{ marginBottom: 16 }}>
          <select className="deploy-select" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      )}

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
      ) : (
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
