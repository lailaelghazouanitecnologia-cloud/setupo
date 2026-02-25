"use client";

import { useState } from "react";
import { Puzzle, Download, Check, ExternalLink, Package } from "lucide-react";

interface Plugin {
  id: string;
  name: string;
  description: string;
  version: string;
  installed: boolean;
  category: string;
}

const AVAILABLE_PLUGINS: Plugin[] = [
  {
    id: "monitoring",
    name: "Monitoring",
    description: "System metrics, alerts, and uptime tracking",
    version: "1.0.0",
    installed: false,
    category: "observability",
  },
  {
    id: "backups",
    name: "Backups",
    description: "Automated snapshot and restore for workspaces",
    version: "1.0.0",
    installed: false,
    category: "data",
  },
  {
    id: "ci-cd",
    name: "CI/CD",
    description: "Build and deploy pipelines for your projects",
    version: "0.9.0",
    installed: false,
    category: "devops",
  },
  {
    id: "logs",
    name: "Log Viewer",
    description: "Centralized log aggregation and search",
    version: "1.0.0",
    installed: false,
    category: "observability",
  },
  {
    id: "dns",
    name: "DNS Manager",
    description: "Manage DNS records for your domains",
    version: "1.0.0",
    installed: false,
    category: "networking",
  },
  {
    id: "cron",
    name: "Cron Jobs",
    description: "Schedule and manage recurring tasks",
    version: "1.0.0",
    installed: false,
    category: "automation",
  },
];

export function PluginsPanel() {
  const [plugins, setPlugins] = useState<Plugin[]>(AVAILABLE_PLUGINS);
  const [installing, setInstalling] = useState<string | null>(null);

  const toggleInstall = async (id: string) => {
    const plugin = plugins.find((p) => p.id === id);
    if (!plugin) return;

    if (plugin.installed) {
      setPlugins((prev) => prev.map((p) => (p.id === id ? { ...p, installed: false } : p)));
      return;
    }

    setInstalling(id);
    // Simulate install
    await new Promise((r) => setTimeout(r, 1200));
    setPlugins((prev) => prev.map((p) => (p.id === id ? { ...p, installed: true } : p)));
    setInstalling(null);
  };

  const installed = plugins.filter((p) => p.installed);
  const available = plugins.filter((p) => !p.installed);

  return (
    <div>
      {installed.length > 0 && (
        <div className="settings-section">
          <div className="settings-section-title">Installed</div>
          <div className="plugin-grid">
            {installed.map((p) => (
              <PluginCard
                key={p.id}
                plugin={p}
                installing={installing === p.id}
                onToggle={() => toggleInstall(p.id)}
              />
            ))}
          </div>
        </div>
      )}

      <div className="settings-section">
        <div className="settings-section-title">
          {installed.length > 0 ? "Available" : "Plugins"}
        </div>
        {available.length === 0 ? (
          <div className="panel-empty">
            <Package className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
            <div className="panel-empty-title">All installed</div>
            <div className="panel-empty-sub">Every available plugin is installed</div>
          </div>
        ) : (
          <div className="plugin-grid">
            {available.map((p) => (
              <PluginCard
                key={p.id}
                plugin={p}
                installing={installing === p.id}
                onToggle={() => toggleInstall(p.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function PluginCard({
  plugin,
  installing,
  onToggle,
}: {
  plugin: Plugin;
  installing: boolean;
  onToggle: () => void;
}) {
  return (
    <div className={`plugin-card ${plugin.installed ? "installed" : ""}`}>
      <div className="plugin-icon">
        <Puzzle className="h-5 w-5" style={{ color: plugin.installed ? "var(--color-teal)" : "var(--muted-foreground)" }} />
      </div>
      <div className="plugin-info">
        <div className="plugin-name">{plugin.name}</div>
        <div className="plugin-desc">{plugin.description}</div>
        <div className="plugin-meta">
          <span className="plugin-version">v{plugin.version}</span>
          <span className="plugin-category">{plugin.category}</span>
        </div>
      </div>
      <button
        className={`plugin-action ${plugin.installed ? "installed" : ""}`}
        onClick={onToggle}
        disabled={installing}
      >
        {installing ? (
          <span className="term-spinner" />
        ) : plugin.installed ? (
          <>
            <Check className="h-3 w-3" />
            <span>Installed</span>
          </>
        ) : (
          <>
            <Download className="h-3 w-3" />
            <span>Install</span>
          </>
        )}
      </button>
    </div>
  );
}
