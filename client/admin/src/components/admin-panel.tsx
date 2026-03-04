"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  Users, TrendingUp, Shield, Search, ChevronRight,
  RefreshCw, AlertTriangle, CheckCircle, Key, Eye,
  XCircle, BarChart3, Activity, Link2, ArrowDownUp,
  Server, Cpu, HardDrive, Clock, Play, Square,
  Zap, Network, Plus, Trash2, Copy, Route,
  FolderOpen, ChevronDown,
} from "lucide-react";
import {
  getAdminOverview,
  adminListUsers,
  adminGetUser,
  adminUpdateUser,
  adminResetPassword,
  adminDisableUser,
  adminGetUserActivity,
  getRevenueAnalytics,
  getGrowthAnalytics,
  getCashflowAnalytics,
  runFraudScan,
  getLedgerStats,
  getUserLedger,
  verifyUserChain,
  getBalanceProof,
  adminListProjects,
  adminListProjectWorkspaces,
  adminListAllWorkspaces,
  adminListAllInstances,
  getOrchestratorOverview,
  updatePoolNode,
  listBuilds,
  cancelBuild,
  getScalingRecommendations,
  getOrchestratorAlerts,
  resolveOrchestratorAlert,
  rebalancePool,
  getLBOverview,
  listLBPools,
  createLBPool,
  deleteLBPool,
  removeLBBackend,
  listLBRules,
  createLBRule,
  deleteLBRule,
  syncLBWithOrchestrator,
  drainLBInstance,
  getLBNginxConfig,
  type AdminUser,
  type DashboardOverview,
  type RevenueSummary,
  type GrowthSummary,
  type CashflowResult,
  type CashflowPeriod,
  type FraudScanResult,
  type LedgerBlock,
  type ActivityEntry,
  type AdminProject,
  type AdminWorkspace,
  type AdminInstance,
  type OrchestratorOverview,
  type PoolNode,
  type BuildJob,
  type LBOverview,
  type LBPool,
  type LBBackend,
  type LBRule,
} from "@/lib/api/client";

type AdminTab = "overview" | "users" | "cashflow" | "analytics" | "fraud" | "ledger" | "projects" | "orchestrator" | "loadbalancer";

export function AdminPanel({ tab = "overview" }: { tab?: AdminTab }) {
  return (
    <div>
      {tab === "overview" && <OverviewTab />}
      {tab === "users" && <UsersTab />}
      {tab === "projects" && <ProjectsTab />}
      {tab === "orchestrator" && <OrchestratorTab />}
      {tab === "loadbalancer" && <LoadBalancerTab />}
      {tab === "cashflow" && <CashflowTab />}
      {tab === "analytics" && <AnalyticsTab />}
      {tab === "fraud" && <FraudTab />}
      {tab === "ledger" && <LedgerTab />}
    </div>
  );
}

/* ═══════════════════════════════════════
   OVERVIEW TAB
   ═══════════════════════════════════════ */
function OverviewTab() {
  const [data, setData] = useState<DashboardOverview | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getAdminOverview().then(setData).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="admin-loading"><div className="term-spinner" /> Loading...</div>;
  if (!data) return <div className="admin-empty">Could not load overview</div>;

  const fmt = (cents: number) => `$${(cents / 100).toFixed(2)}`;

  return (
    <div className="admin-overview">
      <div className="admin-cards-grid">
        <div className="admin-card">
          <div className="admin-card-label">Total Users</div>
          <div className="admin-card-value">{data.users.total}</div>
          <div className="admin-card-sub">+{data.users.new_7d} this week</div>
        </div>
        <div className="admin-card">
          <div className="admin-card-label">Daily Active</div>
          <div className="admin-card-value">{data.users.dau}</div>
          <div className="admin-card-sub">Last 24 hours</div>
        </div>
        <div className="admin-card">
          <div className="admin-card-label">MRR</div>
          <div className="admin-card-value">{fmt(data.revenue.mrr_cents)}</div>
          <div className="admin-card-sub">Last 30 days</div>
        </div>
        <div className="admin-card">
          <div className="admin-card-label">Total Revenue</div>
          <div className="admin-card-value">{fmt(data.revenue.total_cents)}</div>
          <div className="admin-card-sub">All time</div>
        </div>
        <div className="admin-card">
          <div className="admin-card-label">Active Subs</div>
          <div className="admin-card-value">{data.subscriptions.active}</div>
          <div className="admin-card-sub">
            {Object.entries(data.subscriptions.plan_distribution).map(([p, c]) => (
              <span key={p} style={{ marginRight: 8 }}>{p}: {c}</span>
            ))}
          </div>
        </div>
        <div className="admin-card">
          <div className="admin-card-label">Infrastructure</div>
          <div className="admin-card-value">{data.infrastructure.active_instances}</div>
          <div className="admin-card-sub">{data.infrastructure.total_projects} projects</div>
        </div>
      </div>

      <div className="admin-fraud-banner" data-status={data.fraud_status}>
        {data.fraud_status === "clean" ? (
          <><CheckCircle className="h-4 w-4" /> All checks passed — no issues detected</>
        ) : data.fraud_status === "issues_found" ? (
          <><AlertTriangle className="h-4 w-4" /> Issues detected — review the Fraud tab</>
        ) : (
          <><Shield className="h-4 w-4" /> Fraud status: {data.fraud_status}</>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════
   CASHFLOW TAB
   ═══════════════════════════════════════ */
function CashflowTab() {
  const [data, setData] = useState<CashflowResult | null>(null);
  const [granularity, setGranularity] = useState<string>("month");
  const [periods, setPeriods] = useState(12);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    getCashflowAnalytics(granularity, periods)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [granularity, periods]);

  useEffect(() => { load(); }, [load]);

  const fmt = (cents: number) => {
    const sign = cents < 0 ? "-" : "";
    return `${sign}$${(Math.abs(cents) / 100).toFixed(2)}`;
  };

  const granOpts: { id: string; label: string; defaultPeriods: number }[] = [
    { id: "day", label: "Daily", defaultPeriods: 30 },
    { id: "week", label: "Weekly", defaultPeriods: 12 },
    { id: "month", label: "Monthly", defaultPeriods: 12 },
    { id: "year", label: "Yearly", defaultPeriods: 5 },
  ];

  if (loading) return <div className="admin-loading"><div className="term-spinner" /> Loading cashflow...</div>;

  return (
    <div className="admin-cashflow">
      <div className="admin-period-row">
        <span className="admin-section-label">View by</span>
        {granOpts.map((g) => (
          <button
            key={g.id}
            className={`admin-period-btn ${granularity === g.id ? "active" : ""}`}
            onClick={() => { setGranularity(g.id); setPeriods(g.defaultPeriods); }}
          >
            {g.label}
          </button>
        ))}
      </div>

      {data && (
        <>
          <div className="admin-cards-grid sm">
            <div className="admin-card sm">
              <div className="admin-card-label">Total Inflow</div>
              <div className="admin-card-value teal">{fmt(data.totals.inflow_cents)}</div>
            </div>
            <div className="admin-card sm">
              <div className="admin-card-label">Total Outflow</div>
              <div className="admin-card-value red">{fmt(data.totals.outflow_cents)}</div>
            </div>
            <div className="admin-card sm">
              <div className="admin-card-label">Net</div>
              <div className={`admin-card-value ${data.totals.net_cents >= 0 ? "teal" : "red"}`}>
                {fmt(data.totals.net_cents)}
              </div>
            </div>
            <div className="admin-card sm">
              <div className="admin-card-label">From Invoices</div>
              <div className="admin-card-value">{fmt(data.totals.by_source.invoices_cents)}</div>
            </div>
            <div className="admin-card sm">
              <div className="admin-card-label">From Top-ups</div>
              <div className="admin-card-value">{fmt(data.totals.by_source.topups_cents)}</div>
            </div>
            <div className="admin-card sm">
              <div className="admin-card-label">Refunds</div>
              <div className="admin-card-value red">{fmt(data.totals.by_source.refunds_cents)}</div>
            </div>
          </div>

          {data.timeline.length > 0 && (
            <div className="cf-chart">
              <div className="admin-subsection-title">Inflow vs Outflow</div>
              <div className="cf-bars">
                {data.timeline.map((p) => {
                  const maxVal = Math.max(
                    ...data.timeline.map((x) => Math.max(x.inflow_cents, x.outflow_cents)),
                    1,
                  );
                  const inPct = (p.inflow_cents / maxVal) * 100;
                  const outPct = (p.outflow_cents / maxVal) * 100;
                  return (
                    <div
                      key={p.period}
                      className={`cf-bar-col ${expanded === p.period ? "expanded" : ""}`}
                      onClick={() => setExpanded(expanded === p.period ? null : p.period)}
                      title={`${p.period}: In ${fmt(p.inflow_cents)} / Out ${fmt(p.outflow_cents)}`}
                    >
                      <div className="cf-bar-pair">
                        <div className="cf-bar in" style={{ height: `${Math.max(inPct, 2)}%` }} />
                        <div className="cf-bar out" style={{ height: `${Math.max(outPct, 2)}%` }} />
                      </div>
                      <div className="cf-bar-label">{p.period.length > 7 ? p.period.slice(5) : p.period}</div>
                    </div>
                  );
                })}
              </div>
              <div className="cf-legend">
                <span className="cf-legend-item"><span className="cf-dot in" /> Inflow</span>
                <span className="cf-legend-item"><span className="cf-dot out" /> Outflow</span>
              </div>
            </div>
          )}

          {expanded && (() => {
            const p = data.timeline.find((x) => x.period === expanded);
            if (!p) return null;
            return (
              <div className="cf-detail">
                <div className="cf-detail-title">
                  {expanded}
                  <span className={`cf-net ${p.net_cents >= 0 ? "positive" : "negative"}`}>
                    Net: {fmt(p.net_cents)}
                  </span>
                </div>
                <div className="cf-detail-grid">
                  <div className="cf-detail-col">
                    <div className="cf-detail-heading teal">Inflow — {fmt(p.inflow_cents)}</div>
                    <div className="cf-detail-row">
                      <span>Invoices</span>
                      <span className="admin-mono">{fmt(p.breakdown.invoices.cents)}</span>
                      <span className="admin-muted">{p.breakdown.invoices.count}x</span>
                    </div>
                    <div className="cf-detail-row">
                      <span>Wallet top-ups</span>
                      <span className="admin-mono">{fmt(p.breakdown.topups.cents)}</span>
                      <span className="admin-muted">{p.breakdown.topups.count}x</span>
                    </div>
                    <div className="cf-detail-row">
                      <span>Ledger inflow</span>
                      <span className="admin-mono">{fmt(p.breakdown.ledger_in.cents)}</span>
                      <span className="admin-muted">{p.breakdown.ledger_in.count}x</span>
                    </div>
                  </div>
                  <div className="cf-detail-col">
                    <div className="cf-detail-heading red">Outflow — {fmt(p.outflow_cents)}</div>
                    <div className="cf-detail-row">
                      <span>Refunds</span>
                      <span className="admin-mono">{fmt(p.breakdown.refunds.cents)}</span>
                      <span className="admin-muted">{p.breakdown.refunds.count}x</span>
                    </div>
                    <div className="cf-detail-row">
                      <span>Wallet debits</span>
                      <span className="admin-mono">{fmt(p.breakdown.wallet_debits.cents)}</span>
                      <span className="admin-muted">{p.breakdown.wallet_debits.count}x</span>
                    </div>
                    <div className="cf-detail-row">
                      <span>Ledger outflow</span>
                      <span className="admin-mono">{fmt(p.breakdown.ledger_out.cents)}</span>
                      <span className="admin-muted">{p.breakdown.ledger_out.count}x</span>
                    </div>
                  </div>
                </div>
                <div className="cf-detail-meta">
                  <span>Signups: {p.signups}</span>
                  <span>Subs created: {p.subs_created}</span>
                  <span>Subs cancelled: {p.subs_cancelled}</span>
                </div>
              </div>
            );
          })()}

          <div className="cf-table">
            <div className="admin-subsection-title" style={{ marginTop: 16 }}>Timeline Detail</div>
            <div className="admin-table">
              <div className="admin-thead">
                <div className="admin-th" style={{ flex: 1.2 }}>Period</div>
                <div className="admin-th">Inflow</div>
                <div className="admin-th">Outflow</div>
                <div className="admin-th">Net</div>
                <div className="admin-th">Signups</div>
                <div className="admin-th">+Subs</div>
                <div className="admin-th">-Subs</div>
              </div>
              {data.timeline.map((p) => (
                <div
                  key={p.period}
                  className={`admin-trow ${expanded === p.period ? "active-row" : ""}`}
                  onClick={() => setExpanded(expanded === p.period ? null : p.period)}
                >
                  <div className="admin-tcell admin-mono" style={{ flex: 1.2, fontWeight: 600 }}>{p.period}</div>
                  <div className="admin-tcell admin-mono" style={{ color: "var(--color-teal)" }}>{fmt(p.inflow_cents)}</div>
                  <div className="admin-tcell admin-mono" style={{ color: "var(--color-red)" }}>{fmt(p.outflow_cents)}</div>
                  <div className="admin-tcell admin-mono" style={{ fontWeight: 600, color: p.net_cents >= 0 ? "var(--color-teal)" : "var(--color-red)" }}>
                    {fmt(p.net_cents)}
                  </div>
                  <div className="admin-tcell">{p.signups}</div>
                  <div className="admin-tcell">{p.subs_created}</div>
                  <div className="admin-tcell">{p.subs_cancelled}</div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════
   USERS TAB
   ═══════════════════════════════════════ */
function UsersTab() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<AdminUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const load = useCallback(() => {
    setLoading(true);
    adminListUsers({ search, limit: pageSize, offset: page * pageSize })
      .then((r) => { setUsers(r.users); setTotal(r.total); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [search, page]);

  useEffect(() => { load(); }, [load]);

  if (selected) {
    return <UserDetail user={selected} onBack={() => { setSelected(null); load(); }} />;
  }

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div>
      <div className="admin-search-row">
        <div className="admin-search-wrap">
          <Search className="h-3.5 w-3.5" />
          <input
            className="admin-search-input"
            placeholder="Search by email, name, or ID..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0); }}
          />
        </div>
        <div className="admin-count">{total} users</div>
      </div>

      {loading ? (
        <div className="admin-loading"><div className="term-spinner" /> Loading...</div>
      ) : (
        <>
          <div className="admin-table">
            <div className="admin-thead">
              <div className="admin-th" style={{ flex: 2 }}>User</div>
              <div className="admin-th">Role</div>
              <div className="admin-th">Balance</div>
              <div className="admin-th">Last Active</div>
              <div className="admin-th">Joined</div>
              <div className="admin-th" style={{ flex: 0.5 }}></div>
            </div>
            {users.map((u) => (
              <div key={u.id} className="admin-trow" onClick={() => {
                adminGetUser(u.id).then((r) => setSelected(r.user)).catch(() => setSelected(u));
              }}>
                <div className="admin-tcell" style={{ flex: 2 }}>
                  <div>
                    <div className="admin-user-name">{u.name || u.email.split("@")[0]}</div>
                    <div className="admin-user-email">{u.email}</div>
                  </div>
                </div>
                <div className="admin-tcell">
                  <span className={`admin-role-badge ${u.role}`}>{u.role}</span>
                </div>
                <div className="admin-tcell admin-mono">${u.balance.toFixed(2)}</div>
                <div className="admin-tcell admin-muted">
                  {u.last_active ? new Date(u.last_active).toLocaleDateString() : "Never"}
                </div>
                <div className="admin-tcell admin-muted">
                  {new Date(u.created_at).toLocaleDateString()}
                </div>
                <div className="admin-tcell" style={{ flex: 0.5 }}>
                  <ChevronRight className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)" }} />
                </div>
              </div>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="admin-pagination">
              <button disabled={page === 0} onClick={() => setPage(page - 1)} className="panel-btn-sm">Prev</button>
              <span className="admin-page-info">Page {page + 1} of {totalPages}</span>
              <button disabled={page >= totalPages - 1} onClick={() => setPage(page + 1)} className="panel-btn-sm">Next</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════
   USER DETAIL VIEW
   ═══════════════════════════════════════ */
function UserDetail({ user, onBack }: { user: AdminUser; onBack: () => void }) {
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [showResetPw, setShowResetPw] = useState(false);
  const [newPw, setNewPw] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    adminGetUserActivity(user.id, 30).then((r) => setActivity(r.activity)).catch(() => {});
  }, [user.id]);

  const handleResetPw = async () => {
    if (newPw.length < 6) { setErr("Min 6 characters"); return; }
    try {
      await adminResetPassword(user.id, newPw);
      setMsg("Password reset successfully");
      setShowResetPw(false);
      setNewPw("");
      setErr("");
    } catch (e: any) { setErr(e.message); }
  };

  const handleDisable = async () => {
    try {
      await adminDisableUser(user.id);
      setMsg("User disabled");
    } catch (e: any) { setErr(e.message); }
  };

  const fmt = (cents: number) => `$${(cents / 100).toFixed(2)}`;

  return (
    <div>
      <button className="panel-btn-sm" onClick={onBack} style={{ marginBottom: 12 }}>
        &larr; Back to users
      </button>

      {msg && <div className="admin-success">{msg}</div>}
      {err && <div className="admin-error">{err}</div>}

      <div className="admin-detail-header">
        <div className="admin-detail-avatar">{(user.name || user.email)[0].toUpperCase()}</div>
        <div>
          <div className="admin-detail-name">{user.name}</div>
          <div className="admin-detail-email">{user.email}</div>
          <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
            <span className={`admin-role-badge ${user.role}`}>{user.role}</span>
            {user.verified && <span className="admin-role-badge verified">Verified</span>}
            {user.subdomain && <span className="admin-role-badge subdomain">{user.subdomain}.nso.dev</span>}
          </div>
        </div>
      </div>

      <div className="admin-detail-cards">
        <div className="admin-card sm">
          <div className="admin-card-label">Balance</div>
          <div className="admin-card-value">${user.balance.toFixed(2)}</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Wallet</div>
          <div className="admin-card-value">{fmt(user.wallet_balance_cents || 0)}</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Total Paid</div>
          <div className="admin-card-value">{fmt(user.total_paid_cents || 0)}</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Invoices</div>
          <div className="admin-card-value">{user.invoice_count || 0}</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Projects</div>
          <div className="admin-card-value">{user.project_count || 0}</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Plan</div>
          <div className="admin-card-value" style={{ fontSize: 14 }}>
            {user.subscription?.plan_code || "none"}
          </div>
        </div>
      </div>

      <div className="admin-detail-section">
        <div className="admin-detail-section-title">Actions</div>
        <div className="admin-detail-actions">
          <button className="panel-btn-sm" onClick={() => setShowResetPw(!showResetPw)}>
            <Key className="h-3 w-3" /> Reset Password
          </button>
          <button className="panel-btn-sm" onClick={handleDisable} style={{ color: "var(--color-red)" }}>
            <XCircle className="h-3 w-3" /> Disable Account
          </button>
        </div>
        {showResetPw && (
          <div className="admin-reset-form">
            <input
              className="settings-input"
              type="password"
              placeholder="New password (min 6 chars)"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
            />
            <button className="panel-btn" onClick={handleResetPw}>Set Password</button>
          </div>
        )}
      </div>

      <div className="admin-detail-section">
        <div className="admin-detail-section-title">
          <Activity className="h-3.5 w-3.5" /> Recent Activity
        </div>
        {activity.length === 0 ? (
          <div className="admin-muted" style={{ fontSize: 12 }}>No activity recorded</div>
        ) : (
          <div className="admin-activity-list">
            {activity.map((a) => (
              <div key={a.id} className="admin-activity-row">
                <div className="admin-activity-action">{a.action}</div>
                <div className="admin-activity-resource">
                  {a.resource_type && `${a.resource_type}`}
                  {a.resource_id && ` · ${a.resource_id.slice(0, 16)}`}
                </div>
                <div className="admin-activity-ip">{a.ip}</div>
                <div className="admin-activity-date">
                  {new Date(a.created_at).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="admin-detail-section">
        <div className="admin-detail-section-title">Info</div>
        <div className="admin-info-grid">
          <div className="admin-info-row">
            <span className="admin-info-label">User ID</span>
            <span className="admin-mono" style={{ fontSize: 11 }}>{user.id}</span>
          </div>
          <div className="admin-info-row">
            <span className="admin-info-label">Created</span>
            <span>{new Date(user.created_at).toLocaleString()}</span>
          </div>
          <div className="admin-info-row">
            <span className="admin-info-label">Last Active</span>
            <span>{user.last_active ? new Date(user.last_active).toLocaleString() : "Never"}</span>
          </div>
          <div className="admin-info-row">
            <span className="admin-info-label">Activity Events</span>
            <span>{user.activity_count || 0}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════
   ANALYTICS TAB
   ═══════════════════════════════════════ */
function AnalyticsTab() {
  const [revenue, setRevenue] = useState<RevenueSummary | null>(null);
  const [growth, setGrowth] = useState<GrowthSummary | null>(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      getRevenueAnalytics(days),
      getGrowthAnalytics(days),
    ]).then(([r, g]) => { setRevenue(r); setGrowth(g); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [days]);

  useEffect(() => { load(); }, [load]);

  const fmt = (cents: number) => `$${(cents / 100).toFixed(2)}`;

  if (loading) return <div className="admin-loading"><div className="term-spinner" /> Loading analytics...</div>;

  return (
    <div className="admin-analytics">
      <div className="admin-period-row">
        <span className="admin-section-label">Period</span>
        {[7, 30, 90].map((d) => (
          <button key={d} className={`admin-period-btn ${days === d ? "active" : ""}`} onClick={() => setDays(d)}>
            {d}d
          </button>
        ))}
      </div>

      {revenue && (
        <div className="admin-section">
          <div className="admin-section-title">Revenue</div>
          <div className="admin-cards-grid sm">
            <div className="admin-card sm">
              <div className="admin-card-label">Net Revenue</div>
              <div className="admin-card-value teal">{fmt(revenue.net_revenue_cents)}</div>
            </div>
            <div className="admin-card sm">
              <div className="admin-card-label">Paid Invoices</div>
              <div className="admin-card-value">{revenue.paid_invoices}</div>
            </div>
            <div className="admin-card sm">
              <div className="admin-card-label">Refunds</div>
              <div className="admin-card-value red">{fmt(revenue.refund_cents)}</div>
              <div className="admin-card-sub">{revenue.refund_count} refunds</div>
            </div>
            <div className="admin-card sm">
              <div className="admin-card-label">Wallet Top-ups</div>
              <div className="admin-card-value">{fmt(revenue.wallet_topups_cents)}</div>
            </div>
          </div>

          {Object.keys(revenue.by_plan).length > 0 && (
            <div className="admin-plan-breakdown">
              <div className="admin-subsection-title">Revenue by Plan</div>
              {Object.entries(revenue.by_plan).map(([plan, data]) => (
                <div key={plan} className="admin-plan-row">
                  <span className="admin-plan-name">{plan}</span>
                  <span className="admin-plan-count">{data.count} invoices</span>
                  <span className="admin-mono">{fmt(data.revenue_cents)}</span>
                </div>
              ))}
            </div>
          )}

          {revenue.daily_trend.length > 0 && (
            <div className="admin-trend">
              <div className="admin-subsection-title">Daily Revenue</div>
              <div className="admin-trend-bars">
                {revenue.daily_trend.map((d) => {
                  const max = Math.max(...revenue.daily_trend.map((x) => x.revenue_cents), 1);
                  const pct = (d.revenue_cents / max) * 100;
                  return (
                    <div key={d.date} className="admin-trend-bar-wrap" title={`${d.date}: ${fmt(d.revenue_cents)}`}>
                      <div className="admin-trend-bar" style={{ height: `${Math.max(pct, 2)}%` }} />
                      <div className="admin-trend-label">{d.date.slice(5)}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {growth && (
        <div className="admin-section">
          <div className="admin-section-title">Growth</div>
          <div className="admin-cards-grid sm">
            <div className="admin-card sm">
              <div className="admin-card-label">Total Users</div>
              <div className="admin-card-value">{growth.total_users}</div>
            </div>
            <div className="admin-card sm">
              <div className="admin-card-label">New Users</div>
              <div className="admin-card-value teal">+{growth.new_users}</div>
            </div>
            <div className="admin-card sm">
              <div className="admin-card-label">Active Users</div>
              <div className="admin-card-value">{growth.active_users}</div>
            </div>
            <div className="admin-card sm">
              <div className="admin-card-label">Churn Rate</div>
              <div className={`admin-card-value ${growth.churn_rate > 5 ? "red" : ""}`}>
                {growth.churn_rate}%
              </div>
              <div className="admin-card-sub">{growth.churned_users} churned</div>
            </div>
          </div>

          {Object.keys(growth.plan_distribution).length > 0 && (
            <div className="admin-plan-breakdown">
              <div className="admin-subsection-title">Active Subscriptions</div>
              {Object.entries(growth.plan_distribution).map(([plan, count]) => (
                <div key={plan} className="admin-plan-row">
                  <span className="admin-plan-name">{plan}</span>
                  <span className="admin-mono">{count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════
   FRAUD TAB
   ═══════════════════════════════════════ */
function FraudTab() {
  const [result, setResult] = useState<FraudScanResult | null>(null);
  const [loading, setLoading] = useState(false);

  const scan = () => {
    setLoading(true);
    runFraudScan().then(setResult).catch(() => {}).finally(() => setLoading(false));
  };

  return (
    <div>
      <div className="admin-fraud-header">
        <button className="panel-btn" onClick={scan} disabled={loading}>
          {loading ? <><div className="term-spinner" /> Scanning...</> : <><Shield className="h-3.5 w-3.5" /> Run Fraud Scan</>}
        </button>
      </div>

      {result && (
        <div className="admin-fraud-results">
          <div className={`admin-fraud-status ${result.status}`}>
            {result.status === "clean" ? (
              <><CheckCircle className="h-4 w-4" /> All checks passed — 0 issues</>
            ) : (
              <><AlertTriangle className="h-4 w-4" /> {result.total_issues} issue(s) found</>
            )}
            <span className="admin-muted" style={{ marginLeft: "auto" }}>
              {new Date(result.scan_time).toLocaleString()}
            </span>
          </div>

          {result.balance_discrepancies.length > 0 && (
            <div className="admin-fraud-section">
              <div className="admin-fraud-section-title">
                <AlertTriangle className="h-3.5 w-3.5" /> Balance Discrepancies ({result.balance_discrepancies.length})
              </div>
              {result.balance_discrepancies.map((d: any, i: number) => (
                <div key={i} className="admin-fraud-item">
                  <span className="admin-mono">{d.user_id?.slice(0, 16)}</span>
                  <span>Chain: ${(d.chain_balance_cents / 100).toFixed(2)}</span>
                  <span>Recorded: ${(d.total_recorded_cents / 100).toFixed(2)}</span>
                  <span className="admin-fraud-diff">
                    Diff: ${(d.discrepancy_cents / 100).toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {result.chain_violations.length > 0 && (
            <div className="admin-fraud-section">
              <div className="admin-fraud-section-title">
                <XCircle className="h-3.5 w-3.5" /> Chain Integrity Violations ({result.chain_violations.length})
              </div>
              {result.chain_violations.map((v: any, i: number) => (
                <div key={i} className="admin-fraud-item">
                  <span className="admin-mono">{v.user_id?.slice(0, 16)}</span>
                  <span>{v.errors?.length} error(s) in {v.chain_length} blocks</span>
                </div>
              ))}
            </div>
          )}

          {result.suspicious_accounts.length > 0 && (
            <div className="admin-fraud-section">
              <div className="admin-fraud-section-title">
                <Eye className="h-3.5 w-3.5" /> Suspicious Accounts ({result.suspicious_accounts.length})
              </div>
              {result.suspicious_accounts.map((s: any, i: number) => (
                <div key={i} className="admin-fraud-item">
                  <span>{s.email}</span>
                  <span className="admin-mono">${s.balance?.toFixed(2)}</span>
                  <span className="admin-muted">{s.reason}</span>
                </div>
              ))}
            </div>
          )}

          {result.anomalies.length > 0 && (
            <div className="admin-fraud-section">
              <div className="admin-fraud-section-title">
                <Activity className="h-3.5 w-3.5" /> Anomalies ({result.anomalies.length})
              </div>
              {result.anomalies.map((a: any, i: number) => (
                <div key={i} className="admin-fraud-item">
                  <span className="admin-mono">{a.user_id?.slice(0, 16)}</span>
                  <span className="admin-muted">{a.reason}</span>
                  <span>{a.period}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════
   LEDGER TAB
   ═══════════════════════════════════════ */
function LedgerTab() {
  const [stats, setStats] = useState<any>(null);
  const [userId, setUserId] = useState("");
  const [chain, setChain] = useState<LedgerBlock[]>([]);
  const [chainTotal, setChainTotal] = useState(0);
  const [verification, setVerification] = useState<any>(null);
  const [proof, setProof] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getLedgerStats().then(setStats).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const loadChain = () => {
    if (!userId.trim()) return;
    getUserLedger(userId.trim()).then((r) => {
      setChain(r.blocks);
      setChainTotal(r.total);
      setVerification(null);
      setProof(null);
    }).catch(() => {});
  };

  const verify = () => {
    if (!userId.trim()) return;
    verifyUserChain(userId.trim()).then(setVerification).catch(() => {});
  };

  const loadProof = () => {
    if (!userId.trim()) return;
    getBalanceProof(userId.trim()).then(setProof).catch(() => {});
  };

  const fmt = (cents: number) => `$${(cents / 100).toFixed(2)}`;

  if (loading) return <div className="admin-loading"><div className="term-spinner" /> Loading...</div>;

  return (
    <div>
      {stats && (
        <div className="admin-cards-grid sm">
          <div className="admin-card sm">
            <div className="admin-card-label">Total Blocks</div>
            <div className="admin-card-value">{stats.total_blocks}</div>
          </div>
          <div className="admin-card sm">
            <div className="admin-card-label">Users Tracked</div>
            <div className="admin-card-value">{stats.total_users}</div>
          </div>
          <div className="admin-card sm">
            <div className="admin-card-label">Total Inflow</div>
            <div className="admin-card-value teal">{fmt(stats.total_inflow_cents)}</div>
          </div>
          <div className="admin-card sm">
            <div className="admin-card-label">Total Outflow</div>
            <div className="admin-card-value red">{fmt(Math.abs(stats.total_outflow_cents))}</div>
          </div>
        </div>
      )}

      <div className="admin-ledger-search">
        <input
          className="admin-search-input"
          placeholder="Enter user ID (e.g. user_abc123)"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && loadChain()}
        />
        <button className="panel-btn-sm" onClick={loadChain}>View Chain</button>
        <button className="panel-btn-sm" onClick={verify}>Verify</button>
        <button className="panel-btn-sm" onClick={loadProof}>Balance Proof</button>
      </div>

      {verification && (
        <div className={`admin-verification ${verification.valid ? "valid" : "invalid"}`}>
          {verification.valid ? (
            <><CheckCircle className="h-3.5 w-3.5" /> Chain valid — {verification.length} blocks, no tampering</>
          ) : (
            <><XCircle className="h-3.5 w-3.5" /> Chain INVALID — {verification.errors.length} error(s) detected</>
          )}
        </div>
      )}

      {proof && (
        <div className="admin-proof">
          <div className="admin-subsection-title">Balance Proof</div>
          <div className="admin-info-grid">
            <div className="admin-info-row">
              <span className="admin-info-label">Chain Balance</span>
              <span className="admin-mono">{fmt(proof.chain_balance_cents)}</span>
            </div>
            <div className="admin-info-row">
              <span className="admin-info-label">User Balance</span>
              <span className="admin-mono">{fmt(proof.user_balance_cents)}</span>
            </div>
            <div className="admin-info-row">
              <span className="admin-info-label">Wallet Balance</span>
              <span className="admin-mono">{fmt(proof.wallet_balance_cents)}</span>
            </div>
            <div className="admin-info-row">
              <span className="admin-info-label">Verified</span>
              <span className={proof.verified ? "admin-ok" : "admin-fail"}>
                {proof.verified ? "Match" : `Discrepancy: ${fmt(proof.discrepancy_cents)}`}
              </span>
            </div>
            <div className="admin-info-row">
              <span className="admin-info-label">Last Hash</span>
              <span className="admin-mono" style={{ fontSize: 10 }}>{proof.last_block_hash?.slice(0, 24)}...</span>
            </div>
          </div>
        </div>
      )}

      {chain.length > 0 && (
        <div className="admin-chain">
          <div className="admin-subsection-title">Ledger — {chainTotal} blocks</div>
          <div className="admin-chain-list">
            {chain.map((b) => (
              <div key={b.id} className="admin-block">
                <div className="admin-block-idx">#{b.idx}</div>
                <div className="admin-block-type">{b.block_type}</div>
                <div className={`admin-block-amount ${b.amount_cents >= 0 ? "in" : "out"}`}>
                  {b.amount_cents >= 0 ? "+" : ""}{fmt(b.amount_cents)}
                </div>
                <div className="admin-block-bal">bal: {fmt(b.balance_after_cents)}</div>
                <div className="admin-block-hash" title={b.hash}>
                  {b.hash.slice(0, 12)}...
                </div>
                <div className="admin-block-date">
                  {new Date(b.timestamp).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


/* ═══════════════════════════════════════
   PROJECTS & WORKSPACES TAB
   ═══════════════════════════════════════ */
function ProjectsTab() {
  const [projects, setProjects] = useState<AdminProject[]>([]);
  const [workspaces, setWorkspaces] = useState<AdminWorkspace[]>([]);
  const [instances, setInstances] = useState<AdminInstance[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [view, setView] = useState<"projects" | "workspaces" | "instances">("projects");
  const [expandedProject, setExpandedProject] = useState<string | null>(null);
  const [projectWorkspaces, setProjectWorkspaces] = useState<AdminWorkspace[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (view === "projects") {
        const res = await adminListProjects({ search, limit: 100 });
        setProjects(res.projects);
      } else if (view === "workspaces") {
        const res = await adminListAllWorkspaces({ search, limit: 200 });
        setWorkspaces(res.workspaces);
      } else {
        const res = await adminListAllInstances({ limit: 200 });
        setInstances(res.instances);
      }
    } catch {}
    setLoading(false);
  }, [search, view]);

  useEffect(() => { load(); }, [load]);

  const expandProject = async (pid: string) => {
    if (expandedProject === pid) {
      setExpandedProject(null);
      return;
    }
    try {
      const res = await adminListProjectWorkspaces(pid);
      setProjectWorkspaces(res.workspaces);
      setExpandedProject(pid);
    } catch {}
  };

  return (
    <div className="admin-section">
      {/* View switcher */}
      <div style={{ display: "flex", gap: 6, marginBottom: 12, alignItems: "center" }}>
        {(["projects", "workspaces", "instances"] as const).map((v) => (
          <button
            key={v}
            className={`admin-filter-btn ${view === v ? "active" : ""}`}
            onClick={() => setView(v)}
          >
            {v.charAt(0).toUpperCase() + v.slice(1)}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <div className="admin-search-box">
          <Search className="h-3.5 w-3.5" />
          <input
            placeholder={`Search ${view}...`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <button className="admin-filter-btn" onClick={load}>
          <RefreshCw className="h-3 w-3" />
        </button>
      </div>

      {loading ? (
        <div className="admin-loading"><div className="term-spinner" /> Loading...</div>
      ) : view === "projects" ? (
        /* Projects list */
        <div className="admin-users-list">
          {projects.length === 0 ? (
            <div className="admin-empty">No projects found</div>
          ) : (
            projects.map((p) => (
              <div key={p.id}>
                <div
                  className="admin-user-row"
                  onClick={() => expandProject(p.id)}
                  style={{ cursor: "pointer" }}
                >
                  <div className="admin-user-info">
                    <div className="admin-user-avatar" style={{ background: "var(--color-purple, #8b5cf6)" }}>
                      <FolderOpen className="h-3.5 w-3.5" />
                    </div>
                    <div>
                      <div className="admin-user-email">{p.name}</div>
                      <div className="admin-user-meta">
                        {p.owner_email || "no owner"} — {p.id.slice(0, 16)}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 16, alignItems: "center", fontSize: 12 }}>
                    <span>{p.workspace_count} workspaces</span>
                    <span>{p.instance_count} instances</span>
                    <span className="admin-user-meta">{new Date(p.created_at).toLocaleDateString()}</span>
                    <ChevronDown
                      className="h-3.5 w-3.5"
                      style={{
                        transform: expandedProject === p.id ? "rotate(180deg)" : "rotate(0)",
                        transition: "transform 0.15s",
                        opacity: 0.5,
                      }}
                    />
                  </div>
                </div>

                {/* Expanded workspaces */}
                {expandedProject === p.id && (
                  <div style={{ padding: "0 16px 12px 56px", background: "var(--sidebar-bg)" }}>
                    {projectWorkspaces.length === 0 ? (
                      <div style={{ fontSize: 12, opacity: 0.5, padding: "8px 0" }}>No workspaces</div>
                    ) : (
                      projectWorkspaces.map((w) => (
                        <div key={w.id} style={{
                          display: "flex", gap: 12, alignItems: "center",
                          padding: "6px 0", borderBottom: "1px solid var(--border)",
                          fontSize: 12,
                        }}>
                          <span style={{ fontWeight: 500, minWidth: 120 }}>{w.name}</span>
                          <span className="admin-badge">{w.ws_type}</span>
                          {w.stack && <span style={{ opacity: 0.5 }}>{w.stack}</span>}
                          <span style={{ opacity: 0.4, fontFamily: "monospace", fontSize: 11 }}>{w.path}</span>
                          <span style={{ marginLeft: "auto", opacity: 0.4 }}>
                            {new Date(w.updated_at).toLocaleDateString()}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      ) : view === "workspaces" ? (
        /* All workspaces */
        <div className="admin-users-list">
          {workspaces.length === 0 ? (
            <div className="admin-empty">No workspaces found</div>
          ) : (
            workspaces.map((w) => (
              <div key={w.id} className="admin-user-row">
                <div className="admin-user-info">
                  <div className="admin-user-avatar" style={{ background: "var(--color-blue, #3b82f6)" }}>
                    <FolderOpen className="h-3.5 w-3.5" />
                  </div>
                  <div>
                    <div className="admin-user-email">{w.name}</div>
                    <div className="admin-user-meta">
                      {w.project_name || w.project_id.slice(0, 16)} — {w.owner_email || "—"}
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 12, alignItems: "center", fontSize: 12 }}>
                  <span className="admin-badge">{w.ws_type}</span>
                  {w.stack && <span style={{ opacity: 0.5 }}>{w.stack}</span>}
                  <span className="admin-user-meta">{new Date(w.updated_at).toLocaleDateString()}</span>
                </div>
              </div>
            ))
          )}
        </div>
      ) : (
        /* All instances */
        <div className="admin-users-list">
          {instances.length === 0 ? (
            <div className="admin-empty">No instances found</div>
          ) : (
            instances.map((inst) => (
              <div key={inst.id} className="admin-user-row">
                <div className="admin-user-info">
                  <div className="admin-user-avatar" style={{ background: "var(--color-teal, #14b8a6)" }}>
                    <Server className="h-3.5 w-3.5" />
                  </div>
                  <div>
                    <div className="admin-user-email">{inst.label || inst.id.slice(0, 16)}</div>
                    <div className="admin-user-meta">
                      {inst.project_name || inst.project_id.slice(0, 16)} — {inst.region} — {inst.plan}
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 12, alignItems: "center", fontSize: 12 }}>
                  <span className="admin-badge" style={{
                    color: inst.state === "active" ? "var(--color-green, green)" :
                      inst.state === "creating" ? "var(--color-yellow, orange)" : undefined,
                  }}>{inst.state}</span>
                  <span className="admin-user-meta" style={{ fontFamily: "monospace" }}>{inst.ip || "—"}</span>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}


/* ═══════════════════════════════════════
   ORCHESTRATOR TAB
   ═══════════════════════════════════════ */
function OrchestratorTab() {
  const [data, setData] = useState<OrchestratorOverview | null>(null);
  const [builds, setBuilds] = useState<BuildJob[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [recs, setRecs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [buildFilter, setBuildFilter] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [overview, b, a, r] = await Promise.all([
        getOrchestratorOverview(),
        listBuilds(buildFilter || undefined, 50),
        getOrchestratorAlerts(),
        getScalingRecommendations(),
      ]);
      setData(overview);
      setBuilds(b);
      setAlerts(a);
      setRecs(r);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, [buildFilter]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="admin-loading"><div className="term-spinner" /> Loading orchestrator...</div>;
  if (!data) return <div className="admin-empty">Could not load orchestrator data</div>;

  return (
    <div className="admin-section">
      {/* Metrics */}
      <div className="admin-cards-grid">
        <div className="admin-card">
          <div className="admin-card-label">Nodes</div>
          <div className="admin-card-value">{data.active_nodes}/{data.total_nodes}</div>
        </div>
        <div className="admin-card">
          <div className="admin-card-label">Avg CPU</div>
          <div className="admin-card-value" style={{ color: data.avg_cpu > 80 ? "var(--color-red, red)" : undefined }}>
            {data.avg_cpu}%
          </div>
        </div>
        <div className="admin-card">
          <div className="admin-card-label">Avg Memory</div>
          <div className="admin-card-value" style={{ color: data.avg_mem > 80 ? "var(--color-red, red)" : undefined }}>
            {data.avg_mem}%
          </div>
        </div>
        <div className="admin-card">
          <div className="admin-card-label">Queued Builds</div>
          <div className="admin-card-value">{data.queued_builds}</div>
        </div>
        <div className="admin-card">
          <div className="admin-card-label">Active Builds</div>
          <div className="admin-card-value">{data.active_builds}</div>
        </div>
        <div className="admin-card">
          <div className="admin-card-label">Done (24h)</div>
          <div className="admin-card-value" style={{ color: "var(--color-green, green)" }}>{data.completed_builds_24h}</div>
        </div>
      </div>

      {/* Recommendations */}
      {recs.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div className="admin-subsection-title">Scaling Recommendations</div>
          {recs.map((r: any, i: number) => (
            <div key={i} className="admin-alert" style={{ marginBottom: 6 }}>
              <TrendingUp className="h-3.5 w-3.5" />
              <div>
                <div style={{ fontWeight: 500, fontSize: 13 }}>{r.reason}</div>
                <div style={{ fontSize: 11, opacity: 0.6 }}>{r.action}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Nodes */}
      <div style={{ marginTop: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <div className="admin-subsection-title">Pool Nodes</div>
          <div style={{ display: "flex", gap: 6 }}>
            <button className="admin-filter-btn" onClick={async () => { await rebalancePool(); load(); }}>
              <RefreshCw className="h-3 w-3" /> Rebalance
            </button>
            <button className="admin-filter-btn" onClick={load}>
              <RefreshCw className="h-3 w-3" />
            </button>
          </div>
        </div>
        <div className="admin-users-list">
          {data.nodes.map((n) => (
            <div key={n.id} className="admin-user-row">
              <div className="admin-user-info">
                <div className="admin-user-avatar" style={{
                  background: n.status === "active" ? "var(--color-green, green)" :
                    n.status === "draining" ? "var(--color-yellow, orange)" : "var(--color-red, red)",
                }}>
                  <Server className="h-3.5 w-3.5" />
                </div>
                <div>
                  <div className="admin-user-email">{n.label || n.id.slice(0, 16)}</div>
                  <div className="admin-user-meta">{n.ip || "—"} — {n.role} — {n.region}</div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 12, alignItems: "center", fontSize: 12 }}>
                <BarInline label="CPU" value={n.cpu_percent} />
                <BarInline label="Mem" value={n.mem_percent} />
                <span>{n.active_builds}/{n.max_concurrent_builds} builds</span>
                <span className="admin-badge">{n.status}</span>
                {n.status === "active" ? (
                  <button className="admin-filter-btn" title="Drain" onClick={async () => {
                    await updatePoolNode(n.id, { status: "draining" }); load();
                  }}>
                    <Square className="h-3 w-3" />
                  </button>
                ) : (
                  <button className="admin-filter-btn" title="Activate" onClick={async () => {
                    await updatePoolNode(n.id, { status: "active" }); load();
                  }}>
                    <Play className="h-3 w-3" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Builds */}
      <div style={{ marginTop: 16 }}>
        <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 8 }}>
          <div className="admin-subsection-title" style={{ margin: 0 }}>Recent Builds</div>
          <div style={{ flex: 1 }} />
          {["", "queued", "building", "done", "failed"].map((f) => (
            <button
              key={f}
              className={`admin-filter-btn ${buildFilter === f ? "active" : ""}`}
              onClick={() => setBuildFilter(f)}
              style={{ fontSize: 11 }}
            >
              {f || "All"}
            </button>
          ))}
        </div>
        <div className="admin-users-list">
          {builds.length === 0 ? (
            <div className="admin-empty">No builds</div>
          ) : (
            builds.slice(0, 20).map((b) => (
              <div key={b.id} className="admin-user-row">
                <div className="admin-user-info">
                  <div className="admin-user-avatar" style={{
                    background: b.status === "done" ? "var(--color-green, green)" :
                      b.status === "failed" ? "var(--color-red, red)" :
                      b.status === "building" ? "var(--color-blue, blue)" : "var(--color-yellow, orange)",
                  }}>
                    {b.status === "done" ? <CheckCircle className="h-3.5 w-3.5" /> :
                     b.status === "failed" ? <XCircle className="h-3.5 w-3.5" /> :
                     <Activity className="h-3.5 w-3.5" />}
                  </div>
                  <div>
                    <div className="admin-user-email" style={{ fontFamily: "monospace", fontSize: 12 }}>
                      {b.workspace}/{b.branch}
                    </div>
                    <div className="admin-user-meta">{b.id.slice(0, 20)} — {timeAgo(b.queued_at)}</div>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
                  <span className="admin-badge">{b.status}</span>
                  {(b.status === "queued" || b.status === "assigned") && (
                    <button className="admin-filter-btn" onClick={async () => { await cancelBuild(b.id); load(); }}>
                      <XCircle className="h-3 w-3" /> Cancel
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div className="admin-subsection-title">Active Alerts ({alerts.length})</div>
          {alerts.slice(0, 10).map((a: any) => (
            <div key={a.id} className="admin-alert" style={{ marginBottom: 6, display: "flex", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <AlertTriangle className="h-3.5 w-3.5" />
                <span style={{ fontSize: 13 }}>{a.message}</span>
              </div>
              <button className="admin-filter-btn" onClick={async () => { await resolveOrchestratorAlert(a.id); load(); }}>
                <CheckCircle className="h-3 w-3" /> Resolve
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


/* ═══════════════════════════════════════
   LOAD BALANCER TAB
   ═══════════════════════════════════════ */
function LoadBalancerTab() {
  const [overview, setOverview] = useState<LBOverview | null>(null);
  const [rules, setRules] = useState<LBRule[]>([]);
  const [nginxConfig, setNginxConfig] = useState("");
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [showNginx, setShowNginx] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newAlgo, setNewAlgo] = useState("round_robin");
  const [creatingRule, setCreatingRule] = useState(false);
  const [newRulePoolId, setNewRulePoolId] = useState("");
  const [newRuleType, setNewRuleType] = useState("prefix");
  const [newRuleValue, setNewRuleValue] = useState("/");
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [o, r] = await Promise.all([getLBOverview(), listLBRules()]);
      setOverview(o);
      setRules(r);
      if (o.pools.length > 0 && !newRulePoolId) setNewRulePoolId(o.pools[0].id);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [newRulePoolId]);

  useEffect(() => { load(); }, [load]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      const r = await syncLBWithOrchestrator();
      alert(`Synced: ${r.synced} added, ${r.removed} removed`);
      load();
    } catch (e: any) { alert(e.message); }
    setSyncing(false);
  };

  const handleCreatePool = async () => {
    if (!newName.trim()) return;
    try {
      await createLBPool({ name: newName.trim(), algorithm: newAlgo });
      setNewName(""); setCreating(false); load();
    } catch (e: any) { alert(e.message); }
  };

  const handleDeletePool = async (id: string) => {
    if (!confirm("Delete this pool?")) return;
    try { await deleteLBPool(id); load(); } catch (e: any) { alert(e.message); }
  };

  const handleCreateRule = async () => {
    if (!newRulePoolId) return;
    try {
      await createLBRule({ pool_id: newRulePoolId, match_type: newRuleType, match_value: newRuleValue });
      setCreatingRule(false); load();
    } catch (e: any) { alert(e.message); }
  };

  const handleShowNginx = async () => {
    try {
      const cfg = await getLBNginxConfig();
      setNginxConfig(cfg);
      setShowNginx(true);
    } catch (e: any) { alert(e.message); }
  };

  if (loading) return <div className="admin-loading"><div className="term-spinner" /> Loading load balancer...</div>;
  if (!overview) return <div className="admin-empty">Could not load LB data</div>;

  return (
    <div className="admin-section">
      {/* Metrics */}
      <div className="admin-cards-grid">
        <div className="admin-card">
          <div className="admin-card-label">Pools</div>
          <div className="admin-card-value">{overview.active_pools}/{overview.total_pools}</div>
        </div>
        <div className="admin-card">
          <div className="admin-card-label">Backends</div>
          <div className="admin-card-value">{overview.total_backends}</div>
        </div>
        <div className="admin-card">
          <div className="admin-card-label">Healthy</div>
          <div className="admin-card-value" style={{ color: "var(--color-green, green)" }}>{overview.healthy_backends}</div>
        </div>
        <div className="admin-card">
          <div className="admin-card-label">Unhealthy</div>
          <div className="admin-card-value" style={{ color: overview.unhealthy_backends > 0 ? "var(--color-red, red)" : undefined }}>
            {overview.unhealthy_backends}
          </div>
        </div>
        <div className="admin-card">
          <div className="admin-card-label">Rules</div>
          <div className="admin-card-value">{overview.total_rules}</div>
        </div>
        <div className="admin-card">
          <div className="admin-card-label">Total Requests</div>
          <div className="admin-card-value">{fmtNum(overview.total_requests)}</div>
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: 6, marginTop: 12 }}>
        <button className="admin-filter-btn" onClick={handleSync} disabled={syncing}>
          <RefreshCw className={`h-3 w-3 ${syncing ? "spinning" : ""}`} />
          {syncing ? "Syncing..." : "Sync Orchestrator"}
        </button>
        <button className="admin-filter-btn" onClick={() => setCreating(!creating)}>
          <Plus className="h-3 w-3" /> New Pool
        </button>
        <button className="admin-filter-btn" onClick={handleShowNginx}>
          Nginx Config
        </button>
        <button className="admin-filter-btn" onClick={load} style={{ marginLeft: "auto" }}>
          <RefreshCw className="h-3 w-3" />
        </button>
      </div>

      {/* Create pool form */}
      {creating && (
        <div className="admin-alert" style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center" }}>
          <input
            className="admin-search-input"
            placeholder="Pool name..."
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreatePool()}
            autoFocus
            style={{ flex: 1, maxWidth: 200 }}
          />
          <select
            className="admin-search-input"
            value={newAlgo}
            onChange={(e) => setNewAlgo(e.target.value)}
            style={{ maxWidth: 160 }}
          >
            <option value="round_robin">Round Robin</option>
            <option value="least_conn">Least Connections</option>
            <option value="weighted">Weighted</option>
            <option value="ip_hash">IP Hash</option>
          </select>
          <button className="admin-filter-btn active" onClick={handleCreatePool}>Create</button>
        </div>
      )}

      {/* Pools */}
      <div style={{ marginTop: 16 }}>
        <div className="admin-subsection-title">Pools</div>
        {overview.pools.length === 0 ? (
          <div className="admin-empty">No pools. Create one or sync with orchestrator.</div>
        ) : (
          overview.pools.map((pool) => (
            <div key={pool.id} style={{
              background: "var(--sidebar-bg)", border: "1px solid var(--border)",
              borderRadius: 8, padding: 14, marginBottom: 10,
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{pool.name}</div>
                  <div style={{ fontSize: 11, opacity: 0.5, fontFamily: "monospace" }}>{pool.id}</div>
                </div>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <span className="admin-badge">{pool.algorithm}</span>
                  <span className="admin-badge" style={{
                    color: pool.active ? "var(--color-green, green)" : "var(--color-red, red)",
                  }}>{pool.active ? "active" : "inactive"}</span>
                  <button className="admin-filter-btn" onClick={() => handleDeletePool(pool.id)}>
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              </div>

              {/* Backends */}
              {pool.backends.length > 0 && (
                <div style={{ marginTop: 10, borderTop: "1px solid var(--border)", paddingTop: 8 }}>
                  {pool.backends.map((b) => (
                    <div key={b.id} style={{
                      display: "flex", alignItems: "center", gap: 10,
                      fontSize: 12, padding: "4px 0",
                    }}>
                      <span style={{
                        width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
                        background: b.status === "healthy" ? "var(--color-green, green)" :
                          b.status === "draining" ? "orange" : "var(--color-red, red)",
                      }} />
                      <span style={{ fontFamily: "monospace", minWidth: 130 }}>{b.ip}:{b.port}</span>
                      <span style={{ opacity: 0.5 }}>w={b.weight}</span>
                      <span style={{ opacity: 0.5 }}>{b.active_connections} conn</span>
                      <span style={{ opacity: 0.5 }}>{fmtNum(b.total_requests)} req</span>
                      <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
                        {b.status === "healthy" && (
                          <button className="admin-filter-btn" title="Drain" onClick={async () => {
                            await drainLBInstance(b.instance_id); load();
                          }}>
                            <Square className="h-3 w-3" />
                          </button>
                        )}
                        <button className="admin-filter-btn" title="Remove" onClick={async () => {
                          await removeLBBackend(b.id); load();
                        }}>
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Rules */}
      <div style={{ marginTop: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <div className="admin-subsection-title" style={{ margin: 0 }}>Routing Rules ({rules.length})</div>
          <button className="admin-filter-btn" onClick={() => setCreatingRule(!creatingRule)}>
            <Plus className="h-3 w-3" /> New Rule
          </button>
        </div>

        {creatingRule && (
          <div className="admin-alert" style={{ marginBottom: 8, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <select className="admin-search-input" value={newRuleType} onChange={(e) => setNewRuleType(e.target.value)} style={{ maxWidth: 100 }}>
              <option value="prefix">Prefix</option>
              <option value="exact">Exact</option>
              <option value="host">Host</option>
            </select>
            <input
              className="admin-search-input"
              placeholder={newRuleType === "host" ? "app.nso.dev" : "/api/"}
              value={newRuleValue}
              onChange={(e) => setNewRuleValue(e.target.value)}
              style={{ maxWidth: 150 }}
            />
            <span style={{ fontSize: 12, opacity: 0.5 }}>&rarr;</span>
            <select className="admin-search-input" value={newRulePoolId} onChange={(e) => setNewRulePoolId(e.target.value)} style={{ maxWidth: 200 }}>
              {overview.pools.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <button className="admin-filter-btn active" onClick={handleCreateRule}>Create</button>
          </div>
        )}

        <div className="admin-users-list">
          {rules.map((r) => (
            <div key={r.id} className="admin-user-row">
              <div className="admin-user-info">
                <div className="admin-user-avatar" style={{ background: "var(--color-purple, #8b5cf6)" }}>
                  <Route className="h-3.5 w-3.5" />
                </div>
                <div>
                  <div className="admin-user-email">
                    <span className="admin-badge">{r.match_type}</span> {r.match_value}
                  </div>
                  <div className="admin-user-meta">
                    &rarr; {overview.pools.find((p) => p.id === r.pool_id)?.name || r.pool_id.slice(0, 16)}
                    {" — priority: "}{r.priority}
                  </div>
                </div>
              </div>
              <button className="admin-filter-btn" onClick={async () => { await deleteLBRule(r.id); load(); }}>
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Nginx Config */}
      {showNginx && (
        <div style={{ marginTop: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <div className="admin-subsection-title" style={{ margin: 0 }}>Nginx Config</div>
            <div style={{ display: "flex", gap: 6 }}>
              <button className="admin-filter-btn" onClick={() => {
                navigator.clipboard.writeText(nginxConfig);
                setCopied(true); setTimeout(() => setCopied(false), 2000);
              }}>
                <Copy className="h-3 w-3" /> {copied ? "Copied!" : "Copy"}
              </button>
              <button className="admin-filter-btn" onClick={() => setShowNginx(false)}>
                <XCircle className="h-3 w-3" /> Close
              </button>
            </div>
          </div>
          <pre style={{
            background: "var(--sidebar-bg)", border: "1px solid var(--border)",
            borderRadius: 6, padding: 14, fontSize: 11, lineHeight: 1.5,
            overflow: "auto", maxHeight: 400, fontFamily: "'JetBrains Mono', monospace",
          }}>
            {nginxConfig}
          </pre>
        </div>
      )}
    </div>
  );
}


/* ═══════════════════════════════════════
   SHARED HELPERS
   ═══════════════════════════════════════ */
function BarInline({ label, value }: { label: string; value: number }) {
  const color = value > 90 ? "var(--color-red, red)" : value > 70 ? "orange" : "var(--color-green, green)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4, minWidth: 90 }}>
      <span style={{ fontSize: 10, opacity: 0.5, minWidth: 24 }}>{label}</span>
      <div style={{ flex: 1, height: 3, background: "var(--border)", borderRadius: 2, overflow: "hidden", minWidth: 40 }}>
        <div style={{ width: `${Math.min(100, value)}%`, height: "100%", background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontSize: 10, opacity: 0.6, minWidth: 28 }}>{value.toFixed(0)}%</span>
    </div>
  );
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function fmtNum(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}
