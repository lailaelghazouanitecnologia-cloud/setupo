const API_BASE = "/api";

function getToken(): string {
  return localStorage.getItem("mms_token") || "";
}

export function setToken(token: string) {
  localStorage.setItem("mms_token", token.trim());
}

export function hasToken(): boolean {
  return !!getToken();
}

async function request<T = unknown>(
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const opts: RequestInit = {
    method,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getToken()}`,
    },
  };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(`${API_BASE}${path}`, opts);
  if (res.status === 401) {
    localStorage.removeItem("mms_token");
    window.location.reload();
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: res.statusText }));
    throw new Error(err.message || err.error || res.statusText);
  }
  return res.json();
}

// Auth
export async function login(
  email: string,
  password: string
): Promise<{ token: string; email: string; role: string }> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: res.statusText }));
    throw new Error(err.detail || err.message || "Login failed");
  }
  const data = await res.json();
  setToken(data.token);
  return data;
}

// Health
export const getHealth = () => request("GET", "/health");

// Capsules (legacy)
export const listCapsules = (state?: string) =>
  request<{ capsules: Capsule[]; count: number }>(
    "GET",
    `/capsules/${state ? `?state=${state}` : ""}`
  );

export const createCapsule = (data: CreateCapsuleInput) =>
  request<{ capsule: Capsule }>("POST", "/capsules/", data);

export const startCapsule = (id: string) =>
  request<{ capsule: Capsule }>("POST", `/capsules/${id}/start`);

export const stopCapsule = (id: string) =>
  request<{ capsule: Capsule }>("POST", `/capsules/${id}/stop`);

export const destroyCapsule = (id: string) =>
  request("DELETE", `/capsules/${id}`);

export const getCapsuleLogs = (id: string) =>
  request<{ logs: LogEntry[] }>("GET", `/capsules/${id}/logs`);

export const execInCapsule = (capsuleId: string, command: string) =>
  request<{ result: ExecResult }>("POST", "/commands/exec", {
    capsule_id: capsuleId,
    command,
  });

// Services
export const listServices = () =>
  request<{ services: Service[]; count: number }>("GET", "/services/");

export const createService = (data: CreateServiceInput) =>
  request("POST", "/services/", data);

export const stopService = (name: string) =>
  request("POST", `/services/${name}/stop`);

export const restartService = (name: string) =>
  request("POST", `/services/${name}/restart`);

export const deleteService = (name: string) =>
  request("DELETE", `/services/${name}`);

export const getServiceLogs = (name: string, tail?: number) =>
  request<{ name: string; logs: string[]; total: number }>(
    "GET",
    `/services/${name}/logs${tail ? `?tail=${tail}` : ""}`
  );

// File System
export const listDir = (path?: string) =>
  request<{ path: string; items: FSItem[]; count: number }>(
    "GET",
    `/fs/list${path ? `?path=${encodeURIComponent(path)}` : ""}`
  );

export const readFile = (path: string) =>
  request<{ path: string; content: string; size: number }>(
    "GET",
    `/fs/read?path=${encodeURIComponent(path)}`
  );

export const writeFile = (path: string, content: string) =>
  request("POST", "/fs/write", { path, content });

export const deleteFile = (path: string) =>
  request("DELETE", `/fs/delete?path=${encodeURIComponent(path)}`);

export const mkDir = (path: string) =>
  request("POST", "/fs/mkdir", { path });

// Workspaces
export const listWorkspaces = () =>
  request<{ workspaces: Workspace[]; count: number }>("GET", "/workspaces/");

export const cloneWorkspace = (
  repo: string,
  branch?: string,
  name?: string
) => request("POST", "/workspaces/clone", { repo, branch: branch || "main", name });

export const pullWorkspace = (name: string) =>
  request("POST", `/workspaces/${name}/pull`);

export const deleteWorkspace = (name: string) =>
  request("DELETE", `/workspaces/${name}`);

// Environments (legacy)
export const listEnvironments = () =>
  request<{ environments: Environment[] }>("GET", "/envs/");

export const createEnvironment = (data: CreateEnvInput) =>
  request("POST", "/envs/", data);

export const destroyEnvironment = (id: string) =>
  request("DELETE", `/envs/${id}`);

// Pipelines (legacy)
export const listPipelines = () =>
  request<{ pipelines: Pipeline[] }>("GET", "/pipelines/");

export const runPipeline = (name: string, steps: PipelineStep[]) =>
  request("POST", "/pipelines/", { name, steps });

// Protocol (legacy)
export const execProtocol = (code: string) =>
  request<{ results: unknown[] }>("POST", "/commands/protocol", { code });

// Types - Services
export interface Service {
  id: string;
  name: string;
  command: string;
  port: number | null;
  pid: number | null;
  status: string;
  working_dir: string;
  started_at: string | null;
  output_lines: number;
}

export interface CreateServiceInput {
  name: string;
  command: string;
  working_dir?: string;
  port?: number;
  env?: Record<string, string>;
}

// Types - File System
export interface FSItem {
  name: string;
  path: string;
  type: "file" | "dir" | "unknown";
  size: number | null;
  modified: number | null;
  permissions: string;
}

// Types - Workspaces
export interface Workspace {
  name: string;
  path: string;
  is_git: boolean;
  modified: number;
  repo?: string;
  branch?: string;
}

// Types - Capsules (legacy)
export interface Capsule {
  id: string;
  name: string;
  state: string;
  manifest: {
    name: string;
    runtime: string;
    isolation: string;
    entrypoint: string;
    ports: number[];
  };
  container_id?: string;
  ip?: string;
  created_at: string;
  error?: string;
}

export interface CreateCapsuleInput {
  name: string;
  runtime: string;
  isolation: string;
  entrypoint: string;
  code?: string;
  dependencies: string[];
  env?: Record<string, string>;
  ports?: number[];
}

export interface Environment {
  id: string;
  name: string;
  runtime: string;
  version?: string;
  packages?: string;
  created_at: string;
}

export interface CreateEnvInput {
  name: string;
  runtime: string;
  packages: string[];
}

export interface Pipeline {
  id: string;
  name: string;
  state: string;
  steps: string;
  results: string;
  created_at: string;
}

export interface PipelineStep {
  capsule: string;
  params: Record<string, string>;
  depends_on?: string[];
}

export interface LogEntry {
  level: string;
  message: string;
  created_at: string;
  capsule_id: string;
}

export interface ExecResult {
  stdout: string;
  stderr: string;
  exit_code: number;
  error?: string;
}
