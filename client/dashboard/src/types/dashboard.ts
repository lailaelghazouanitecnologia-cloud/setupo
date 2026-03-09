export type DashboardView = "inbox" | "infrastructure" | "projects" | "workspaces" | "deploy" | "secrets" | "addons" | "billing" | "settings" | "admin";

export type AddonTab = "connectors" | "plugins" | "marketplace";

export interface Instance {
  id: string;
  label: string;
  region: string;
  plan: string;
  main_ip: string;
  status: string;
  power_status: string;
  os: string;
  ram: number;
  vcpu_count: number;
  date_created: string;
  tag: string;
}

export interface FSItem {
  name: string;
  path: string;
  type: "file" | "dir" | "link" | "unknown";
  size?: number;
  modified?: number;
  permissions: string;
}

export interface ExecResult {
  stdout: string;
  stderr: string;
  exit_code: number;
  timed_out: boolean;
}

export interface HealthInfo {
  service: string;
  status: string;
  version: string;
  tracked_instances: number;
  features: string[];
}

export interface ApiHealth {
  status: string;
  version: string;
  uptime_seconds: number;
  platform: string;
}

export interface Project {
  name: string;
  path: string;
  created?: number;
}

export interface Secret {
  key: string;
  value?: string;
  masked: boolean;
}

export interface ComputeNode {
  id: string;
  project_id: string;
  label: string;
  provider: string;
  instance_id: string | null;
  ip: string;
  agent_port: number;
  agent_reachable: boolean;
  status: string;
  role: string;
  cpu_cores: number;
  mem_total_mb: number;
  disk_total_gb: number;
  cpu_allocated: number;
  mem_allocated_mb: number;
  cpu_used_percent: number;
  mem_used_percent: number;
  disk_used_percent: number;
  load_1m: number;
  reserved_for: string | null;
  max_services: number;
  tags: string;
  capabilities: string;
  labels: string;
  agent_version: string;
  last_heartbeat: string;
  created_at: string;
  updated_at: string;
}
