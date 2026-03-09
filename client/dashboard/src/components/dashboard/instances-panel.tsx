"use client";

import { useState, useEffect, useRef } from "react";
import {
  Server, RefreshCw, Play, Square, Trash2, Plus,
  Activity, Monitor, Terminal, FolderOpen,
  Send, RotateCcw, Power, FileText, Loader, Globe,
  Cpu, Pause, ShieldCheck, ShieldOff, Download, ChevronRight,
} from "lucide-react";
import { useDashboardStore } from "@/stores/dashboard-store";
import { formatSize, stateColor, stateBadgeClass } from "@/lib/format";
import {
  listProjects, createProject as apiCreateProject,
  listInstances, createInstance, deleteInstance,
  stopInstance, startInstance, execOnInstance,
  execCommand, manageService, listFiles,
  listWorkspaces, getInstanceMetrics,
  listComputeNodes, registerComputeNode, deleteComputeNode,
  drainNode, cordonNode, uncordonNode, syncInstancesToNodes,
} from "@/lib/api/client";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";

type Tab = "instances" | "services";

interface Instance {
  id: string;
  label: string;
  type: string;
  state: string;
  region: string;
  plan: string;
  domain: string | null;
  provider_id: string;
  ip: string | null;
  created_at: string;
  metadata?: {
    source_type?: string;
    git_url?: string;
    git_branch?: string;
    zar_name?: string;
    app_ready_key?: string;
  };
}

/* ═══════════════════════════════════════════
   CONSTANTS — regions, plans, types
   ═══════════════════════════════════════════ */

const REGIONS = [
  { id: "ewr", city: "New Jersey", country: "US" },
  { id: "ord", city: "Chicago", country: "US" },
  { id: "dfw", city: "Dallas", country: "US" },
  { id: "lax", city: "Los Angeles", country: "US" },
  { id: "atl", city: "Atlanta", country: "US" },
  { id: "mia", city: "Miami", country: "US" },
  { id: "ams", city: "Amsterdam", country: "NL" },
  { id: "lhr", city: "London", country: "GB" },
  { id: "fra", city: "Frankfurt", country: "DE" },
  { id: "cdg", city: "Paris", country: "FR" },
  { id: "mad", city: "Madrid", country: "ES" },
  { id: "nrt", city: "Tokyo", country: "JP" },
  { id: "sgp", city: "Singapore", country: "SG" },
] as const;

const PLANS = [
  { id: "vc2-1c-1gb", cpu: 1, ram: "1 GB", disk: "25 GB", price: "$5/mo" },
  { id: "vc2-1c-2gb", cpu: 1, ram: "2 GB", disk: "55 GB", price: "$10/mo" },
  { id: "vc2-2c-4gb", cpu: 2, ram: "4 GB", disk: "80 GB", price: "$20/mo" },
  { id: "vc2-4c-8gb", cpu: 4, ram: "8 GB", disk: "160 GB", price: "$40/mo" },
  { id: "vc2-6c-16gb", cpu: 6, ram: "16 GB", disk: "320 GB", price: "$80/mo" },
] as const;


const SYSTEM_SERVICES = [
  { name: "nso", display: "nso", description: "API server" },
  { name: "nso-agent", display: "nso-agent", description: "Agent" },
  { name: "nginx", display: "nginx", description: "Reverse proxy" },
];

/* ═══════════════════════════════════════════
   MAIN PANEL
   ═══════════════════════════════════════════ */

export function InstancesPanel() {
  const [tab, setTab] = useState<Tab>("instances");

  return (
    <div>
      <div className="tab-bar">
        <button className={`tab-item ${tab === "instances" ? "active" : ""}`} onClick={() => setTab("instances")}>
          <Server className="h-3.5 w-3.5" />
          <span>Instances</span>
        </button>
        <button className={`tab-item ${tab === "services" ? "active" : ""}`} onClick={() => setTab("services")}>
          <Activity className="h-3.5 w-3.5" />
          <span>Services</span>
        </button>
      </div>
      {tab === "instances" ? <InstancesTab /> : <ServicesTab />}
    </div>
  );
}

/* ═══════════════════════════════════════════
   CREATE INSTANCE FORM
   ═══════════════════════════════════════════ */

interface CreateFormProps {
  projectId: string;
  onCreated: () => void;
  onCancel: () => void;
}

type SourceType = "empty" | "repository" | "zar";

function CreateInstanceForm({ projectId, onCreated, onCancel }: CreateFormProps) {
  const [label, setLabel] = useState("");
  const [region, setRegion] = useState("mad");
  const [plan, setPlan] = useState("vc2-1c-1gb");
  const [domain, setDomain] = useState("");
  const [sourceType, setSourceType] = useState<SourceType>("empty");
  const [gitUrl, setGitUrl] = useState("");
  const [gitBranch, setGitBranch] = useState("main");
  const [zarName, setZarName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const sanitizedLabel = label.trim().replace(/[^a-zA-Z0-9_-]/g, "-");

  const validate = (): string | null => {
    if (sanitizedLabel.length > 0 && sanitizedLabel.length < 2) {
      return "Label must be at least 2 characters";
    }
    if (sanitizedLabel.length > 64) {
      return "Label must be under 64 characters";
    }
    if (domain && !/^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(domain.trim())) {
      return "Invalid domain format (e.g. app.example.com)";
    }
    if (!REGIONS.some((r) => r.id === region)) {
      return "Invalid region selected";
    }
    if (!PLANS.some((p) => p.id === plan)) {
      return "Invalid plan selected";
    }
    if (sourceType === "repository" && !gitUrl.trim()) {
      return "Git URL is required for repository source";
    }
    if (sourceType === "zar" && !zarName.trim()) {
      return "Package name is required for .zar source";
    }
    return null;
  };

  const handleCreate = async () => {
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    setCreating(true);
    setError("");

    try {
      await createInstance(projectId, {
        label: sanitizedLabel || undefined,
        region,
        plan,
        domain: domain.trim() || undefined,
        source_type: sourceType === "empty" ? undefined : sourceType,
        git_url: sourceType === "repository" ? gitUrl.trim() : undefined,
        git_branch: sourceType === "repository" ? gitBranch.trim() || "main" : undefined,
        zar_name: sourceType === "zar" ? zarName.trim() : undefined,
      });
      onCreated();
    } catch (e: any) {
      const msg = e.message || "Failed to create instance";
      setError(msg.includes("401") ? "Not authorized — check your credentials" : msg);
    }

    setCreating(false);
  };

  const selectedPlan = PLANS.find((p) => p.id === plan);
  const selectedRegion = REGIONS.find((r) => r.id === region);

  return (
    <div style={{
      border: "1px solid var(--border)",
      borderRadius: 8,
      padding: 16,
      marginBottom: 16,
      background: "var(--sidebar-background)",
    }}>
      <div style={{ fontWeight: 600, fontSize: "var(--font-sm)", marginBottom: 12 }}>
        New Instance
      </div>

      {error && (
        <div style={{
          padding: "8px 12px",
          fontSize: "var(--font-xs)",
          color: "var(--color-red)",
          background: "rgba(239,68,68,0.08)",
          borderRadius: 6,
          marginBottom: 12,
        }}>
          {error}
        </div>
      )}

      {/* Row 1: Label */}
      <div style={{ marginBottom: 10 }}>
        <label style={labelStyle}>Label</label>
        <input
          className="proj-input"
          type="text"
          placeholder="my-server (optional)"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Escape") onCancel(); }}
          style={{ width: "100%" }}
          autoFocus
        />
      </div>

      {/* Row 2: Source selector */}
      <div style={{ marginBottom: 10 }}>
        <label style={labelStyle}>Source</label>
        <div style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
          {(["empty", "repository", "zar"] as SourceType[]).map((st) => (
            <button
              key={st}
              className={`scope-chip ${sourceType === st ? "active" : ""}`}
              onClick={() => setSourceType(st)}
              type="button"
            >
              {st === "empty" && <Server className="h-3 w-3" />}
              {st === "repository" && <FolderOpen className="h-3 w-3" />}
              {st === "zar" && <FileText className="h-3 w-3" />}
              <span>{st === "repository" ? "GitHub" : st === "zar" ? ".zar" : "Empty"}</span>
            </button>
          ))}
        </div>

        {/* Source-specific fields */}
        {sourceType === "repository" && (
          <div style={{ display: "flex", gap: 8 }}>
            <div style={{ flex: 2 }}>
              <input
                className="proj-input"
                type="text"
                placeholder="https://github.com/user/repo.git"
                value={gitUrl}
                onChange={(e) => setGitUrl(e.target.value)}
                style={{ width: "100%" }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <input
                className="proj-input"
                type="text"
                placeholder="branch (main)"
                value={gitBranch}
                onChange={(e) => setGitBranch(e.target.value)}
                style={{ width: "100%" }}
              />
            </div>
          </div>
        )}

        {sourceType === "zar" && (
          <input
            className="proj-input"
            type="text"
            placeholder="workspace name"
            value={zarName}
            onChange={(e) => setZarName(e.target.value)}
            style={{ width: "100%" }}
          />
        )}
      </div>

      {/* Row 3: Region + Plan */}
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Region</label>
          <Select value={region} onValueChange={setRegion}>
            <SelectTrigger style={{ width: "100%" }}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {REGIONS.map((r) => (
                <SelectItem key={r.id} value={r.id}>{r.city}, {r.country} ({r.id})</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Plan</label>
          <Select value={plan} onValueChange={setPlan}>
            <SelectTrigger style={{ width: "100%" }}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PLANS.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.cpu}vCPU / {p.ram} / {p.disk} — {p.price}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Row 4: Domain (optional) */}
      <div style={{ marginBottom: 12 }}>
        <label style={labelStyle}>Domain (optional)</label>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Globe className="h-3 w-3" style={{ color: "var(--muted-foreground)", flexShrink: 0 }} />
          <input
            className="proj-input"
            type="text"
            placeholder="app.example.com"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCreate();
              if (e.key === "Escape") onCancel();
            }}
            style={{ flex: 1 }}
          />
        </div>
      </div>

      {/* Summary */}
      <div style={{
        fontSize: "var(--font-xxs)",
        color: "var(--muted-foreground)",
        marginBottom: 12,
        fontFamily: "monospace",
      }}>
        {selectedRegion?.city} · {selectedPlan?.cpu}vCPU · {selectedPlan?.ram} · {selectedPlan?.price}
        {sourceType === "repository" && gitUrl ? ` · ${gitUrl.split("/").pop()?.replace(".git", "") || "repo"}` : ""}
        {sourceType === "zar" && zarName ? ` · ${zarName}.zar` : ""}
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: 6 }}>
        <button
          className="deploy-action-btn teal"
          onClick={handleCreate}
          disabled={creating}
          style={{ padding: "5px 14px" }}
        >
          {creating ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Server className="h-3.5 w-3.5" />}
          <span>{creating ? "Provisioning..." : "Create Instance"}</span>
        </button>
        <button
          className="panel-btn-sm"
          onClick={onCancel}
          disabled={creating}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: "var(--font-xxs)",
  color: "var(--muted-foreground)",
  marginBottom: 4,
  textTransform: "uppercase",
  letterSpacing: "0.03em",
};

const selectStyle: React.CSSProperties = {
  width: "100%",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: "6px 8px",
  fontSize: "var(--font-xs)",
};

/* ═══════════════════════════════════════════
   INSTANCES TAB
   ═══════════════════════════════════════════ */

interface InstanceMetrics {
  instance_id: string;
  cpu_percent: number;
  mem_percent: number;
  disk_percent: number;
  load_1m: number;
  uptime: number;
  reachable: boolean;
  collected_at: string;
}

function MetricBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ flex: 1, minWidth: 50 }}>
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        fontSize: 9, color: "var(--muted-foreground)", marginBottom: 2,
      }}>
        <span>{label}</span>
        <span style={{ fontFamily: "monospace", color: value > 80 ? "var(--color-red)" : "inherit" }}>
          {value}%
        </span>
      </div>
      <div style={{
        height: 3, background: "var(--border)", borderRadius: 2, overflow: "hidden",
      }}>
        <div style={{
          height: "100%", width: `${Math.min(value, 100)}%`,
          background: value > 90 ? "var(--color-red)" : value > 70 ? "var(--color-yellow)" : color,
          borderRadius: 2, transition: "width 0.3s ease",
        }} />
      </div>
    </div>
  );
}

function InstanceMetricsBar({ metrics }: { metrics?: InstanceMetrics }) {
  if (!metrics || !metrics.reachable) return null;
  return (
    <div style={{
      display: "flex", gap: 8, padding: "4px 0 0",
      marginTop: 4,
    }}>
      <MetricBar label="CPU" value={metrics.cpu_percent} color="var(--color-blue)" />
      <MetricBar label="RAM" value={metrics.mem_percent} color="var(--color-green)" />
      <MetricBar label="Disk" value={metrics.disk_percent} color="var(--color-yellow)" />
    </div>
  );
}

export function InstancesTab() {
  const activeProject = useDashboardStore((s) => s.activeProject);
  const projectId = activeProject?.id || null;
  const [loading, setLoading] = useState(true);
  const [instances, setInstances] = useState<Instance[]>([]);
  const [metrics, setMetrics] = useState<Record<string, InstanceMetrics>>({});
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Instance | null>(null);
  const [panel, setPanel] = useState<"terminal" | "files" | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const fetchData = async () => {
    if (!projectId) {
      setInstances([]);
      setLoading(false);
      setError("No project selected");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const instRes = await listInstances(projectId, true);
      setInstances(instRes.instances || []);
      // Map metrics by instance_id
      if (instRes.metrics) {
        const m: Record<string, InstanceMetrics> = {};
        for (const item of instRes.metrics) {
          m[item.instance_id] = item;
        }
        setMetrics(m);
      }
    } catch {
      setInstances([]);
    }
    setLoading(false);
  };

  useEffect(() => { fetchData(); }, [projectId]);

  // Auto-refresh every 10s during install, otherwise 30s
  const hasInstalling = instances.some((i) => i.state === "creating" || i.state === "installing");
  useEffect(() => {
    const interval = setInterval(fetchData, hasInstalling ? 10000 : 30000);
    return () => clearInterval(interval);
  }, [hasInstalling]);

  const handleDelete = async (inst: Instance) => {
    if (!projectId) return;
    if (!confirm(`Destroy instance "${inst.label || inst.id}"? This will permanently delete the VPS.`)) return;
    try {
      await deleteInstance(projectId, inst.id);
      setInstances((prev) => prev.filter((i) => i.id !== inst.id));
      if (selected?.id === inst.id) {
        setSelected(null);
        setPanel(null);
      }
    } catch (e: any) {
      alert(e.message || "Delete failed");
    }
  };

  const handleStop = async (inst: Instance) => {
    if (!projectId) return;
    try {
      await stopInstance(projectId, inst.id);
      fetchData();
    } catch (e: any) {
      alert(e.message || "Stop failed");
    }
  };

  const handleStart = async (inst: Instance) => {
    if (!projectId) return;
    try {
      await startInstance(projectId, inst.id);
      fetchData();
    } catch (e: any) {
      alert(e.message || "Start failed");
    }
  };

  // Loading state
  if (loading && instances.length === 0) {
    return (
      <div className="panel-empty">
        <RefreshCw className="h-8 w-8 animate-spin" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-sub">Loading instances...</div>
      </div>
    );
  }

  // Error state — special handling for "no projects"
  if (error) {
    const isNoProjects = error.includes("No projects");
    return (
      <div className="panel-empty">
        <Server className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-title">{isNoProjects ? "No project yet" : "Error"}</div>
        <div className="panel-empty-sub">{isNoProjects ? "Create a project first to manage instances." : error}</div>
        {isNoProjects ? (
          <button className="panel-btn" onClick={async () => {
            try {
              await apiCreateProject("main");
              setError("");
              fetchData();
            } catch (e: any) {
              setError(e.message || "Failed to create project");
            }
          }}>
            <Plus className="h-3.5 w-3.5" />
            <span>Create project</span>
          </button>
        ) : (
          <button className="panel-btn" onClick={fetchData}>
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Retry</span>
          </button>
        )}
      </div>
    );
  }

  // Empty state
  if (instances.length === 0 && !showCreate) {
    return (
      <div className="panel-empty">
        <Server className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-title">No instances</div>
        <div className="panel-empty-sub">Create a VPS instance to get started.</div>
        <button className="panel-btn" onClick={() => setShowCreate(true)}>
          <Plus className="h-3.5 w-3.5" />
          <span>Create Instance</span>
        </button>
      </div>
    );
  }

  return (
    <div style={{ padding: "16px 0" }}>
      {/* Header */}
      <div className="panel-header-row" style={{ padding: "0 0 12px" }}>
        <span className="panel-count">
          {instances.length} instance{instances.length !== 1 ? "s" : ""}
        </span>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="panel-btn-sm" onClick={fetchData} disabled={loading}>
            <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button className="panel-btn-sm" onClick={() => setShowCreate(true)}>
            <Plus className="h-3 w-3" />
            <span>New</span>
          </button>
        </div>
      </div>

      {/* Create form */}
      {showCreate && projectId && (
        <CreateInstanceForm
          projectId={projectId}
          onCreated={() => { setShowCreate(false); fetchData(); }}
          onCancel={() => setShowCreate(false)}
        />
      )}

      {/* Instance cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {instances.map((inst) => (
          <div
            key={inst.id}
            className={`proj-card ${selected?.id === inst.id ? "active" : ""}`}
            onClick={() => { setSelected(inst); setPanel(null); }}
          >
            <div className="proj-card-icon">
              <Server className="h-4 w-4" style={{ color: stateColor(inst.state) }} />
            </div>
            <div className="proj-card-info" style={{ flex: 1 }}>
              <div className="proj-card-name">
                {inst.label || inst.domain || inst.id}
              </div>
              <div className="proj-card-meta">
                {inst.ip || "installing..."} — {inst.plan} / {inst.region}
                {inst.metadata?.source_type === "repository" ? " · github" : ""}
                {inst.metadata?.source_type === "zar" ? ` · ${inst.metadata.zar_name || "zar"}` : ""}
              </div>
              <InstanceMetricsBar metrics={metrics[inst.id]} />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              {(inst.state === "creating" || inst.state === "installing") && (
                <Loader className="h-3 w-3 animate-spin" style={{ color: "var(--color-yellow)" }} />
              )}
              <span className={`inst-badge ${stateBadgeClass(inst.state)}`}>
                {inst.state}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Selected instance detail */}
      {selected && (
        <div style={{ marginTop: 16, borderTop: "1px solid var(--border)", paddingTop: 16 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Server className="h-4 w-4" style={{ color: stateColor(selected.state) }} />
              <span style={{ fontWeight: 600, fontSize: "var(--font-sm)" }}>
                {selected.label || selected.domain || selected.id}
              </span>
              {selected.ip && (
                <span style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)", fontFamily: "monospace" }}>
                  {selected.ip}
                </span>
              )}
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              <button
                className={`svc-btn ${panel === "terminal" ? "green" : ""}`}
                title="Terminal"
                aria-label="Toggle terminal"
                onClick={() => setPanel(panel === "terminal" ? null : "terminal")}
              >
                <Terminal className="h-3.5 w-3.5" />
              </button>
              <button
                className={`svc-btn ${panel === "files" ? "green" : ""}`}
                title="Files"
                aria-label="Toggle file browser"
                onClick={() => setPanel(panel === "files" ? null : "files")}
              >
                <FolderOpen className="h-3.5 w-3.5" />
              </button>
              {selected.state === "ready" || selected.state === "active" ? (
                <button className="svc-btn yellow" title="Stop" aria-label="Stop instance" onClick={() => handleStop(selected)}>
                  <Power className="h-3.5 w-3.5" />
                </button>
              ) : selected.state === "stopped" ? (
                <button className="svc-btn green" title="Start" aria-label="Start instance" onClick={() => handleStart(selected)}>
                  <Play className="h-3.5 w-3.5" />
                </button>
              ) : null}
              <button className="svc-btn red" title="Destroy" aria-label="Destroy instance" onClick={() => handleDelete(selected)}>
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          {/* Info grid */}
          <div className="sys-grid" style={{ marginBottom: 12 }}>
            {[
              { label: "Name", value: selected.label || "—" },
              { label: "IP", value: selected.ip || "—" },
              { label: "Source", value: selected.metadata?.source_type === "repository"
                ? (selected.metadata.git_url?.split("/").pop()?.replace(".git", "") || "github")
                : selected.metadata?.source_type === "zar"
                ? (selected.metadata.zar_name || "zar")
                : "empty" },
              { label: "Plan", value: selected.plan },
              { label: "Region", value: selected.region },
              { label: "Created", value: selected.created_at?.split("T")[0] || "—" },
            ].map((item) => (
              <div key={item.label} className="sys-card">
                <div className="sys-label">{item.label}</div>
                <div className="sys-value">{item.value}</div>
              </div>
            ))}
          </div>

          {/* Metrics detail */}
          {metrics[selected.id]?.reachable && (
            <div className="sys-grid" style={{ marginBottom: 12 }}>
              {[
                { label: "CPU", value: `${metrics[selected.id].cpu_percent}%` },
                { label: "Memory", value: `${metrics[selected.id].mem_percent}%` },
                { label: "Disk", value: `${metrics[selected.id].disk_percent}%` },
                { label: "Load", value: `${metrics[selected.id].load_1m}` },
                { label: "Uptime", value: metrics[selected.id].uptime > 86400
                  ? `${Math.floor(metrics[selected.id].uptime / 86400)}d`
                  : metrics[selected.id].uptime > 3600
                  ? `${Math.floor(metrics[selected.id].uptime / 3600)}h`
                  : `${Math.floor(metrics[selected.id].uptime / 60)}m` },
                { label: "Status", value: metrics[selected.id].reachable ? "Online" : "Offline" },
              ].map((item) => (
                <div key={item.label} className="sys-card">
                  <div className="sys-label">{item.label}</div>
                  <div className="sys-value">{item.value}</div>
                </div>
              ))}
            </div>
          )}

          {/* Sub-panels */}
          {panel === "terminal" && projectId && (
            <TerminalPanel projectId={projectId} instance={selected} />
          )}
          {panel === "files" && projectId && (
            <FilesPanel instance={selected} />
          )}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════
   TERMINAL PANEL
   ═══════════════════════════════════════════ */

function TerminalPanel({ projectId, instance }: { projectId: string; instance: Instance }) {
  const [cmd, setCmd] = useState("");
  const [history, setHistory] = useState<{ cmd: string; output: string; code: number }[]>([]);
  const [running, setRunning] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [history]);

  const run = async () => {
    const command = cmd.trim();
    if (!command || running) return;
    setCmd("");
    setRunning(true);
    try {
      const res = await execOnInstance(projectId, instance.id, command, 30);
      setHistory((h) => [...h, { cmd: command, output: res.output || "", code: res.exit_code }]);
    } catch (e: any) {
      setHistory((h) => [...h, { cmd: command, output: e.message || "Error", code: -1 }]);
    }
    setRunning(false);
  };

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
      <div style={{ padding: "6px 12px", background: "var(--sidebar-background)", display: "flex", alignItems: "center", gap: 6, borderBottom: "1px solid var(--border)" }}>
        <Terminal className="h-3 w-3" style={{ color: "var(--color-green)" }} />
        <span style={{ fontSize: "var(--font-xs)", fontWeight: 600 }}>
          {instance.label || instance.ip || instance.id}
        </span>
        {instance.ip && instance.label && (
          <span style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)", fontFamily: "monospace" }}>
            {instance.ip}
          </span>
        )}
      </div>
      <div
        ref={scrollRef}
        className="terminal-output"
        style={{ height: 280 }}
      >
        {history.length === 0 && (
          <div className="terminal-muted">Type a command and press Enter...</div>
        )}
        {history.map((h, i) => (
          <div key={i} style={{ marginBottom: 8 }}>
            <div style={{ color: "var(--blue-accent)" }}>$ {h.cmd}</div>
            <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-all" }} className={h.code === 0 ? "" : "terminal-error"}>
              {h.output || "(no output)"}
            </pre>
          </div>
        ))}
        {running && (
          <div className="terminal-muted">Running...</div>
        )}
      </div>
      <div className="terminal-input-bar">
        <span style={{ padding: "8px 0 8px 12px", color: "var(--blue-accent)", fontFamily: "monospace", fontSize: 12 }}>$</span>
        <input
          type="text"
          value={cmd}
          onChange={(e) => setCmd(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run(); }}
          placeholder="Enter command..."
          disabled={running}
          autoFocus
        />
        <button
          onClick={run}
          disabled={running || !cmd.trim()}
          style={{ padding: "8px 12px", border: "none", background: "transparent", color: "var(--blue-accent)", cursor: "pointer" }}
        >
          <Send className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   FILES PANEL
   ═══════════════════════════════════════════ */

function FilesPanel({ instance }: { instance: Instance }) {
  const [files, setFiles] = useState<any[]>([]);
  const [currentPath, setCurrentPath] = useState("/opt/app");
  const [loading, setLoading] = useState(true);

  const fetchFiles = async (path: string) => {
    if (!instance.ip) return;
    setLoading(true);
    try {
      const res = await listFiles(path);
      setFiles(res.items || []);
      setCurrentPath(path);
    } catch {
      setFiles([]);
    }
    setLoading(false);
  };

  useEffect(() => { fetchFiles(currentPath); }, [instance.id]);

  const goUp = () => {
    const parent = currentPath.split("/").slice(0, -1).join("/") || "/";
    fetchFiles(parent);
  };

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
      <div style={{ padding: "6px 12px", background: "var(--sidebar-background)", display: "flex", alignItems: "center", gap: 6, borderBottom: "1px solid var(--border)" }}>
        <FolderOpen className="h-3 w-3" style={{ color: "var(--color-blue)" }} />
        <span style={{ fontSize: "var(--font-xs)", fontFamily: "monospace", flex: 1 }}>
          {currentPath}
        </span>
        <button className="panel-btn-sm" onClick={goUp} style={{ fontSize: 10 }}>
          ..
        </button>
        <button className="panel-btn-sm" onClick={() => fetchFiles(currentPath)} disabled={loading}>
          <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>
      <div style={{ maxHeight: 300, overflowY: "auto" }}>
        {loading ? (
          <div style={{ padding: 20, textAlign: "center", color: "var(--muted-foreground)", fontSize: "var(--font-xs)" }}>
            Loading...
          </div>
        ) : files.length === 0 ? (
          <div style={{ padding: 20, textAlign: "center", color: "var(--muted-foreground)", fontSize: "var(--font-xs)" }}>
            Empty directory
          </div>
        ) : (
          files.map((f) => (
            <div
              key={f.name}
              className="proj-file-row"
              style={{ cursor: f.type === "dir" ? "pointer" : "default" }}
              onClick={() => {
                if (f.type === "dir") {
                  fetchFiles(`${currentPath}/${f.name}`.replace("//", "/"));
                }
              }}
            >
              {f.type === "dir"
                ? <FolderOpen className="h-3.5 w-3.5" style={{ color: "var(--color-blue)" }} />
                : <FileText className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)" }} />}
              <span className="proj-file-name">{f.name}</span>
              {f.size != null && f.type !== "dir" && (
                <span className="proj-file-size">{formatSize(f.size)}</span>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   HELPERS
   ═══════════════════════════════════════════ */


/* ═══════════════════════════════════════════
   SERVICES TAB
   ═══════════════════════════════════════════ */

/* ═══════════════════════════════════════════
   NODES TAB
   ═══════════════════════════════════════════ */

interface ComputeNode {
  id: string;
  label: string;
  provider: string;
  instance_id: string | null;
  ip: string;
  agent_port: number;
  agent_reachable: number;
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
  tags: string;
  agent_version: string;
  last_heartbeat: string;
  created_at: string;
}

function nodeStatusColor(status: string): string {
  switch (status) {
    case "online": return "var(--color-green)";
    case "draining": return "var(--color-yellow)";
    case "maintenance": return "var(--color-yellow)";
    case "offline": return "var(--color-red)";
    case "pending": return "var(--muted-foreground)";
    default: return "var(--muted-foreground)";
  }
}

export function NodesTab() {
  const activeProject = useDashboardStore((s) => s.activeProject);
  const projectId = activeProject?.id || null;
  const [loading, setLoading] = useState(true);
  const [nodes, setNodes] = useState<ComputeNode[]>([]);
  const [selected, setSelected] = useState<ComputeNode | null>(null);
  const [showRegister, setShowRegister] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState("");

  const fetchNodes = async () => {
    if (!projectId) { setNodes([]); setLoading(false); return; }
    setLoading(true);
    try {
      const res = await listComputeNodes(projectId);
      setNodes(res.nodes || []);
    } catch {
      setNodes([]);
    }
    setLoading(false);
  };

  useEffect(() => { fetchNodes(); }, [projectId]);

  const handleSync = async () => {
    if (!projectId) return;
    setSyncing(true);
    setSyncResult("");
    try {
      const res = await syncInstancesToNodes(projectId);
      setSyncResult(`Registered ${res.registered}, skipped ${res.skipped}`);
      fetchNodes();
    } catch (e: any) {
      setSyncResult(e.message || "Sync failed");
    }
    setSyncing(false);
  };

  const handleDelete = async (node: ComputeNode) => {
    if (!projectId) return;
    if (!confirm(`Delete node "${node.label}"? This removes the node from the cluster.`)) return;
    try {
      await deleteComputeNode(projectId, node.id);
      setNodes((prev) => prev.filter((n) => n.id !== node.id));
      if (selected?.id === node.id) setSelected(null);
    } catch (e: any) {
      alert(e.message || "Delete failed");
    }
  };

  const handleDrain = async (node: ComputeNode) => {
    if (!projectId) return;
    try {
      await drainNode(projectId, node.id);
      fetchNodes();
    } catch (e: any) { alert(e.message || "Drain failed"); }
  };

  const handleCordon = async (node: ComputeNode) => {
    if (!projectId) return;
    try {
      await cordonNode(projectId, node.id);
      fetchNodes();
    } catch (e: any) { alert(e.message || "Cordon failed"); }
  };

  const handleUncordon = async (node: ComputeNode) => {
    if (!projectId) return;
    try {
      await uncordonNode(projectId, node.id);
      fetchNodes();
    } catch (e: any) { alert(e.message || "Uncordon failed"); }
  };

  if (!projectId) {
    return <div className="panel-empty"><div className="panel-empty-sub">Select a project first</div></div>;
  }

  if (loading && nodes.length === 0) {
    return (
      <div className="panel-empty">
        <RefreshCw className="h-8 w-8 animate-spin" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-sub">Loading nodes...</div>
      </div>
    );
  }

  if (nodes.length === 0 && !showRegister) {
    return (
      <div className="panel-empty">
        <Cpu className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-title">No compute nodes</div>
        <div className="panel-empty-sub">Add a node from Vultr, Hetzner, or connect via SSH.</div>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="panel-btn" onClick={() => setShowRegister(true)}>
            <Plus className="h-3.5 w-3.5" /><span>Add Node</span>
          </button>
          <button className="panel-btn" onClick={handleSync} disabled={syncing}>
            <Download className="h-3.5 w-3.5" /><span>{syncing ? "Syncing..." : "Sync Instances"}</span>
          </button>
        </div>
        {syncResult && <div className="panel-empty-sub" style={{ marginTop: 8 }}>{syncResult}</div>}
      </div>
    );
  }

  return (
    <div style={{ padding: "16px 0" }}>
      {/* Header */}
      <div className="panel-header-row" style={{ padding: "0 0 12px" }}>
        <span className="panel-count">
          {nodes.length} node{nodes.length !== 1 ? "s" : ""}
        </span>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="panel-btn-sm" onClick={fetchNodes} disabled={loading}>
            <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button className="panel-btn-sm" onClick={handleSync} disabled={syncing} title="Sync instances as nodes">
            <Download className="h-3 w-3" />
            <span>{syncing ? "..." : "Sync"}</span>
          </button>
          <button className="panel-btn-sm" onClick={() => setShowRegister(true)}>
            <Plus className="h-3 w-3" /><span>Add</span>
          </button>
        </div>
      </div>

      {syncResult && (
        <div style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", padding: "0 0 8px" }}>
          {syncResult}
        </div>
      )}

      {/* Register form */}
      {showRegister && projectId && (
        <RegisterNodeForm
          projectId={projectId}
          onCreated={() => { setShowRegister(false); fetchNodes(); }}
          onCancel={() => setShowRegister(false)}
        />
      )}

      {/* Node cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {nodes.map((node) => (
          <div
            key={node.id}
            className={`proj-card ${selected?.id === node.id ? "active" : ""}`}
            onClick={() => setSelected(node)}
          >
            <div className="proj-card-icon">
              <Cpu className="h-4 w-4" style={{ color: nodeStatusColor(node.status) }} />
            </div>
            <div className="proj-card-info" style={{ flex: 1 }}>
              <div className="proj-card-name">{node.label}</div>
              <div className="proj-card-meta">
                {node.ip || "no ip"} — {node.provider} / {node.role}
                {node.reserved_for ? ` · reserved` : ""}
              </div>
              {node.status === "online" && (
                <div style={{ display: "flex", gap: 8, paddingTop: 4 }}>
                  <MetricBar label="CPU" value={node.cpu_used_percent} color="var(--color-blue)" />
                  <MetricBar label="RAM" value={node.mem_used_percent} color="var(--color-green)" />
                  <MetricBar label="Disk" value={node.disk_used_percent} color="var(--color-yellow)" />
                </div>
              )}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span className={`inst-badge ${node.status === "online" ? "badge-success" : node.status === "offline" ? "badge-error" : "badge-warning"}`}>
                {node.status}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Selected node detail */}
      {selected && (
        <div style={{ marginTop: 16, borderTop: "1px solid var(--border)", paddingTop: 16 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Cpu className="h-4 w-4" style={{ color: nodeStatusColor(selected.status) }} />
              <span style={{ fontWeight: 600, fontSize: "var(--font-sm)" }}>{selected.label}</span>
              {selected.ip && (
                <span style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)", fontFamily: "monospace" }}>
                  {selected.ip}:{selected.agent_port}
                </span>
              )}
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              {selected.status === "online" && (
                <>
                  <button className="svc-btn yellow" title="Drain (stop scheduling)" onClick={() => handleDrain(selected)}>
                    <Pause className="h-3.5 w-3.5" />
                  </button>
                  <button className="svc-btn yellow" title="Cordon (maintenance)" onClick={() => handleCordon(selected)}>
                    <ShieldCheck className="h-3.5 w-3.5" />
                  </button>
                </>
              )}
              {(selected.status === "draining" || selected.status === "maintenance") && (
                <button className="svc-btn green" title="Uncordon (restore)" onClick={() => handleUncordon(selected)}>
                  <ShieldOff className="h-3.5 w-3.5" />
                </button>
              )}
              <button className="svc-btn red" title="Delete node" onClick={() => handleDelete(selected)}>
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          {/* Info grid */}
          <div className="sys-grid" style={{ marginBottom: 12 }}>
            {[
              { label: "Provider", value: selected.provider },
              { label: "Role", value: selected.role },
              { label: "CPU", value: `${selected.cpu_allocated}/${selected.cpu_cores} cores` },
              { label: "Memory", value: `${selected.mem_allocated_mb}/${selected.mem_total_mb} MB` },
              { label: "Disk", value: `${selected.disk_total_gb} GB` },
              { label: "Agent", value: selected.agent_reachable ? `v${selected.agent_version || "?"}` : "unreachable" },
              { label: "Heartbeat", value: selected.last_heartbeat ? selected.last_heartbeat.split("T")[0] : "never" },
              { label: "Created", value: selected.created_at?.split("T")[0] || "—" },
            ].map((item) => (
              <div key={item.label} className="sys-card">
                <div className="sys-label">{item.label}</div>
                <div className="sys-value">{item.value}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Register Node Form (connector-style) ── */

type NodeProvider = "vultr" | "hetzner" | "ssh" | null;

const PROVIDER_OPTIONS: { id: NodeProvider & string; name: string; desc: string; icon: string }[] = [
  { id: "vultr", name: "Vultr", desc: "Provision a new VPS automatically", icon: "V" },
  { id: "hetzner", name: "Hetzner", desc: "Provision a Hetzner Cloud server", icon: "H" },
  { id: "ssh", name: "SSH / Manual", desc: "Connect any machine with SSH access", icon: ">" },
];

function RegisterNodeForm({ projectId, onCreated, onCancel }: {
  projectId: string;
  onCreated: () => void;
  onCancel: () => void;
}) {
  const [step, setStep] = useState<"pick" | "configure">("pick");
  const [selectedProvider, setSelectedProvider] = useState<NodeProvider>(null);
  const [label, setLabel] = useState("");
  const [ip, setIp] = useState("");
  const [sshUser, setSshUser] = useState("root");
  const [sshPort, setSshPort] = useState("22");
  const [agentPort, setAgentPort] = useState("8081");
  const [region, setRegion] = useState("ewr");
  const [plan, setPlan] = useState("vc2-1c-1gb");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const pickProvider = (p: NodeProvider) => {
    setSelectedProvider(p);
    setStep("configure");
    setError("");
    if (p === "vultr") setLabel("vultr-node");
    else if (p === "hetzner") setLabel("hetzner-node");
    else setLabel("");
  };

  const submit = async () => {
    if (!label.trim()) { setError("Label is required"); return; }
    if (selectedProvider === "ssh" && !ip.trim()) { setError("IP address is required"); return; }
    setCreating(true);
    setError("");
    try {
      const selectedPlan = PLANS.find((p) => p.id === plan);
      const providerName = selectedProvider === "ssh" ? "manual" : (selectedProvider || "manual");
      await registerComputeNode(projectId, {
        label: label.trim(),
        provider: providerName,
        ip: ip.trim() || undefined,
        agent_port: parseInt(agentPort) || 8081,
        cpu_cores: selectedPlan?.cpu || 1,
        mem_total_mb: selectedProvider === "ssh" ? 1024 : (selectedPlan ? parseInt(selectedPlan.ram) * 1024 : 1024),
      });
      onCreated();
    } catch (e: any) {
      setError(e.message || "Failed to register node");
    }
    setCreating(false);
  };

  // Step 1: Provider picker (connector-style cards)
  if (step === "pick") {
    return (
      <div style={{
        border: "1px solid var(--border)", borderRadius: 8, padding: 16,
        marginBottom: 16, background: "var(--sidebar-background)",
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <div style={{ fontWeight: 600, fontSize: "var(--font-sm)" }}>Add Node</div>
          <button className="panel-btn-sm" onClick={onCancel} style={{ fontSize: "var(--font-xxs)" }}>Cancel</button>
        </div>
        <div style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)", marginBottom: 14 }}>
          Choose how to connect your infrastructure
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {PROVIDER_OPTIONS.map((p) => (
            <button
              key={p.id}
              onClick={() => pickProvider(p.id as NodeProvider)}
              style={{
                display: "flex", alignItems: "center", gap: 12,
                padding: "12px 14px", borderRadius: 8,
                border: "1px solid var(--border)",
                background: "var(--background)",
                cursor: "pointer", textAlign: "left",
                transition: "all 0.15s ease",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = "var(--color-teal)";
                e.currentTarget.style.background = "var(--accent)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = "var(--border)";
                e.currentTarget.style.background = "var(--background)";
              }}
            >
              <div style={{
                width: 36, height: 36, borderRadius: 8,
                background: p.id === "vultr" ? "rgba(0, 124, 255, 0.1)"
                  : p.id === "hetzner" ? "rgba(213, 0, 41, 0.1)"
                  : "rgba(100, 200, 180, 0.1)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontWeight: 700, fontSize: 16, flexShrink: 0,
                color: p.id === "vultr" ? "#007CFF"
                  : p.id === "hetzner" ? "#D50029"
                  : "var(--color-teal)",
              }}>
                {p.icon}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: "var(--font-sm)", color: "var(--foreground)" }}>{p.name}</div>
                <div style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginTop: 1 }}>{p.desc}</div>
              </div>
              <ChevronRight className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)", opacity: 0.4, flexShrink: 0 }} />
            </button>
          ))}
        </div>
      </div>
    );
  }

  // Step 2: Configuration form based on provider
  return (
    <div style={{
      border: "1px solid var(--border)", borderRadius: 8, padding: 16,
      marginBottom: 16, background: "var(--sidebar-background)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
        <button
          className="panel-btn-sm"
          onClick={() => { setStep("pick"); setError(""); }}
          style={{ fontSize: "var(--font-xxs)", padding: "3px 8px" }}
        >
          ← Back
        </button>
        <div style={{
          width: 24, height: 24, borderRadius: 6,
          background: selectedProvider === "vultr" ? "rgba(0, 124, 255, 0.1)"
            : selectedProvider === "hetzner" ? "rgba(213, 0, 41, 0.1)"
            : "rgba(100, 200, 180, 0.1)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontWeight: 700, fontSize: 12, flexShrink: 0,
          color: selectedProvider === "vultr" ? "#007CFF"
            : selectedProvider === "hetzner" ? "#D50029"
            : "var(--color-teal)",
        }}>
          {PROVIDER_OPTIONS.find((p) => p.id === selectedProvider)?.icon}
        </div>
        <span style={{ fontWeight: 600, fontSize: "var(--font-sm)" }}>
          {PROVIDER_OPTIONS.find((p) => p.id === selectedProvider)?.name}
        </span>
      </div>

      {error && (
        <div style={{ padding: "8px 12px", fontSize: "var(--font-xs)", color: "var(--color-red)", background: "rgba(239,68,68,0.08)", borderRadius: 6, marginBottom: 12 }}>
          {error}
        </div>
      )}

      {/* Label */}
      <div style={{ marginBottom: 10 }}>
        <label style={labelStyle}>Label</label>
        <input className="proj-input" type="text" placeholder="my-node" value={label} onChange={(e) => setLabel(e.target.value)} style={{ width: "100%" }} autoFocus />
      </div>

      {/* SSH / Manual: IP + SSH credentials */}
      {selectedProvider === "ssh" && (
        <>
          <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
            <div style={{ flex: 2 }}>
              <label style={labelStyle}>IP Address</label>
              <input className="proj-input" type="text" placeholder="192.168.1.100" value={ip} onChange={(e) => setIp(e.target.value)} style={{ width: "100%" }} />
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>SSH User</label>
              <input className="proj-input" type="text" placeholder="root" value={sshUser} onChange={(e) => setSshUser(e.target.value)} style={{ width: "100%" }} />
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>SSH Port</label>
              <input className="proj-input" type="number" placeholder="22" value={sshPort} onChange={(e) => setSshPort(e.target.value)} style={{ width: "100%" }} />
            </div>
          </div>
          <div style={{ marginBottom: 10 }}>
            <label style={labelStyle}>Agent Port</label>
            <input className="proj-input" type="number" value={agentPort} onChange={(e) => setAgentPort(e.target.value)} style={{ width: "100%" }} />
          </div>
          <div style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginBottom: 12, lineHeight: 1.5 }}>
            The agent will be installed automatically on the target machine via SSH. Make sure port {sshPort} is open and the user has sudo access.
          </div>
        </>
      )}

      {/* Vultr / Hetzner: Region + Plan */}
      {(selectedProvider === "vultr" || selectedProvider === "hetzner") && (
        <>
          <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Region</label>
              <select className="proj-input" value={region} onChange={(e) => setRegion(e.target.value)} style={{ width: "100%" }}>
                {REGIONS.map((r) => (
                  <option key={r.id} value={r.id}>{r.city}, {r.country}</option>
                ))}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Plan</label>
              <select className="proj-input" value={plan} onChange={(e) => setPlan(e.target.value)} style={{ width: "100%" }}>
                {PLANS.map((p) => (
                  <option key={p.id} value={p.id}>{p.cpu} CPU · {p.ram} · {p.price}</option>
                ))}
              </select>
            </div>
          </div>
          <div style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginBottom: 12, lineHeight: 1.5 }}>
            A new {selectedProvider === "vultr" ? "Vultr" : "Hetzner"} VPS will be provisioned and the NSO agent installed automatically.
          </div>
        </>
      )}

      <div style={{ display: "flex", gap: 6 }}>
        <button className="deploy-action-btn teal" onClick={submit} disabled={creating} style={{ padding: "5px 14px" }}>
          {creating ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
          <span>{creating ? "Connecting..." : "Connect Node"}</span>
        </button>
        <button className="panel-btn-sm" onClick={onCancel} disabled={creating}>Cancel</button>
      </div>
    </div>
  );
}

export function ServicesTab() {
  const activeProject = useDashboardStore((s) => s.activeProject);
  const workspaces = useDashboardStore((s) => s.workspaces);
  const setWorkspaces = useDashboardStore((s) => s.setWorkspaces);
  const setActiveView = useDashboardStore((s) => s.setActiveView);
  const setActiveWorkspace = useDashboardStore((s) => s.setActiveWorkspace);
  const [statuses, setStatuses] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState<string | null>(null);
  const [sysInfo, setSysInfo] = useState<Record<string, string>>({});
  const [sysLoading, setSysLoading] = useState(false);

  const handleService = async (action: string, name: string) => {
    setLoading(`${name}-${action}`);
    try {
      const res = await manageService(action, name);
      setStatuses((prev) => ({ ...prev, [name]: res }));
    } catch (err: any) {
      setStatuses((prev) => ({ ...prev, [name]: { error: err.message } }));
    }
    setLoading(null);
  };

  const fetchSysInfo = async () => {
    setSysLoading(true);
    try {
      const os = await execCommand("cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'", "/opt/nso", 5);
      const mem = await execCommand("free -h | awk '/Mem:/{print $2, $3}'", "/opt/nso", 5);
      const disk = await execCommand("df -h / | awk 'NR==2{print $2, $3, $5}'", "/opt/nso", 5);
      const cpu = await execCommand("nproc", "/opt/nso", 5);
      const up = await execCommand("uptime -p", "/opt/nso", 5);
      setSysInfo({
        os: os.stdout.trim(),
        memory: mem.stdout.trim(),
        disk: disk.stdout.trim(),
        cpu: `${cpu.stdout.trim()} cores`,
        uptime: up.stdout.trim().replace("up ", ""),
      });
    } catch {}
    setSysLoading(false);
  };

  const goToWorkspace = (ws: any) => {
    setActiveWorkspace(ws);
    setActiveView("workspaces");
  };

  useEffect(() => {
    SYSTEM_SERVICES.forEach((svc) => handleService("status", svc.name));
    fetchSysInfo();
    // Load workspaces if not already loaded
    if (activeProject && workspaces.length === 0) {
      listWorkspaces(activeProject.id).then((res) => setWorkspaces(res.workspaces || [])).catch(() => {});
    }
  }, [activeProject]);

  return (
    <div style={{ padding: "16px 0" }}>
      {/* Workspaces as services */}
      <div className="settings-section">
        <div className="settings-section-title">Workspaces</div>
        <div className="svc-list">
          {workspaces.map((ws: any) => {
            const deployed = ws.deployed === true;
            const state = ws.instance_state || "";
            return (
              <div key={ws.id} className="svc-row">
                <div className="svc-info">
                  <div className="svc-status-dot" style={{
                    background: deployed ? "var(--color-green)"
                      : state === "error" ? "var(--color-red)"
                      : state ? "var(--color-yellow)"
                      : "var(--muted-foreground)",
                    opacity: !deployed && !state ? 0.3 : 1,
                  }} />
                  <div>
                    <button
                      className="svc-name"
                      onClick={() => goToWorkspace(ws)}
                      style={{ background: "none", border: "none", cursor: "pointer", padding: 0, color: "inherit", textDecoration: "none" }}
                    >
                      {ws.name} →
                    </button>
                    <div className="svc-desc">
                      {deployed ? "running" : state || "not deployed"}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
          {workspaces.length === 0 && (
            <div className="svc-desc" style={{ padding: "8px 0", opacity: 0.5 }}>No workspaces</div>
          )}
        </div>
      </div>

      {/* System services */}
      <div className="settings-section">
        <div className="settings-section-title">System Services</div>
        <div className="svc-list">
          {SYSTEM_SERVICES.map((svc) => {
            const st = statuses[svc.name];
            const isActive = st?.active;
            const hasError = st?.error;
            return (
              <div key={svc.name} className="svc-row">
                <div className="svc-info">
                  <div className="svc-status-dot" style={{
                    background: hasError ? "var(--color-red)"
                      : isActive ? "var(--color-green)"
                      : isActive === false ? "var(--color-red)"
                      : "var(--muted-foreground)",
                    opacity: isActive == null && !hasError ? 0.3 : 1,
                  }} />
                  <div>
                    <div className="svc-name">{svc.display}</div>
                    <div className="svc-desc">
                      {hasError ? <span style={{ color: "var(--color-red)" }}>{st.error}</span>
                        : isActive != null ? (isActive ? "Active" : "Inactive")
                        : svc.description}
                    </div>
                  </div>
                </div>
                <div className="svc-actions">
                  <button className="svc-btn" title="Check status" onClick={() => handleService("status", svc.name)} disabled={loading === `${svc.name}-status`}>
                    <RefreshCw className={`h-3 w-3 ${loading === `${svc.name}-status` ? "animate-spin" : ""}`} />
                  </button>
                  <button className="svc-btn green" title="Start" onClick={() => handleService("start", svc.name)}>
                    <Play className="h-3 w-3" />
                  </button>
                  <button className="svc-btn red" title="Stop" onClick={() => handleService("stop", svc.name)}>
                    <Square className="h-3 w-3" />
                  </button>
                  <button className="svc-btn yellow" title="Restart" onClick={() => handleService("restart", svc.name)}>
                    <RotateCcw className="h-3 w-3" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="settings-section">
        <div className="settings-section-header">
          <span className="settings-section-title">System</span>
          <button className="panel-btn-sm" onClick={fetchSysInfo} disabled={sysLoading}>
            <RefreshCw className={`h-3 w-3 ${sysLoading ? "animate-spin" : ""}`} />
            <span>{sysLoading ? "Loading" : "Refresh"}</span>
          </button>
        </div>
        {Object.keys(sysInfo).length > 0 ? (
          <div className="sys-grid">
            {[
              { label: "OS", value: sysInfo.os },
              { label: "CPU", value: sysInfo.cpu },
              { label: "Memory", value: sysInfo.memory },
              { label: "Disk", value: sysInfo.disk },
              { label: "Uptime", value: sysInfo.uptime },
            ].map((item) => (
              <div key={item.label} className="sys-card">
                <div className="sys-label">{item.label}</div>
                <div className="sys-value">{item.value || "—"}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="settings-placeholder">
            <Monitor className="h-6 w-6" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
            <span>Loading system info...</span>
          </div>
        )}
      </div>
    </div>
  );
}
