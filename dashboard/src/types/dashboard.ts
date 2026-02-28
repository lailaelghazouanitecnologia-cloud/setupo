export type DashboardView = "inbox" | "instances" | "projects" | "deploy" | "secrets" | "plugins" | "billing" | "settings";

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
