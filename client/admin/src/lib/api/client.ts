/**
 * Admin API client for sonfazt.nso.dev
 * All calls go to the central API (/api/admin/*) using the admin token.
 */

const API_BASE = typeof window !== "undefined" ? window.location.origin : "";

function getToken(): string | null {
  return typeof window !== "undefined" ? localStorage.getItem("sonfazt_token") : null;
}

async function adminApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (err: any) {
    throw new Error(`Network error: ${err.message || "Could not reach the server"}`);
  }

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${resp.status}: ${parseErrorText(resp.status, text)}`);
  }
  return resp.json();
}

function parseErrorText(status: number, text: string): string {
  try {
    const json = JSON.parse(text);
    if (json.detail) return json.detail;
    if (json.error) return json.error;
    if (json.message) return json.message;
  } catch {}

  if (text.includes("<html") || text.includes("<!DOCTYPE")) {
    if (status === 502) return "Bad Gateway — the server is unreachable or restarting";
    if (status === 503) return "Service unavailable — the server may be starting up";
    if (status === 504) return "Gateway timeout — the server did not respond in time";
    return `HTTP ${status} — server returned an error page`;
  }

  return text.length > 300 ? text.slice(0, 300) + "..." : text;
}

// ── Auth ──

export async function adminLogin(email: string, password: string) {
  const res = await adminApi<{ token: string; email: string; role: string }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

  if (res.role !== "admin") {
    throw new Error("403: Admin access required");
  }

  if (typeof window !== "undefined") {
    localStorage.setItem("sonfazt_token", res.token);
  }

  return res;
}

export function adminLogout() {
  if (typeof window !== "undefined") {
    localStorage.removeItem("sonfazt_token");
    localStorage.removeItem("sonfazt_email");
    localStorage.removeItem("sonfazt_role");
  }
}

// ── Types ──

export interface AdminUser {
  id: string;
  email: string;
  name: string;
  role: string;
  balance: number;
  verified: boolean;
  subdomain: string | null;
  last_active: string | null;
  created_at: string;
  subscription?: { plan_code: string; status: string } | null;
  invoice_count?: number;
  total_paid_cents?: number;
  wallet_balance_cents?: number;
  activity_count?: number;
  project_count?: number;
}

export interface DashboardOverview {
  users: { total: number; new_7d: number; dau: number };
  revenue: { total_cents: number; mrr_cents: number };
  subscriptions: { active: number; plan_distribution: Record<string, number> };
  infrastructure: { active_instances: number; total_projects: number };
  fraud_status: string;
}

export interface RevenueSummary {
  period_days: number;
  total_revenue_cents: number;
  paid_invoices: number;
  wallet_topups_cents: number;
  refund_cents: number;
  refund_count: number;
  net_revenue_cents: number;
  by_plan: Record<string, { count: number; revenue_cents: number }>;
  daily_trend: { date: string; revenue_cents: number; count: number }[];
}

export interface GrowthSummary {
  period_days: number;
  total_users: number;
  new_users: number;
  active_users: number;
  churned_users: number;
  churn_rate: number;
  daily_signups: { date: string; count: number }[];
  plan_distribution: Record<string, number>;
}

export interface FraudScanResult {
  scan_time: string;
  status: string;
  total_issues: number;
  balance_discrepancies: any[];
  chain_violations: any[];
  suspicious_accounts: any[];
  anomalies: any[];
}

export interface LedgerBlock {
  id: string;
  user_id: string;
  idx: number;
  prev_hash: string;
  hash: string;
  timestamp: string;
  block_type: string;
  amount_cents: number;
  balance_after_cents: number;
  resource_type: string;
  resource_id: string;
  data: any;
  nonce: string;
}

export interface ActivityEntry {
  id: string;
  user_id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  ip: string;
  created_at: string;
}

export interface CashflowPeriod {
  period: string;
  inflow_cents: number;
  outflow_cents: number;
  net_cents: number;
  breakdown: {
    invoices: { cents: number; count: number };
    topups: { cents: number; count: number };
    refunds: { cents: number; count: number };
    wallet_debits: { cents: number; count: number };
    ledger_in: { cents: number; count: number };
    ledger_out: { cents: number; count: number };
  };
  signups: number;
  subs_created: number;
  subs_cancelled: number;
}

export interface CashflowResult {
  granularity: string;
  periods_requested: number;
  periods_returned: number;
  timeline: CashflowPeriod[];
  totals: {
    inflow_cents: number;
    outflow_cents: number;
    net_cents: number;
    by_source: {
      invoices_cents: number;
      topups_cents: number;
      refunds_cents: number;
    };
  };
}

// ── Dashboard overview ──
export async function getAdminOverview() {
  return adminApi<DashboardOverview>("/api/admin/overview");
}

// ── User management ──
export async function adminListUsers(params: {
  search?: string; role?: string; sort?: string; order?: string; limit?: number; offset?: number;
} = {}) {
  const q = new URLSearchParams();
  if (params.search) q.set("search", params.search);
  if (params.role) q.set("role", params.role);
  if (params.sort) q.set("sort", params.sort);
  if (params.order) q.set("order", params.order);
  if (params.limit) q.set("limit", String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));
  return adminApi<{ users: AdminUser[]; total: number }>(`/api/admin/users?${q}`);
}

export async function adminGetUser(userId: string) {
  return adminApi<{ user: AdminUser }>(`/api/admin/users/${userId}`);
}

export async function adminUpdateUser(userId: string, data: { name?: string; email?: string; role?: string; verified?: boolean }) {
  return adminApi<{ ok: boolean; user: AdminUser }>(`/api/admin/users/${userId}`, {
    method: "PATCH", body: JSON.stringify(data),
  });
}

export async function adminResetPassword(userId: string, newPassword: string) {
  return adminApi<{ ok: boolean }>(`/api/admin/users/${userId}/reset-password`, {
    method: "POST", body: JSON.stringify({ new_password: newPassword }),
  });
}

export async function adminDisableUser(userId: string) {
  return adminApi<{ ok: boolean }>(`/api/admin/users/${userId}/disable`, { method: "POST" });
}

export async function adminGetUserActivity(userId: string, limit = 50) {
  return adminApi<{ activity: ActivityEntry[]; count: number }>(
    `/api/admin/users/${userId}/activity?limit=${limit}`,
  );
}

// ── Analytics ──
export async function getRevenueAnalytics(days = 30) {
  return adminApi<RevenueSummary>(`/api/admin/analytics/revenue?days=${days}`);
}

export async function getGrowthAnalytics(days = 30) {
  return adminApi<GrowthSummary>(`/api/admin/analytics/growth?days=${days}`);
}

export async function getRecentActivity(limit = 100, action = "") {
  const q = new URLSearchParams({ limit: String(limit) });
  if (action) q.set("action", action);
  return adminApi<{ activity: ActivityEntry[]; count: number }>(`/api/admin/analytics/activity?${q}`);
}

export async function getCashflowAnalytics(granularity: string = "month", periods: number = 12) {
  return adminApi<CashflowResult>(
    `/api/admin/analytics/cashflow?granularity=${granularity}&periods=${periods}`,
  );
}

export async function createAnalyticsSnapshot() {
  return adminApi<{ ok: boolean; snapshot: any }>("/api/admin/analytics/snapshot", { method: "POST" });
}

export async function getAnalyticsSnapshots(limit = 24) {
  return adminApi<{ snapshots: any[]; count: number }>(`/api/admin/analytics/snapshots?limit=${limit}`);
}

// ── Fraud detection ──
export async function runFraudScan() {
  return adminApi<FraudScanResult>("/api/admin/fraud/scan", { method: "POST" });
}

// ── Blockchain ledger ──
export async function getLedgerStats() {
  return adminApi<any>("/api/admin/ledger/stats");
}

export async function getUserLedger(userId: string, limit = 100) {
  return adminApi<{ blocks: LedgerBlock[]; total: number }>(
    `/api/admin/ledger/users/${userId}?limit=${limit}`,
  );
}

export async function verifyUserChain(userId: string) {
  return adminApi<{ valid: boolean; length: number; errors: any[] }>(
    `/api/admin/ledger/users/${userId}/verify`, { method: "POST" },
  );
}

export async function getBalanceProof(userId: string) {
  return adminApi<any>(`/api/admin/ledger/users/${userId}/balance-proof`);
}

export async function getLedgerDiscrepancies() {
  return adminApi<{ discrepancies: any[]; count: number }>("/api/admin/ledger/discrepancies");
}
