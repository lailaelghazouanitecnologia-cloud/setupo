"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  Server, Activity, AlertTriangle, CheckCircle,
  RefreshCw, XCircle, Clock, Cpu, HardDrive,
  Play, Square, Zap, BarChart3, TrendingUp,
} from "lucide-react";
import { timeAgo } from "@/lib/format";
import {
  getOrchestratorOverview,
  listBuilds,
  cancelBuild,
  getOrchestratorAlerts,
  resolveOrchestratorAlert,
  getScalingRecommendations,
  rebalancePool,
  updatePoolNode,
  type OrchestratorOverview,
  type BuildJob,
  type ScaleAlert,
  type PoolNode,
} from "@/lib/api/client";

type OrcTab = "overview" | "nodes" | "builds" | "alerts";

export function OrchestratorPanel() {
  const [tab, setTab] = useState<OrcTab>("overview");

  const tabs: { id: OrcTab; label: string; icon: React.ElementType }[] = [
    { id: "overview", label: "Overview", icon: BarChart3 },
    { id: "nodes", label: "Nodes", icon: Server },
    { id: "builds", label: "Builds", icon: Play },
    { id: "alerts", label: "Alerts", icon: AlertTriangle },
  ];

  return (
    <div>
      <div className="admin-tabs">
        {tabs.map((t) => (
          <button
            key={t.id}
            className={`admin-tab ${tab === t.id ? "active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            <t.icon className="h-3.5 w-3.5" />
            <span>{t.label}</span>
          </button>
        ))}
      </div>
      {tab === "overview" && <OverviewTab />}
      {tab === "nodes" && <NodesTab />}
      {tab === "builds" && <BuildsTab />}
      {tab === "alerts" && <AlertsTab />}
    </div>
  );
}

/* ═══════════════════════════════════════
   OVERVIEW
   ═══════════════════════════════════════ */
function OverviewTab() {
  const [data, setData] = useState<OrchestratorOverview | null>(null);
  const [recs, setRecs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [overview, recommendations] = await Promise.all([
        getOrchestratorOverview(),
        getScalingRecommendations(),
      ]);
      setData(overview);
      setRecs(recommendations);
    } catch (e: any) {
      console.error(e);
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="panel-loading">Loading orchestrator...</div>;
  if (!data) return <div className="panel-empty">Failed to load orchestrator data</div>;

  return (
    <div style={{ padding: 16 }}>
      {/* Metrics cards */}
      <div className="metrics-grid">
        <MetricCard label="Nodes" value={`${data.active_nodes}/${data.total_nodes}`} icon={Server} />
        <MetricCard label="Avg CPU" value={`${data.avg_cpu}%`} icon={Cpu} color={data.avg_cpu > 80 ? "red" : data.avg_cpu > 60 ? "orange" : "green"} />
        <MetricCard label="Avg Memory" value={`${data.avg_mem}%`} icon={HardDrive} color={data.avg_mem > 80 ? "red" : data.avg_mem > 60 ? "orange" : "green"} />
        <MetricCard label="Builders" value={String(data.builders)} icon={Zap} />
        <MetricCard label="Runners" value={String(data.runners)} icon={Play} />
        <MetricCard label="Queued" value={String(data.queued_builds)} icon={Clock} color={data.queued_builds > 3 ? "orange" : undefined} />
        <MetricCard label="Active Builds" value={String(data.active_builds)} icon={Activity} />
        <MetricCard label="Done (24h)" value={String(data.completed_builds_24h)} icon={CheckCircle} color="green" />
        <MetricCard label="Failed (24h)" value={String(data.failed_builds_24h)} icon={XCircle} color={data.failed_builds_24h > 0 ? "red" : undefined} />
      </div>

      {/* Recommendations */}
      {recs.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <h3 className="section-title">Scaling Recommendations</h3>
          {recs.map((r, i) => (
            <div key={i} className={`alert-card ${r.severity}`} style={{ marginBottom: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <TrendingUp className="h-4 w-4" />
                <div>
                  <div style={{ fontWeight: 500, fontSize: 13 }}>{r.reason}</div>
                  <div style={{ fontSize: 12, opacity: 0.7, marginTop: 2 }}>{r.action}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Alerts */}
      {data.alerts.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <h3 className="section-title">Active Alerts ({data.alerts.length})</h3>
          {data.alerts.slice(0, 5).map((a: any) => (
            <div key={a.id} className={`alert-card ${a.severity}`} style={{ marginBottom: 6 }}>
              <AlertTriangle className="h-3.5 w-3.5" />
              <span style={{ fontSize: 13 }}>{a.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════
   NODES
   ═══════════════════════════════════════ */
function NodesTab() {
  const [data, setData] = useState<OrchestratorOverview | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await getOrchestratorOverview());
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleDrain = async (node: PoolNode) => {
    try {
      await updatePoolNode(node.id, { status: "draining" });
      load();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleActivate = async (node: PoolNode) => {
    try {
      await updatePoolNode(node.id, { status: "active" });
      load();
    } catch (e: any) {
      alert(e.message);
    }
  };

  if (loading) return <div className="panel-loading">Loading nodes...</div>;
  if (!data) return <div className="panel-empty">No data</div>;

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 className="section-title" style={{ margin: 0 }}>Pool Nodes ({data.total_nodes})</h3>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="btn-sm" onClick={async () => { await rebalancePool(); load(); }}>
            <RefreshCw className="h-3 w-3" /> Rebalance
          </button>
          <button className="btn-sm" onClick={load}>
            <RefreshCw className="h-3 w-3" /> Refresh
          </button>
        </div>
      </div>

      <div className="table-wrapper">
        <table className="data-table">
          <thead>
            <tr>
              <th>Label</th>
              <th>Role</th>
              <th>Status</th>
              <th>IP</th>
              <th>CPU</th>
              <th>Mem</th>
              <th>Disk</th>
              <th>Builds</th>
              <th>Last HB</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.nodes.map((n) => (
              <tr key={n.id}>
                <td style={{ fontWeight: 500 }}>{n.label || n.id.slice(0, 12)}</td>
                <td><span className={`badge ${n.role}`}>{n.role}</span></td>
                <td><StatusBadge status={n.status} /></td>
                <td className="mono">{n.ip || "—"}</td>
                <td><PercentBar value={n.cpu_percent} /></td>
                <td><PercentBar value={n.mem_percent} /></td>
                <td><PercentBar value={n.disk_percent} /></td>
                <td>{n.active_builds}/{n.max_concurrent_builds}</td>
                <td className="muted">{n.last_heartbeat ? timeAgo(n.last_heartbeat) : "—"}</td>
                <td>
                  {n.status === "active" ? (
                    <button className="btn-sm danger" onClick={() => handleDrain(n)} title="Drain">
                      <Square className="h-3 w-3" />
                    </button>
                  ) : n.status === "draining" || n.status === "offline" ? (
                    <button className="btn-sm" onClick={() => handleActivate(n)} title="Activate">
                      <Play className="h-3 w-3" />
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════
   BUILDS
   ═══════════════════════════════════════ */
function BuildsTab() {
  const [builds, setBuilds] = useState<BuildJob[]>([]);
  const [filter, setFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setBuilds(await listBuilds(filter || undefined, undefined, 100));
    } catch {}
    setLoading(false);
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const handleCancel = async (id: string) => {
    try {
      await cancelBuild(id);
      load();
    } catch (e: any) {
      alert(e.message);
    }
  };

  if (loading) return <div className="panel-loading">Loading builds...</div>;

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        {["", "queued", "building", "done", "failed"].map((f) => (
          <button
            key={f}
            className={`btn-sm ${filter === f ? "active" : ""}`}
            onClick={() => setFilter(f)}
          >
            {f || "All"}
          </button>
        ))}
        <button className="btn-sm" onClick={load} style={{ marginLeft: "auto" }}>
          <RefreshCw className="h-3 w-3" />
        </button>
      </div>

      {builds.length === 0 ? (
        <div className="panel-empty">No builds found</div>
      ) : (
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Workspace</th>
                <th>Branch</th>
                <th>Status</th>
                <th>Node</th>
                <th>Queued</th>
                <th>Duration</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {builds.map((b) => (
                <tr key={b.id}>
                  <td className="mono">{b.id.slice(0, 16)}</td>
                  <td>{b.workspace}</td>
                  <td>{b.branch}</td>
                  <td><BuildStatusBadge status={b.status} /></td>
                  <td className="mono muted">{b.assigned_node_id?.slice(0, 12) || "—"}</td>
                  <td className="muted">{timeAgo(b.queued_at)}</td>
                  <td className="muted">{buildDuration(b)}</td>
                  <td>
                    {(b.status === "queued" || b.status === "assigned") && (
                      <button className="btn-sm danger" onClick={() => handleCancel(b.id)} title="Cancel">
                        <XCircle className="h-3 w-3" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════
   ALERTS
   ═══════════════════════════════════════ */
function AlertsTab() {
  const [alerts, setAlerts] = useState<ScaleAlert[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setAlerts(await getOrchestratorAlerts());
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleResolve = async (id: string) => {
    try {
      await resolveOrchestratorAlert(id);
      load();
    } catch (e: any) {
      alert(e.message);
    }
  };

  if (loading) return <div className="panel-loading">Loading alerts...</div>;

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 className="section-title" style={{ margin: 0 }}>Active Alerts ({alerts.length})</h3>
        <button className="btn-sm" onClick={load}><RefreshCw className="h-3 w-3" /> Refresh</button>
      </div>

      {alerts.length === 0 ? (
        <div className="panel-empty" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <CheckCircle className="h-4 w-4" style={{ color: "var(--success)" }} />
          No active alerts
        </div>
      ) : (
        alerts.map((a) => (
          <div key={a.id} className={`alert-card ${a.severity}`} style={{ marginBottom: 8, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <AlertTriangle className="h-4 w-4" />
              <div>
                <div style={{ fontWeight: 500, fontSize: 13 }}>{a.message}</div>
                <div style={{ fontSize: 11, opacity: 0.6 }}>
                  {a.alert_type} — {a.value.toFixed(1)}% (threshold: {a.threshold}%) — {timeAgo(a.created_at)}
                </div>
              </div>
            </div>
            <button className="btn-sm" onClick={() => handleResolve(a.id)}>
              <CheckCircle className="h-3 w-3" /> Resolve
            </button>
          </div>
        ))
      )}
    </div>
  );
}

/* ═══════════════════════════════════════
   HELPERS
   ═══════════════════════════════════════ */
function MetricCard({ label, value, icon: Icon, color }: { label: string; value: string; icon: React.ElementType; color?: string }) {
  return (
    <div className="metric-card">
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
        <Icon className="h-3.5 w-3.5" style={{ opacity: 0.5 }} />
        <span style={{ fontSize: 11, opacity: 0.6, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</span>
      </div>
      <div style={{ fontSize: 22, fontWeight: 600, color: color ? `var(--${color}, ${color})` : undefined }}>{value}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    active: "green", draining: "orange", offline: "red", maintenance: "yellow",
  };
  return <span className={`badge ${colors[status] || ""}`}>{status}</span>;
}

function BuildStatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    queued: "yellow", assigned: "blue", building: "blue", pushing: "blue", done: "green", failed: "red",
  };
  return <span className={`badge ${colors[status] || ""}`}>{status}</span>;
}

function PercentBar({ value }: { value: number }) {
  const color = value > 90 ? "var(--destructive, red)" : value > 70 ? "orange" : "var(--success, green)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 80 }}>
      <div style={{ flex: 1, height: 4, background: "var(--border)", borderRadius: 2, overflow: "hidden" }}>
        <div style={{ width: `${Math.min(100, value)}%`, height: "100%", background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontSize: 11, opacity: 0.7, minWidth: 32 }}>{value.toFixed(0)}%</span>
    </div>
  );
}



function buildDuration(b: BuildJob): string {
  if (!b.started_at) return "—";
  const end = b.finished_at ? new Date(b.finished_at).getTime() : Date.now();
  const secs = Math.floor((end - new Date(b.started_at).getTime()) / 1000);
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}
