"use client";

import { useState, useEffect } from "react";
import {
  Puzzle, Download, Check, Trash2, Package,
  Loader, AlertCircle, ToggleLeft, ToggleRight,
} from "lucide-react";
import {
  listProjects, listPlugins, installPlugin, uninstallPlugin, updatePlugin,
  type PluginInfo,
} from "@/lib/api/client";

export function PluginsPanel() {
  const [projectId, setProjectId] = useState("");
  const [projects, setProjects] = useState<any[]>([]);
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionId, setActionId] = useState<string | null>(null);

  // Load projects
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

  // Load plugins when project changes
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
      {/* Project selector (if multiple) */}
      {projects.length > 1 && (
        <div style={{ marginBottom: 16 }}>
          <select className="deploy-select" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div style={{ padding: "8px 12px", fontSize: "var(--font-xs)", color: "var(--color-red)", background: "rgba(239,68,68,0.08)", borderRadius: 6, marginBottom: 12, display: "flex", alignItems: "center", gap: 6 }}>
          <AlertCircle className="h-3.5 w-3.5" style={{ flexShrink: 0 }} />
          <span>{error}</span>
        </div>
      )}

      {/* Loading */}
      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 40, gap: 8, color: "var(--muted-foreground)" }}>
          <Loader className="h-4 w-4 animate-spin" />
          <span style={{ fontSize: "var(--font-xs)" }}>Loading plugins...</span>
        </div>
      ) : (
        <>
          {/* Installed */}
          {installed.length > 0 && (
            <div className="settings-section">
              <div className="settings-section-title">Installed ({installed.length})</div>
              <div className="plugin-grid">
                {installed.map((p) => (
                  <PluginCard
                    key={p.plugin_id}
                    plugin={p}
                    busy={actionId === p.plugin_id}
                    onInstall={() => handleInstall(p.plugin_id)}
                    onUninstall={() => handleUninstall(p.plugin_id)}
                    onToggle={(enabled) => handleToggle(p.plugin_id, enabled)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Available */}
          <div className="settings-section">
            <div className="settings-section-title">
              {installed.length > 0 ? "Available" : "Plugins"}
            </div>
            {available.length === 0 && installed.length > 0 ? (
              <div className="panel-empty">
                <Package className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
                <div className="panel-empty-title">All installed</div>
                <div className="panel-empty-sub">Every available plugin is installed</div>
              </div>
            ) : available.length === 0 && installed.length === 0 ? (
              <div className="panel-empty">
                <Puzzle className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
                <div className="panel-empty-title">No plugins available</div>
                <div className="panel-empty-sub">Check back later for new plugins</div>
              </div>
            ) : (
              <div className="plugin-grid">
                {available.map((p) => (
                  <PluginCard
                    key={p.plugin_id}
                    plugin={p}
                    busy={actionId === p.plugin_id}
                    onInstall={() => handleInstall(p.plugin_id)}
                    onUninstall={() => handleUninstall(p.plugin_id)}
                    onToggle={(enabled) => handleToggle(p.plugin_id, enabled)}
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
  plugin,
  busy,
  onInstall,
  onUninstall,
  onToggle,
}: {
  plugin: PluginInfo;
  busy: boolean;
  onInstall: () => void;
  onUninstall: () => void;
  onToggle: (enabled: boolean) => void;
}) {
  return (
    <div className={`plugin-card ${plugin.installed ? "installed" : ""}`}>
      <div className="plugin-icon">
        <Puzzle className="h-5 w-5" style={{ color: plugin.installed && plugin.enabled ? "var(--color-teal)" : "var(--muted-foreground)" }} />
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
      <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-end" }}>
        {plugin.installed ? (
          <>
            {/* Toggle enable/disable */}
            <button
              className="plugin-action installed"
              onClick={() => onToggle(!plugin.enabled)}
              disabled={busy}
              title={plugin.enabled ? "Disable" : "Enable"}
            >
              {busy ? (
                <Loader className="h-3 w-3 animate-spin" />
              ) : plugin.enabled ? (
                <>
                  <ToggleRight className="h-3 w-3" />
                  <span>Enabled</span>
                </>
              ) : (
                <>
                  <ToggleLeft className="h-3 w-3" />
                  <span>Disabled</span>
                </>
              )}
            </button>
            {/* Uninstall */}
            <button
              className="plugin-action"
              onClick={onUninstall}
              disabled={busy}
              style={{ color: "var(--color-red)", fontSize: 10 }}
              title="Uninstall"
            >
              <Trash2 className="h-3 w-3" />
              <span>Remove</span>
            </button>
          </>
        ) : (
          <button
            className="plugin-action"
            onClick={onInstall}
            disabled={busy}
          >
            {busy ? (
              <Loader className="h-3 w-3 animate-spin" />
            ) : (
              <>
                <Download className="h-3 w-3" />
                <span>Install</span>
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}
