"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  Network, Server, Route, RefreshCw, Plus,
  Trash2, CheckCircle, XCircle, AlertTriangle,
  Activity, BarChart3, Settings, Copy, ArrowDownUp,
} from "lucide-react";
import { timeAgo, formatNum } from "@/lib/format";
import {
  getLBOverview,
  listLBPools,
  createLBPool,
  deleteLBPool,
  addLBBackend,
  removeLBBackend,
  updateLBBackend,
  listLBRules,
  createLBRule,
  deleteLBRule,
  syncLBWithOrchestrator,
  drainLBInstance,
  getLBStats,
  getLBNginxConfig,
  type LBOverview,
  type LBPool,
  type LBBackend,
  type LBRule,
} from "@/lib/api/client";

type LBTab = "overview" | "pools" | "rules" | "nginx";

export function LoadBalancerPanel() {
  const [tab, setTab] = useState<LBTab>("overview");

  const tabs: { id: LBTab; label: string; icon: React.ElementType }[] = [
    { id: "overview", label: "Overview", icon: BarChart3 },
    { id: "pools", label: "Pools", icon: Network },
    { id: "rules", label: "Rules", icon: Route },
    { id: "nginx", label: "Nginx", icon: Settings },
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
      {tab === "pools" && <PoolsTab />}
      {tab === "rules" && <RulesTab />}
      {tab === "nginx" && <NginxTab />}
    </div>
  );
}

/* ═══════════════════════════════════════
   OVERVIEW
   ═══════════════════════════════════════ */
function OverviewTab() {
  const [data, setData] = useState<LBOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await getLBOverview());
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      const result = await syncLBWithOrchestrator();
      alert(`Sync complete: ${result.synced} added, ${result.removed} removed`);
      load();
    } catch (e: any) {
      alert(e.message);
    }
    setSyncing(false);
  };

  if (loading) return <div className="panel-loading">Loading load balancer...</div>;
  if (!data) return <div className="panel-empty">Failed to load LB data</div>;

  return (
    <div style={{ padding: 16 }}>
      {/* Actions */}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 6, marginBottom: 16 }}>
        <button className="btn-sm" onClick={handleSync} disabled={syncing}>
          <RefreshCw className={`h-3 w-3 ${syncing ? "spinning" : ""}`} />
          {syncing ? "Syncing..." : "Sync with Orchestrator"}
        </button>
        <button className="btn-sm" onClick={load}>
          <RefreshCw className="h-3 w-3" /> Refresh
        </button>
      </div>

      {/* Metrics */}
      <div className="metrics-grid">
        <MetricCard label="Pools" value={`${data.active_pools}/${data.total_pools}`} icon={Network} />
        <MetricCard label="Backends" value={String(data.total_backends)} icon={Server} />
        <MetricCard label="Healthy" value={String(data.healthy_backends)} icon={CheckCircle} color="green" />
        <MetricCard label="Unhealthy" value={String(data.unhealthy_backends)} icon={XCircle}
          color={data.unhealthy_backends > 0 ? "red" : undefined} />
        <MetricCard label="Rules" value={String(data.total_rules)} icon={Route} />
        <MetricCard label="Total Requests" value={formatNum(data.total_requests)} icon={Activity} />
      </div>

      {/* Pool summaries */}
      <h3 className="section-title" style={{ marginTop: 20 }}>Pools</h3>
      {data.pools.length === 0 ? (
        <div className="panel-empty">No pools configured. Create one or sync with orchestrator.</div>
      ) : (
        data.pools.map((pool) => (
          <PoolCard key={pool.id} pool={pool} onRefresh={load} />
        ))
      )}
    </div>
  );
}

function PoolCard({ pool, onRefresh }: { pool: LBPool; onRefresh: () => void }) {
  const healthy = pool.backends.filter((b) => b.status === "healthy").length;
  const total = pool.backends.length;

  return (
    <div className="card" style={{ marginBottom: 10, padding: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 14 }}>{pool.name}</div>
          <div style={{ fontSize: 12, opacity: 0.6, marginTop: 2 }}>
            {pool.algorithm} — {healthy}/{total} healthy — check: {pool.health_check_path} every {pool.health_check_interval}s
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className={`badge ${pool.active ? "green" : "red"}`}>
            {pool.active ? "active" : "inactive"}
          </span>
        </div>
      </div>

      {/* Backend list */}
      {pool.backends.length > 0 && (
        <div style={{ marginTop: 10, borderTop: "1px solid var(--border)", paddingTop: 8 }}>
          {pool.backends.map((b) => (
            <div key={b.id} style={{
              display: "flex", alignItems: "center", gap: 8,
              fontSize: 12, padding: "4px 0",
            }}>
              <span style={{
                width: 6, height: 6, borderRadius: "50%",
                background: b.status === "healthy" ? "var(--success, green)" :
                  b.status === "draining" ? "orange" : "var(--destructive, red)",
                flexShrink: 0,
              }} />
              <span className="mono" style={{ minWidth: 120 }}>{b.ip}:{b.port}</span>
              <span className="muted">w={b.weight}</span>
              <span className="muted">{b.active_connections} conn</span>
              <span className="muted">{formatNum(b.total_requests)} req</span>
              <span className="muted" style={{ marginLeft: "auto" }}>
                {b.last_health_check ? timeAgo(b.last_health_check) : "no check"}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════
   POOLS
   ═══════════════════════════════════════ */
function PoolsTab() {
  const [pools, setPools] = useState<LBPool[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newAlgo, setNewAlgo] = useState("round_robin");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setPools(await listLBPools());
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      await createLBPool({ name: newName.trim(), algorithm: newAlgo });
      setNewName("");
      setCreating(false);
      load();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this pool and all its backends?")) return;
    try {
      await deleteLBPool(id);
      load();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleDrain = async (instanceId: string) => {
    try {
      await drainLBInstance(instanceId);
      load();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleRemoveBackend = async (backendId: string) => {
    try {
      await removeLBBackend(backendId);
      load();
    } catch (e: any) {
      alert(e.message);
    }
  };

  if (loading) return <div className="panel-loading">Loading pools...</div>;

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 className="section-title" style={{ margin: 0 }}>LB Pools ({pools.length})</h3>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="btn-sm" onClick={() => setCreating(!creating)}>
            <Plus className="h-3 w-3" /> New Pool
          </button>
          <button className="btn-sm" onClick={load}><RefreshCw className="h-3 w-3" /></button>
        </div>
      </div>

      {creating && (
        <div className="card" style={{ padding: 12, marginBottom: 12, display: "flex", gap: 8, alignItems: "center" }}>
          <input
            className="input-sm"
            placeholder="Pool name..."
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            autoFocus
          />
          <select className="input-sm" value={newAlgo} onChange={(e) => setNewAlgo(e.target.value)}>
            <option value="round_robin">Round Robin</option>
            <option value="least_conn">Least Connections</option>
            <option value="weighted">Weighted</option>
            <option value="ip_hash">IP Hash</option>
            <option value="least_load">Least Load</option>
          </select>
          <button className="btn-sm" onClick={handleCreate}><CheckCircle className="h-3 w-3" /> Create</button>
        </div>
      )}

      {pools.map((pool) => (
        <div key={pool.id} className="card" style={{ marginBottom: 12, padding: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 14 }}>{pool.name}</div>
              <div style={{ fontSize: 11, opacity: 0.5, fontFamily: "monospace" }}>{pool.id}</div>
            </div>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <span className={`badge ${pool.active ? "green" : "red"}`}>{pool.algorithm}</span>
              <button className="btn-sm danger" onClick={() => handleDelete(pool.id)} title="Delete">
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          </div>

          {/* Config */}
          <div style={{ fontSize: 12, opacity: 0.6, marginTop: 6 }}>
            Health: {pool.health_check_path} every {pool.health_check_interval}s, timeout {pool.health_check_timeout}s, max fails: {pool.max_fails}
            {pool.sticky_sessions && ` — sticky (${pool.sticky_cookie})`}
          </div>

          {/* Backends */}
          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 6 }}>
              Backends ({pool.backends.length})
            </div>
            {pool.backends.length === 0 ? (
              <div style={{ fontSize: 12, opacity: 0.5 }}>No backends. Sync with orchestrator or add manually.</div>
            ) : (
              <div className="table-wrapper">
                <table className="data-table compact">
                  <thead>
                    <tr>
                      <th>Status</th>
                      <th>IP:Port</th>
                      <th>Weight</th>
                      <th>Connections</th>
                      <th>Requests</th>
                      <th>Health Fails</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {pool.backends.map((b) => (
                      <tr key={b.id}>
                        <td>
                          <span className={`badge ${b.status === "healthy" ? "green" : b.status === "draining" ? "yellow" : "red"}`}>
                            {b.status}
                          </span>
                        </td>
                        <td className="mono">{b.ip}:{b.port}</td>
                        <td>{b.weight}</td>
                        <td>{b.active_connections}</td>
                        <td>{formatNum(b.total_requests)}</td>
                        <td>{b.failed_health_checks}</td>
                        <td>
                          <div style={{ display: "flex", gap: 4 }}>
                            {b.status === "healthy" && (
                              <button className="btn-sm" onClick={() => handleDrain(b.instance_id)} title="Drain">
                                <ArrowDownUp className="h-3 w-3" />
                              </button>
                            )}
                            <button className="btn-sm danger" onClick={() => handleRemoveBackend(b.id)} title="Remove">
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ═══════════════════════════════════════
   RULES
   ═══════════════════════════════════════ */
function RulesTab() {
  const [rules, setRules] = useState<LBRule[]>([]);
  const [pools, setPools] = useState<LBPool[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newPoolId, setNewPoolId] = useState("");
  const [newType, setNewType] = useState("prefix");
  const [newValue, setNewValue] = useState("/");
  const [newPriority, setNewPriority] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, p] = await Promise.all([listLBRules(), listLBPools()]);
      setRules(r);
      setPools(p);
      if (p.length > 0 && !newPoolId) setNewPoolId(p[0].id);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [newPoolId]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!newPoolId || !newValue.trim()) return;
    try {
      await createLBRule({
        pool_id: newPoolId,
        match_type: newType,
        match_value: newValue.trim(),
        priority: newPriority,
      });
      setCreating(false);
      load();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteLBRule(id);
      load();
    } catch (e: any) {
      alert(e.message);
    }
  };

  if (loading) return <div className="panel-loading">Loading rules...</div>;

  const poolName = (id: string) => pools.find((p) => p.id === id)?.name || id.slice(0, 16);

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 className="section-title" style={{ margin: 0 }}>Routing Rules ({rules.length})</h3>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="btn-sm" onClick={() => setCreating(!creating)}>
            <Plus className="h-3 w-3" /> New Rule
          </button>
          <button className="btn-sm" onClick={load}><RefreshCw className="h-3 w-3" /></button>
        </div>
      </div>

      {creating && (
        <div className="card" style={{ padding: 12, marginBottom: 12 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <select className="input-sm" value={newType} onChange={(e) => setNewType(e.target.value)}>
              <option value="prefix">Prefix</option>
              <option value="exact">Exact</option>
              <option value="host">Host</option>
            </select>
            <input
              className="input-sm"
              placeholder={newType === "host" ? "app.nso.dev" : "/api/"}
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              style={{ minWidth: 150 }}
            />
            <span style={{ fontSize: 12, opacity: 0.5 }}>&rarr;</span>
            <select className="input-sm" value={newPoolId} onChange={(e) => setNewPoolId(e.target.value)}>
              {pools.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <input
              className="input-sm"
              type="number"
              placeholder="Priority"
              value={newPriority}
              onChange={(e) => setNewPriority(parseInt(e.target.value) || 0)}
              style={{ width: 70 }}
            />
            <button className="btn-sm" onClick={handleCreate}><CheckCircle className="h-3 w-3" /> Create</button>
          </div>
        </div>
      )}

      {rules.length === 0 ? (
        <div className="panel-empty">No routing rules. Create one to start routing traffic.</div>
      ) : (
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Priority</th>
                <th>Match</th>
                <th>Value</th>
                <th>Pool</th>
                <th>Active</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id}>
                  <td style={{ fontWeight: 600 }}>{r.priority}</td>
                  <td><span className="badge">{r.match_type}</span></td>
                  <td className="mono">{r.match_value}</td>
                  <td>{poolName(r.pool_id)}</td>
                  <td>
                    <span className={`badge ${r.active ? "green" : "red"}`}>
                      {r.active ? "yes" : "no"}
                    </span>
                  </td>
                  <td>
                    <button className="btn-sm danger" onClick={() => handleDelete(r.id)} title="Delete">
                      <Trash2 className="h-3 w-3" />
                    </button>
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
   NGINX CONFIG
   ═══════════════════════════════════════ */
function NginxTab() {
  const [config, setConfig] = useState("");
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setConfig(await getLBNginxConfig());
    } catch (e: any) {
      setConfig(`# Error loading config: ${e.message}`);
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCopy = () => {
    navigator.clipboard.writeText(config);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) return <div className="panel-loading">Generating nginx config...</div>;

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 className="section-title" style={{ margin: 0 }}>Generated Nginx Config</h3>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="btn-sm" onClick={handleCopy}>
            <Copy className="h-3 w-3" /> {copied ? "Copied!" : "Copy"}
          </button>
          <button className="btn-sm" onClick={load}>
            <RefreshCw className="h-3 w-3" /> Regenerate
          </button>
        </div>
      </div>

      <pre style={{
        background: "var(--sidebar-background)",
        border: "1px solid var(--border)",
        borderRadius: 6,
        padding: 16,
        fontSize: 12,
        lineHeight: 1.5,
        overflow: "auto",
        maxHeight: "calc(100vh - 250px)",
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
        whiteSpace: "pre-wrap",
      }}>
        {config}
      </pre>
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

