const API_BASE = typeof window !== "undefined" ? window.location.origin : "";

function getToken(key = "nso_token"): string | null {
  return typeof window !== "undefined" ? localStorage.getItem(key) : null;
}

export async function apiCall<T>(
  path: string,
  options: RequestInit = {},
  tokenKey = "nso_token",
): Promise<T> {
  const token = getToken(tokenKey);
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

export function centralApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  return apiCall<T>(path, options, "nso_api_token");
}

export async function login(email: string, password: string) {
  const apiRes = await apiCall<{ token: string; email: string; role: string }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

  if (typeof window !== "undefined") {
    localStorage.setItem("nso_api_token", apiRes.token);
  }

  if (apiRes.role === "admin") {
    try {
      const agentRes = await apiCall<{ token: string }>("/agent/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      if (typeof window !== "undefined") {
        localStorage.setItem("nso_token", agentRes.token);
      }
    } catch {}
  }

  return apiRes;
}

export async function register(email: string, password: string, name = "") {
  const res = await apiCall<{ token: string; email: string; role: string; user_id: string }>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, name }),
  });

  if (typeof window !== "undefined") {
    localStorage.setItem("nso_api_token", res.token);
  }

  return res;
}

export async function getMe() {
  return centralApi<{
    id: string; email: string; name: string;
    role: string; balance: number; verified: boolean;
    subdomain: string | null; created_at: string;
  }>("/api/auth/me");
}

export async function updateProfile(updates: { name?: string; email?: string }) {
  return centralApi<{ ok: boolean; user: any }>("/api/auth/profile", {
    method: "PATCH",
    body: JSON.stringify(updates),
  });
}

export async function changePassword(currentPassword: string, newPassword: string) {
  return centralApi<{ ok: boolean }>("/api/auth/change-password", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

export async function checkSubdomain(name: string) {
  return centralApi<{ subdomain: string; available: boolean; domain: string | null }>(
    `/api/subdomain/check?name=${encodeURIComponent(name)}`,
  );
}

export async function getApiHealth() {
  return apiCall<{ status: string; version: string; uptime_seconds: number }>("/api/health");
}

export async function getAgentHealth() {
  return apiCall<{ service: string; status: string; version: string; features: string[] }>("/agent/health");
}

export async function listFiles(path: string) {
  return apiCall<{ path: string; items: any[]; count: number }>(`/agent/files/list?path=${encodeURIComponent(path)}`);
}

export async function readFile(path: string) {
  return apiCall<{ path: string; content: string; size: number }>(`/agent/files/read?path=${encodeURIComponent(path)}`);
}

export async function writeFile(path: string, content: string) {
  return apiCall<{ ok: boolean }>("/agent/files/write", {
    method: "POST",
    body: JSON.stringify({ path, content }),
  });
}

export async function deleteFile(path: string) {
  return apiCall<{ ok: boolean }>(`/agent/files/?path=${encodeURIComponent(path)}`, {
    method: "DELETE",
  });
}

export async function getFileTree(path: string, depth = 3) {
  return apiCall<any>(`/agent/files/tree?path=${encodeURIComponent(path)}&depth=${depth}`);
}

export async function execCommand(command: string, workingDir = "/opt/setupo", timeout = 60) {
  return apiCall<{ stdout: string; stderr: string; exit_code: number; timed_out: boolean }>("/agent/exec/", {
    method: "POST",
    body: JSON.stringify({ command, working_dir: workingDir, timeout }),
  });
}

export async function manageService(action: string, name: string) {
  return apiCall<any>(`/agent/exec/service?action=${action}&name=${name}`, { method: "POST" });
}

export interface AgentSecret {
  key: string;
  value: string;
  bucket: string;
}

export async function listSecrets() {
  return apiCall<{ secrets: AgentSecret[]; buckets: Record<string, { key: string; value: string }[]>; count: number }>("/agent/secrets");
}

export async function addSecret(key: string, value: string) {
  return apiCall<{ ok: boolean; key: string; bucket: string }>("/agent/secrets", {
    method: "POST",
    body: JSON.stringify({ key, value }),
  });
}

export async function updateSecret(key: string, value: string) {
  return apiCall<{ ok: boolean; key: string }>(`/agent/secrets/${encodeURIComponent(key)}`, {
    method: "PUT",
    body: JSON.stringify({ value }),
  });
}

export async function deleteSecret(key: string) {
  return apiCall<{ ok: boolean; key: string }>(`/agent/secrets/${encodeURIComponent(key)}`, {
    method: "DELETE",
  });
}

export async function listProjects() {
  return centralApi<{ projects: any[] }>("/api/projects");
}

export async function listWorkspaces(projectId: string) {
  return centralApi<{ workspaces: any[] }>(`/api/projects/${projectId}/workspaces`);
}

export async function createWorkspace(projectId: string, name: string, stack = "node", description = "") {
  return centralApi<any>(`/api/projects/${projectId}/workspaces`, {
    method: "POST",
    body: JSON.stringify({ name, stack, description }),
  });
}

export async function deleteWorkspace(projectId: string, name: string) {
  return centralApi<any>(`/api/projects/${projectId}/workspaces/${name}`, {
    method: "DELETE",
  });
}

export async function getWorkspaceFiles(projectId: string, name: string, path = ".") {
  return centralApi<{ path: string; items: any[] }>(`/api/projects/${projectId}/workspaces/${name}/files?path=${encodeURIComponent(path)}`);
}

export async function readWorkspaceFile(projectId: string, name: string, path: string) {
  return centralApi<{ path: string; content: string; size: number }>(`/api/projects/${projectId}/workspaces/${name}/files/read?path=${encodeURIComponent(path)}`);
}

export async function writeWorkspaceFile(projectId: string, name: string, path: string, content: string) {
  return centralApi<{ path: string; written: boolean; size: number }>(`/api/projects/${projectId}/workspaces/${name}/files/write`, {
    method: "POST",
    body: JSON.stringify({ path, content }),
  });
}

export async function listInstances(projectId: string) {
  return centralApi<{ instances: any[] }>(`/api/projects/${projectId}/instances`);
}

export async function createInstance(projectId: string, opts: {
  type?: string; label?: string; region?: string; plan?: string; domain?: string; workspace?: string;
} = {}) {
  return centralApi<{ instance: any; message: string }>(`/api/projects/${projectId}/instances`, {
    method: "POST",
    body: JSON.stringify(opts),
  });
}

export async function getInstance(projectId: string, instanceId: string) {
  return centralApi<{ instance: any }>(`/api/projects/${projectId}/instances/${instanceId}`);
}

export async function deleteInstance(projectId: string, instanceId: string) {
  return centralApi<{ deleted: boolean }>(`/api/projects/${projectId}/instances/${instanceId}`, {
    method: "DELETE",
  });
}

export async function stopInstance(projectId: string, instanceId: string) {
  return centralApi<{ stopped: boolean }>(`/api/projects/${projectId}/instances/${instanceId}/stop`, {
    method: "POST",
  });
}

export async function startInstance(projectId: string, instanceId: string) {
  return centralApi<{ started: boolean }>(`/api/projects/${projectId}/instances/${instanceId}/start`, {
    method: "POST",
  });
}

export async function execOnInstance(projectId: string, instanceId: string, command: string, timeout = 30) {
  return centralApi<{ output: string; exit_code: number }>(`/api/projects/${projectId}/instances/${instanceId}/exec`, {
    method: "POST",
    body: JSON.stringify({ command, timeout }),
  });
}

export async function zarPack(projectId: string, name: string) {
  return centralApi<{ ok: boolean; manifest: any; size: number }>(
    `/api/projects/${projectId}/zar/${name}/pack`,
    { method: "POST" },
  );
}

export async function zarPush(projectId: string, name: string, branch = "main") {
  return centralApi<{ name: string; version: string; branch: string; hash: string; r2_key: string; size: number }>(
    `/api/projects/${projectId}/zar/${name}/push?branch=${encodeURIComponent(branch)}`,
    { method: "POST" },
  );
}

export async function zarDeploy(projectId: string, name: string, opts: { branch?: string; version?: string; instance_id?: string } = {}) {
  return centralApi<any>(
    `/api/projects/${projectId}/zar/${name}/deploy`,
    { method: "POST", body: JSON.stringify({ branch: opts.branch || "main", version: opts.version || "", instance_id: opts.instance_id || "" }) },
  );
}

export async function zarShip(projectId: string, name: string, opts: { branch?: string; instance_id?: string } = {}) {
  return centralApi<any>(
    `/api/projects/${projectId}/zar/${name}/ship`,
    { method: "POST", body: JSON.stringify({ branch: opts.branch || "main", instance_id: opts.instance_id || "" }) },
  );
}

export async function zarRollback(projectId: string, name: string, instanceId: string, snapshot = "") {
  return centralApi<any>(
    `/api/projects/${projectId}/zar/${name}/rollback`,
    { method: "POST", body: JSON.stringify({ instance_id: instanceId, snapshot }) },
  );
}

export async function zarVersions(projectId: string, name: string, branch = "main") {
  return centralApi<{ workspace: string; branch: string; versions: string[]; branches: string[] }>(
    `/api/projects/${projectId}/zar/${name}/versions?branch=${encodeURIComponent(branch)}`,
  );
}

export async function zarSelfUpdate(projectId: string, instanceId: string, component: string) {
  return centralApi<any>(
    `/api/projects/${projectId}/zar/self-update`,
    { method: "POST", body: JSON.stringify({ instance_id: instanceId, component }) },
  );
}

export interface PluginInfo {
  plugin_id: string;
  name: string;
  description: string;
  version: string;
  category: string;
  installed: boolean;
  enabled: boolean;
  config: Record<string, any>;
  installed_at: string | null;
  id: string | null;
}

export async function listPlugins(projectId: string) {
  return centralApi<{ plugins: PluginInfo[] }>(`/api/projects/${projectId}/plugins`);
}

export async function installPlugin(projectId: string, pluginId: string, config: Record<string, any> = {}) {
  return centralApi<{ ok: boolean; plugin: PluginInfo }>(`/api/projects/${projectId}/plugins/install`, {
    method: "POST",
    body: JSON.stringify({ plugin_id: pluginId, config }),
  });
}

export async function updatePlugin(projectId: string, pluginId: string, opts: { enabled?: boolean; config?: Record<string, any> }) {
  return centralApi<{ ok: boolean; plugin_id: string; updated: string[] }>(`/api/projects/${projectId}/plugins/${pluginId}`, {
    method: "PATCH",
    body: JSON.stringify(opts),
  });
}

export async function uninstallPlugin(projectId: string, pluginId: string) {
  return centralApi<{ ok: boolean; plugin_id: string }>(`/api/projects/${projectId}/plugins/${pluginId}`, {
    method: "DELETE",
  });
}

export interface CatalogEntry {
  id: string;
  plugin_id: string;
  name: string;
  description: string;
  version: string;
  category: string;
  icon: string;
  author: string;
  published: boolean;
  config_schema: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export async function listCatalog(projectId: string) {
  return centralApi<{ catalog: CatalogEntry[] }>(`/api/projects/${projectId}/plugins/catalog`);
}

export async function publishPlugin(projectId: string, entry: Partial<CatalogEntry>) {
  return centralApi<{ ok: boolean; entry: CatalogEntry }>(`/api/projects/${projectId}/plugins/catalog`, {
    method: "POST",
    body: JSON.stringify(entry),
  });
}

export async function updateCatalogEntry(projectId: string, pluginId: string, updates: Partial<CatalogEntry>) {
  return centralApi<{ ok: boolean; plugin_id: string }>(`/api/projects/${projectId}/plugins/catalog/${pluginId}`, {
    method: "PATCH",
    body: JSON.stringify(updates),
  });
}

export async function removeCatalogEntry(projectId: string, pluginId: string) {
  return centralApi<{ ok: boolean; plugin_id: string }>(`/api/projects/${projectId}/plugins/catalog/${pluginId}`, {
    method: "DELETE",
  });
}

export async function getDeployStatus() {
  return apiCall<any>("/agent/deploy/current");
}

export async function getDeploySnapshots() {
  return apiCall<{ target: string; snapshots: string[] }>("/agent/deploy/snapshots");
}

export interface Transaction {
  id: string;
  type: string;
  amount: number;
  description: string;
  reference: string;
  created_at: string;
}

export interface BillingPlan {
  id: string;
  code: string;
  name: string;
  description: string;
  interval: string;
  amount_cents: number;
  currency: string;
  features: Record<string, any>;
}

export interface BillingSubscription {
  id: string;
  user_id: string;
  plan_id: string;
  plan_code: string;
  status: string;
  current_period_start: string;
  current_period_end: string;
  amount_cents: number;
  currency: string;
  created_at: string;
  cancelled_at: string | null;
}

export interface Invoice {
  id: string;
  user_id: string;
  subscription_id: string | null;
  number: string;
  status: string;
  payment_status: string;
  currency: string;
  subtotal_cents: number;
  credits_applied_cents: number;
  total_cents: number;
  period_start: string;
  period_end: string;
  due_date: string;
  finalized_at: string | null;
  paid_at: string | null;
  created_at: string;
  items: InvoiceItem[];
}

export interface InvoiceItem {
  id: string;
  invoice_id: string;
  type: string;
  description: string;
  units: number;
  unit_price_cents: number;
  amount_cents: number;
  metric: string | null;
}

export interface PaymentMethod {
  id: string;
  user_id: string;
  type: string;
  provider: string;
  provider_id: string;
  label: string;
  is_default: boolean;
  metadata: Record<string, any>;
  created_at: string;
}

export interface BillingOverview {
  balance: number;
  currency: string;
  plan: BillingPlan | null;
  subscription: BillingSubscription | null;
  invoices: Invoice[];
  payment_methods: PaymentMethod[];
  transactions: Transaction[];
  usage: Record<string, number>;
}

// ── Plans ──
export async function listBillingPlans() {
  return centralApi<{ plans: BillingPlan[] }>("/api/billing/plans");
}

// ── Subscriptions ──
export async function getSubscription() {
  return centralApi<{ subscription: BillingSubscription | null; plan: BillingPlan | null }>("/api/billing/subscription");
}

export async function subscribe(planCode: string) {
  return centralApi<{ ok: boolean; subscription: BillingSubscription }>("/api/billing/subscribe", {
    method: "POST",
    body: JSON.stringify({ plan_code: planCode }),
  });
}

export async function cancelSubscription() {
  return centralApi<{ ok: boolean; subscription: BillingSubscription }>("/api/billing/cancel", {
    method: "POST",
  });
}

// ── Checkout (Stripe) ──
export async function createCheckout(planCode: string, successUrl = "", cancelUrl = "") {
  return centralApi<{ session_id?: string; url?: string; plan_code: string; subscription?: any; free?: boolean }>("/api/billing/checkout", {
    method: "POST",
    body: JSON.stringify({ plan_code: planCode, success_url: successUrl, cancel_url: cancelUrl }),
  });
}

export async function createTopUpCheckout(amountCents: number, successUrl = "", cancelUrl = "") {
  return centralApi<{ session_id: string; url: string; amount_cents: number }>("/api/billing/topup/checkout", {
    method: "POST",
    body: JSON.stringify({ amount_cents: amountCents, success_url: successUrl, cancel_url: cancelUrl }),
  });
}

// ── Invoices ──
export async function listInvoices() {
  return centralApi<{ invoices: Invoice[]; count: number }>("/api/billing/invoices");
}

export async function getInvoice(invoiceId: string) {
  return centralApi<{ invoice: Invoice }>(`/api/billing/invoices/${invoiceId}`);
}

// ── Payment Methods ──
export async function listPaymentMethods() {
  return centralApi<{ payment_methods: PaymentMethod[] }>("/api/billing/payment-methods");
}

export async function removePaymentMethod(pmId: string) {
  return centralApi<{ ok: boolean }>(`/api/billing/payment-methods/${pmId}`, { method: "DELETE" });
}

export async function setDefaultPaymentMethod(pmId: string) {
  return centralApi<{ ok: boolean; payment_method: PaymentMethod }>(`/api/billing/payment-methods/${pmId}/default`, { method: "POST" });
}

// ── Wallet ──
export async function getBalance() {
  return centralApi<{ balance: number; currency: string }>("/api/billing/balance");
}

export async function getTransactions() {
  return centralApi<{ transactions: Transaction[]; count: number }>("/api/billing/transactions");
}

export async function topUp(amount: number, reference = "") {
  return centralApi<{ ok: boolean; balance: number; transaction_id: string }>("/api/billing/topup", {
    method: "POST",
    body: JSON.stringify({ amount, reference }),
  });
}

// ── Overview ──
export async function getBillingOverview() {
  return centralApi<BillingOverview>("/api/billing/overview");
}

export interface Notification {
  id: string;
  type: "info" | "warning" | "success" | "alert";
  title: string;
  message: string;
  read: boolean;
  created_at: string;
}

export async function listNotifications() {
  return centralApi<{ notifications: Notification[]; count: number; unread: number }>("/api/notifications");
}

export async function markNotificationRead(id: string) {
  return centralApi<{ ok: boolean }>(`/api/notifications/${id}/read`, { method: "POST" });
}

export async function markAllNotificationsRead() {
  return centralApi<{ ok: boolean }>("/api/notifications/read-all", { method: "POST" });
}

export async function deleteNotification(id: string) {
  return centralApi<{ ok: boolean }>(`/api/notifications/${id}`, { method: "DELETE" });
}

export async function claimSubdomain(subdomain: string) {
  return centralApi<{ ok: boolean; subdomain: string; domain: string }>("/api/subdomain/claim", {
    method: "POST",
    body: JSON.stringify({ subdomain }),
  });
}

export async function getSubdomain() {
  return centralApi<{ subdomain: string | null; domain: string | null }>("/api/subdomain");
}

// ═══════════════════════════════════════════
//  PLUGIN APIs
// ═══════════════════════════════════════════

export async function pluginStorageList(projectId: string, prefix = "") {
  return centralApi<{ files: { key: string; full_key: string }[]; count: number }>(
    `/api/projects/${projectId}/p/storage/files?prefix=${encodeURIComponent(prefix)}`,
  );
}

export async function pluginStorageUpload(projectId: string, path: string, content: string, contentType = "application/octet-stream") {
  return centralApi<{ ok: boolean; path: string; size: number; hash: string }>(
    `/api/projects/${projectId}/p/storage/upload`,
    { method: "POST", body: JSON.stringify({ path, content, content_type: contentType }) },
  );
}

export async function pluginStorageDelete(projectId: string, path: string) {
  return centralApi<{ ok: boolean }>(
    `/api/projects/${projectId}/p/storage/files?path=${encodeURIComponent(path)}`,
    { method: "DELETE" },
  );
}

export async function pluginLogsList(projectId: string, instanceId = "", level = "", limit = 100) {
  const params = new URLSearchParams();
  if (instanceId) params.set("instance_id", instanceId);
  if (level) params.set("level", level);
  params.set("limit", String(limit));
  return centralApi<{ logs: any[]; count: number }>(
    `/api/projects/${projectId}/p/logs?${params}`,
  );
}

export async function pluginDnsList(projectId: string) {
  return centralApi<{ records: any[]; count: number }>(
    `/api/projects/${projectId}/p/dns/records`,
  );
}

export async function pluginDnsCreate(projectId: string, instanceId: string, domain: string, proxied = false) {
  return centralApi<{ ok: boolean; record: any }>(
    `/api/projects/${projectId}/p/dns/records`,
    { method: "POST", body: JSON.stringify({ instance_id: instanceId, domain, proxied }) },
  );
}

export async function pluginDnsDelete(projectId: string, domainId: string) {
  return centralApi<{ ok: boolean }>(
    `/api/projects/${projectId}/p/dns/records/${domainId}`,
    { method: "DELETE" },
  );
}

export async function pluginMonitoring(projectId: string) {
  return centralApi<{ instances: any[]; count: number }>(
    `/api/projects/${projectId}/p/monitoring/instances`,
  );
}

export async function pluginBackupsList(projectId: string) {
  return centralApi<{ backups: any[]; count: number }>(
    `/api/projects/${projectId}/p/backups/list`,
  );
}
