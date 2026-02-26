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
  const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${resp.status}: ${text}`);
  }
  return resp.json();
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

// ─── Central API: Projects & Workspaces ───

export async function listProjects() {
  return centralApi<{ projects: any[] }>("/api/projects");
}

export async function listWorkspaces(projectId: string) {
  return centralApi<{ workspaces: any[] }>(`/api/projects/${projectId}/workspaces`);
}

export async function createWorkspace(projectId: string, name: string, type = "custom", description = "") {
  return centralApi<any>(`/api/projects/${projectId}/workspaces`, {
    method: "POST",
    body: JSON.stringify({ name, type, description }),
  });
}

export async function deleteWorkspace(projectId: string, name: string) {
  return centralApi<any>(`/api/projects/${projectId}/workspaces/${name}`, {
    method: "DELETE",
  });
}

export async function getWorkspaceFiles(projectId: string, name: string) {
  return centralApi<{ files: any[] }>(`/api/projects/${projectId}/workspaces/${name}/files`);
}

// ─── Central API: Instances ───

export async function listInstances(projectId: string) {
  return centralApi<{ instances: any[] }>(`/api/projects/${projectId}/instances`);
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
