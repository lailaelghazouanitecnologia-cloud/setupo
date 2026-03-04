// z86 dashboard talks to NSO central API at nso.dev
// In production, nginx proxies /api/* to the NSO central server

const API_BASE = typeof window !== "undefined" ? window.location.origin : "";

function getToken(): string | null {
  return typeof window !== "undefined" ? localStorage.getItem("z86_token") : null;
}

export async function apiCall<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (err: any) {
    throw new Error(`Network error: ${err.message || "Could not reach the server"}`);
  }

  if (!resp.ok) {
    const text = await resp.text();
    if (
      resp.status === 401 &&
      typeof window !== "undefined" &&
      !path.includes("/auth/login") &&
      !path.includes("/auth/register")
    ) {
      localStorage.removeItem("z86_token");
      localStorage.removeItem("z86_email");
      localStorage.removeItem("z86_role");
      window.location.reload();
    }
    throw new Error(`${resp.status}: ${parseError(resp.status, text)}`);
  }
  return resp.json();
}

function parseError(status: number, text: string): string {
  try {
    const json = JSON.parse(text);
    if (json.detail) return json.detail;
    if (json.error) return json.error;
  } catch {}
  if (status === 502) return "Bad Gateway — server unreachable";
  if (status === 503) return "Service unavailable";
  return text.length > 300 ? text.slice(0, 300) + "..." : text;
}

// ── Auth ──────────────────────────────────────────────

export async function login(email: string, password: string) {
  return apiCall<{ token: string; email: string; role: string }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function register(email: string, password: string, name = "") {
  return apiCall<{ token: string; email: string; role: string; user_id: string }>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, name }),
  });
}

export async function getMe() {
  return apiCall<{ email: string; role: string; name?: string; user_id: string }>("/api/auth/me");
}

// ── Projects (to find user's project with z86 storage) ──

export async function getProjects() {
  return apiCall<any[]>("/api/projects");
}

// ── Z86 Storage ──────────────────────────────────────

export interface Z86StorageInfo {
  bucket: string;
  access_key_id: string;
  endpoint: string;
  status: string;
}

export interface Z86BucketInfo {
  name: string;
  owner_id: string;
  region: string;
  object_count: number;
  total_size: number;
  created_at: string;
}

export interface Z86ObjectInfo {
  key: string;
  size: number;
  content_type: string;
  sha256: string;
  updated_at: string;
}

export interface Z86KeyInfo {
  id: string;
  access_key_id: string;
  label: string;
  active: boolean;
  created_at: string;
  allowed_buckets?: string;
}

export interface Z86StorageStats {
  total_buckets: number;
  total_objects: number;
  total_size_bytes: number;
  disk_used_bytes: number;
  total_keys: number;
}

// Project-scoped z86 routes
export async function getStorageInfo(projectId: string) {
  return apiCall<Z86StorageInfo>(`/api/projects/${projectId}/z86/storage`);
}

export async function provisionStorage(projectId: string) {
  return apiCall<Z86StorageInfo>(`/api/projects/${projectId}/z86/storage/provision`, { method: "POST" });
}

export async function rotateStorageKey(projectId: string) {
  return apiCall<{ access_key_id: string; secret_access_key: string }>(
    `/api/projects/${projectId}/z86/storage/keys/rotate`,
    { method: "POST" },
  );
}

// Admin z86 routes (for admin users)
export async function getZ86Overview() {
  return apiCall<{
    configured: boolean;
    endpoint?: string;
    health?: any;
    stats?: Z86StorageStats;
    buckets?: Z86BucketInfo[];
    total_keys?: number;
  }>("/api/admin/z86/overview");
}

export async function getZ86Buckets() {
  return apiCall<Z86BucketInfo[]>("/api/admin/z86/buckets");
}

export async function getZ86BucketObjects(bucket: string, prefix = "") {
  const q = prefix ? `?prefix=${encodeURIComponent(prefix)}` : "";
  return apiCall<Z86ObjectInfo[]>(`/api/admin/z86/buckets/${bucket}/objects${q}`);
}

export async function deleteZ86Object(bucket: string, key: string) {
  return apiCall<{ ok: boolean }>(
    `/api/admin/z86/buckets/${encodeURIComponent(bucket)}/objects/${encodeURIComponent(key)}`,
    { method: "DELETE" },
  );
}

// ── Billing plans (public) ──
export async function getBillingPlans() {
  return apiCall<any[]>("/api/billing/plans");
}
