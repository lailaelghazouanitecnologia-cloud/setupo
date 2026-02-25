const API_BASE = typeof window !== "undefined" ? window.location.origin : "";

export async function apiCall<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("nso_token") : null;
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

// Auth
export async function login(email: string, password: string) {
  return apiCall<{ token: string; email: string; role: string }>("/agent/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
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
