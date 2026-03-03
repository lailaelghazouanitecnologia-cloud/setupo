"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  Users, TrendingUp, Shield, Search, ChevronRight,
  RefreshCw, AlertTriangle, CheckCircle, Key, Eye,
  XCircle, BarChart3, Activity, Link2, ArrowDownUp,
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
  type AdminUser,
  type DashboardOverview,
  type RevenueSummary,
  type GrowthSummary,
  type CashflowResult,
  type CashflowPeriod,
  type FraudScanResult,
  type LedgerBlock,
  type ActivityEntry,
} from "@/lib/api/client";

type AdminTab = "overview" | "users" | "cashflow" | "analytics" | "fraud" | "ledger";

export function AdminPanel({ tab = "overview" }: { tab?: AdminTab }) {
  return (
    <div>
      {tab === "overview" && <OverviewTab />}
      {tab === "users" && <UsersTab />}
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
