"use client";

import { useState, useEffect, useRef } from "react";
import {
  Server, RefreshCw, Play, Square, Trash2, Plus,
  Activity, Monitor, Terminal, FolderOpen,
  Send, RotateCcw, Power, FileText, Loader, Globe, Zap,
} from "lucide-react";
import {
  listProjects, createProject as apiCreateProject,
  listInstances, createInstance, deleteInstance,
  stopInstance, startInstance, execOnInstance,
  execCommand, manageService, listFiles,
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


const SERVICES = [
  { name: "nso", display: "NSO API", description: "Main REST API server" },
  { name: "nso-agent", display: "NSO Agent", description: "Remote execution agent" },
  { name: "nginx", display: "nginx", description: "Reverse proxy & TLS" },
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

type SourceType = "repository" | "zar" | "ready" | "empty";

function CreateInstanceForm({ projectId, onCreated, onCancel }: CreateFormProps) {
  const [label, setLabel] = useState("");
  const [region, setRegion] = useState("mad");
  const [plan, setPlan] = useState("vc2-1c-1gb");
  const [domain, setDomain] = useState("");
  const [sourceType, setSourceType] = useState<SourceType>("empty");
  const [gitUrl, setGitUrl] = useState("");
  const [gitBranch, setGitBranch] = useState("main");
  const [zarName, setZarName] = useState("");
  const [readyWorkspace, setReadyWorkspace] = useState("");
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
    if (sourceType === "ready" && !readyWorkspace.trim()) {
      return "Workspace name is required for pre-built source";
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
        zar_name: sourceType === "zar" ? zarName.trim() : sourceType === "ready" ? readyWorkspace.trim() : undefined,
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
      background: "var(--sidebar-bg)",
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
          {(["ready", "repository", "zar", "empty"] as SourceType[]).map((st) => (
            <button
              key={st}
              className={`scope-chip ${sourceType === st ? "active" : ""}`}
              onClick={() => setSourceType(st)}
              type="button"
            >
              {st === "ready" && <Zap className="h-3 w-3" />}
              {st === "repository" && <FolderOpen className="h-3 w-3" />}
              {st === "zar" && <FileText className="h-3 w-3" />}
              {st === "empty" && <Server className="h-3 w-3" />}
              <span>{st === "ready" ? "Pre-built" : st === "repository" ? "Repository" : st === "zar" ? ".zar" : "Empty"}</span>
            </button>
          ))}
        </div>

        {/* Source-specific fields */}
        {sourceType === "ready" && (
          <div>
            <input
              className="proj-input"
              type="text"
              placeholder="workspace name (frozen app)"
              value={readyWorkspace}
              onChange={(e) => setReadyWorkspace(e.target.value)}
              style={{ width: "100%" }}
            />
            <div style={{ fontSize: "var(--font-xxs)", color: "var(--color-green)", marginTop: 4 }}>
              Instant deploy from pre-built image — boots in ~3 min
            </div>
          </div>
        )}

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
        {sourceType === "ready" && readyWorkspace ? ` · ${readyWorkspace} (pre-built)` : ""}
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

function InstancesTab() {
  const [loading, setLoading] = useState(true);
  const [instances, setInstances] = useState<Instance[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Instance | null>(null);
  const [panel, setPanel] = useState<"terminal" | "files" | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    setError("");
    try {
      const projRes = await listProjects();
      const proj = projRes.projects?.[0];
      if (!proj) {
        setInstances([]);
        setLoading(false);
        return;
      }
      setProjectId(proj.id);
      const instRes = await listInstances(proj.id);
      setInstances(instRes.instances || []);
    } catch {
      setInstances([]);
    }
    setLoading(false);
  };

  useEffect(() => { fetchData(); }, []);

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
                {inst.metadata?.source_type === "ready" ? " · pre-built" : ""}
                {inst.metadata?.source_type === "repository" ? " · repo" : ""}
                {inst.metadata?.source_type === "zar" ? ` · ${inst.metadata.zar_name || "zar"}` : ""}
              </div>
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
                onClick={() => setPanel(panel === "terminal" ? null : "terminal")}
              >
                <Terminal className="h-3.5 w-3.5" />
              </button>
              <button
                className={`svc-btn ${panel === "files" ? "green" : ""}`}
                title="Files"
                onClick={() => setPanel(panel === "files" ? null : "files")}
              >
                <FolderOpen className="h-3.5 w-3.5" />
              </button>
              {selected.state === "ready" || selected.state === "active" ? (
                <button className="svc-btn yellow" title="Stop" onClick={() => handleStop(selected)}>
                  <Power className="h-3.5 w-3.5" />
                </button>
              ) : selected.state === "stopped" ? (
                <button className="svc-btn green" title="Start" onClick={() => handleStart(selected)}>
                  <Play className="h-3.5 w-3.5" />
                </button>
              ) : null}
              <button className="svc-btn red" title="Destroy" onClick={() => handleDelete(selected)}>
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          {/* Info grid */}
          <div className="sys-grid" style={{ marginBottom: 12 }}>
            {[
              { label: "Name", value: selected.label || "—" },
              { label: "IP", value: selected.ip || "—" },
              { label: "Source", value: selected.metadata?.source_type === "ready"
                ? `pre-built (${selected.metadata.zar_name || "app"})`
                : selected.metadata?.source_type === "repository"
                ? (selected.metadata.git_url?.split("/").pop()?.replace(".git", "") || "repo")
                : selected.metadata?.source_type === "zar"
                ? (selected.metadata.zar_name || "zar")
                : "—" },
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
      <div style={{ padding: "6px 12px", background: "var(--sidebar-bg)", display: "flex", alignItems: "center", gap: 6, borderBottom: "1px solid var(--border)" }}>
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
        style={{ height: 280, overflowY: "auto", padding: 12, fontFamily: "monospace", fontSize: 12, background: "#0d1117", color: "#c9d1d9" }}
      >
        {history.length === 0 && (
          <div style={{ color: "#484f58" }}>Type a command and press Enter...</div>
        )}
        {history.map((h, i) => (
          <div key={i} style={{ marginBottom: 8 }}>
            <div style={{ color: "#58a6ff" }}>$ {h.cmd}</div>
            <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-all", color: h.code === 0 ? "#c9d1d9" : "#f85149" }}>
              {h.output || "(no output)"}
            </pre>
          </div>
        ))}
        {running && (
          <div style={{ color: "#484f58" }}>Running...</div>
        )}
      </div>
      <div style={{ display: "flex", borderTop: "1px solid var(--border)", background: "#0d1117" }}>
        <span style={{ padding: "8px 0 8px 12px", color: "#58a6ff", fontFamily: "monospace", fontSize: 12 }}>$</span>
        <input
          type="text"
          value={cmd}
          onChange={(e) => setCmd(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run(); }}
          placeholder="Enter command..."
          disabled={running}
          autoFocus
          style={{
            flex: 1, padding: "8px", border: "none", outline: "none",
            fontFamily: "monospace", fontSize: 12,
            background: "transparent", color: "#c9d1d9",
          }}
        />
        <button
          onClick={run}
          disabled={running || !cmd.trim()}
          style={{ padding: "8px 12px", border: "none", background: "transparent", color: "#58a6ff", cursor: "pointer" }}
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
      <div style={{ padding: "6px 12px", background: "var(--sidebar-bg)", display: "flex", alignItems: "center", gap: 6, borderBottom: "1px solid var(--border)" }}>
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

function stateColor(state: string): string {
  if (state === "ready" || state === "active" || state === "running") return "var(--color-green)";
  if (state === "creating" || state === "installing" || state === "deploying") return "var(--color-yellow)";
  if (state === "stopped") return "var(--muted-foreground)";
  return "var(--color-red)";
}

function stateBadgeClass(state: string): string {
  if (state === "ready" || state === "active" || state === "running") return "green";
  if (state === "creating" || state === "installing" || state === "deploying") return "yellow";
  return "red";
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/* ═══════════════════════════════════════════
   SERVICES TAB
   ═══════════════════════════════════════════ */

function ServicesTab() {
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

  useEffect(() => {
    SERVICES.forEach((svc) => handleService("status", svc.name));
    fetchSysInfo();
  }, []);

  return (
    <div style={{ padding: "16px 0" }}>
      <div className="settings-section">
        <div className="settings-section-title">Services</div>
        <div className="svc-list">
          {SERVICES.map((svc) => {
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
