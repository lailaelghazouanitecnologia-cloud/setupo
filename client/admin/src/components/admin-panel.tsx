"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  Users, TrendingUp, Shield, Search, ChevronRight,
  RefreshCw, AlertTriangle, CheckCircle, Key, Eye,
  XCircle, BarChart3, Activity, Link2, ArrowDownUp,
  FolderOpen, ChevronDown, Plus, Server, UserPlus,
  Database, HardDrive, Play, Square, Trash2,
  Cpu, Clock, Zap, Network, Route, Settings, Copy,
} from "lucide-react";
import {
  getAdminOverview,
  adminListUsers,
  adminGetUser,
  adminUpdateUser,
  adminResetPassword,
  adminDisableUser,
  adminGetUserActivity,
  adminCreateUser,
  adminGetUserProjects,
  adminListProjectWorkspaces,
  adminListAllInstances,
  getDatabaseInfo,
  getDatabaseTable,
  getStorageOverview,
  deleteStorageObject,
  instanceAction,
  getRevenueAnalytics,
  getGrowthAnalytics,
  getCashflowAnalytics,
  runFraudScan,
  getLedgerStats,
  getUserLedger,
  verifyUserChain,
  getBalanceProof,
  getOrchestratorOverview,
  listPoolNodes,
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
  addLBBackend,
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
  type DbOverview,
  type DbTableDetail,
  type StorageOverview,
  type OrchestratorOverview,
  type PoolNode,
  type BuildJob,
  type LBOverview,
  type LBPool,
  type LBBackend,
  type LBRule,

} from "@/lib/api/client";
import { fmtCents, timeAgo, formatNum } from "@/lib/format";

type AdminTab = "overview" | "users" | "infra" | "cashflow" | "analytics" | "fraud" | "ledger" | "orchestrator" | "loadbalancer";

export function AdminPanel({ tab = "overview" }: { tab?: AdminTab }) {
  return (
    <div>
      {tab === "overview" && <OverviewTab />}
      {tab === "users" && <UsersTab />}
      {tab === "infra" && <InfraTab />}
      {tab === "cashflow" && <CashflowTab />}
      {tab === "analytics" && <AnalyticsTab />}
      {tab === "fraud" && <FraudTab />}
      {tab === "ledger" && <LedgerTab />}
      {tab === "orchestrator" && <OrchestratorTab />}
      {tab === "loadbalancer" && <LoadBalancerTab />}
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

  const fmt = fmtCents;

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

  const fmt = fmtCents;

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
  const [showCreate, setShowCreate] = useState(false);
  const [createEmail, setCreateEmail] = useState("");
  const [createPassword, setCreatePassword] = useState("");
  const [createName, setCreateName] = useState("");
  const [createRole, setCreateRole] = useState("user");
  const [createErr, setCreateErr] = useState("");
  const pageSize = 20;

  const load = useCallback(() => {
    setLoading(true);
    adminListUsers({ search, limit: pageSize, offset: page * pageSize })
      .then((r) => { setUsers(r.users); setTotal(r.total); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [search, page]);

  useEffect(() => { load(); }, [load]);

  const handleCreateUser = async () => {
    setCreateErr("");
    if (!createEmail || !createPassword) { setCreateErr("Email and password required"); return; }
    try {
      await adminCreateUser({ email: createEmail, password: createPassword, name: createName, role: createRole });
      setShowCreate(false);
      setCreateEmail(""); setCreatePassword(""); setCreateName(""); setCreateRole("user");
      load();
    } catch (e: any) { setCreateErr(e.message); }
  };

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
        <button className="panel-btn-sm" onClick={() => setShowCreate(!showCreate)} style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <UserPlus className="h-3.5 w-3.5" /> New User
        </button>
        <div className="admin-count">{total} users</div>
      </div>

      {showCreate && (
        <div style={{ padding: 14, background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, marginBottom: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Create User</div>
          {createErr && <div className="admin-error" style={{ marginBottom: 8 }}>{createErr}</div>}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <input className="settings-input" placeholder="Email" value={createEmail} onChange={(e) => setCreateEmail(e.target.value)} style={{ flex: 1, minWidth: 180 }} />
            <input className="settings-input" placeholder="Password (min 6)" type="password" value={createPassword} onChange={(e) => setCreatePassword(e.target.value)} style={{ flex: 1, minWidth: 140 }} />
            <input className="settings-input" placeholder="Name (optional)" value={createName} onChange={(e) => setCreateName(e.target.value)} style={{ flex: 1, minWidth: 120 }} />
            <select className="settings-input" value={createRole} onChange={(e) => setCreateRole(e.target.value)} style={{ width: 90 }}>
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
            <button className="panel-btn" onClick={handleCreateUser}>Create</button>
          </div>
        </div>
      )}

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
  const [projects, setProjects] = useState<AdminProject[]>([]);
  const [expandedProject, setExpandedProject] = useState<string | null>(null);
  const [projectWorkspaces, setProjectWorkspaces] = useState<AdminWorkspace[]>([]);
  const [showResetPw, setShowResetPw] = useState(false);
  const [newPw, setNewPw] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    adminGetUserActivity(user.id, 30).then((r) => setActivity(r.activity)).catch(() => {});
    adminGetUserProjects(user.id).then((r) => setProjects(r.projects)).catch(() => {});
  }, [user.id]);

  const expandProject = async (pid: string) => {
    if (expandedProject === pid) { setExpandedProject(null); return; }
    try {
      const res = await adminListProjectWorkspaces(pid);
      setProjectWorkspaces(res.workspaces);
      setExpandedProject(pid);
    } catch {}
  };

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

  const fmt = fmtCents;

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

      {/* Projects & Workspaces */}
      <div className="admin-detail-section">
        <div className="admin-detail-section-title">
          <FolderOpen className="h-3.5 w-3.5" /> Projects ({projects.length})
        </div>
        {projects.length === 0 ? (
          <div className="admin-muted" style={{ fontSize: 12 }}>No projects</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {projects.map((p) => (
              <div key={p.id}>
                <div
                  onClick={() => expandProject(p.id)}
                  style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: "8px 10px", borderRadius: 6, cursor: "pointer",
                    background: expandedProject === p.id ? "var(--card)" : "transparent",
                    border: "1px solid var(--border)",
                    fontSize: 13,
                  }}
                >
                  <FolderOpen className="h-3.5 w-3.5" style={{ opacity: 0.5, flexShrink: 0 }} />
                  <span style={{ fontWeight: 500, flex: 1 }}>{p.name}</span>
                  <span style={{ fontSize: 11, opacity: 0.5 }}>{p.workspace_count} ws</span>
                  <span style={{ fontSize: 11, opacity: 0.5 }}>{p.instance_count} inst</span>
                  <span style={{ fontSize: 11, opacity: 0.4, fontFamily: "monospace" }}>{p.id.slice(0, 14)}</span>
                  <ChevronDown className="h-3 w-3" style={{
                    opacity: 0.4, transition: "transform 0.15s",
                    transform: expandedProject === p.id ? "rotate(180deg)" : "rotate(0)",
                  }} />
                </div>
                {expandedProject === p.id && (
                  <div style={{ padding: "6px 12px 8px 32px", background: "var(--card)", borderRadius: "0 0 6px 6px" }}>
                    {projectWorkspaces.length === 0 ? (
                      <div style={{ fontSize: 12, opacity: 0.5, padding: "4px 0" }}>No workspaces</div>
                    ) : (
                      projectWorkspaces.map((w) => (
                        <div key={w.id} style={{
                          display: "flex", gap: 10, alignItems: "center",
                          padding: "5px 0", borderBottom: "1px solid var(--border)", fontSize: 12,
                        }}>
                          <Server className="h-3 w-3" style={{ opacity: 0.4, flexShrink: 0 }} />
                          <span style={{ fontWeight: 500, minWidth: 100 }}>{w.name}</span>
                          <span className="admin-badge">{w.ws_type}</span>
                          {w.stack && <span style={{ opacity: 0.5 }}>{w.stack}</span>}
                          <span style={{ marginLeft: "auto", opacity: 0.4, fontFamily: "monospace", fontSize: 11 }}>{w.path}</span>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            ))}
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

  const fmt = fmtCents;

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

  const fmt = fmtCents;

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
   INFRASTRUCTURE TAB
   ═══════════════════════════════════════ */
function InfraTab() {
  const [view, setView] = useState<"instances" | "database" | "storage">("instances");

  return (
    <div>
      <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
        {(["instances", "database", "storage"] as const).map((v) => (
          <button
            key={v}
            className={`admin-period-btn ${view === v ? "active" : ""}`}
            onClick={() => setView(v)}
            style={{ display: "flex", alignItems: "center", gap: 4 }}
          >
            {v === "instances" && <><Server className="h-3 w-3" /> Instances</>}
            {v === "database" && <><Database className="h-3 w-3" /> Database</>}
            {v === "storage" && <><HardDrive className="h-3 w-3" /> Storage (R2)</>}
          </button>
        ))}
      </div>
      {view === "instances" && <InstancesView />}
      {view === "database" && <DatabaseView />}
      {view === "storage" && <StorageView />}
    </div>
  );
}

/* ── Instances ── */
function InstancesView() {
  const [instances, setInstances] = useState<AdminInstance[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    adminListAllInstances({ limit: 200 })
      .then((r) => { setInstances(r.instances); setTotal(r.total); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const doAction = async (id: string, action: "start" | "stop" | "reboot") => {
    setActionLoading(id);
    try {
      await instanceAction(id, action);
      setTimeout(load, 2000);
    } catch (e: any) { alert(e.message); }
    setActionLoading(null);
  };

  if (loading) return <div className="admin-loading"><div className="term-spinner" /> Loading instances...</div>;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <span style={{ fontSize: 12, opacity: 0.5 }}>{total} instances</span>
        <button className="admin-filter-btn" onClick={load}><RefreshCw className="h-3 w-3" /></button>
      </div>

      {instances.length === 0 ? (
        <div className="admin-empty">No instances</div>
      ) : (
        <div className="admin-users-list">
          {instances.map((inst) => (
            <div key={inst.id} className="admin-user-row">
              <div className="admin-user-info">
                <div className="admin-user-avatar" style={{
                  background: inst.state === "active" || inst.state === "ready" ? "var(--color-green, green)" :
                    inst.state === "creating" ? "var(--color-yellow, orange)" : "var(--color-red, red)",
                }}>
                  <Server className="h-3.5 w-3.5" />
                </div>
                <div>
                  <div className="admin-user-email">{inst.label || inst.id.slice(0, 16)}</div>
                  <div className="admin-user-meta">
                    {inst.project_name || inst.project_id?.slice(0, 14)} — {inst.region} — {inst.plan}
                  </div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
                <span style={{ fontFamily: "monospace", opacity: 0.6 }}>{inst.ip || "—"}</span>
                <span className="admin-badge" style={{
                  color: (inst.state === "active" || inst.state === "ready") ? "var(--color-green, green)" :
                    inst.state === "creating" ? "var(--color-yellow, orange)" : undefined,
                }}>{inst.state}</span>
                {actionLoading === inst.id ? (
                  <div className="term-spinner" />
                ) : (
                  <div style={{ display: "flex", gap: 4 }}>
                    {(inst.state === "stopped" || inst.state === "inactive") && (
                      <button className="admin-filter-btn" title="Start" onClick={() => doAction(inst.id, "start")}>
                        <Play className="h-3 w-3" />
                      </button>
                    )}
                    {(inst.state === "active" || inst.state === "ready") && (
                      <button className="admin-filter-btn" title="Stop" onClick={() => doAction(inst.id, "stop")}>
                        <Square className="h-3 w-3" />
                      </button>
                    )}
                    <button className="admin-filter-btn" title="Reboot" onClick={() => doAction(inst.id, "reboot")}>
                      <RefreshCw className="h-3 w-3" />
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Database ── */
function DatabaseView() {
  const [dbInfo, setDbInfo] = useState<DbOverview | null>(null);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [tableDetail, setTableDetail] = useState<DbTableDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [tablePage, setTablePage] = useState(0);
  const pageSize = 30;

  useEffect(() => {
    getDatabaseInfo().then(setDbInfo).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const loadTable = useCallback(async (name: string, page = 0) => {
    setSelectedTable(name);
    setTablePage(page);
    try {
      const detail = await getDatabaseTable(name, pageSize, page * pageSize);
      setTableDetail(detail);
    } catch {}
  }, []);

  if (loading) return <div className="admin-loading"><div className="term-spinner" /> Loading database...</div>;
  if (!dbInfo) return <div className="admin-empty">Could not load database info</div>;

  if (selectedTable && tableDetail) {
    const totalPages = Math.ceil(tableDetail.total / pageSize);
    return (
      <div>
        <button className="panel-btn-sm" onClick={() => { setSelectedTable(null); setTableDetail(null); }} style={{ marginBottom: 10 }}>
          &larr; Back to tables
        </button>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <div>
            <span style={{ fontWeight: 600, fontSize: 14 }}>{tableDetail.table}</span>
            <span style={{ fontSize: 12, opacity: 0.5, marginLeft: 8 }}>{tableDetail.total} rows</span>
          </div>
        </div>
        <div style={{ fontSize: 11, opacity: 0.5, marginBottom: 8 }}>
          Columns: {tableDetail.columns.map((c) => `${c.name} (${c.type}${c.pk ? ", PK" : ""})`).join(" · ")}
        </div>
        <div style={{ overflow: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, fontFamily: "monospace" }}>
            <thead>
              <tr>
                {tableDetail.columns.map((c) => (
                  <th key={c.name} style={{
                    textAlign: "left", padding: "6px 8px", borderBottom: "2px solid var(--border)",
                    fontSize: 11, fontWeight: 600, whiteSpace: "nowrap",
                  }}>{c.name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tableDetail.rows.map((row, i) => (
                <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                  {tableDetail.columns.map((c) => (
                    <td key={c.name} style={{
                      padding: "5px 8px", maxWidth: 200, overflow: "hidden",
                      textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 11,
                    }} title={String(row[c.name] ?? "")}>
                      {row[c.name] === null ? <span style={{ opacity: 0.3 }}>null</span> :
                       typeof row[c.name] === "object" ? JSON.stringify(row[c.name]).slice(0, 50) :
                       String(row[c.name]).slice(0, 60)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {totalPages > 1 && (
          <div className="admin-pagination" style={{ marginTop: 10 }}>
            <button disabled={tablePage === 0} onClick={() => loadTable(selectedTable, tablePage - 1)} className="panel-btn-sm">Prev</button>
            <span className="admin-page-info">Page {tablePage + 1} of {totalPages}</span>
            <button disabled={tablePage >= totalPages - 1} onClick={() => loadTable(selectedTable, tablePage + 1)} className="panel-btn-sm">Next</button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      <div className="admin-cards-grid sm">
        <div className="admin-card sm">
          <div className="admin-card-label">Database Size</div>
          <div className="admin-card-value">{dbInfo.size_mb} MB</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Tables</div>
          <div className="admin-card-value">{dbInfo.table_count}</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Total Rows</div>
          <div className="admin-card-value">{dbInfo.tables.reduce((s, t) => s + t.row_count, 0)}</div>
        </div>
      </div>
      <div style={{ fontSize: 11, opacity: 0.4, marginBottom: 10, fontFamily: "monospace" }}>{dbInfo.path}</div>

      <div className="admin-users-list">
        {dbInfo.tables.map((t) => (
          <div key={t.name} className="admin-user-row" onClick={() => loadTable(t.name)} style={{ cursor: "pointer" }}>
            <div className="admin-user-info">
              <div className="admin-user-avatar" style={{ background: "var(--color-blue, #3b82f6)" }}>
                <Database className="h-3.5 w-3.5" />
              </div>
              <div>
                <div className="admin-user-email">{t.name}</div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
              <span style={{ fontFamily: "monospace" }}>{t.row_count} rows</span>
              <ChevronRight className="h-3.5 w-3.5" style={{ opacity: 0.3 }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Storage (R2) ── */
function StorageView() {
  const [data, setData] = useState<StorageOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [prefix, setPrefix] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    getStorageOverview(prefix)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [prefix]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async (key: string) => {
    if (!confirm(`Delete ${key}?`)) return;
    setDeleting(key);
    try {
      await deleteStorageObject(key);
      load();
    } catch (e: any) { alert(e.message); }
    setDeleting(null);
  };

  if (loading) return <div className="admin-loading"><div className="term-spinner" /> Loading storage...</div>;

  if (!data?.configured) {
    return <div className="admin-empty">R2 storage not configured. Set R2_ENDPOINT, R2_ACCESS_KEY_ID, and R2_SECRET_ACCESS_KEY.</div>;
  }

  if (data.error) {
    return <div className="admin-error">Error: {data.error}</div>;
  }

  // Group objects by first-level folder
  const folders = new Map<string, { count: number; types: Set<string> }>();
  const files: typeof data.objects = [];
  for (const obj of data.objects || []) {
    const relKey = prefix ? obj.key.slice(prefix.length) : obj.key;
    const slashIdx = relKey.indexOf("/");
    if (slashIdx > 0 && relKey.length > slashIdx + 1) {
      const folder = relKey.slice(0, slashIdx);
      if (!folders.has(folder)) folders.set(folder, { count: 0, types: new Set() });
      const f = folders.get(folder)!;
      f.count++;
      f.types.add(obj.type);
    } else {
      files.push(obj);
    }
  }

  return (
    <div>
      <div className="admin-cards-grid sm">
        <div className="admin-card sm">
          <div className="admin-card-label">Bucket</div>
          <div className="admin-card-value" style={{ fontSize: 14 }}>{data.bucket}</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Objects</div>
          <div className="admin-card-value">{data.object_count}</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Projects</div>
          <div className="admin-card-value">{data.projects_count}</div>
        </div>
      </div>
      <div style={{ fontSize: 11, opacity: 0.4, marginBottom: 4, fontFamily: "monospace" }}>{data.endpoint}</div>

      {/* Breadcrumb */}
      <div style={{ display: "flex", gap: 4, alignItems: "center", marginBottom: 10, fontSize: 12 }}>
        <button className="admin-filter-btn" onClick={() => setPrefix("")} style={{ fontWeight: !prefix ? 600 : 400 }}>
          /
        </button>
        {prefix && prefix.split("/").filter(Boolean).map((part, i, arr) => {
          const path = arr.slice(0, i + 1).join("/") + "/";
          return (
            <React.Fragment key={i}>
              <span style={{ opacity: 0.3 }}>/</span>
              <button className="admin-filter-btn" onClick={() => setPrefix(path)}>{part}</button>
            </React.Fragment>
          );
        })}
        <div style={{ flex: 1 }} />
        <button className="admin-filter-btn" onClick={load}><RefreshCw className="h-3 w-3" /></button>
      </div>

      <div className="admin-users-list">
        {/* Folders */}
        {Array.from(folders.entries()).sort().map(([name, info]) => (
          <div
            key={name}
            className="admin-user-row"
            onClick={() => setPrefix(prefix + name + "/")}
            style={{ cursor: "pointer" }}
          >
            <div className="admin-user-info">
              <div className="admin-user-avatar" style={{ background: "var(--color-yellow, #eab308)" }}>
                <FolderOpen className="h-3.5 w-3.5" />
              </div>
              <div>
                <div className="admin-user-email">{name}/</div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
              <span style={{ opacity: 0.5 }}>{info.count} objects</span>
              <span className="admin-badge">{Array.from(info.types).join(", ")}</span>
              <ChevronRight className="h-3.5 w-3.5" style={{ opacity: 0.3 }} />
            </div>
          </div>
        ))}

        {/* Files */}
        {files.map((obj) => {
          const fileName = obj.key.split("/").pop() || obj.key;
          return (
            <div key={obj.key} className="admin-user-row">
              <div className="admin-user-info">
                <div className="admin-user-avatar" style={{
                  background: obj.type === "zar" ? "var(--color-teal, #14b8a6)" :
                    obj.type === "json" ? "var(--color-blue, #3b82f6)" : "var(--color-gray, #6b7280)",
                }}>
                  <HardDrive className="h-3.5 w-3.5" />
                </div>
                <div>
                  <div className="admin-user-email">{fileName}</div>
                  <div className="admin-user-meta" style={{ fontFamily: "monospace", fontSize: 10 }}>{obj.key}</div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
                <span className="admin-badge">{obj.type}</span>
                <button
                  className="admin-filter-btn"
                  onClick={() => handleDelete(obj.key)}
                  disabled={deleting === obj.key}
                  title="Delete"
                >
                  {deleting === obj.key ? <div className="term-spinner" /> : <Trash2 className="h-3 w-3" />}
                </button>
              </div>
            </div>
          );
        })}

        {folders.size === 0 && files.length === 0 && (
          <div className="admin-empty">No objects{prefix ? ` under ${prefix}` : ""}</div>
        )}
      </div>
    </div>
  );
}


/* ═══════════════════════════════════════
   ORCHESTRATOR TAB
   ═══════════════════════════════════════ */
function OrchestratorTab() {
  const [view, setView] = useState<"overview" | "nodes" | "builds" | "alerts">("overview");

  return (
    <div>
      <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
        {(["overview", "nodes", "builds", "alerts"] as const).map((v) => (
          <button
            key={v}
            className={`admin-period-btn ${view === v ? "active" : ""}`}
            onClick={() => setView(v)}
            style={{ display: "flex", alignItems: "center", gap: 4 }}
          >
            {v === "overview" && <><BarChart3 className="h-3 w-3" /> Overview</>}
            {v === "nodes" && <><Server className="h-3 w-3" /> Nodes</>}
            {v === "builds" && <><Play className="h-3 w-3" /> Builds</>}
            {v === "alerts" && <><AlertTriangle className="h-3 w-3" /> Alerts</>}
          </button>
        ))}
      </div>
      {view === "overview" && <OrcOverview />}
      {view === "nodes" && <OrcNodes />}
      {view === "builds" && <OrcBuilds />}
      {view === "alerts" && <OrcAlerts />}
    </div>
  );
}

function OrcOverview() {
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
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="admin-loading"><div className="term-spinner" /> Loading orchestrator...</div>;
  if (!data) return <div className="admin-empty">Failed to load orchestrator data</div>;

  return (
    <div>
      <div className="admin-cards-grid sm">
        <div className="admin-card sm">
          <div className="admin-card-label">Nodes</div>
          <div className="admin-card-value">{data.active_nodes}/{data.total_nodes}</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Avg CPU</div>
          <div className={`admin-card-value ${data.avg_cpu > 80 ? "red" : data.avg_cpu > 60 ? "" : "teal"}`}>{data.avg_cpu}%</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Avg Memory</div>
          <div className={`admin-card-value ${data.avg_mem > 80 ? "red" : data.avg_mem > 60 ? "" : "teal"}`}>{data.avg_mem}%</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Builders</div>
          <div className="admin-card-value">{data.builders}</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Queued</div>
          <div className={`admin-card-value ${data.queued_builds > 3 ? "red" : ""}`}>{data.queued_builds}</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Active Builds</div>
          <div className="admin-card-value">{data.active_builds}</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Done (24h)</div>
          <div className="admin-card-value teal">{data.completed_builds_24h}</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Failed (24h)</div>
          <div className={`admin-card-value ${data.failed_builds_24h > 0 ? "red" : ""}`}>{data.failed_builds_24h}</div>
        </div>
      </div>

      {recs.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div className="admin-subsection-title">Scaling Recommendations</div>
          {recs.map((r: any, i: number) => (
            <div key={i} className="admin-fraud-item" style={{ marginBottom: 6 }}>
              <TrendingUp className="h-3.5 w-3.5" style={{ opacity: 0.6 }} />
              <span style={{ fontWeight: 500, fontSize: 13 }}>{r.reason}</span>
              <span className="admin-muted">{r.action}</span>
            </div>
          ))}
        </div>
      )}

      {data.alerts.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div className="admin-subsection-title">Active Alerts ({data.alerts.length})</div>
          {data.alerts.slice(0, 5).map((a: any) => (
            <div key={a.id} className="admin-fraud-item" style={{ marginBottom: 4 }}>
              <AlertTriangle className="h-3.5 w-3.5" style={{ color: "var(--color-red)" }} />
              <span style={{ fontSize: 13 }}>{a.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function OrcNodes() {
  const [data, setData] = useState<OrchestratorOverview | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { setData(await getOrchestratorOverview()); } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleToggle = async (node: PoolNode, newStatus: string) => {
    try {
      await updatePoolNode(node.id, { status: newStatus });
      load();
    } catch (e: any) { alert(e.message); }
  };

  if (loading) return <div className="admin-loading"><div className="term-spinner" /> Loading nodes...</div>;
  if (!data) return <div className="admin-empty">No data</div>;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <span style={{ fontSize: 12, opacity: 0.5 }}>{data.total_nodes} nodes</span>
        <div style={{ display: "flex", gap: 4 }}>
          <button className="admin-filter-btn" onClick={async () => { await rebalancePool(); load(); }} title="Rebalance">
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
                <div className="admin-user-email">{n.label || n.id.slice(0, 12)}</div>
                <div className="admin-user-meta">
                  {n.role} — {n.region} — {n.plan} — CPU {n.cpu_percent.toFixed(0)}% / Mem {n.mem_percent.toFixed(0)}% / Disk {n.disk_percent.toFixed(0)}%
                </div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
              <span style={{ fontFamily: "monospace", opacity: 0.6 }}>{n.ip || "—"}</span>
              <span className="admin-badge" style={{
                color: n.status === "active" ? "var(--color-green, green)" :
                  n.status === "draining" ? "var(--color-yellow, orange)" : undefined,
              }}>{n.status}</span>
              <span className="admin-muted">{n.active_builds}/{n.max_concurrent_builds} builds</span>
              {n.status === "active" ? (
                <button className="admin-filter-btn" title="Drain" onClick={() => handleToggle(n, "draining")}>
                  <Square className="h-3 w-3" />
                </button>
              ) : (
                <button className="admin-filter-btn" title="Activate" onClick={() => handleToggle(n, "active")}>
                  <Play className="h-3 w-3" />
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function OrcBuilds() {
  const [builds, setBuilds] = useState<BuildJob[]>([]);
  const [filter, setFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setBuilds(await listBuilds(filter || undefined, 100));
    } catch {}
    setLoading(false);
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const handleCancel = async (id: string) => {
    try { await cancelBuild(id); load(); } catch (e: any) { alert(e.message); }
  };

  const orcTimeAgo = (iso: string): string => {
    const diff = Date.now() - new Date(iso).getTime();
    const secs = Math.floor(diff / 1000);
    if (secs < 60) return `${secs}s ago`;
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  };

  if (loading) return <div className="admin-loading"><div className="term-spinner" /> Loading builds...</div>;

  return (
    <div>
      <div style={{ display: "flex", gap: 6, marginBottom: 10, alignItems: "center" }}>
        {["", "queued", "building", "done", "failed"].map((f) => (
          <button key={f} className={`admin-period-btn ${filter === f ? "active" : ""}`} onClick={() => setFilter(f)}>
            {f || "All"}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button className="admin-filter-btn" onClick={load}><RefreshCw className="h-3 w-3" /></button>
      </div>

      {builds.length === 0 ? (
        <div className="admin-empty">No builds found</div>
      ) : (
        <div className="admin-users-list">
          {builds.map((b) => (
            <div key={b.id} className="admin-user-row">
              <div className="admin-user-info">
                <div className="admin-user-avatar" style={{
                  background: b.status === "done" ? "var(--color-green, green)" :
                    b.status === "failed" ? "var(--color-red, red)" :
                    b.status === "building" ? "var(--color-blue, #3b82f6)" : "var(--color-yellow, orange)",
                }}>
                  <Play className="h-3.5 w-3.5" />
                </div>
                <div>
                  <div className="admin-user-email">{b.workspace} / {b.branch}</div>
                  <div className="admin-user-meta">
                    {b.id.slice(0, 16)} — {orcTimeAgo(b.queued_at)}
                    {b.assigned_node_id && ` — node ${b.assigned_node_id.slice(0, 12)}`}
                  </div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
                <span className="admin-badge" style={{
                  color: b.status === "done" ? "var(--color-green, green)" :
                    b.status === "failed" ? "var(--color-red, red)" : undefined,
                }}>{b.status}</span>
                {(b.status === "queued" || b.status === "assigned") && (
                  <button className="admin-filter-btn" title="Cancel" onClick={() => handleCancel(b.id)}>
                    <XCircle className="h-3 w-3" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function OrcAlerts() {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { setAlerts(await getOrchestratorAlerts()); } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleResolve = async (id: string) => {
    try { await resolveOrchestratorAlert(id); load(); } catch (e: any) { alert(e.message); }
  };

  if (loading) return <div className="admin-loading"><div className="term-spinner" /> Loading alerts...</div>;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <span style={{ fontSize: 12, opacity: 0.5 }}>{alerts.length} alerts</span>
        <button className="admin-filter-btn" onClick={load}><RefreshCw className="h-3 w-3" /></button>
      </div>

      {alerts.length === 0 ? (
        <div className="admin-empty" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <CheckCircle className="h-4 w-4" style={{ color: "var(--color-green, green)" }} />
          No active alerts
        </div>
      ) : (
        <div className="admin-users-list">
          {alerts.map((a: any) => (
            <div key={a.id} className="admin-user-row">
              <div className="admin-user-info">
                <div className="admin-user-avatar" style={{
                  background: a.severity === "critical" ? "var(--color-red, red)" : "var(--color-yellow, orange)",
                }}>
                  <AlertTriangle className="h-3.5 w-3.5" />
                </div>
                <div>
                  <div className="admin-user-email">{a.message}</div>
                  <div className="admin-user-meta">
                    {a.alert_type} — {a.value?.toFixed(1)}% (threshold: {a.threshold}%)
                  </div>
                </div>
              </div>
              <button className="panel-btn-sm" onClick={() => handleResolve(a.id)}>
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
  const [view, setView] = useState<"overview" | "pools" | "rules" | "nginx">("overview");

  return (
    <div>
      <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
        {(["overview", "pools", "rules", "nginx"] as const).map((v) => (
          <button
            key={v}
            className={`admin-period-btn ${view === v ? "active" : ""}`}
            onClick={() => setView(v)}
            style={{ display: "flex", alignItems: "center", gap: 4 }}
          >
            {v === "overview" && <><BarChart3 className="h-3 w-3" /> Overview</>}
            {v === "pools" && <><Network className="h-3 w-3" /> Pools</>}
            {v === "rules" && <><Route className="h-3 w-3" /> Rules</>}
            {v === "nginx" && <><Settings className="h-3 w-3" /> Nginx</>}
          </button>
        ))}
      </div>
      {view === "overview" && <LBOverviewView />}
      {view === "pools" && <LBPoolsView />}
      {view === "rules" && <LBRulesView />}
      {view === "nginx" && <LBNginxView />}
    </div>
  );
}

function LBOverviewView() {
  const [data, setData] = useState<LBOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setData(await getLBOverview()); } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      await syncLBWithOrchestrator();
      load();
    } catch (e: any) { alert(e.message); }
    setSyncing(false);
  };

  if (loading) return <div className="admin-loading"><div className="term-spinner" /> Loading load balancer...</div>;
  if (!data) return <div className="admin-empty">Failed to load LB data</div>;

  const fmtNum = formatNum;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 6, marginBottom: 12 }}>
        <button className="panel-btn-sm" onClick={handleSync} disabled={syncing}>
          <RefreshCw className="h-3 w-3" /> {syncing ? "Syncing..." : "Sync Orchestrator"}
        </button>
        <button className="admin-filter-btn" onClick={load}><RefreshCw className="h-3 w-3" /></button>
      </div>

      <div className="admin-cards-grid sm">
        <div className="admin-card sm">
          <div className="admin-card-label">Pools</div>
          <div className="admin-card-value">{data.active_pools}/{data.total_pools}</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Backends</div>
          <div className="admin-card-value">{data.total_backends}</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Healthy</div>
          <div className="admin-card-value teal">{data.healthy_backends}</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Unhealthy</div>
          <div className={`admin-card-value ${data.unhealthy_backends > 0 ? "red" : ""}`}>{data.unhealthy_backends}</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Rules</div>
          <div className="admin-card-value">{data.total_rules}</div>
        </div>
        <div className="admin-card sm">
          <div className="admin-card-label">Total Requests</div>
          <div className="admin-card-value">{fmtNum(data.total_requests)}</div>
        </div>
      </div>

      {data.pools.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div className="admin-subsection-title">Pools</div>
          <div className="admin-users-list">
            {data.pools.map((pool) => (
              <div key={pool.id} className="admin-user-row" style={{ flexDirection: "column", alignItems: "stretch" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div className="admin-user-info">
                    <div className="admin-user-avatar" style={{ background: pool.active ? "var(--color-green, green)" : "var(--color-red, red)" }}>
                      <Network className="h-3.5 w-3.5" />
                    </div>
                    <div>
                      <div className="admin-user-email">{pool.name}</div>
                      <div className="admin-user-meta">{pool.algorithm} — {pool.backends.filter((b) => b.status === "healthy").length}/{pool.backends.length} healthy</div>
                    </div>
                  </div>
                  <span className="admin-badge">{pool.active ? "active" : "inactive"}</span>
                </div>
                {pool.backends.length > 0 && (
                  <div style={{ paddingLeft: 42, marginTop: 6 }}>
                    {pool.backends.map((b) => (
                      <div key={b.id} style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 12, padding: "3px 0", borderTop: "1px solid var(--border)" }}>
                        <span style={{ width: 6, height: 6, borderRadius: "50%", background: b.status === "healthy" ? "var(--color-green, green)" : "var(--color-red, red)", flexShrink: 0 }} />
                        <span style={{ fontFamily: "monospace" }}>{b.ip}:{b.port}</span>
                        <span className="admin-muted">w={b.weight}</span>
                        <span className="admin-muted">{b.active_connections} conn</span>
                        <span className="admin-muted">{fmtNum(b.total_requests)} req</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function LBPoolsView() {
  const [pools, setPools] = useState<LBPool[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newAlgo, setNewAlgo] = useState("round_robin");

  const load = useCallback(async () => {
    setLoading(true);
    try { setPools(await listLBPools()); } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      await createLBPool({ name: newName.trim(), algorithm: newAlgo });
      setNewName(""); setCreating(false); load();
    } catch (e: any) { alert(e.message); }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this pool and all its backends?")) return;
    try { await deleteLBPool(id); load(); } catch (e: any) { alert(e.message); }
  };

  const handleRemoveBackend = async (backendId: string) => {
    try { await removeLBBackend(backendId); load(); } catch (e: any) { alert(e.message); }
  };

  const handleDrain = async (instanceId: string) => {
    try { await drainLBInstance(instanceId); load(); } catch (e: any) { alert(e.message); }
  };

  if (loading) return <div className="admin-loading"><div className="term-spinner" /> Loading pools...</div>;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <span style={{ fontSize: 12, opacity: 0.5 }}>{pools.length} pools</span>
        <div style={{ display: "flex", gap: 4 }}>
          <button className="panel-btn-sm" onClick={() => setCreating(!creating)} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <Plus className="h-3 w-3" /> New Pool
          </button>
          <button className="admin-filter-btn" onClick={load}><RefreshCw className="h-3 w-3" /></button>
        </div>
      </div>

      {creating && (
        <div style={{ padding: 12, background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, marginBottom: 10, display: "flex", gap: 8, alignItems: "center" }}>
          <input className="settings-input" placeholder="Pool name..." value={newName} onChange={(e) => setNewName(e.target.value)} style={{ flex: 1 }} />
          <select className="settings-input" value={newAlgo} onChange={(e) => setNewAlgo(e.target.value)} style={{ width: 140 }}>
            <option value="round_robin">Round Robin</option>
            <option value="least_conn">Least Conn</option>
            <option value="weighted">Weighted</option>
            <option value="ip_hash">IP Hash</option>
          </select>
          <button className="panel-btn" onClick={handleCreate}>Create</button>
        </div>
      )}

      <div className="admin-users-list">
        {pools.map((pool) => (
          <div key={pool.id} className="admin-user-row" style={{ flexDirection: "column", alignItems: "stretch" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div className="admin-user-info">
                <div className="admin-user-avatar" style={{ background: pool.active ? "var(--color-green, green)" : "var(--color-red, red)" }}>
                  <Network className="h-3.5 w-3.5" />
                </div>
                <div>
                  <div className="admin-user-email">{pool.name}</div>
                  <div className="admin-user-meta">{pool.algorithm} — health: {pool.health_check_path} every {pool.health_check_interval}s</div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                <span className="admin-badge">{pool.algorithm}</span>
                <button className="admin-filter-btn" onClick={() => handleDelete(pool.id)} title="Delete">
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            </div>

            {pool.backends.length > 0 && (
              <div style={{ paddingLeft: 42, marginTop: 6 }}>
                {pool.backends.map((b) => (
                  <div key={b.id} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, padding: "4px 0", borderTop: "1px solid var(--border)" }}>
                    <span className="admin-badge" style={{
                      color: b.status === "healthy" ? "var(--color-green, green)" :
                        b.status === "draining" ? "var(--color-yellow, orange)" : "var(--color-red, red)",
                    }}>{b.status}</span>
                    <span style={{ fontFamily: "monospace" }}>{b.ip}:{b.port}</span>
                    <span className="admin-muted">w={b.weight}</span>
                    <span className="admin-muted">{b.active_connections} conn</span>
                    <span className="admin-muted">{b.failed_health_checks} fails</span>
                    <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
                      {b.status === "healthy" && (
                        <button className="admin-filter-btn" onClick={() => handleDrain(b.instance_id)} title="Drain">
                          <ArrowDownUp className="h-3 w-3" />
                        </button>
                      )}
                      <button className="admin-filter-btn" onClick={() => handleRemoveBackend(b.id)} title="Remove">
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function LBRulesView() {
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
      setRules(r); setPools(p);
      if (p.length > 0 && !newPoolId) setNewPoolId(p[0].id);
    } catch {}
    setLoading(false);
  }, [newPoolId]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!newPoolId || !newValue.trim()) return;
    try {
      await createLBRule({ pool_id: newPoolId, match_type: newType, match_value: newValue.trim(), priority: newPriority });
      setCreating(false); load();
    } catch (e: any) { alert(e.message); }
  };

  const handleDelete = async (id: string) => {
    try { await deleteLBRule(id); load(); } catch (e: any) { alert(e.message); }
  };

  if (loading) return <div className="admin-loading"><div className="term-spinner" /> Loading rules...</div>;

  const poolName = (id: string) => pools.find((p) => p.id === id)?.name || id.slice(0, 16);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <span style={{ fontSize: 12, opacity: 0.5 }}>{rules.length} rules</span>
        <div style={{ display: "flex", gap: 4 }}>
          <button className="panel-btn-sm" onClick={() => setCreating(!creating)} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <Plus className="h-3 w-3" /> New Rule
          </button>
          <button className="admin-filter-btn" onClick={load}><RefreshCw className="h-3 w-3" /></button>
        </div>
      </div>

      {creating && (
        <div style={{ padding: 12, background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, marginBottom: 10, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <select className="settings-input" value={newType} onChange={(e) => setNewType(e.target.value)} style={{ width: 100 }}>
            <option value="prefix">Prefix</option>
            <option value="exact">Exact</option>
            <option value="host">Host</option>
          </select>
          <input className="settings-input" placeholder={newType === "host" ? "app.nso.dev" : "/api/"} value={newValue} onChange={(e) => setNewValue(e.target.value)} style={{ flex: 1, minWidth: 120 }} />
          <select className="settings-input" value={newPoolId} onChange={(e) => setNewPoolId(e.target.value)} style={{ width: 140 }}>
            {pools.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <input className="settings-input" type="number" placeholder="Priority" value={newPriority} onChange={(e) => setNewPriority(parseInt(e.target.value) || 0)} style={{ width: 70 }} />
          <button className="panel-btn" onClick={handleCreate}>Create</button>
        </div>
      )}

      {rules.length === 0 ? (
        <div className="admin-empty">No routing rules</div>
      ) : (
        <div className="admin-users-list">
          {rules.map((r) => (
            <div key={r.id} className="admin-user-row">
              <div className="admin-user-info">
                <div className="admin-user-avatar" style={{ background: r.active ? "var(--color-green, green)" : "var(--color-red, red)" }}>
                  <Route className="h-3.5 w-3.5" />
                </div>
                <div>
                  <div className="admin-user-email">
                    <span className="admin-badge" style={{ marginRight: 6 }}>{r.match_type}</span>
                    <span style={{ fontFamily: "monospace" }}>{r.match_value}</span>
                  </div>
                  <div className="admin-user-meta">Priority {r.priority} — Pool: {poolName(r.pool_id)}</div>
                </div>
              </div>
              <button className="admin-filter-btn" onClick={() => handleDelete(r.id)} title="Delete">
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function LBNginxView() {
  const [config, setConfig] = useState("");
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setConfig(await getLBNginxConfig()); } catch (e: any) { setConfig(`# Error: ${e.message}`); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCopy = () => {
    navigator.clipboard.writeText(config);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) return <div className="admin-loading"><div className="term-spinner" /> Generating nginx config...</div>;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 6, marginBottom: 10 }}>
        <button className="panel-btn-sm" onClick={handleCopy} style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <Copy className="h-3 w-3" /> {copied ? "Copied!" : "Copy"}
        </button>
        <button className="admin-filter-btn" onClick={load}><RefreshCw className="h-3 w-3" /></button>
      </div>
      <pre style={{
        background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8,
        padding: 16, fontSize: 12, lineHeight: 1.5, overflow: "auto",
        maxHeight: "calc(100vh - 280px)", fontFamily: "monospace", whiteSpace: "pre-wrap",
      }}>
        {config}
      </pre>
    </div>
  );
}
