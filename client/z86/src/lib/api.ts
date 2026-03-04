const API_BASE = typeof window !== "undefined" && window.location.hostname !== "localhost"
  ? `https://${window.location.hostname}`
  : "http://localhost:8082";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("z86_token");
}

export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (resp.status === 401 && path !== "/auth/login" && path !== "/auth/register") {
    localStorage.removeItem("z86_token");
    window.location.reload();
    throw new Error("Session expired");
  }

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || err.message || err.error || "Request failed");
  }

  return resp.json();
}

// Auth
export const authApi = {
  register: (email: string, password: string, name: string) =>
    api<{ token: string; user: any }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, name }),
    }),
  login: (email: string, password: string) =>
    api<{ token: string; user: any }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => api<any>("/auth/me"),
  updateProfile: (data: { name?: string; email?: string }) =>
    api<any>("/auth/profile", { method: "PATCH", body: JSON.stringify(data) }),
  changePassword: (current: string, newPwd: string) =>
    api<any>("/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password: current, new_password: newPwd }),
    }),
};

// Dashboard
export const dashApi = {
  overview: () => api<any>("/api/overview"),
  // Buckets
  listBuckets: () => api<any[]>("/api/buckets"),
  createBucket: (name: string) => {
    const fd = new FormData();
    fd.append("name", name);
    return api<any>("/api/buckets", { method: "POST", body: fd });
  },
  getBucket: (name: string) => api<any>(`/api/buckets/${name}`),
  deleteBucket: (name: string) => api<any>(`/api/buckets/${name}`, { method: "DELETE" }),
  // Objects
  listObjects: (bucket: string, prefix = "", maxKeys = 100) =>
    api<any>(`/api/buckets/${bucket}/objects?prefix=${encodeURIComponent(prefix)}&max_keys=${maxKeys}`),
  uploadObject: (bucket: string, key: string, file: File) => {
    const fd = new FormData();
    fd.append("key", key);
    fd.append("file", file);
    return api<any>(`/api/buckets/${bucket}/upload`, { method: "POST", body: fd });
  },
  deleteObject: (bucket: string, key: string) =>
    api<any>(`/api/buckets/${bucket}/objects/${key}`, { method: "DELETE" }),
  // Keys
  listKeys: () => api<any[]>("/api/keys"),
  createKey: (label: string, allowedBuckets = "") => {
    const fd = new FormData();
    fd.append("label", label);
    fd.append("allowed_buckets", allowedBuckets);
    return api<any>("/api/keys", { method: "POST", body: fd });
  },
  deleteKey: (id: string) => api<any>(`/api/keys/${id}`, { method: "DELETE" }),
  // Usage
  usage: () => api<any>("/api/usage"),
};
