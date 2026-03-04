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

export async function adminCreateUser(data: { email: string; password: string; name?: string; role?: string }) {
  return adminApi<{ ok: boolean; user: AdminUser }>("/api/admin/users", {
    method: "POST", body: JSON.stringify(data),
  });
}

export async function adminGetUserProjects(userId: string) {
  return adminApi<{ projects: AdminProject[] }>(`/api/admin/users/${userId}/projects`);
}

// ── Infrastructure: Database ──

export interface DbTableInfo {
  name: string;
  row_count: number;
}

export interface DbOverview {
  path: string;
  size_bytes: number;
  size_mb: number;
  tables: DbTableInfo[];
  table_count: number;
}

export interface DbColumn {
  name: string;
  type: string;
  notnull: boolean;
  pk: boolean;
}

export interface DbTableDetail {
  table: string;
  columns: DbColumn[];
  rows: Record<string, any>[];
  total: number;
}

export async function getDatabaseInfo() {
  return adminApi<DbOverview>("/api/admin/infra/database");
}

export async function getDatabaseTable(tableName: string, limit = 50, offset = 0) {
  return adminApi<DbTableDetail>(`/api/admin/infra/database/${tableName}?limit=${limit}&offset=${offset}`);
}

// ── Infrastructure: R2 Storage ──

export interface StorageObject {
  key: string;
  parts: string[];
  type: string;
}

export interface StorageOverview {
  configured: boolean;
  bucket?: string;
  endpoint?: string;
  object_count?: number;
  projects_count?: number;
  objects?: StorageObject[];
  prefix?: string;
  error?: string;
}

export async function getStorageOverview(prefix = "") {
  const q = prefix ? `?prefix=${encodeURIComponent(prefix)}` : "";
  return adminApi<StorageOverview>(`/api/admin/infra/storage${q}`);
}

export async function deleteStorageObject(key: string) {
  return adminApi<{ ok: boolean }>(`/api/admin/infra/storage?key=${encodeURIComponent(key)}`, {
    method: "DELETE",
  });
}

// ── Infrastructure: Instances ──

export async function instanceAction(instanceId: string, action: "start" | "stop" | "reboot") {
  return adminApi<{ ok: boolean }>(`/api/admin/infra/instances/${instanceId}/action?action=${action}`, {
    method: "POST",
  });
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

// ── Projects & Workspaces ──

export interface AdminProject {
  id: string;
  name: string;
  owner: string;
  owner_email: string;
  workspace_count: number;
  instance_count: number;
  settings: any;
  created_at: string;
}

export interface AdminWorkspace {
  id: string;
  project_id: string;
  name: string;
  path: string;
  ws_type: string;
  stack: string;
  description: string;
  instance_id: string | null;
  project_name?: string;
  owner_email?: string;
  created_at: string;
  updated_at: string;
}

export interface AdminInstance {
  id: string;
  project_id: string;
  project_name?: string;
  label: string;
  region: string;
  plan: string;
  ip: string | null;
  state: string;
  workspace: string | null;
  created_at: string;
}

export async function adminListProjects(params: {
  search?: string; sort?: string; order?: string; limit?: number; offset?: number;
} = {}) {
  const q = new URLSearchParams();
  if (params.search) q.set("search", params.search);
  if (params.sort) q.set("sort", params.sort);
  if (params.order) q.set("order", params.order);
  if (params.limit) q.set("limit", String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));
  return adminApi<{ projects: AdminProject[]; total: number }>(`/api/admin/projects?${q}`);
}

export async function adminListProjectWorkspaces(projectId: string) {
  return adminApi<{ workspaces: AdminWorkspace[]; project: any }>(
    `/api/admin/projects/${projectId}/workspaces`,
  );
}

export async function adminListAllWorkspaces(params: {
  search?: string; ws_type?: string; limit?: number; offset?: number;
} = {}) {
  const q = new URLSearchParams();
  if (params.search) q.set("search", params.search);
  if (params.ws_type) q.set("ws_type", params.ws_type);
  if (params.limit) q.set("limit", String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));
  return adminApi<{ workspaces: AdminWorkspace[]; total: number }>(`/api/admin/workspaces?${q}`);
}

export async function adminListAllInstances(params: {
  state?: string; limit?: number; offset?: number;
} = {}) {
  const q = new URLSearchParams();
  if (params.state) q.set("state", params.state);
  if (params.limit) q.set("limit", String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));
  return adminApi<{ instances: AdminInstance[]; total: number }>(`/api/admin/instances?${q}`);
}

// ── Orchestrator ──

export interface PoolNode {
  id: string;
  instance_id: string;
  label: string;
  role: string;
  status: string;
  ip: string | null;
  region: string;
  plan: string;
  max_concurrent_builds: number;
  cpu_percent: number;
  mem_percent: number;
  disk_percent: number;
  active_builds: number;
  last_heartbeat: string | null;
  created_at: string;
}

export interface BuildJob {
  id: string;
  project_id: string;
  workspace: string;
  branch: string;
  assigned_node_id: string | null;
  status: string;
  priority: number;
  build_command: string;
  logs: string;
  error: string | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface OrchestratorOverview {
  total_nodes: number;
  active_nodes: number;
  builders: number;
  runners: number;
  avg_cpu: number;
  avg_mem: number;
  queued_builds: number;
  active_builds: number;
  completed_builds_24h: number;
  failed_builds_24h: number;
  alerts: any[];
  nodes: PoolNode[];
}

export async function getOrchestratorOverview() {
  return adminApi<OrchestratorOverview>("/api/admin/orchestrator/overview");
}

export async function listPoolNodes() {
  return adminApi<PoolNode[]>("/api/admin/orchestrator/pool");
}

export async function updatePoolNode(nodeId: string, data: Record<string, any>) {
  return adminApi<PoolNode>(`/api/admin/orchestrator/pool/${nodeId}`, {
    method: "PATCH", body: JSON.stringify(data),
  });
}

export async function listBuilds(status?: string, limit = 50) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("limit", String(limit));
  return adminApi<BuildJob[]>(`/api/admin/orchestrator/builds?${params}`);
}

export async function cancelBuild(buildId: string) {
  return adminApi<{ ok: boolean }>(`/api/admin/orchestrator/builds/${buildId}/cancel`, {
    method: "POST",
  });
}

export async function getScalingRecommendations() {
  return adminApi<any[]>("/api/admin/orchestrator/recommendations");
}

export async function getOrchestratorAlerts() {
  return adminApi<any[]>("/api/admin/orchestrator/alerts");
}

export async function resolveOrchestratorAlert(alertId: string) {
  return adminApi<{ ok: boolean }>(`/api/admin/orchestrator/alerts/${alertId}/resolve`, {
    method: "POST",
  });
}

export async function rebalancePool() {
  return adminApi<{ ok: boolean }>("/api/admin/orchestrator/rebalance", {
    method: "POST",
  });
}

// ── Load Balancer ──

export interface LBPool {
  id: string;
  name: string;
  algorithm: string;
  health_check_path: string;
  health_check_interval: number;
  max_fails: number;
  sticky_sessions: boolean;
  backends: LBBackend[];
  active: boolean;
  created_at: string;
}

export interface LBBackend {
  id: string;
  pool_id: string;
  instance_id: string;
  ip: string;
  port: number;
  weight: number;
  status: string;
  active_connections: number;
  total_requests: number;
  failed_health_checks: number;
  last_health_check: string | null;
}

export interface LBOverview {
  total_pools: number;
  active_pools: number;
  total_backends: number;
  healthy_backends: number;
  unhealthy_backends: number;
  total_rules: number;
  total_requests: number;
  pools: LBPool[];
}

export interface LBRule {
  id: string;
  pool_id: string;
  match_type: string;
  match_value: string;
  priority: number;
  active: boolean;
}

export async function getLBOverview() {
  return adminApi<LBOverview>("/api/admin/lb/overview");
}

export async function listLBPools() {
  return adminApi<LBPool[]>("/api/admin/lb/pools");
}

export async function createLBPool(data: { name: string; algorithm?: string }) {
  return adminApi<LBPool>("/api/admin/lb/pools", {
    method: "POST", body: JSON.stringify(data),
  });
}

export async function deleteLBPool(poolId: string) {
  return adminApi<{ ok: boolean }>(`/api/admin/lb/pools/${poolId}`, { method: "DELETE" });
}

export async function addLBBackend(poolId: string, data: { instance_id: string; port?: number; weight?: number }) {
  return adminApi<LBBackend>(`/api/admin/lb/pools/${poolId}/backends`, {
    method: "POST", body: JSON.stringify(data),
  });
}

export async function removeLBBackend(backendId: string) {
  return adminApi<{ ok: boolean }>(`/api/admin/lb/backends/${backendId}`, { method: "DELETE" });
}

export async function listLBRules() {
  return adminApi<LBRule[]>("/api/admin/lb/rules");
}

export async function createLBRule(data: { pool_id: string; match_type?: string; match_value?: string; priority?: number }) {
  return adminApi<LBRule>("/api/admin/lb/rules", {
    method: "POST", body: JSON.stringify(data),
  });
}

export async function deleteLBRule(ruleId: string) {
  return adminApi<{ ok: boolean }>(`/api/admin/lb/rules/${ruleId}`, { method: "DELETE" });
}

export async function syncLBWithOrchestrator() {
  return adminApi<{ ok: boolean; synced: number; removed: number }>("/api/admin/lb/sync", {
    method: "POST",
  });
}

export async function drainLBInstance(instanceId: string) {
  return adminApi<{ ok: boolean }>(`/api/admin/lb/drain/${instanceId}`, { method: "POST" });
}

export async function getLBNginxConfig() {
  const token = getToken();
  const resp = await fetch(`${API_BASE}/api/admin/lb/nginx/config`, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  });
  if (!resp.ok) throw new Error(`${resp.status}`);
  return resp.text();
}
