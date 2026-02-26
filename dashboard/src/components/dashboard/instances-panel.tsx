"use client";

import { useState, useEffect, useRef } from "react";
import {
  Server, RefreshCw, Play, Square, Trash2,
  Activity, Monitor, Terminal, FolderOpen,
  ChevronDown, X, Send, RotateCcw, Power,
  FileText,
} from "lucide-react";
import {
  listProjects, listInstances, deleteInstance,
  stopInstance, startInstance, execOnInstance,
  execCommand, manageService, listFiles,
} from "@/lib/api/client";

type Tab = "instances" | "services";

interface Instance {
  id: string;
  type: string;
  state: string;
  region: string;
  plan: string;
  domain: string | null;
  provider_id: string;
  ip: string | null;
  created_at: string;
}

const SERVICES = [
  { name: "setupo", display: "NSO API", description: "Main REST API server" },
  { name: "setupo-agent", display: "NSO Agent", description: "Remote execution agent" },
  { name: "nginx", display: "nginx", description: "Reverse proxy & TLS" },
];

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

/* ═══ INSTANCES TAB ═══ */
function InstancesTab() {
  const [loading, setLoading] = useState(true);
  const [instances, setInstances] = useState<Instance[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Instance | null>(null);
  const [panel, setPanel] = useState<"terminal" | "files" | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError("");
    try {
      const projRes = await listProjects();
      const proj = projRes.projects?.[0];
      if (!proj) {
        setError("No projects found");
        setLoading(false);
        return;
      }
      setProjectId(proj.id);
      const instRes = await listInstances(proj.id);
      setInstances(instRes.instances || []);
    } catch (e: any) {
      setError(e.message || "Failed to load");
    }
    setLoading(false);
  };

  useEffect(() => { fetchData(); }, []);

  // Auto-refresh every 30s
  useEffect(() => {
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleDelete = async (inst: Instance) => {
    if (!projectId) return;
    if (!confirm(`Destroy instance "${inst.id}"? This will permanently delete the VPS.`)) return;
    try {
      await deleteInstance(projectId, inst.id);
      setInstances((prev) => prev.filter((i) => i.id !== inst.id));
      if (selected?.id === inst.id) { setSelected(null); setPanel(null); }
    } catch (e: any) {
      alert(e.message || "Delete failed");
    }
  };

  const handleStop = async (inst: Instance) => {
    if (!projectId) return;
    try {
      await stopInstance(projectId, inst.id);
      fetchData();
    } catch (e: any) { alert(e.message || "Stop failed"); }
  };

  const handleStart = async (inst: Instance) => {
    if (!projectId) return;
    try {
      await startInstance(projectId, inst.id);
      fetchData();
    } catch (e: any) { alert(e.message || "Start failed"); }
  };

  if (loading && instances.length === 0) {
    return (
      <div className="panel-empty">
        <RefreshCw className="h-8 w-8 animate-spin" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-sub">Loading instances...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="panel-empty">
        <Server className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-title">Error</div>
        <div className="panel-empty-sub">{error}</div>
        <button className="panel-btn" onClick={fetchData}>
          <RefreshCw className="h-3.5 w-3.5" />
          <span>Retry</span>
        </button>
      </div>
    );
  }

  if (instances.length === 0) {
    return (
      <div className="panel-empty">
        <Server className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-title">No instances</div>
        <div className="panel-empty-sub">Create instances via the API or CLI</div>
        <button className="panel-btn" onClick={fetchData}>
          <RefreshCw className="h-3.5 w-3.5" />
          <span>Refresh</span>
        </button>
      </div>
    );
  }

  return (
    <div style={{ padding: "16px 0" }}>
      <div className="panel-header-row" style={{ padding: "0 0 12px" }}>
        <span className="panel-count">
          {instances.length} instance{instances.length !== 1 ? "s" : ""}
        </span>
        <button className="panel-btn-sm" onClick={fetchData} disabled={loading}>
          <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

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
                {inst.domain || inst.ip || inst.id}
              </div>
              <div className="proj-card-meta">
                {inst.type} / {inst.plan} / {inst.region}
                {inst.ip ? ` — ${inst.ip}` : ""}
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span className={`inst-badge ${inst.state === "ready" || inst.state === "active" ? "green" : inst.state === "provisioning" ? "yellow" : "red"}`}>
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
                {selected.domain || selected.ip || selected.id}
              </span>
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
              {selected.state === "ready" ? (
                <button className="svc-btn yellow" title="Stop" onClick={() => handleStop(selected)}>
                  <Power className="h-3.5 w-3.5" />
                </button>
              ) : (
                <button className="svc-btn green" title="Start" onClick={() => handleStart(selected)}>
                  <Play className="h-3.5 w-3.5" />
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
              { label: "ID", value: selected.id },
              { label: "IP", value: selected.ip || "—" },
              { label: "Type", value: selected.type },
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

/* ═══ TERMINAL PANEL ═══ */
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
          {instance.ip || instance.id}
        </span>
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

/* ═══ FILES PANEL ═══ */
function FilesPanel({ instance }: { instance: Instance }) {
  const [files, setFiles] = useState<any[]>([]);
  const [currentPath, setCurrentPath] = useState("/opt/app");
  const [loading, setLoading] = useState(true);
  const [fileContent, setFileContent] = useState<{ path: string; content: string } | null>(null);

  const fetchFiles = async (path: string) => {
    if (!instance.ip) return;
    setLoading(true);
    setFileContent(null);
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

function stateColor(state: string): string {
  if (state === "ready" || state === "active") return "var(--color-green)";
  if (state === "provisioning" || state === "pending") return "var(--color-yellow)";
  return "var(--color-red)";
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/* ═══ SERVICES TAB ═══ */
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
      const os = await execCommand("cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'", "/opt/setupo", 5);
      const mem = await execCommand("free -h | awk '/Mem:/{print $2, $3}'", "/opt/setupo", 5);
      const disk = await execCommand("df -h / | awk 'NR==2{print $2, $3, $5}'", "/opt/setupo", 5);
      const cpu = await execCommand("nproc", "/opt/setupo", 5);
      const up = await execCommand("uptime -p", "/opt/setupo", 5);
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

  // Auto-fetch on mount
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
