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

/** Extract a human-readable message from error response text. */
function parseErrorText(status: number, text: string): string {
  // Try JSON first (FastAPI returns {"detail": "..."})
  try {
    const json = JSON.parse(text);
    if (json.detail) return json.detail;
    if (json.error) return json.error;
    if (json.message) return json.message;
  } catch {}
  // Strip HTML (e.g. Cloudflare 502 pages)
  if (text.includes("<html") || text.includes("<!DOCTYPE")) {
    if (status === 502) return "Bad Gateway — the server is unreachable or restarting";
    if (status === 503) return "Service unavailable — the server may be starting up";
    if (status === 504) return "Gateway timeout — the server did not respond in time";
    return `HTTP ${status} — server returned an error page`;
  }
  // Truncate long plain-text errors
  return text.length > 300 ? text.slice(0, 300) + "..." : text;
}

/** Call the central API (uses nso_api_token). */
export function centralApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  return apiCall<T>(path, options, "nso_api_token");
}

// Auth — dual login: agent + central API
export async function login(email: string, password: string) {
  // Login to agent (for exec, files, deploy)
  const agentRes = await apiCall<{ token: string; email: string; role: string }>("/agent/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  // Login to central API (for projects, workspaces, instances)
  try {
    const apiRes = await apiCall<{ token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    if (typeof window !== "undefined") {
      localStorage.setItem("nso_api_token", apiRes.token);
    }
  } catch {
    // Agent-only mode if central API uses different password
  }
  return agentRes;
}

// API health
export async function getApiHealth() {
  return apiCall<{ status: string; version: string; uptime_seconds: number }>("/api/health");
}

// Agent health
export async function getAgentHealth() {
  return apiCall<{ service: string; status: string; version: string; features: string[] }>("/agent/health");
}

// Files
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

// Exec
export async function execCommand(command: string, workingDir = "/opt/setupo", timeout = 60) {
  return apiCall<{ stdout: string; stderr: string; exit_code: number; timed_out: boolean }>("/agent/exec/", {
    method: "POST",
    body: JSON.stringify({ command, working_dir: workingDir, timeout }),
  });
}

// Service management
export async function manageService(action: string, name: string) {
  return apiCall<any>(`/agent/exec/service?action=${action}&name=${name}`, { method: "POST" });
}

// ─── Agent: Secrets management ───

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

// ─── Central API: Projects & Workspaces ───

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

// ─── Central API: Instances ───

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

// ─── Central API: Zar (deploy) ───

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

// ─── Central API: Plugins ───

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

// Admin: Plugin catalog management
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

// Agent deploy endpoints (direct agent calls, routed via /agent/ prefix by nginx)
export async function getDeployStatus() {
  return apiCall<any>("/agent/deploy/current");
}

export async function getDeploySnapshots() {
  return apiCall<{ target: string; snapshots: string[] }>("/agent/deploy/snapshots");
}
