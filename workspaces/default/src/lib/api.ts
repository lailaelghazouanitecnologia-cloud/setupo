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

// Health
export const getHealth = () => request("GET", "/health");

// Capsules
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

// Environments
export const listEnvironments = () =>
  request<{ environments: Environment[] }>("GET", "/envs/");

export const createEnvironment = (data: CreateEnvInput) =>
  request("POST", "/envs/", data);

export const destroyEnvironment = (id: string) =>
  request("DELETE", `/envs/${id}`);

// Pipelines
export const listPipelines = () =>
  request<{ pipelines: Pipeline[] }>("GET", "/pipelines/");

export const runPipeline = (name: string, steps: PipelineStep[]) =>
  request("POST", "/pipelines/", { name, steps });

// Protocol
export const execProtocol = (code: string) =>
  request<{ results: unknown[] }>("POST", "/commands/protocol", { code });

// Types
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
