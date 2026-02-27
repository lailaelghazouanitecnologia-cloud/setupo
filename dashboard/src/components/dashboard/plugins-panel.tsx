"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Puzzle, Download, Trash2, Package,
  Loader, AlertCircle, ToggleLeft, ToggleRight,
  HardDrive, FileText, Globe, Activity, Archive,
  Clock, ChevronDown, ChevronUp, RefreshCw,
} from "lucide-react";
import {
  listProjects, listPlugins, installPlugin, uninstallPlugin, updatePlugin,
  pluginStorageList, pluginStorageDelete,
  pluginLogsList, pluginDnsList, pluginMonitoring, pluginBackupsList,
  type PluginInfo,
} from "@/lib/api/client";

const PLUGIN_ICONS: Record<string, typeof Puzzle> = {
  storage: HardDrive,
  monitoring: Activity,
  backups: Archive,
  logs: FileText,
  dns: Globe,
  cron: Clock,
};

function PluginDetailView({ pluginId, projectId }: { pluginId: string; projectId: string }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (pluginId === "storage") {
        const res = await pluginStorageList(projectId);
        setData(res);
      } else if (pluginId === "logs") {
        const res = await pluginLogsList(projectId, "", "", 50);
        setData(res);
      } else if (pluginId === "dns") {
        const res = await pluginDnsList(projectId);
        setData(res);
      } else if (pluginId === "monitoring") {
        const res = await pluginMonitoring(projectId);
        setData(res);
      } else if (pluginId === "backups") {
        const res = await pluginBackupsList(projectId);
        setData(res);
      }
    } catch (e: any) {
      setError(e.message || "Failed to load");
    }
    setLoading(false);
  }, [pluginId, projectId]);

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

  if (pluginId === "storage") {
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

  if (pluginId === "logs") {
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

  if (pluginId === "dns") {
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

  if (pluginId === "monitoring") {
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

  if (pluginId === "backups") {
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

  if (pluginId === "cron") {
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

export function PluginsPanel() {
  const [projectId, setProjectId] = useState("");
  const [projects, setProjects] = useState<any[]>([]);
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionId, setActionId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

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
    loadPlugins();
  }, [projectId]);

  const loadPlugins = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await listPlugins(projectId);
      setPlugins(res.plugins || []);
    } catch (e: any) {
      setError(e.message?.includes("401") ? "Not authorized" : `Failed to load plugins: ${e.message}`);
    }
    setLoading(false);
  };

  const handleInstall = async (pluginId: string) => {
    setActionId(pluginId);
    setError("");
    try {
      await installPlugin(projectId, pluginId);
      await loadPlugins();
    } catch (e: any) {
      setError(`Install failed: ${e.message}`);
    }
    setActionId(null);
  };

  const handleUninstall = async (pluginId: string) => {
    setActionId(pluginId);
    setError("");
    try {
      await uninstallPlugin(projectId, pluginId);
      setExpandedId(null);
      await loadPlugins();
    } catch (e: any) {
      setError(`Uninstall failed: ${e.message}`);
    }
    setActionId(null);
  };

  const handleToggle = async (pluginId: string, enabled: boolean) => {
    setActionId(pluginId);
    setError("");
    try {
      await updatePlugin(projectId, pluginId, { enabled });
      setPlugins((prev) =>
        prev.map((p) => (p.plugin_id === pluginId ? { ...p, enabled } : p))
      );
    } catch (e: any) {
      setError(`Update failed: ${e.message}`);
    }
    setActionId(null);
  };

  const installed = plugins.filter((p) => p.installed);
  const available = plugins.filter((p) => !p.installed);

  return (
    <div>
      {projects.length > 1 && (
        <div style={{ marginBottom: 16 }}>
          <select className="deploy-select" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      )}

      {error && (
        <div style={{ padding: "8px 12px", fontSize: "var(--font-xs)", color: "var(--color-red)", background: "rgba(239,68,68,0.08)", borderRadius: 6, marginBottom: 12, display: "flex", alignItems: "center", gap: 6 }}>
          <AlertCircle className="h-3.5 w-3.5" style={{ flexShrink: 0 }} />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 40, gap: 8, color: "var(--muted-foreground)" }}>
          <Loader className="h-4 w-4 animate-spin" />
          <span style={{ fontSize: "var(--font-xs)" }}>Loading plugins...</span>
        </div>
      ) : (
        <>
          {installed.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: "var(--font-xs)", fontWeight: 600, color: "var(--muted-foreground)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 8 }}>
                Installed ({installed.length})
              </div>
              <div className="plugin-grid">
                {installed.map((p) => (
                  <PluginCard
                    key={p.plugin_id}
                    plugin={p}
                    projectId={projectId}
                    busy={actionId === p.plugin_id}
                    expanded={expandedId === p.plugin_id}
                    onInstall={() => handleInstall(p.plugin_id)}
                    onUninstall={() => handleUninstall(p.plugin_id)}
                    onToggle={(enabled) => handleToggle(p.plugin_id, enabled)}
                    onToggleExpand={() => setExpandedId(expandedId === p.plugin_id ? null : p.plugin_id)}
                  />
                ))}
              </div>
            </div>
          )}

          <div>
            <div style={{ fontSize: "var(--font-xs)", fontWeight: 600, color: "var(--muted-foreground)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 8 }}>
              {installed.length > 0 ? "Available" : "Plugins"}
            </div>
            {available.length === 0 && installed.length > 0 ? (
              <div className="panel-empty">
                <Package className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
                <div className="panel-empty-title">All installed</div>
              </div>
            ) : available.length === 0 ? (
              <div className="panel-empty">
                <Puzzle className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
                <div className="panel-empty-title">No plugins available</div>
              </div>
            ) : (
              <div className="plugin-grid">
                {available.map((p) => (
                  <PluginCard
                    key={p.plugin_id}
                    plugin={p}
                    projectId={projectId}
                    busy={actionId === p.plugin_id}
                    expanded={false}
                    onInstall={() => handleInstall(p.plugin_id)}
                    onUninstall={() => handleUninstall(p.plugin_id)}
                    onToggle={(enabled) => handleToggle(p.plugin_id, enabled)}
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

function PluginCard({
  plugin, projectId, busy, expanded,
  onInstall, onUninstall, onToggle, onToggleExpand,
}: {
  plugin: PluginInfo;
  projectId: string;
  busy: boolean;
  expanded: boolean;
  onInstall: () => void;
  onUninstall: () => void;
  onToggle: (enabled: boolean) => void;
  onToggleExpand: () => void;
}) {
  const Icon = PLUGIN_ICONS[plugin.plugin_id] || Puzzle;

  return (
    <div className={`plugin-card ${plugin.installed ? "installed" : ""}`}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <div className="plugin-icon">
          <Icon className="h-5 w-5" style={{ color: plugin.installed && plugin.enabled ? "var(--color-teal)" : "var(--muted-foreground)" }} />
        </div>
        <div className="plugin-info">
          <div className="plugin-name">
            {plugin.name}
            {plugin.installed && !plugin.enabled && (
              <span style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginLeft: 6 }}>disabled</span>
            )}
          </div>
          <div className="plugin-desc">{plugin.description}</div>
          <div className="plugin-meta">
            <span className="plugin-version">v{plugin.version}</span>
            <span className="plugin-category">{plugin.category}</span>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-end", flexShrink: 0 }}>
          {plugin.installed ? (
            <>
              <button
                className="plugin-action installed"
                onClick={() => onToggle(!plugin.enabled)}
                disabled={busy}
              >
                {busy ? (
                  <Loader className="h-3 w-3 animate-spin" />
                ) : plugin.enabled ? (
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
      {expanded && plugin.installed && plugin.enabled && (
        <PluginDetailView pluginId={plugin.plugin_id} projectId={projectId} />
      )}
    </div>
  );
}
