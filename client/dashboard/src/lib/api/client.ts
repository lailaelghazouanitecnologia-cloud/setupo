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
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Could not reach the server";
    throw new Error(`Network error: ${msg}`);
  }

  if (!resp.ok) {
    const text = await resp.text();
    // Auto-logout on 401 from authenticated API calls only
    // Skip login/register (they're public) and agent endpoints
    if (
      resp.status === 401 &&
      typeof window !== "undefined" &&
      path.startsWith("/api/") &&
      !path.startsWith("/api/auth/login") &&
      !path.startsWith("/api/auth/register")
    ) {
      localStorage.removeItem("nso_token");
      localStorage.removeItem("nso_api_token");
      localStorage.removeItem("nso_email");
      localStorage.removeItem("nso_role");
      window.dispatchEvent(new CustomEvent("nso:session-expired"));
    }
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
  } catch {
    // text is not JSON — fall through to plaintext handling
  }

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
    } catch {
      console.warn("Agent auth failed — deploy/file features may be unavailable");
    }
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

export async function execCommand(command: string, workingDir = "/opt/nso", timeout = 60) {
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

export interface SecretScope {
  id: string;
  label: string;
  type: "general" | "domain";
  domain: string | null;
  count?: number;
}

// ── Project-scoped secrets (central API) ──

export async function listSecretScopes(projectId: string) {
  return centralApi<{ scopes: SecretScope[]; count: number }>(`/api/projects/${projectId}/secrets/scopes`);
}

export async function createSecretScope(projectId: string, name: string) {
  return centralApi<{ ok: boolean; scope: string; domain: string }>(`/api/projects/${projectId}/secrets/scopes`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function deleteSecretScope(projectId: string, domain: string) {
  return centralApi<{ ok: boolean; domain: string }>(`/api/projects/${projectId}/secrets/scopes/${encodeURIComponent(domain)}`, {
    method: "DELETE",
  });
}

export async function listSecrets(projectId: string, scope = "general") {
  return centralApi<{ secrets: AgentSecret[]; buckets: Record<string, { key: string; value: string }[]>; count: number; scope: string }>(
    `/api/projects/${projectId}/secrets?scope=${encodeURIComponent(scope)}`,
  );
}

export async function addSecret(projectId: string, key: string, value: string, scope = "general") {
  return centralApi<{ ok: boolean; key: string; bucket: string; scope: string }>(`/api/projects/${projectId}/secrets`, {
    method: "POST",
    body: JSON.stringify({ key, value, scope }),
  });
}

export async function updateSecret(projectId: string, key: string, value: string, scope = "general") {
  return centralApi<{ ok: boolean; key: string; scope: string }>(`/api/projects/${projectId}/secrets/${encodeURIComponent(key)}?scope=${encodeURIComponent(scope)}`, {
    method: "PUT",
    body: JSON.stringify({ value }),
  });
}

export async function deleteSecret(projectId: string, key: string, scope = "general") {
  return centralApi<{ ok: boolean; key: string; scope: string }>(`/api/projects/${projectId}/secrets/${encodeURIComponent(key)}?scope=${encodeURIComponent(scope)}`, {
    method: "DELETE",
  });
}

export async function listProjects() {
  return centralApi<{ projects: any[] }>("/api/projects");
}

export async function createProject(name: string, description = "") {
  return centralApi<{ project: any; api_key: string; message: string }>("/api/projects", {
    method: "POST",
    body: JSON.stringify({ name, description }),
  });
}

export async function deleteProject(projectId: string) {
  return centralApi<{ deleted: boolean }>(`/api/projects/${projectId}`, {
    method: "DELETE",
  });
}

export async function rotateProjectKey(projectId: string) {
  return centralApi<{ api_key: string }>(`/api/projects/${projectId}/rotate-key`, {
    method: "POST",
  });
}

export async function listWorkspaces(projectId: string) {
  return centralApi<{ workspaces: any[] }>(`/api/projects/${projectId}/workspaces`);
}

export async function createWorkspace(projectId: string, name: string, description = "", git_url = "") {
  const body: Record<string, string> = { name, description };
  if (git_url) body.git_url = git_url;
  return centralApi<any>(`/api/projects/${projectId}/workspaces`, {
    method: "POST",
    body: JSON.stringify(body),
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

export async function listInstances(projectId: string, withMetrics = false) {
  const url = withMetrics
    ? `/api/projects/${projectId}/instances?metrics=true`
    : `/api/projects/${projectId}/instances`;
  return centralApi<{ instances: any[]; metrics?: any[] }>(url);
}

export async function getInstanceMetrics(projectId: string, instanceId: string) {
  return centralApi<any>(`/api/projects/${projectId}/instances/${instanceId}/metrics`);
}

export async function createInstance(projectId: string, opts: {
  type?: string; label?: string; region?: string; plan?: string; domain?: string; workspace?: string;
  source_type?: string; git_url?: string; git_branch?: string; zar_name?: string; app_ready_key?: string;
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

// ═══════════════════════════════════════════
//  COMPUTE NODES API
// ═══════════════════════════════════════════

export async function listComputeNodes(projectId: string, status = "", role = "") {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (role) params.set("role", role);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return centralApi<{ nodes: any[] }>(`/api/projects/${projectId}/nodes${qs}`);
}

export async function registerComputeNode(projectId: string, opts: { label: string; provider?: string; ip?: string; agent_port?: number; cpu_cores?: number; mem_total_mb?: number; instance_id?: string }) {
  return centralApi<{ node: any }>(`/api/projects/${projectId}/nodes`, {
    method: "POST",
    body: JSON.stringify(opts),
  });
}

export async function getComputeNode(projectId: string, nodeId: string) {
  return centralApi<{ node: any }>(`/api/projects/${projectId}/nodes/${nodeId}`);
}

export async function updateComputeNode(projectId: string, nodeId: string, updates: Record<string, any>) {
  return centralApi<{ node: any }>(`/api/projects/${projectId}/nodes/${nodeId}`, {
    method: "PATCH",
    body: JSON.stringify(updates),
  });
}

export async function deleteComputeNode(projectId: string, nodeId: string) {
  return centralApi<{ deleted: boolean }>(`/api/projects/${projectId}/nodes/${nodeId}`, {
    method: "DELETE",
  });
}

export async function drainNode(projectId: string, nodeId: string) {
  return centralApi<{ node: any }>(`/api/projects/${projectId}/nodes/${nodeId}/drain`, { method: "POST" });
}

export async function cordonNode(projectId: string, nodeId: string) {
  return centralApi<{ node: any }>(`/api/projects/${projectId}/nodes/${nodeId}/cordon`, { method: "POST" });
}

export async function uncordonNode(projectId: string, nodeId: string) {
  return centralApi<{ node: any }>(`/api/projects/${projectId}/nodes/${nodeId}/uncordon`, { method: "POST" });
}

export async function syncInstancesToNodes(projectId: string) {
  return centralApi<{ registered: number; skipped: number; node_ids: string[] }>(`/api/projects/${projectId}/nodes/sync-instances`, { method: "POST" });
}

export async function getNodeResources(projectId: string, nodeId: string) {
  return centralApi<{ resources: any }>(`/api/projects/${projectId}/nodes/${nodeId}/resources`);
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

export async function zarDeploy(projectId: string, name: string, opts: { branch?: string; version?: string; instance_id?: string; node_id?: string } = {}) {
  return centralApi<any>(
    `/api/projects/${projectId}/zar/${name}/deploy`,
    { method: "POST", body: JSON.stringify({ branch: opts.branch || "main", version: opts.version || "", instance_id: opts.instance_id || "", node_id: opts.node_id || "" }) },
  );
}

export async function zarShip(projectId: string, name: string, opts: { branch?: string; instance_id?: string; node_id?: string } = {}) {
  return centralApi<any>(
    `/api/projects/${projectId}/zar/${name}/ship`,
    { method: "POST", body: JSON.stringify({ branch: opts.branch || "main", instance_id: opts.instance_id || "", node_id: opts.node_id || "" }) },
  );
}

/** SSE event from ship-stream endpoint */
export interface ShipStreamEvent {
  type: "phase" | "pipeline_phase" | "error" | "done";
  phase?: string;
  status?: string;
  message?: string;
  size?: number;
  r2_key?: string;
  strategy?: string;
  cached?: boolean;
  ok?: boolean;
  version?: string;
  workspace?: string;
  branch?: string;
  snapshot?: string;
  // pipeline_phase fields
  name?: string;
  duration_ms?: number;
}

/**
 * Ship a workspace with real-time SSE progress streaming.
 * Returns an AbortController and a callback-based event reader.
 */
export function zarShipStream(
  projectId: string,
  name: string,
  opts: { branch?: string; instance_id?: string; domain?: string } = {},
  onEvent: (event: ShipStreamEvent) => void,
): { controller: AbortController; done: Promise<void> } {
  const controller = new AbortController();
  const token = getToken("nso_api_token");

  const done = (async () => {
    const resp = await fetch(
      `${API_BASE}/api/projects/${projectId}/zar/${name}/ship-stream`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          branch: opts.branch || "main",
          instance_id: opts.instance_id || "",
          domain: opts.domain || "",
        }),
        signal: controller.signal,
      },
    );

    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      onEvent({ type: "error", message: `HTTP ${resp.status}: ${text}` });
      return;
    }

    const reader = resp.body?.getReader();
    if (!reader) return;

    const decoder = new TextDecoder();
    let buffer = "";
    let currentEventType = "";

    while (true) {
      const { done: readerDone, value } = await reader.read();
      if (readerDone) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentEventType = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          const data = line.slice(6).trim();
          try {
            const parsed = JSON.parse(data);
            onEvent({ type: currentEventType as ShipStreamEvent["type"], ...parsed });
          } catch { /* skip malformed */ }
          currentEventType = "";
        }
      }
    }
  })();

  return { controller, done };
}

export async function zarRollback(projectId: string, name: string, instanceId: string, snapshot = "") {
  return centralApi<any>(
    `/api/projects/${projectId}/zar/${name}/rollback`,
    { method: "POST", body: JSON.stringify({ instance_id: instanceId, snapshot }) },
  );
}

export async function zarVersions(projectId: string, name: string, branch = "main") {
  return centralApi<{ workspace: string; branch: string; versions: string[]; branches: Record<string, string> }>(
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

export interface AddonInfo {
  addon_id: string;
  addon_type: "connector" | "plugin" | "marketplace";
  name: string;
  description: string;
  version: string;
  category: string;
  icon: string;
  author: string;
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

// ═══════════════════════════════════════════
//  ADDONS API
// ═══════════════════════════════════════════

export async function listAddons(projectId: string, addonType = "") {
  const params = addonType ? `?addon_type=${encodeURIComponent(addonType)}` : "";
  return centralApi<{ addons: AddonInfo[] }>(`/api/projects/${projectId}/addons${params}`);
}

export async function installAddon(projectId: string, addonId: string, addonType = "plugin", config: Record<string, any> = {}) {
  return centralApi<{ ok: boolean; addon: AddonInfo }>(`/api/projects/${projectId}/addons/install?addon_type=${encodeURIComponent(addonType)}`, {
    method: "POST",
    body: JSON.stringify({ plugin_id: addonId, config }),
  });
}

export async function updateAddon(projectId: string, addonId: string, opts: { enabled?: boolean; config?: Record<string, any> }, addonType = "") {
  const params = addonType ? `?addon_type=${encodeURIComponent(addonType)}` : "";
  return centralApi<{ ok: boolean; addon_id: string; updated: string[] }>(`/api/projects/${projectId}/addons/${addonId}${params}`, {
    method: "PATCH",
    body: JSON.stringify(opts),
  });
}

export async function uninstallAddon(projectId: string, addonId: string, addonType = "") {
  const params = addonType ? `?addon_type=${encodeURIComponent(addonType)}` : "";
  return centralApi<{ ok: boolean; addon_id: string }>(`/api/projects/${projectId}/addons/${addonId}${params}`, {
    method: "DELETE",
  });
}

export async function testConnector(projectId: string, connectorId: string) {
  return centralApi<{ ok: boolean; message: string }>(`/api/projects/${projectId}/addons/connectors/${connectorId}/test`, {
    method: "POST",
  });
}

export async function getConnectorStatus(projectId: string, connectorId: string) {
  return centralApi<{ connector_id: string; name: string; connected: boolean; config_keys: string[]; enabled: boolean }>(
    `/api/projects/${projectId}/addons/connectors/${connectorId}/status`,
  );
}

export async function getMarketplaceAppStatus(projectId: string, appId: string) {
  return centralApi<{ app_id: string; name: string; version: string; enabled: boolean; config: Record<string, any> }>(
    `/api/projects/${projectId}/addons/marketplace/${appId}/status`,
  );
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

export interface Coupon {
  id: string;
  code: string;
  name: string;
  coupon_type: string;
  value: number;
  currency: string;
  frequency: string;
  frequency_duration: number;
  plan_codes: string[];
  max_redemptions: number;
  redemptions_count: number;
  active: boolean;
  expires_at: string | null;
  created_at: string;
}

export interface AppliedCoupon {
  id: string;
  user_id: string;
  coupon_id: string;
  subscription_id: string;
  status: string;
  amount_cents_used: number;
  periods_remaining: number;
  applied_at: string;
  expires_at: string | null;
}

export interface CreditNote {
  id: string;
  user_id: string;
  invoice_id: string | null;
  number: string;
  reason: string;
  credit_type: string;
  status: string;
  total_cents: number;
  balance_cents: number;
  currency: string;
  items: any[];
  refund_status: string;
  created_at: string;
  voided_at: string | null;
}

export interface BillableMetric {
  id: string;
  code: string;
  name: string;
  description: string;
  aggregation_type: string;
  field_name: string;
  recurring: boolean;
  filters: any[];
  created_at: string;
  updated_at: string;
}

export interface TaxRate {
  id: string;
  name: string;
  code: string;
  rate: number;
  description: string;
  applied_to: string;
  region: string;
  active: boolean;
  created_at: string;
}

export interface BillingWallet {
  id: string;
  user_id: string;
  name: string;
  currency: string;
  balance_cents: number;
  consumed_cents: number;
  rate_amount: number;
  credits_balance: number;
  credits_consumed: number;
  status: string;
  expiration_at: string | null;
  priority: number;
  created_at: string;
  depleted_at: string | null;
}

export interface WalletTransaction {
  id: string;
  wallet_id: string;
  transaction_type: string;
  amount: number;
  credit_amount: number;
  source: string;
  settled_at: string | null;
  created_at: string;
}

export interface BillingEvent {
  id: string;
  event_type: string;
  resource_type: string;
  resource_id: string;
  user_id: string;
  data: Record<string, any>;
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
  applied_coupons: AppliedCoupon[];
  credit_notes: CreditNote[];
  credit_notes_balance_cents: number;
  wallets: BillingWallet[];
  wallet_balance_cents: number;
}

// ── Plans ──
export async function listBillingPlans() {
  return centralApi<{ plans: BillingPlan[] }>("/api/billing/plans");
}

// ── Subscriptions ──
export async function getSubscription() {
  return centralApi<{ subscription: BillingSubscription | null; plan: BillingPlan | null }>("/api/billing/subscription");
}

export async function subscribe(planCode: string, trial = false) {
  return centralApi<{ ok: boolean; subscription: BillingSubscription }>("/api/billing/subscribe", {
    method: "POST",
    body: JSON.stringify({ plan_code: planCode, trial }),
  });
}

export async function cancelSubscription() {
  return centralApi<{ ok: boolean; subscription: BillingSubscription }>("/api/billing/cancel", {
    method: "POST",
  });
}

export async function pauseSubscription() {
  return centralApi<{ ok: boolean; subscription: BillingSubscription }>("/api/billing/pause", { method: "POST" });
}

export async function resumeSubscription() {
  return centralApi<{ ok: boolean; subscription: BillingSubscription }>("/api/billing/resume", { method: "POST" });
}

// ── Checkout (Stripe + Google Pay) ──
export async function createCheckout(planCode: string, successUrl = "", cancelUrl = "", paymentMethods?: string[]) {
  return centralApi<{ session_id?: string; url?: string; plan_code: string; subscription?: any; free?: boolean }>("/api/billing/checkout", {
    method: "POST",
    body: JSON.stringify({ plan_code: planCode, success_url: successUrl, cancel_url: cancelUrl, payment_methods: paymentMethods }),
  });
}

export async function createTopUpCheckout(amountCents: number, successUrl = "", cancelUrl = "", paymentMethods?: string[]) {
  return centralApi<{ session_id: string; url: string; amount_cents: number }>("/api/billing/topup/checkout", {
    method: "POST",
    body: JSON.stringify({ amount_cents: amountCents, success_url: successUrl, cancel_url: cancelUrl, payment_methods: paymentMethods }),
  });
}

// ── Coupons ──
export async function listCoupons() {
  return centralApi<{ coupons: Coupon[]; count: number }>("/api/billing/coupons");
}

export async function createCoupon(data: {
  code: string; name: string; coupon_type?: string; value: number;
  frequency?: string; frequency_duration?: number; plan_codes?: string[];
  max_redemptions?: number; expires_at?: string;
}) {
  return centralApi<{ ok: boolean; coupon: Coupon }>("/api/billing/coupons", {
    method: "POST", body: JSON.stringify(data),
  });
}

export async function deactivateCoupon(code: string) {
  return centralApi<{ ok: boolean; coupon: Coupon }>(`/api/billing/coupons/${code}/deactivate`, { method: "POST" });
}

export async function applyCoupon(couponCode: string) {
  return centralApi<{ ok: boolean; applied_coupon: AppliedCoupon }>("/api/billing/coupons/apply", {
    method: "POST", body: JSON.stringify({ coupon_code: couponCode }),
  });
}

export async function removeAppliedCoupon(appliedId: string) {
  return centralApi<{ ok: boolean }>(`/api/billing/coupons/applied/${appliedId}`, { method: "DELETE" });
}

export async function listAppliedCoupons() {
  return centralApi<{ applied_coupons: AppliedCoupon[]; count: number }>("/api/billing/coupons/applied");
}

// ── Credit Notes ──
export async function listCreditNotes() {
  return centralApi<{ credit_notes: CreditNote[]; count: number }>("/api/billing/credit-notes");
}

export async function createCreditNote(data: {
  user_id: string; invoice_id?: string; total_cents: number; reason?: string; credit_type?: string;
}) {
  return centralApi<{ ok: boolean; credit_note: CreditNote }>("/api/billing/credit-notes", {
    method: "POST", body: JSON.stringify(data),
  });
}

export async function getCreditNote(cnId: string) {
  return centralApi<{ credit_note: CreditNote }>(`/api/billing/credit-notes/${cnId}`);
}

export async function voidCreditNote(cnId: string) {
  return centralApi<{ ok: boolean; credit_note: CreditNote }>(`/api/billing/credit-notes/${cnId}/void`, { method: "POST" });
}

// ── Billable Metrics ──
export async function listBillableMetrics() {
  return centralApi<{ metrics: BillableMetric[]; count: number }>("/api/billing/metrics");
}

export async function createBillableMetric(data: {
  code: string; name: string; aggregation_type?: string; description?: string;
  field_name?: string; recurring?: boolean;
}) {
  return centralApi<{ ok: boolean; metric: BillableMetric }>("/api/billing/metrics", {
    method: "POST", body: JSON.stringify(data),
  });
}

export async function deleteBillableMetric(code: string) {
  return centralApi<{ ok: boolean }>(`/api/billing/metrics/${code}`, { method: "DELETE" });
}

// ── Usage ──
export async function recordUsage(metric: string, units: number, properties?: Record<string, any>, transactionId?: string) {
  return centralApi<{ ok: boolean; event_id: string }>("/api/billing/usage", {
    method: "POST",
    body: JSON.stringify({ metric, units, properties, transaction_id: transactionId }),
  });
}

export async function getUsageSummary() {
  return centralApi<{ usage: Record<string, number>; period_start: string | null; period_end: string | null }>("/api/billing/usage/summary");
}

// ── Tax Rates ──
export async function listTaxRates() {
  return centralApi<{ taxes: TaxRate[]; count: number }>("/api/billing/taxes");
}

export async function createTaxRate(data: {
  name: string; code: string; rate: number; description?: string; applied_to?: string; region?: string;
}) {
  return centralApi<{ ok: boolean; tax: TaxRate }>("/api/billing/taxes", {
    method: "POST", body: JSON.stringify(data),
  });
}

// ── Wallets ──
export async function listBillingWallets() {
  return centralApi<{ wallets: BillingWallet[]; count: number }>("/api/billing/wallets");
}

export async function createBillingWallet(data: {
  name?: string; paid_credits?: number; granted_credits?: number; rate_amount?: number; expiration_at?: string;
}) {
  return centralApi<{ ok: boolean; wallet: BillingWallet }>("/api/billing/wallets", {
    method: "POST", body: JSON.stringify(data),
  });
}

export async function getBillingWallet(walletId: string) {
  return centralApi<{ wallet: BillingWallet }>(`/api/billing/wallets/${walletId}`);
}

export async function topUpBillingWallet(walletId: string, paidCredits = 0, grantedCredits = 0) {
  return centralApi<{ ok: boolean; wallet: BillingWallet }>(`/api/billing/wallets/${walletId}/topup`, {
    method: "POST", body: JSON.stringify({ paid_credits: paidCredits, granted_credits: grantedCredits }),
  });
}

export async function getWalletTransactions(walletId: string) {
  return centralApi<{ transactions: WalletTransaction[]; count: number }>(`/api/billing/wallets/${walletId}/transactions`);
}

// ── Billing Events ──
export async function listBillingEvents(eventType = "", limit = 50) {
  const params = new URLSearchParams();
  if (eventType) params.set("event_type", eventType);
  params.set("limit", String(limit));
  return centralApi<{ events: BillingEvent[]; count: number }>(`/api/billing/events/user?${params}`);
}

// ── Invoices ──
export async function listInvoices() {
  return centralApi<{ invoices: Invoice[]; count: number }>("/api/billing/invoices");
}

export async function getInvoice(invoiceId: string) {
  return centralApi<{ invoice: Invoice }>(`/api/billing/invoices/${invoiceId}`);
}

export async function generateInvoice() {
  return centralApi<{ ok: boolean; invoice: Invoice }>("/api/billing/invoices/generate", { method: "POST" });
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

// ── Wallet (legacy) ──
export async function getBalance() {
  return centralApi<{ balance: number; currency: string }>("/api/billing/balance");
}

export async function getTransactions() {
  return centralApi<{ transactions: Transaction[]; count: number }>("/api/billing/transactions");
}

export async function topUp(userId: string, amount: number, reference = "") {
  return centralApi<{ ok: boolean; balance: number; transaction_id: string }>("/api/billing/topup", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, amount, reference }),
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

// ── Admin Types ──

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

// ── Admin API functions ──

export async function getAdminOverview() {
  return centralApi<DashboardOverview>("/api/admin/overview");
}

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
  return centralApi<{ users: AdminUser[]; total: number }>(`/api/admin/users?${q}`);
}

export async function adminGetUser(userId: string) {
  return centralApi<{ user: AdminUser }>(`/api/admin/users/${userId}`);
}

export async function adminUpdateUser(userId: string, data: { name?: string; email?: string; role?: string; verified?: boolean }) {
  return centralApi<{ ok: boolean; user: AdminUser }>(`/api/admin/users/${userId}`, {
    method: "PATCH", body: JSON.stringify(data),
  });
}

export async function adminResetPassword(userId: string, newPassword: string) {
  return centralApi<{ ok: boolean }>(`/api/admin/users/${userId}/reset-password`, {
    method: "POST", body: JSON.stringify({ new_password: newPassword }),
  });
}

export async function adminDisableUser(userId: string) {
  return centralApi<{ ok: boolean }>(`/api/admin/users/${userId}/disable`, { method: "POST" });
}

export async function adminGetUserActivity(userId: string, limit = 50) {
  return centralApi<{ activity: ActivityEntry[]; count: number }>(
    `/api/admin/users/${userId}/activity?limit=${limit}`,
  );
}

export async function getRevenueAnalytics(days = 30) {
  return centralApi<RevenueSummary>(`/api/admin/analytics/revenue?days=${days}`);
}

export async function getGrowthAnalytics(days = 30) {
  return centralApi<GrowthSummary>(`/api/admin/analytics/growth?days=${days}`);
}

export async function getCashflowAnalytics(granularity = "month", periods = 12) {
  return centralApi<CashflowResult>(
    `/api/admin/analytics/cashflow?granularity=${granularity}&periods=${periods}`,
  );
}

export async function runFraudScan() {
  return centralApi<FraudScanResult>("/api/admin/fraud/scan", { method: "POST" });
}

export async function getLedgerStats() {
  return centralApi<any>("/api/admin/ledger/stats");
}

export async function getUserLedger(userId: string, limit = 100) {
  return centralApi<{ blocks: LedgerBlock[]; total: number }>(
    `/api/admin/ledger/users/${userId}?limit=${limit}`,
  );
}

export async function verifyUserChain(userId: string) {
  return centralApi<{ valid: boolean; length: number; errors: any[] }>(
    `/api/admin/ledger/users/${userId}/verify`, { method: "POST" },
  );
}

export async function getBalanceProof(userId: string) {
  return centralApi<any>(`/api/admin/ledger/users/${userId}/balance-proof`);
}

/* ═══════════════════════════════════════
   ORCHESTRATOR
   ═══════════════════════════════════════ */

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

export interface ScaleAlert {
  id: string;
  node_id: string;
  alert_type: string;
  severity: string;
  message: string;
  value: number;
  threshold: number;
  resolved: boolean;
  created_at: string;
}

export async function getOrchestratorOverview() {
  return centralApi<OrchestratorOverview>("/api/admin/orchestrator/overview");
}

export async function listPoolNodes(role?: string, status?: string) {
  const params = new URLSearchParams();
  if (role) params.set("role", role);
  if (status) params.set("status", status);
  const q = params.toString();
  return centralApi<PoolNode[]>(`/api/admin/orchestrator/pool${q ? `?${q}` : ""}`);
}

export async function registerPoolNode(data: {
  instance_id: string;
  label?: string;
  role?: string;
  ip?: string;
  region?: string;
  max_concurrent_builds?: number;
}) {
  return centralApi<PoolNode>("/api/admin/orchestrator/pool", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updatePoolNode(nodeId: string, data: { label?: string; role?: string; status?: string; max_concurrent_builds?: number }) {
  return centralApi<PoolNode>(`/api/admin/orchestrator/pool/${nodeId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function removePoolNode(nodeId: string) {
  return centralApi<{ ok: boolean }>(`/api/admin/orchestrator/pool/${nodeId}`, {
    method: "DELETE",
  });
}

export async function listBuilds(status?: string, projectId?: string, limit = 50) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (projectId) params.set("project_id", projectId);
  params.set("limit", String(limit));
  return centralApi<BuildJob[]>(`/api/admin/orchestrator/builds?${params}`);
}

export async function submitBuild(data: {
  project_id: string;
  workspace: string;
  branch?: string;
  build_command?: string;
  priority?: number;
  deploy_after?: boolean;
  target_instance_id?: string;
}) {
  return centralApi<BuildJob>("/api/admin/orchestrator/builds", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function cancelBuild(buildId: string) {
  return centralApi<{ ok: boolean }>(`/api/admin/orchestrator/builds/${buildId}/cancel`, {
    method: "POST",
  });
}

export async function getOrchestratorAlerts(nodeId?: string) {
  const q = nodeId ? `?node_id=${nodeId}` : "";
  return centralApi<ScaleAlert[]>(`/api/admin/orchestrator/alerts${q}`);
}

export async function resolveOrchestratorAlert(alertId: string) {
  return centralApi<{ ok: boolean }>(`/api/admin/orchestrator/alerts/${alertId}/resolve`, {
    method: "POST",
  });
}

export async function getScalingRecommendations() {
  return centralApi<any[]>("/api/admin/orchestrator/recommendations");
}

export async function rebalancePool() {
  return centralApi<{ ok: boolean }>("/api/admin/orchestrator/rebalance", {
    method: "POST",
  });
}

/* ═══════════════════════════════════════
   LOAD BALANCER
   ═══════════════════════════════════════ */

export interface LBPool {
  id: string;
  name: string;
  project_id: string;
  algorithm: string;
  health_check_path: string;
  health_check_interval: number;
  health_check_timeout: number;
  max_fails: number;
  sticky_sessions: boolean;
  sticky_cookie: string;
  backends: LBBackend[];
  active: boolean;
  created_at: string;
  updated_at: string;
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
  created_at: string;
}

export interface LBRule {
  id: string;
  pool_id: string;
  match_type: string;
  match_value: string;
  priority: number;
  headers: Record<string, string>;
  active: boolean;
  created_at: string;
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

export async function getLBOverview() {
  return centralApi<LBOverview>("/api/admin/lb/overview");
}

export async function listLBPools(projectId?: string) {
  const q = projectId ? `?project_id=${projectId}` : "";
  return centralApi<LBPool[]>(`/api/admin/lb/pools${q}`);
}

export async function createLBPool(data: {
  name: string;
  project_id?: string;
  algorithm?: string;
  health_check_path?: string;
  health_check_interval?: number;
  max_fails?: number;
  sticky_sessions?: boolean;
}) {
  return centralApi<LBPool>("/api/admin/lb/pools", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateLBPool(poolId: string, data: Record<string, any>) {
  return centralApi<LBPool>(`/api/admin/lb/pools/${poolId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteLBPool(poolId: string) {
  return centralApi<{ ok: boolean }>(`/api/admin/lb/pools/${poolId}`, {
    method: "DELETE",
  });
}

export async function addLBBackend(poolId: string, data: { instance_id: string; port?: number; weight?: number }) {
  return centralApi<LBBackend>(`/api/admin/lb/pools/${poolId}/backends`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateLBBackend(backendId: string, data: { weight?: number; status?: string; port?: number }) {
  return centralApi<LBBackend>(`/api/admin/lb/backends/${backendId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function removeLBBackend(backendId: string) {
  return centralApi<{ ok: boolean }>(`/api/admin/lb/backends/${backendId}`, {
    method: "DELETE",
  });
}

export async function listLBRules(poolId?: string) {
  const q = poolId ? `?pool_id=${poolId}` : "";
  return centralApi<LBRule[]>(`/api/admin/lb/rules${q}`);
}

export async function createLBRule(data: {
  pool_id: string;
  match_type?: string;
  match_value?: string;
  priority?: number;
  headers?: Record<string, string>;
}) {
  return centralApi<LBRule>("/api/admin/lb/rules", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function deleteLBRule(ruleId: string) {
  return centralApi<{ ok: boolean }>(`/api/admin/lb/rules/${ruleId}`, {
    method: "DELETE",
  });
}

export async function syncLBWithOrchestrator() {
  return centralApi<{ ok: boolean; synced: number; removed: number }>("/api/admin/lb/sync", {
    method: "POST",
  });
}

export async function drainLBInstance(instanceId: string) {
  return centralApi<{ ok: boolean }>(`/api/admin/lb/drain/${instanceId}`, {
    method: "POST",
  });
}

export async function getLBStats() {
  return centralApi<{ pools: any[] }>("/api/admin/lb/stats");
}

export async function getLBNginxConfig() {
  const token = getToken("nso_api_token");
  const resp = await fetch(`${API_BASE}/api/admin/lb/nginx/config`, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  });
  if (!resp.ok) throw new Error(`${resp.status}`);
  return resp.text();
}

// ── Infrastructure: Database ──────────────────────────────────

export async function listDatabases(projectId: string) {
  return centralApi<{ databases: any[]; count: number }>(`/api/projects/${projectId}/databases`);
}

export async function createDatabase(projectId: string, opts: { name: string; instance_id: string; engine?: string; version?: string }) {
  return centralApi<any>(`/api/projects/${projectId}/databases`, {
    method: "POST",
    body: JSON.stringify(opts),
  });
}

export async function getDatabase(projectId: string, dbId: string) {
  return centralApi<any>(`/api/projects/${projectId}/databases/${dbId}`);
}

export async function deleteDatabase(projectId: string, dbId: string) {
  return centralApi<{ ok: boolean }>(`/api/projects/${projectId}/databases/${dbId}`, { method: "DELETE" });
}

export async function queryDatabase(projectId: string, dbId: string, sql: string) {
  return centralApi<{ ok: boolean; rows?: any[]; row_count?: number; error?: string }>(`/api/projects/${projectId}/databases/${dbId}/query`, {
    method: "POST",
    body: JSON.stringify({ sql }),
  });
}

export async function getDatabaseStatus(projectId: string, dbId: string) {
  return centralApi<{ state: string; size_bytes?: number; size_mb?: number; connections?: number }>(`/api/projects/${projectId}/databases/${dbId}/status`);
}

// ── Infrastructure: Storage ──────────────────────────────────

export async function listBuckets(projectId: string) {
  return centralApi<{ buckets: any[]; count: number }>(`/api/projects/${projectId}/storage/buckets`);
}

export async function createBucket(projectId: string, name: string, publicAccess = false) {
  return centralApi<any>(`/api/projects/${projectId}/storage/buckets`, {
    method: "POST",
    body: JSON.stringify({ name, public_access: publicAccess }),
  });
}

export async function deleteBucket(projectId: string, bucketId: string) {
  return centralApi<{ ok: boolean }>(`/api/projects/${projectId}/storage/buckets/${bucketId}`, { method: "DELETE" });
}

export async function listBucketObjects(projectId: string, bucketId: string, prefix = "") {
  const qs = prefix ? `?prefix=${encodeURIComponent(prefix)}` : "";
  return centralApi<{ objects: any[]; count: number }>(`/api/projects/${projectId}/storage/buckets/${bucketId}/objects${qs}`);
}

export async function uploadObject(projectId: string, bucketId: string, file: File, key?: string) {
  const token = getToken("nso_api_token");
  const form = new FormData();
  form.append("file", file);
  const qs = key ? `?key=${encodeURIComponent(key)}` : `?key=${encodeURIComponent(file.name)}`;
  const resp = await fetch(`${API_BASE}/api/projects/${projectId}/storage/buckets/${bucketId}/upload${qs}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(parseErrorText(resp.status, text));
  }
  return resp.json();
}

export async function downloadObject(projectId: string, bucketId: string, key: string): Promise<Blob> {
  const token = getToken("nso_api_token");
  const resp = await fetch(`${API_BASE}/api/projects/${projectId}/storage/buckets/${bucketId}/download/${encodeURIComponent(key)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) throw new Error(`Download failed: ${resp.status}`);
  return resp.blob();
}

export async function deleteObject(projectId: string, bucketId: string, key: string) {
  return centralApi<{ ok: boolean }>(`/api/projects/${projectId}/storage/buckets/${bucketId}/objects/${encodeURIComponent(key)}`, { method: "DELETE" });
}

/* ═══════════════════════════════════════════
   DEPLOY AGENT (AI chat-based deploy)
   ═══════════════════════════════════════════ */

export interface DeployThread {
  id: string;
  project_id: string;
  user_id: string;
  workspace: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
  messages?: DeployMessage[];
}

export interface DeployMessage {
  id: string;
  thread_id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  tool_calls: string;
  tool_results: string;
  metadata: string;
  created_at: string;
}

export async function createDeployThread(projectId: string, workspace = "", title = "") {
  return centralApi<DeployThread>(`/api/projects/${projectId}/deploy-agent/threads`, {
    method: "POST",
    body: JSON.stringify({ workspace, title }),
  });
}

export async function updateDeployThread(projectId: string, threadId: string, data: { title?: string; workspace?: string }) {
  return centralApi<{ ok: boolean }>(`/api/projects/${projectId}/deploy-agent/threads/${threadId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function listDeployThreads(projectId: string) {
  return centralApi<{ threads: DeployThread[]; count: number }>(`/api/projects/${projectId}/deploy-agent/threads`);
}

export async function getDeployThread(projectId: string, threadId: string) {
  return centralApi<DeployThread & { messages: DeployMessage[] }>(`/api/projects/${projectId}/deploy-agent/threads/${threadId}`);
}

export async function deleteDeployThread(projectId: string, threadId: string) {
  return centralApi<{ ok: boolean }>(`/api/projects/${projectId}/deploy-agent/threads/${threadId}`, { method: "DELETE" });
}

export function streamDeployAgent(projectId: string, threadId: string, message: string): {
  eventSource: AbortController;
  response: Promise<Response>;
} {
  const controller = new AbortController();
  const token = getToken("nso_api_token");
  const response = fetch(`${API_BASE}/api/projects/${projectId}/deploy-agent/threads/${threadId}/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ message }),
    signal: controller.signal,
  });
  return { eventSource: controller, response };
}

/* ═══════════════════════════════════════════
   PROJECT MEMBERS
   ═══════════════════════════════════════════ */

export interface ProjectMember {
  id: string;
  user_id: string;
  role: string;
  joined_at: string;
  email: string;
  name: string;
}

export interface ProjectInvite {
  id: string;
  project_id: string;
  join_code: string;
  role: string;
  max_uses: number;
  uses: number;
  created_by: string;
  expires_at: string;
  created_at: string;
}

export async function listProjectMembers(projectId: string) {
  return centralApi<{ members: ProjectMember[] }>(`/api/projects/${projectId}/members`);
}

export async function createProjectInvite(projectId: string, opts: { role?: string; max_uses?: number; expires_hours?: number } = {}) {
  return centralApi<{ ok: boolean; invite: ProjectInvite }>(`/api/projects/${projectId}/members/invite`, {
    method: "POST",
    body: JSON.stringify(opts),
  });
}

export async function listProjectInvites(projectId: string) {
  return centralApi<{ invites: ProjectInvite[] }>(`/api/projects/${projectId}/members/invites`);
}

export async function revokeProjectInvite(projectId: string, inviteId: string) {
  return centralApi<{ ok: boolean }>(`/api/projects/${projectId}/members/invites/${inviteId}`, { method: "DELETE" });
}

export async function updateMemberRole(projectId: string, userId: string, role: string) {
  return centralApi<{ ok: boolean }>(`/api/projects/${projectId}/members/${userId}`, {
    method: "PATCH",
    body: JSON.stringify({ role }),
  });
}

export async function removeProjectMember(projectId: string, userId: string) {
  return centralApi<{ ok: boolean }>(`/api/projects/${projectId}/members/${userId}`, { method: "DELETE" });
}

export async function previewProjectInvite(code: string) {
  return centralApi<{ project_name: string; role: string; expired: boolean; uses_remaining: number | null }>(`/api/join/project/${code}`);
}

export async function redeemProjectInvite(code: string) {
  return centralApi<{ ok: boolean; member: ProjectMember }>(`/api/join/project/${code}`, { method: "POST" });
}

