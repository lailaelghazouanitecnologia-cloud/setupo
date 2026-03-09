"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import {
  Server, RefreshCw, Play, Square, Trash2, Plus,
  Activity, Monitor, Terminal, FolderOpen,
  Send, RotateCcw, Power, FileText, Loader,
  Cpu, Pause, ShieldCheck, ShieldOff, Download, ChevronRight,
  MapPin,
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
// UI select not needed — using native <select> for simplicity

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

// Unified item for the combined list
interface UnifiedInstance {
  id: string;
  label: string;
  ip: string | null;
  state: string;
  provider: string;
  region: string;
  plan: string;
  type: "instance" | "node";
  raw_instance?: Instance;
  raw_node?: ComputeNode;
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
          <span>Machines</span>
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
   METRICS
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

/* ═══════════════════════════════════════════
   TOPOLOGY GRAPH — mini map of instances
   ═══════════════════════════════════════════ */

// Region coordinates (approximate world map positions scaled to SVG viewbox)
const REGION_COORDS: Record<string, { x: number; y: number }> = {
  ewr: { x: 160, y: 95 },   // New Jersey
  ord: { x: 135, y: 85 },   // Chicago
  dfw: { x: 120, y: 110 },  // Dallas
  lax: { x: 80, y: 100 },   // LA
  atl: { x: 148, y: 108 },  // Atlanta
  mia: { x: 155, y: 125 },  // Miami
  ams: { x: 280, y: 55 },   // Amsterdam
  lhr: { x: 268, y: 58 },   // London
  fra: { x: 288, y: 62 },   // Frankfurt
  cdg: { x: 275, y: 66 },   // Paris
  mad: { x: 262, y: 80 },   // Madrid
  nrt: { x: 420, y: 80 },   // Tokyo
  sgp: { x: 385, y: 140 },  // Singapore
};

function statusColor(state: string): string {
  switch (state) {
    case "ready": case "active": case "online": return "#10B981";
    case "creating": case "installing": case "pending": case "draining": return "#F59E0B";
    case "stopped": case "offline": case "error": return "#EF4444";
    default: return "#6B7280";
  }
}

function TopologyGraph({
  items,
  selectedId,
  onSelect,
}: {
  items: UnifiedInstance[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (items.length === 0) return null;

  const svgW = 480;
  const svgH = 180;
  const hubX = svgW / 2;
  const hubY = svgH / 2;

  // Position items: if they have a region with coords, use that; otherwise arrange in a circle
  const positioned = useMemo(() => {
    const result: { item: UnifiedInstance; x: number; y: number }[] = [];
    const usedPositions = new Map<string, number>(); // region -> count for offset

    for (const item of items) {
      const coords = REGION_COORDS[item.region];
      if (coords) {
        const count = usedPositions.get(item.region) || 0;
        usedPositions.set(item.region, count + 1);
        // Offset slightly if multiple in same region
        result.push({
          item,
          x: coords.x + count * 14,
          y: coords.y + (count % 2 === 0 ? 0 : 12),
        });
      } else {
        // Fallback: arrange around center
        const angle = (result.length / items.length) * Math.PI * 2 - Math.PI / 2;
        result.push({
          item,
          x: hubX + Math.cos(angle) * 70,
          y: hubY + Math.sin(angle) * 50,
        });
      }
    }
    return result;
  }, [items]);

  return (
    <div style={{
      border: "1px solid var(--border)",
      borderRadius: 8,
      background: "var(--sidebar-background)",
      overflow: "hidden",
      marginBottom: 12,
    }}>
      <div style={{
        padding: "5px 10px",
        fontSize: 9,
        color: "var(--muted-foreground)",
        display: "flex",
        alignItems: "center",
        gap: 4,
        borderBottom: "1px solid var(--border)",
        opacity: 0.7,
      }}>
        <MapPin className="h-3 w-3" />
        <span>Topology</span>
      </div>
      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        width="100%"
        height={svgH}
        style={{ display: "block" }}
      >
        {/* Subtle grid dots */}
        <defs>
          <pattern id="dots" x="0" y="0" width="20" height="20" patternUnits="userSpaceOnUse">
            <circle cx="10" cy="10" r="0.5" fill="var(--border)" opacity="0.4" />
          </pattern>
        </defs>
        <rect width={svgW} height={svgH} fill="url(#dots)" />

        {/* Connection lines from hub to each node */}
        {positioned.map(({ item, x, y }) => (
          <line
            key={`line-${item.id}`}
            x1={hubX} y1={hubY}
            x2={x} y2={y}
            stroke={selectedId === item.id ? statusColor(item.state) : "var(--border)"}
            strokeWidth={selectedId === item.id ? 1.5 : 0.8}
            strokeDasharray={item.state === "creating" || item.state === "installing" ? "3,3" : undefined}
            opacity={selectedId === item.id ? 0.8 : 0.4}
          />
        ))}

        {/* Hub (NSO Central) */}
        <circle cx={hubX} cy={hubY} r={8} fill="var(--color-teal)" opacity={0.15} />
        <circle cx={hubX} cy={hubY} r={4} fill="var(--color-teal)" />
        <text
          x={hubX} y={hubY + 16}
          textAnchor="middle" fontSize="7" fill="var(--muted-foreground)"
          fontFamily="inherit" fontWeight="500"
        >
          NSO
        </text>

        {/* Instance nodes */}
        {positioned.map(({ item, x, y }) => {
          const isSelected = selectedId === item.id;
          const color = statusColor(item.state);
          return (
            <g
              key={item.id}
              style={{ cursor: "pointer" }}
              onClick={() => onSelect(item.id)}
            >
              {/* Selection ring */}
              {isSelected && (
                <circle cx={x} cy={y} r={10} fill="none" stroke={color} strokeWidth={1.5} opacity={0.5} />
              )}
              {/* Outer glow for online */}
              {(item.state === "ready" || item.state === "active" || item.state === "online") && (
                <circle cx={x} cy={y} r={7} fill={color} opacity={0.1} />
              )}
              {/* Node dot */}
              <circle
                cx={x} cy={y} r={isSelected ? 5 : 4}
                fill={color}
                stroke={isSelected ? color : "none"}
                strokeWidth={1}
              />
              {/* Label */}
              <text
                x={x} y={y - 8}
                textAnchor="middle" fontSize="7"
                fill={isSelected ? "var(--foreground)" : "var(--muted-foreground)"}
                fontFamily="inherit"
                fontWeight={isSelected ? "600" : "400"}
              >
                {(item.label || item.ip || item.id).slice(0, 16)}
              </text>
              {/* Region tag */}
              <text
                x={x} y={y + 12}
                textAnchor="middle" fontSize="6"
                fill="var(--muted-foreground)" opacity="0.5"
                fontFamily="monospace"
              >
                {item.region || item.provider}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/* ═══════════════════════════════════════════
   UNIFIED INSTANCES TAB
   ═══════════════════════════════════════════ */

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

export function InstancesTab() {
  const activeProject = useDashboardStore((s) => s.activeProject);
  const projectId = activeProject?.id || null;
  const [loading, setLoading] = useState(true);
  const [instances, setInstances] = useState<Instance[]>([]);
  const [nodes, setNodes] = useState<ComputeNode[]>([]);
  const [metrics, setMetrics] = useState<Record<string, InstanceMetrics>>({});
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [panel, setPanel] = useState<"terminal" | "files" | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState("");

  // Unified list
  const unified = useMemo<UnifiedInstance[]>(() => {
    const list: UnifiedInstance[] = [];

    for (const inst of instances) {
      // Check if this instance also has a node entry
      const matchingNode = nodes.find(n => n.instance_id === inst.id);
      list.push({
        id: inst.id,
        label: inst.label || inst.domain || inst.id,
        ip: inst.ip,
        state: matchingNode ? matchingNode.status : inst.state,
        provider: matchingNode?.provider || "nso",
        region: inst.region,
        plan: inst.plan,
        type: "instance",
        raw_instance: inst,
        raw_node: matchingNode || undefined,
      });
    }

    // Add nodes that don't have a matching instance
    for (const node of nodes) {
      if (!node.instance_id || !instances.find(i => i.id === node.instance_id)) {
        list.push({
          id: node.id,
          label: node.label,
          ip: node.ip,
          state: node.status,
          provider: node.provider,
          region: "",
          plan: `${node.cpu_cores}C/${node.mem_total_mb}MB`,
          type: "node",
          raw_node: node,
        });
      }
    }

    return list;
  }, [instances, nodes]);

  const selected = useMemo(() => unified.find(u => u.id === selectedId) || null, [unified, selectedId]);

  const fetchData = async () => {
    if (!projectId) {
      setInstances([]);
      setNodes([]);
      setLoading(false);
      setError("No project selected");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [instRes, nodesRes] = await Promise.all([
        listInstances(projectId, true).catch(() => ({ instances: [], metrics: [] })),
        listComputeNodes(projectId).catch(() => ({ nodes: [] })),
      ]);
      setInstances(instRes.instances || []);
      setNodes(nodesRes.nodes || []);
      if (instRes.metrics) {
        const m: Record<string, InstanceMetrics> = {};
        for (const item of instRes.metrics) m[item.instance_id] = item;
        setMetrics(m);
      }
    } catch {
      setInstances([]);
      setNodes([]);
    }
    setLoading(false);
  };

  useEffect(() => { fetchData(); }, [projectId]);

  const hasInstalling = instances.some((i) => i.state === "creating" || i.state === "installing");
  useEffect(() => {
    const interval = setInterval(fetchData, hasInstalling ? 10000 : 30000);
    return () => clearInterval(interval);
  }, [hasInstalling]);

  const handleSync = async () => {
    if (!projectId) return;
    setSyncing(true);
    setSyncResult("");
    try {
      const res = await syncInstancesToNodes(projectId);
      setSyncResult(`Registered ${res.registered}, skipped ${res.skipped}`);
      fetchData();
    } catch (e: any) {
      setSyncResult(e.message || "Sync failed");
    }
    setSyncing(false);
  };

  // Instance actions
  const handleDelete = async (item: UnifiedInstance) => {
    if (!projectId) return;
    if (!confirm(`Destroy "${item.label}"? This will permanently delete the server.`)) return;
    try {
      if (item.type === "instance" && item.raw_instance) {
        await deleteInstance(projectId, item.raw_instance.id);
      }
      if (item.raw_node) {
        await deleteComputeNode(projectId, item.raw_node.id).catch(() => {});
      } else if (item.type === "node") {
        await deleteComputeNode(projectId, item.id);
      }
      if (selectedId === item.id) { setSelectedId(null); setPanel(null); }
      fetchData();
    } catch (e: any) {
      alert(e.message || "Delete failed");
    }
  };

  const handleStop = async (inst: Instance) => {
    if (!projectId) return;
    try { await stopInstance(projectId, inst.id); fetchData(); } catch (e: any) { alert(e.message || "Stop failed"); }
  };

  const handleStart = async (inst: Instance) => {
    if (!projectId) return;
    try { await startInstance(projectId, inst.id); fetchData(); } catch (e: any) { alert(e.message || "Start failed"); }
  };

  const handleDrain = async (node: ComputeNode) => {
    if (!projectId) return;
    try { await drainNode(projectId, node.id); fetchData(); } catch (e: any) { alert(e.message || "Drain failed"); }
  };

  const handleCordon = async (node: ComputeNode) => {
    if (!projectId) return;
    try { await cordonNode(projectId, node.id); fetchData(); } catch (e: any) { alert(e.message || "Cordon failed"); }
  };

  const handleUncordon = async (node: ComputeNode) => {
    if (!projectId) return;
    try { await uncordonNode(projectId, node.id); fetchData(); } catch (e: any) { alert(e.message || "Uncordon failed"); }
  };

  // Loading state
  if (loading && unified.length === 0) {
    return (
      <div className="panel-empty">
        <RefreshCw className="h-8 w-8 animate-spin" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-sub">Loading machines...</div>
      </div>
    );
  }

  // Error state
  if (error) {
    const isNoProjects = error.includes("No projects") || error.includes("No project");
    return (
      <div className="panel-empty">
        <Server className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-title">{isNoProjects ? "No project yet" : "Error"}</div>
        <div className="panel-empty-sub">{isNoProjects ? "Create a project first to manage machines." : error}</div>
        {isNoProjects ? (
          <button className="panel-btn" onClick={async () => {
            try { await apiCreateProject("main"); setError(""); fetchData(); } catch (e: any) { setError(e.message || "Failed"); }
          }}>
            <Plus className="h-3.5 w-3.5" /><span>Create project</span>
          </button>
        ) : (
          <button className="panel-btn" onClick={fetchData}><RefreshCw className="h-3.5 w-3.5" /><span>Retry</span></button>
        )}
      </div>
    );
  }

  // Empty state
  if (unified.length === 0 && !showCreate) {
    return (
      <div className="panel-empty">
        <Server className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-title">No machines</div>
        <div className="panel-empty-sub">Add a server from NSO Cloud, connect via Vultr/Hetzner, or use SSH.</div>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="panel-btn" onClick={() => setShowCreate(true)}>
            <Plus className="h-3.5 w-3.5" /><span>Add Machine</span>
          </button>
          <button className="panel-btn" onClick={handleSync} disabled={syncing}>
            <Download className="h-3.5 w-3.5" /><span>{syncing ? "Syncing..." : "Sync"}</span>
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
          {unified.length} machine{unified.length !== 1 ? "s" : ""}
        </span>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="panel-btn-sm" onClick={fetchData} disabled={loading}>
            <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button className="panel-btn-sm" onClick={handleSync} disabled={syncing} title="Sync machines to nodes">
            <Download className="h-3 w-3" />
          </button>
          <button className="panel-btn-sm" onClick={() => setShowCreate(true)}>
            <Plus className="h-3 w-3" /><span>New</span>
          </button>
        </div>
      </div>

      {syncResult && (
        <div style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", padding: "0 0 8px" }}>
          {syncResult}
        </div>
      )}

      {/* Topology graph */}
      <TopologyGraph items={unified} selectedId={selectedId} onSelect={setSelectedId} />

      {/* Create form (connector-style) */}
      {showCreate && projectId && (
        <RegisterNodeForm
          projectId={projectId}
          onCreated={() => { setShowCreate(false); fetchData(); }}
          onCancel={() => setShowCreate(false)}
        />
      )}

      {/* Instance cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {unified.map((item) => {
          const isNode = !!item.raw_node && !item.raw_instance;
          const nodeMetrics = item.raw_node;
          const instMetrics = item.raw_instance ? metrics[item.raw_instance.id] : undefined;
          return (
            <div
              key={item.id}
              className={`proj-card ${selectedId === item.id ? "active" : ""}`}
              onClick={() => { setSelectedId(item.id); setPanel(null); }}
            >
              <div className="proj-card-icon">
                {isNode
                  ? <Cpu className="h-4 w-4" style={{ color: nodeStatusColor(item.state) }} />
                  : <Server className="h-4 w-4" style={{ color: stateColor(item.state) }} />
                }
              </div>
              <div className="proj-card-info" style={{ flex: 1 }}>
                <div className="proj-card-name">{item.label}</div>
                <div className="proj-card-meta">
                  {item.ip || "installing..."} — {item.plan}{item.region ? ` / ${item.region}` : ""}
                  {item.provider !== "nso" && ` · ${item.provider}`}
                </div>
                {/* Metrics bars */}
                {isNode && nodeMetrics && nodeMetrics.status === "online" && (
                  <div style={{ display: "flex", gap: 8, paddingTop: 4 }}>
                    <MetricBar label="CPU" value={nodeMetrics.cpu_used_percent} color="var(--color-blue)" />
                    <MetricBar label="RAM" value={nodeMetrics.mem_used_percent} color="var(--color-green)" />
                    <MetricBar label="Disk" value={nodeMetrics.disk_used_percent} color="var(--color-yellow)" />
                  </div>
                )}
                {!isNode && <InstanceMetricsBar metrics={instMetrics} />}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                {(item.state === "creating" || item.state === "installing") && (
                  <Loader className="h-3 w-3 animate-spin" style={{ color: "var(--color-yellow)" }} />
                )}
                <span className={`inst-badge ${
                  item.state === "ready" || item.state === "active" || item.state === "online" ? "badge-success"
                    : item.state === "stopped" || item.state === "offline" || item.state === "error" ? "badge-error"
                    : "badge-warning"
                }`}>
                  {item.state}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Selected detail */}
      {selected && (
        <div style={{ marginTop: 16, borderTop: "1px solid var(--border)", paddingTop: 16 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {selected.raw_instance
                ? <Server className="h-4 w-4" style={{ color: stateColor(selected.state) }} />
                : <Cpu className="h-4 w-4" style={{ color: nodeStatusColor(selected.state) }} />
              }
              <span style={{ fontWeight: 600, fontSize: "var(--font-sm)" }}>{selected.label}</span>
              {selected.ip && (
                <span style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)", fontFamily: "monospace" }}>
                  {selected.ip}{selected.raw_node ? `:${selected.raw_node.agent_port}` : ""}
                </span>
              )}
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              {/* Instance actions */}
              {selected.raw_instance && (
                <>
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
                    <button className="svc-btn yellow" title="Stop" onClick={() => handleStop(selected.raw_instance!)}>
                      <Power className="h-3.5 w-3.5" />
                    </button>
                  ) : selected.state === "stopped" ? (
                    <button className="svc-btn green" title="Start" onClick={() => handleStart(selected.raw_instance!)}>
                      <Play className="h-3.5 w-3.5" />
                    </button>
                  ) : null}
                </>
              )}
              {/* Node actions */}
              {selected.raw_node && selected.raw_node.status === "online" && (
                <>
                  <button className="svc-btn yellow" title="Drain" onClick={() => handleDrain(selected.raw_node!)}>
                    <Pause className="h-3.5 w-3.5" />
                  </button>
                  <button className="svc-btn yellow" title="Cordon" onClick={() => handleCordon(selected.raw_node!)}>
                    <ShieldCheck className="h-3.5 w-3.5" />
                  </button>
                </>
              )}
              {selected.raw_node && (selected.raw_node.status === "draining" || selected.raw_node.status === "maintenance") && (
                <button className="svc-btn green" title="Uncordon" onClick={() => handleUncordon(selected.raw_node!)}>
                  <ShieldOff className="h-3.5 w-3.5" />
                </button>
              )}
              <button className="svc-btn red" title="Destroy" onClick={() => handleDelete(selected)}>
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          {/* Info grid */}
          <div className="sys-grid" style={{ marginBottom: 12 }}>
            {[
              { label: "Name", value: selected.label },
              { label: "IP", value: selected.ip || "—" },
              { label: "Provider", value: selected.provider },
              { label: "Plan", value: selected.plan },
              ...(selected.region ? [{ label: "Region", value: selected.region }] : []),
              ...(selected.raw_instance?.metadata?.source_type ? [{
                label: "Source",
                value: selected.raw_instance.metadata.source_type === "repository"
                  ? (selected.raw_instance.metadata.git_url?.split("/").pop()?.replace(".git", "") || "github")
                  : selected.raw_instance.metadata.source_type === "zar"
                  ? (selected.raw_instance.metadata.zar_name || "zar")
                  : "empty"
              }] : []),
              ...(selected.raw_node ? [
                { label: "Role", value: selected.raw_node.role },
                { label: "CPU", value: `${selected.raw_node.cpu_allocated}/${selected.raw_node.cpu_cores} cores` },
                { label: "Memory", value: `${selected.raw_node.mem_allocated_mb}/${selected.raw_node.mem_total_mb} MB` },
                { label: "Agent", value: selected.raw_node.agent_reachable ? `v${selected.raw_node.agent_version || "?"}` : "unreachable" },
              ] : []),
              { label: "Created", value: (selected.raw_instance?.created_at || selected.raw_node?.created_at)?.split("T")[0] || "—" },
            ].map((item) => (
              <div key={item.label} className="sys-card">
                <div className="sys-label">{item.label}</div>
                <div className="sys-value">{item.value}</div>
              </div>
            ))}
          </div>

          {/* Metrics detail for instances */}
          {selected.raw_instance && metrics[selected.raw_instance.id]?.reachable && (
            <div className="sys-grid" style={{ marginBottom: 12 }}>
              {[
                { label: "CPU", value: `${metrics[selected.raw_instance.id].cpu_percent}%` },
                { label: "Memory", value: `${metrics[selected.raw_instance.id].mem_percent}%` },
                { label: "Disk", value: `${metrics[selected.raw_instance.id].disk_percent}%` },
                { label: "Load", value: `${metrics[selected.raw_instance.id].load_1m}` },
                { label: "Uptime", value: metrics[selected.raw_instance.id].uptime > 86400
                  ? `${Math.floor(metrics[selected.raw_instance.id].uptime / 86400)}d`
                  : metrics[selected.raw_instance.id].uptime > 3600
                  ? `${Math.floor(metrics[selected.raw_instance.id].uptime / 3600)}h`
                  : `${Math.floor(metrics[selected.raw_instance.id].uptime / 60)}m` },
                { label: "Status", value: metrics[selected.raw_instance.id].reachable ? "Online" : "Offline" },
              ].map((item) => (
                <div key={item.label} className="sys-card">
                  <div className="sys-label">{item.label}</div>
                  <div className="sys-value">{item.value}</div>
                </div>
              ))}
            </div>
          )}

          {/* Sub-panels */}
          {panel === "terminal" && projectId && selected.raw_instance && (
            <TerminalPanel projectId={projectId} instance={selected.raw_instance} />
          )}
          {panel === "files" && projectId && selected.raw_instance && (
            <FilesPanel instance={selected.raw_instance} />
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

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: "var(--font-xxs)",
  color: "var(--muted-foreground)",
  marginBottom: 4,
  textTransform: "uppercase",
  letterSpacing: "0.03em",
};

/* ═══════════════════════════════════════════
   ADD INSTANCE FORM
   ═══════════════════════════════════════════ */

function RegisterNodeForm({ projectId, onCreated, onCancel }: {
  projectId: string;
  onCreated: () => void;
  onCancel: () => void;
}) {
  const userEmail = useDashboardStore((s) => s.userEmail);
  const [method, setMethod] = useState<"pick" | "nso" | "ssh" | "install">("pick");
  const [label, setLabel] = useState("");
  const [ip, setIp] = useState("");
  const [region, setRegion] = useState("mad");
  const [plan, setPlan] = useState("vc2-1c-1gb");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const installCmd = `curl -fsSL https://nso.dev/install | bash -s -- \\
  --host https://nso.dev \\
  --email ${userEmail || "you@example.com"} \\
  --password <your-agent-password>`;

  const copyInstallCmd = () => {
    navigator.clipboard.writeText(installCmd);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const submitSSH = async () => {
    if (!ip.trim()) { setError("IP address or hostname is required"); return; }
    setCreating(true);
    setError("");
    try {
      await registerComputeNode(projectId, {
        label: label.trim() || ip.trim(),
        provider: "manual",
        ip: ip.trim(),
        agent_port: 8081,
        cpu_cores: 1,
        mem_total_mb: 1024,
      });
      onCreated();
    } catch (e: any) {
      setError(e.message || "Failed to connect");
    }
    setCreating(false);
  };

  const submitNSO = async () => {
    setCreating(true);
    setError("");
    try {
      await createInstance(projectId, {
        label: label.trim() || undefined,
        region,
        plan,
      });
      onCreated();
    } catch (e: any) {
      setError(e.message || "Failed to create server");
    }
    setCreating(false);
  };

  const formBox: React.CSSProperties = {
    border: "1px solid var(--border)", borderRadius: 8, padding: 16,
    marginBottom: 16, background: "var(--sidebar-background)",
  };

  const optionBtn = (
    onClick: () => void,
    icon: React.ReactNode,
    iconBg: string,
    iconColor: string,
    title: string,
    desc: string,
    hoverColor: string,
  ) => (
    <button
      onClick={onClick}
      style={{
        display: "flex", alignItems: "center", gap: 12,
        padding: "10px 14px", borderRadius: 8,
        border: "1px solid var(--border)",
        background: "var(--background)",
        cursor: "pointer", textAlign: "left",
        transition: "all 0.15s ease",
      }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = hoverColor; e.currentTarget.style.background = "var(--accent)"; }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.background = "var(--background)"; }}
    >
      <div style={{
        width: 32, height: 32, borderRadius: 8, background: iconBg,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontWeight: 700, fontSize: 14, flexShrink: 0, color: iconColor,
      }}>
        {icon}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: "var(--font-sm)", color: "var(--foreground)" }}>{title}</div>
        <div style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginTop: 1 }}>{desc}</div>
      </div>
      <ChevronRight className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)", opacity: 0.4, flexShrink: 0 }} />
    </button>
  );

  // ── Step 1: Pick method ──
  if (method === "pick") {
    return (
      <div style={formBox}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <div style={{ fontWeight: 600, fontSize: "var(--font-sm)" }}>Add Machine</div>
          <button className="panel-btn-sm" onClick={onCancel} style={{ fontSize: "var(--font-xxs)" }}>Cancel</button>
        </div>

        {/* NSO Cloud — primary */}
        <button
          onClick={() => setMethod("nso")}
          style={{
            display: "flex", alignItems: "center", gap: 12,
            padding: "14px 14px", borderRadius: 8,
            border: "1px solid rgba(100, 200, 180, 0.3)",
            background: "rgba(100, 200, 180, 0.06)",
            cursor: "pointer", textAlign: "left",
            transition: "all 0.15s ease",
          }}
          onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--color-teal)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.borderColor = "rgba(100, 200, 180, 0.3)"; }}
        >
          <div style={{
            width: 40, height: 40, borderRadius: 8,
            background: "rgba(100, 200, 180, 0.15)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontWeight: 700, fontSize: 18, flexShrink: 0,
            color: "var(--color-teal)",
          }}>
            N
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontWeight: 600, fontSize: "var(--font-sm)", color: "var(--foreground)" }}>NSO Cloud</span>
              <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 4, background: "rgba(16, 185, 129, 0.15)", color: "var(--color-green)", fontWeight: 600 }}>
                recommended
              </span>
            </div>
            <div style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginTop: 1 }}>
              Get a server from us — ready in minutes
            </div>
          </div>
          <ChevronRight className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)", opacity: 0.4, flexShrink: 0 }} />
        </button>

        <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "10px 0 6px" }}>
          <div style={{ flex: 1, height: 1, background: "var(--border)", opacity: 0.5 }} />
          <span style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", opacity: 0.6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            or connect your own
          </span>
          <div style={{ flex: 1, height: 1, background: "var(--border)", opacity: 0.5 }} />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {optionBtn(
            () => setMethod("ssh"),
            <span style={{ fontFamily: "monospace" }}>{">_"}</span>,
            "rgba(100, 200, 180, 0.1)", "var(--color-teal)",
            "Server or computer",
            "Hetzner, OVH, a VPS, or your own machine",
            "var(--color-teal)",
          )}
          {optionBtn(
            () => setMethod("install"),
            <Download className="h-4 w-4" />,
            "rgba(108, 58, 237, 0.1)", "#6C3AED",
            "Install command",
            "Run a one-liner on any machine to connect it",
            "#6C3AED",
          )}
        </div>
      </div>
    );
  }

  // ── SSH Connect — just IP, that's it ──
  if (method === "ssh") {
    return (
      <div style={formBox}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
          <button className="panel-btn-sm" onClick={() => { setMethod("pick"); setError(""); }} style={{ fontSize: "var(--font-xxs)", padding: "3px 8px" }}>
            ← Back
          </button>
          <div style={{
            width: 24, height: 24, borderRadius: 6,
            background: "rgba(100, 200, 180, 0.12)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontWeight: 700, fontSize: 11, flexShrink: 0,
            color: "var(--color-teal)", fontFamily: "monospace",
          }}>
            {">_"}
          </div>
          <span style={{ fontWeight: 600, fontSize: "var(--font-sm)" }}>Connect a server</span>
        </div>

        {error && (
          <div style={{ padding: "8px 12px", fontSize: "var(--font-xs)", color: "var(--color-red)", background: "rgba(239,68,68,0.08)", borderRadius: 6, marginBottom: 12 }}>
            {error}
          </div>
        )}

        <div style={{ marginBottom: 10 }}>
          <label style={labelStyle}>Host or IP</label>
          <input
            className="proj-input"
            type="text"
            placeholder="192.168.1.100 or server.example.com"
            value={ip}
            onChange={(e) => setIp(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") submitSSH(); if (e.key === "Escape") onCancel(); }}
            style={{ width: "100%" }}
            autoFocus
          />
        </div>

        <div style={{ marginBottom: 10 }}>
          <label style={labelStyle}>Name (optional)</label>
          <input
            className="proj-input"
            type="text"
            placeholder={ip.trim() || "my-server"}
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            style={{ width: "100%" }}
          />
        </div>

        <div style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginBottom: 12, lineHeight: 1.5 }}>
          NSO will connect via SSH, install the agent, and register this machine. Make sure SSH (port 22) is accessible and root login is allowed.
        </div>

        <div style={{ display: "flex", gap: 6 }}>
          <button className="deploy-action-btn teal" onClick={submitSSH} disabled={creating} style={{ padding: "5px 14px" }}>
            {creating ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Server className="h-3.5 w-3.5" />}
            <span>{creating ? "Connecting..." : "Connect"}</span>
          </button>
          <button className="panel-btn-sm" onClick={onCancel} disabled={creating}>Cancel</button>
        </div>
      </div>
    );
  }

  // ── Install command — copy and run ──
  if (method === "install") {
    return (
      <div style={formBox}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
          <button className="panel-btn-sm" onClick={() => { setMethod("pick"); setError(""); }} style={{ fontSize: "var(--font-xxs)", padding: "3px 8px" }}>
            ← Back
          </button>
          <Download className="h-4 w-4" style={{ color: "#6C3AED" }} />
          <span style={{ fontWeight: 600, fontSize: "var(--font-sm)" }}>Install command</span>
        </div>

        <div style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginBottom: 10, lineHeight: 1.5 }}>
          Run this on the machine you want to connect. The installer will set up the NSO agent and register it automatically.
        </div>

        <div style={{
          position: "relative",
          background: "var(--background)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          padding: "10px 12px",
          fontFamily: "monospace",
          fontSize: 11,
          lineHeight: 1.6,
          color: "var(--foreground)",
          whiteSpace: "pre-wrap",
          wordBreak: "break-all",
          marginBottom: 12,
        }}>
          <button
            onClick={copyInstallCmd}
            style={{
              position: "absolute", top: 6, right: 6,
              padding: "3px 8px", borderRadius: 4,
              border: "1px solid var(--border)",
              background: copied ? "rgba(16, 185, 129, 0.1)" : "var(--sidebar-background)",
              color: copied ? "var(--color-green)" : "var(--muted-foreground)",
              fontSize: 10, cursor: "pointer",
              transition: "all 0.15s ease",
            }}
          >
            {copied ? "Copied!" : "Copy"}
          </button>
          {installCmd}
        </div>

        <div style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", lineHeight: 1.5, opacity: 0.7 }}>
          After running the command, the machine will appear in your instances list automatically.
        </div>
      </div>
    );
  }

  // ── NSO Cloud — region + plan, that's all ──
  return (
    <div style={formBox}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
        <button className="panel-btn-sm" onClick={() => { setMethod("pick"); setError(""); }} style={{ fontSize: "var(--font-xxs)", padding: "3px 8px" }}>
          ← Back
        </button>
        <div style={{
          width: 24, height: 24, borderRadius: 6,
          background: "rgba(100, 200, 180, 0.12)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontWeight: 700, fontSize: 12, flexShrink: 0,
          color: "var(--color-teal)",
        }}>
          N
        </div>
        <span style={{ fontWeight: 600, fontSize: "var(--font-sm)" }}>NSO Cloud</span>
      </div>

      {error && (
        <div style={{ padding: "8px 12px", fontSize: "var(--font-xs)", color: "var(--color-red)", background: "rgba(239,68,68,0.08)", borderRadius: 6, marginBottom: 12 }}>
          {error}
        </div>
      )}

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

      <div style={{ marginBottom: 10 }}>
        <label style={labelStyle}>Name (optional)</label>
        <input className="proj-input" type="text" placeholder="my-server" value={label} onChange={(e) => setLabel(e.target.value)} style={{ width: "100%" }} autoFocus />
      </div>

      <div style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginBottom: 12, lineHeight: 1.5 }}>
        Ready in minutes. Agent pre-installed.
      </div>

      <div style={{ display: "flex", gap: 6 }}>
        <button className="deploy-action-btn teal" onClick={submitNSO} disabled={creating} style={{ padding: "5px 14px" }}>
          {creating ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Server className="h-3.5 w-3.5" />}
          <span>{creating ? "Creating..." : "Create Server"}</span>
        </button>
        <button className="panel-btn-sm" onClick={onCancel} disabled={creating}>Cancel</button>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   SERVICES TAB
   ═══════════════════════════════════════════ */

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
    if (activeProject && workspaces.length === 0) {
      listWorkspaces(activeProject.id).then((res) => setWorkspaces(res.workspaces || [])).catch(() => {});
    }
  }, [activeProject]);

  return (
    <div style={{ padding: "16px 0" }}>
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
