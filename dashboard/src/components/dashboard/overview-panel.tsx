"use client";

import { Server, Activity, Clock, Zap } from "lucide-react";

export function OverviewPanel({ apiHealth, agentHealth }: { apiHealth: any; agentHealth: any }) {
  const apiUp = !!apiHealth;
  const agentUp = !!agentHealth;
  const uptime = apiHealth ? formatUptime(apiHealth.uptime_seconds) : "—";

  return (
    <div>
      {/* Status row */}
      <div className="ov-status-row">
        <StatusCard
          label="API"
          version={apiHealth?.version}
          online={apiUp}
        />
        <StatusCard
          label="Agent"
          version={agentHealth?.version}
          online={agentUp}
        />
        <div className="ov-stat-card">
          <Clock className="h-3.5 w-3.5" style={{ color: "var(--color-blue)" }} />
          <div className="ov-stat-info">
            <span className="ov-stat-label">Uptime</span>
            <span className="ov-stat-value">{uptime}</span>
          </div>
        </div>
        <div className="ov-stat-card">
          <Zap className="h-3.5 w-3.5" style={{ color: "var(--color-purple)" }} />
          <div className="ov-stat-info">
            <span className="ov-stat-label">Platform</span>
            <span className="ov-stat-value">{apiHealth?.platform || "—"}</span>
          </div>
        </div>
      </div>

      {/* Capabilities */}
      {agentHealth?.features && agentHealth.features.length > 0 && (
        <div className="ov-section">
          <div className="ov-section-title">Agent Capabilities</div>
          <div className="ov-features">
            {agentHealth.features.map((f: string) => (
              <span key={f} className="ov-feature">{f}</span>
            ))}
          </div>
        </div>
      )}

      {/* Details */}
      {(apiHealth || agentHealth) && (
        <div className="ov-section">
          <div className="ov-section-title">Details</div>
          <div className="ov-details">
            {apiHealth && (
              <>
                <div className="ov-detail-row">
                  <span className="ov-detail-label">API Status</span>
                  <span className="ov-detail-value">{apiHealth.status}</span>
                </div>
                <div className="ov-detail-row">
                  <span className="ov-detail-label">API Version</span>
                  <span className="ov-detail-value">v{apiHealth.version}</span>
                </div>
                <div className="ov-detail-row">
                  <span className="ov-detail-label">Uptime (seconds)</span>
                  <span className="ov-detail-value">{Math.round(apiHealth.uptime_seconds)}</span>
                </div>
              </>
            )}
            {agentHealth && (
              <>
                <div className="ov-detail-row">
                  <span className="ov-detail-label">Agent Status</span>
                  <span className="ov-detail-value">{agentHealth.status}</span>
                </div>
                <div className="ov-detail-row">
                  <span className="ov-detail-label">Agent Version</span>
                  <span className="ov-detail-value">v{agentHealth.version}</span>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function StatusCard({ label, version, online }: { label: string; version?: string; online: boolean }) {
  return (
    <div className="ov-stat-card">
      <div className="ov-status-indicator" style={{ background: online ? "var(--color-green)" : "var(--color-red)" }} />
      <div className="ov-stat-info">
        <span className="ov-stat-label">{label}</span>
        <span className="ov-stat-value">
          {online ? "Online" : "Offline"}
          {version && <span className="ov-stat-version">v{version}</span>}
        </span>
      </div>
    </div>
  );
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}
