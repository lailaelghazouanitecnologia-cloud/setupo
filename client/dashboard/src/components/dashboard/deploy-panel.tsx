"use client";

import { useState, useEffect, useRef } from "react";
import {
  Rocket, RefreshCw, Package, Upload, Play,
  RotateCcw, GitBranch, Clock, Server, Loader,
  Settings2, Heart,
  Zap, AlertTriangle, CheckCircle2, XCircle,
  Box, Globe, Key, Terminal, Hammer, Database,
} from "lucide-react";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import { useDashboardStore } from "@/stores/dashboard-store";
import { formatSize } from "@/lib/format";
import {
  listWorkspaces, listInstances,
  zarPack, zarPush, zarDeploy, zarShip, zarRollback,
  zarVersions, getDeployStatus, getDeploySnapshots,
  readWorkspaceFile, listSecrets,
} from "@/lib/api/client";

type DeployAction = "pack" | "push" | "deploy" | "ship" | "rollback";
type DeployTab = "actions" | "pipeline" | "log";

interface LogEntry {
  time: string;
  action: DeployAction | "info" | "error" | "phase";
  message: string;
  ok: boolean;
}

interface DeployInfo {
  version: string;
  workspace: string;
  branch: string;
  stack: string;
  deployed_at: string;
  snapshot: string;
  hash: string;
}

interface PipelinePhase {
  phase: string;
  ok: boolean;
  message: string;
  duration_s: number;
}

// ── Simple TOML parser for deploy.toml display ──
function parseDeployToml(text: string): Record<string, any> {
  const result: Record<string, any> = {};
  let current = result;

  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;

    // Array of tables [[section]]
    if (line.startsWith("[[") && line.endsWith("]]")) {
      const name = line.slice(2, -2).trim();
      const parts = name.split(".");
      let parent = result;
      for (let i = 0; i < parts.length - 1; i++) {
        if (!parent[parts[i]]) parent[parts[i]] = {};
        parent = parent[parts[i]];
      }
      const key = parts[parts.length - 1];
      if (!parent[key]) parent[key] = [];
      if (!Array.isArray(parent[key])) parent[key] = [parent[key]];
      const entry: Record<string, any> = {};
      parent[key].push(entry);
      current = entry;
      continue;
    }

    // Section [section]
    if (line.startsWith("[") && line.endsWith("]")) {
      const name = line.slice(1, -1).trim();
      const parts = name.split(".");
      current = result;
      for (const p of parts) {
        if (!current[p]) current[p] = {};
        const val = current[p];
        if (Array.isArray(val)) {
          current = val[val.length - 1];
        } else {
          current = val;
        }
      }
      continue;
    }

    // Key = value
    if (line.includes("=")) {
      const idx = line.indexOf("=");
      const key = line.slice(0, idx).trim();
      let val: any = line.slice(idx + 1).trim();
      if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'")))
        val = val.slice(1, -1);
      else if (val === "true") val = true;
      else if (val === "false") val = false;
      else if (/^-?\d+$/.test(val)) val = parseInt(val);
      else if (val.startsWith("[") && val.endsWith("]")) {
        try {
          val = JSON.parse(val.replace(/'/g, '"'));
        } catch {
          val = val.slice(1, -1).split(",").map((s: string) => s.trim().replace(/['"]/g, "")).filter(Boolean);
        }
      }
      current[key] = val;
    }
  }
  return result;
}

// ── Find ${secret:KEY} references ──
function findSecretRefs(text: string): string[] {
  const refs = new Set<string>();
  const regex = /\$\{secret:([^}]+)\}/g;
  let match;
  while ((match = regex.exec(text)) !== null) {
    refs.add(match[1]);
  }
  return Array.from(refs).sort();
}

export function DeployPanel() {
  const activeProject = useDashboardStore((s) => s.activeProject);
  const projectId = activeProject?.id || "";
  const [workspaces, setWorkspaces] = useState<{ id: string; name: string }[]>([]);
  const [instances, setInstances] = useState<{ id: string; label: string; main_ip: string; status: string; state?: string; domain?: string; ip?: string; [key: string]: any }[]>([]);
  const [selectedWs, setSelectedWs] = useState("");
  const [selectedInstance, setSelectedInstance] = useState("");
  const [branch, setBranch] = useState("main");
  const [branches, setBranches] = useState<string[]>([]);
  const [versions, setVersions] = useState<string[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [running, setRunning] = useState<DeployAction | null>(null);
  const [deployInfo, setDeployInfo] = useState<DeployInfo | null>(null);
  const [snapshots, setSnapshots] = useState<string[]>([]);
  const [loadError, setLoadError] = useState("");
  const [dataLoading, setDataLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<DeployTab>("actions");
  const [deployConfig, setDeployConfig] = useState<Record<string, any> | null>(null);
  const [secretRefs, setSecretRefs] = useState<string[]>([]);
  const [projectSecrets, setProjectSecrets] = useState<string[]>([]);
  const [pipelinePhases, setPipelinePhases] = useState<PipelinePhase[]>([]);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo(0, logRef.current.scrollHeight);
  }, [logs]);

  // Reset selections when project changes
  useEffect(() => {
    setSelectedWs("");
    setSelectedInstance("");
    setBranch("main");
    setLogs([]);
    setPipelinePhases([]);
    setDeployInfo(null);
    setSnapshots([]);
  }, [projectId]);

  useEffect(() => {
    if (selectedInstance) loadDeployStatus();
    else { setDeployInfo(null); setSnapshots([]); }
  }, [selectedInstance]);

  const loadDeployStatus = () => {
    getDeployStatus()
      .then((data) => {
        const keys = Object.keys(data);
        if (keys.length > 0) {
          const info = data[keys[0]];
          setDeployInfo({
            version: info.version || "", workspace: info.workspace || "",
            branch: info.branch || "", stack: info.stack || "",
            deployed_at: info.deployed_at || "", snapshot: info.snapshot || "",
            hash: info.hash || "",
          });
        }
      })
      .catch(() => {});
    getDeploySnapshots().then((r) => setSnapshots(r.snapshots || [])).catch(() => {});
  };

  // Load deploy.toml when workspace changes
  useEffect(() => {
    if (!projectId || !selectedWs) {
      setDeployConfig(null); setSecretRefs([]);
      return;
    }
    readWorkspaceFile(projectId, selectedWs, "deploy.toml")
      .then((r) => {
        const content = r.content || "";
        setDeployConfig(parseDeployToml(content));
        setSecretRefs(findSecretRefs(content));
      })
      .catch(() => { setDeployConfig(null); setSecretRefs([]); });
  }, [projectId, selectedWs]);

  // Load project secrets
  useEffect(() => {
    if (!projectId) return;
    listSecrets(projectId)
      .then((r) => setProjectSecrets((r.secrets || []).map((s: any) => s.key)))
      .catch(() => setProjectSecrets([]));
  }, [projectId]);

  // Load workspaces + instances
  useEffect(() => {
    if (!projectId) { setDataLoading(false); return; }
    setLoadError(""); setDataLoading(true);
    setSelectedWs(""); setSelectedInstance("");
    (async () => {
      try {
        const wsRes = await listWorkspaces(projectId);
        const wsList = wsRes.workspaces || [];
        setWorkspaces(wsList);
        if (wsList.length > 0) setSelectedWs(wsList[0].name);
      } catch (e: any) {
        setWorkspaces([]);
        setLoadError(e.message?.includes("401") ? "Not authorized to load workspaces" : "Failed to load workspaces");
      }
      try {
        const instRes = await listInstances(projectId);
        const instList = instRes.instances || [];
        setInstances(instList);
        if (instList.length > 0) setSelectedInstance(instList[0].id);
      } catch (e: any) {
        setInstances([]);
        if (!loadError) setLoadError(e.message?.includes("401") ? "Not authorized to load instances" : "Failed to load instances");
      }
      setDataLoading(false);
    })();
  }, [projectId]);

  useEffect(() => {
    if (!projectId || !selectedWs) return;
    zarVersions(projectId, selectedWs, branch)
      .then((r) => {
        setVersions(r.versions || []);
        const br = r.branches;
        setBranches(Array.isArray(br) ? br : typeof br === "object" && br ? Object.keys(br) : []);
      })
      .catch(() => { setVersions([]); setBranches([]); });
  }, [projectId, selectedWs, branch]);

  const addLog = (action: LogEntry["action"], message: string, ok: boolean) => {
    const time = new Date().toLocaleTimeString("en-GB", { hour12: false });
    setLogs((l) => [...l, { time, action, message, ok }]);
  };

  const validateBeforeAction = (action: DeployAction): string | null => {
    if (!projectId) return "No project selected";
    if (!selectedWs) return "Select a workspace first";
    const needsInstance = ["deploy", "ship", "rollback"].includes(action);
    if (needsInstance && !selectedInstance) return "Select an instance first";
    if (needsInstance) {
      const inst = instances.find((i) => i.id === selectedInstance);
      if (inst) {
        const state = inst.state || "";
        if (state === "creating" || state === "installing") return `Instance is still ${state} — wait until it's ready`;
        if (state === "destroying") return "Instance is being destroyed — cannot deploy";
        if (state === "error") return `Instance is in error state — fix or recreate it first`;
      }
    }
    return null;
  };

  const runAction = async (action: DeployAction) => {
    if (running) return;
    const validationError = validateBeforeAction(action);
    if (validationError) { addLog("error", validationError, false); return; }

    setRunning(action);
    setPipelinePhases([]);
    addLog("info", `Starting ${action}...`, true);
    setActiveTab("log");

    try {
      let result: any;
      switch (action) {
        case "pack":
          result = await zarPack(projectId, selectedWs);
          addLog("pack", `Packed ${selectedWs} — ${formatSize(result.size || 0)}, v${result.manifest?.version || "?"}`, true);
          break;
        case "push":
          result = await zarPush(projectId, selectedWs, branch);
          addLog("push", `Pushed v${result.version || "?"} to R2 (${branch}) — ${formatSize(result.size || 0)}`, true);
          break;
        case "deploy":
          result = await zarDeploy(projectId, selectedWs, { branch, instance_id: selectedInstance });
          addLog("deploy", `Deployed ${selectedWs} to ${instanceLabel(selectedInstance)} — snapshot: ${result.snapshot || "n/a"}`, true);
          break;
        case "ship":
          result = await zarShip(projectId, selectedWs, { branch, instance_id: selectedInstance });
          addLog("ship", `Shipped ${selectedWs} v${result.version || "?"} to ${instanceLabel(selectedInstance)}${result.domain ? ` → https://${result.domain}` : ""}`, true);
          break;
        case "rollback":
          result = await zarRollback(projectId, selectedWs, selectedInstance);
          addLog("rollback", `Rolled back ${selectedWs} on ${instanceLabel(selectedInstance)}`, true);
          break;
      }

      // Log pipeline phases
      if (result?.phases && Array.isArray(result.phases)) {
        setPipelinePhases(result.phases);
        for (const phase of result.phases) {
          addLog("phase",
            `${phase.ok ? "\u2713" : "\u2717"} ${phase.phase} (${phase.duration_s}s)${phase.message ? " — " + phase.message : ""}`,
            phase.ok,
          );
        }
        if (result.pipeline) {
          addLog("info", `Pipeline deploy complete${result.rolled_back ? " (rolled back)" : ""}`, !result.rolled_back);
        }
      }

      if (["push", "ship"].includes(action)) {
        zarVersions(projectId, selectedWs, branch)
          .then((r) => {
            setVersions(r.versions || []);
            const br = r.branches;
            setBranches(Array.isArray(br) ? br : typeof br === "object" && br ? Object.keys(br) : []);
          })
          .catch(() => {});
      }
      if (["deploy", "ship", "rollback"].includes(action)) {
        setTimeout(loadDeployStatus, 2000);
      }
    } catch (e: any) {
      addLog("error", `${action} failed: ${e.message || "Unknown error"}`, false);
    }
    setRunning(null);
  };

  const instanceLabel = (id: string) => {
    const inst = instances.find((i) => i.id === id);
    return inst ? (inst.label || inst.domain || inst.ip || id) : id;
  };

  if (!projectId) {
    return (
      <div className="panel-empty">
        <Rocket className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-title">No project selected</div>
        <div className="panel-empty-sub">Select a project from the sidebar to manage deploys.</div>
      </div>
    );
  }

  if (dataLoading) {
    return (
      <div className="panel-empty">
        <RefreshCw className="h-8 w-8 animate-spin" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-sub">Loading deploy data...</div>
      </div>
    );
  }

  if (workspaces.length === 0 && instances.length === 0 && !loadError) {
    return (
      <div className="panel-empty">
        <Rocket className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-title">Nothing to deploy yet</div>
        <div className="panel-empty-sub">Create a workspace and an instance first.</div>
        <button className="panel-btn" onClick={() => useDashboardStore.getState().setActiveView("infrastructure")}>
          <Server className="h-3.5 w-3.5" /> <span>Create Instance</span>
        </button>
      </div>
    );
  }

  return (
    <div>
      {loadError && (
        <div style={{ padding: "8px 12px", fontSize: "var(--font-xs)", color: "var(--color-red)", background: "rgba(239,68,68,0.08)", borderRadius: 6, marginBottom: 12 }}>
          {loadError}
        </div>
      )}

      {/* Config bar */}
      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
        <div className="deploy-field">
          <Package className="h-3 w-3" style={{ color: "var(--color-teal)" }} />
          <Select value={selectedWs} onValueChange={setSelectedWs}>
            <SelectTrigger style={{ border: "none", background: "transparent", minWidth: 100, padding: "5px 8px" }}>
              <SelectValue placeholder={workspaces.length === 0 ? "No workspaces" : "Workspace..."} />
            </SelectTrigger>
            <SelectContent>
              {workspaces.map((ws) => <SelectItem key={ws.name} value={ws.name}>{ws.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="deploy-field">
          <GitBranch className="h-3 w-3" style={{ color: "var(--color-purple)" }} />
          <Select value={branch} onValueChange={setBranch}>
            <SelectTrigger style={{ border: "none", background: "transparent", minWidth: 80, padding: "5px 8px" }}>
              <SelectValue placeholder="Branch..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="main">main</SelectItem>
              {branches.filter((b) => b !== "main").map((b) => <SelectItem key={b} value={b}>{b}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="deploy-field">
          <Server className="h-3 w-3" style={{ color: "var(--color-blue)" }} />
          <Select value={selectedInstance} onValueChange={setSelectedInstance}>
            <SelectTrigger style={{ border: "none", background: "transparent", minWidth: 100, padding: "5px 8px" }}>
              <SelectValue placeholder={instances.length === 0 ? "No instances" : "Instance..."} />
            </SelectTrigger>
            <SelectContent>
              {instances.map((inst) => {
                const state = inst.state || "";
                const ready = ["ready", "running"].includes(state);
                const label = inst.label || inst.domain || inst.ip || inst.id;
                return (
                  <SelectItem key={inst.id} value={inst.id} disabled={!ready && state !== "deploying"}>
                    {label}{state && !ready ? ` (${state})` : ""}
                  </SelectItem>
                );
              })}
            </SelectContent>
          </Select>
        </div>
        {deployConfig && (
          <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "3px 8px", borderRadius: 4, background: "rgba(2,184,204,0.1)", fontSize: "var(--font-xxs)", color: "var(--color-teal)" }}>
            <Zap className="h-3 w-3" />
            Pipeline
          </div>
        )}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 2, marginBottom: 12, borderBottom: "1px solid var(--border)" }}>
        {([
          { id: "actions" as DeployTab, label: "Ship", icon: Rocket },
          { id: "pipeline" as DeployTab, label: "Pipeline Config", icon: Settings2 },
          { id: "log" as DeployTab, label: "Deploy Log", icon: Terminal },
        ]).map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              display: "flex", alignItems: "center", gap: 5,
              padding: "7px 14px", fontSize: "var(--font-xs)", fontWeight: 500,
              background: "transparent", border: "none", cursor: "pointer",
              color: activeTab === tab.id ? "var(--foreground)" : "var(--muted-foreground)",
              borderBottom: activeTab === tab.id ? "2px solid var(--color-teal)" : "2px solid transparent",
            }}
          >
            <tab.icon className="h-3.5 w-3.5" />
            {tab.label}
            {tab.id === "log" && logs.length > 0 && (
              <span style={{ fontSize: 10, background: "var(--sidebar-background)", padding: "1px 5px", borderRadius: 8 }}>{logs.length}</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab: Actions */}
      {activeTab === "actions" && (
        <div>
          <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
            <button className="deploy-action-btn teal" onClick={() => runAction("ship")} disabled={!!running || !selectedWs || !selectedInstance} style={{ padding: "6px 18px" }}>
              {running === "ship" ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Rocket className="h-3.5 w-3.5" />}
              <span>Ship</span>
            </button>
            <button className="deploy-action-btn yellow" onClick={() => runAction("rollback")} disabled={!!running || !selectedWs || !selectedInstance}>
              {running === "rollback" ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
              <span>Rollback</span>
            </button>
            <div style={{ width: 1, height: 20, background: "var(--border)", margin: "0 4px" }} />
            <button className="deploy-action-btn" onClick={() => runAction("pack")} disabled={!!running || !selectedWs} style={{ opacity: 0.7 }}>
              {running === "pack" ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Package className="h-3.5 w-3.5" />}
              <span>Pack</span>
            </button>
            <button className="deploy-action-btn" onClick={() => runAction("push")} disabled={!!running || !selectedWs} style={{ opacity: 0.7 }}>
              {running === "push" ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
              <span>Push</span>
            </button>
            <button className="deploy-action-btn" onClick={() => runAction("deploy")} disabled={!!running || !selectedWs || !selectedInstance} style={{ opacity: 0.7 }}>
              {running === "deploy" ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              <span>Deploy</span>
            </button>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {/* Current deploy */}
            <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                <div style={{ fontSize: "var(--font-xxs)", fontWeight: 600, color: "var(--muted-foreground)", textTransform: "uppercase", letterSpacing: "0.03em" }}>Current Deploy</div>
                <button className="panel-btn-sm" onClick={loadDeployStatus}><RefreshCw className="h-3 w-3" /></button>
              </div>
              {deployInfo ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {[
                    { label: "Workspace", value: deployInfo.workspace || "—" },
                    { label: "Version", value: deployInfo.version || "—" },
                    { label: "Branch", value: deployInfo.branch || "—" },
                    { label: "Snapshot", value: deployInfo.snapshot || "—" },
                    { label: "Deployed", value: deployInfo.deployed_at ? new Date(deployInfo.deployed_at).toLocaleString() : "—" },
                  ].map((item) => (
                    <div key={item.label} style={{ display: "flex", justifyContent: "space-between", fontSize: "var(--font-xs)" }}>
                      <span style={{ color: "var(--muted-foreground)" }}>{item.label}</span>
                      <span style={{ fontWeight: 500, fontFamily: "monospace", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textAlign: "right" }}>{item.value}</span>
                    </div>
                  ))}
                </div>
              ) : <div style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)" }}>No active deploy</div>}
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12 }}>
                <div style={{ fontSize: "var(--font-xxs)", fontWeight: 600, color: "var(--muted-foreground)", textTransform: "uppercase", letterSpacing: "0.03em", marginBottom: 6 }}>Versions ({branch})</div>
                {versions.length > 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 2, maxHeight: 80, overflowY: "auto" }}>
                    {versions.map((v) => <div key={v} style={{ fontSize: "var(--font-xs)", fontFamily: "monospace" }}>{v}</div>)}
                  </div>
                ) : <div style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)" }}>{selectedWs ? "No versions yet" : "Select a workspace"}</div>}
              </div>
              <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                  <div style={{ fontSize: "var(--font-xxs)", fontWeight: 600, color: "var(--muted-foreground)", textTransform: "uppercase", letterSpacing: "0.03em" }}>Snapshots</div>
                  <button className="panel-btn-sm" onClick={() => getDeploySnapshots().then((r) => setSnapshots(r.snapshots || [])).catch(() => {})}><RefreshCw className="h-3 w-3" /></button>
                </div>
                {snapshots.length > 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 2, maxHeight: 80, overflowY: "auto" }}>
                    {snapshots.map((s, i) => (
                      <div key={i} style={{ fontSize: "var(--font-xs)", fontFamily: "monospace", display: "flex", alignItems: "center", gap: 4 }}>
                        <Clock className="h-3 w-3" style={{ color: "var(--muted-foreground)", flexShrink: 0 }} />{s}
                      </div>
                    ))}
                  </div>
                ) : <div style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)" }}>No snapshots</div>}
              </div>
            </div>
          </div>

          {/* Pipeline phases summary */}
          {pipelinePhases.length > 0 && (
            <div style={{ marginTop: 12, border: "1px solid var(--border)", borderRadius: 8, padding: 12 }}>
              <div style={{ fontSize: "var(--font-xxs)", fontWeight: 600, color: "var(--muted-foreground)", textTransform: "uppercase", letterSpacing: "0.03em", marginBottom: 8 }}>Last Pipeline Run</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {pipelinePhases.map((phase, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "var(--font-xs)" }}>
                    {phase.ok
                      ? <CheckCircle2 className="h-3.5 w-3.5" style={{ color: "#4cb782", flexShrink: 0 }} />
                      : <XCircle className="h-3.5 w-3.5" style={{ color: "#f85149", flexShrink: 0 }} />
                    }
                    <span style={{ fontWeight: 600, minWidth: 110, fontFamily: "monospace" }}>{phase.phase}</span>
                    <span style={{ color: "var(--muted-foreground)", minWidth: 32 }}>{phase.duration_s}s</span>
                    <span style={{ color: phase.ok ? "var(--foreground)" : "#f85149", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{phase.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab: Pipeline Config */}
      {activeTab === "pipeline" && (
        <div>
          {!deployConfig ? (
            <div style={{ textAlign: "center", padding: "40px 20px", color: "var(--muted-foreground)" }}>
              <Settings2 className="h-8 w-8" style={{ margin: "0 auto 8px", opacity: 0.3 }} />
              <div style={{ fontSize: "var(--font-sm)", fontWeight: 500, marginBottom: 4 }}>No deploy.toml</div>
              <div style={{ fontSize: "var(--font-xs)" }}>
                {selectedWs ? `Workspace "${selectedWs}" uses legacy deploy flow.` : "Select a workspace to view its pipeline config."}
              </div>
              <div style={{ fontSize: "var(--font-xxs)", marginTop: 12 }}>
                Add a deploy.toml to enable the full pipeline: system setup, build steps, services, health checks, and hooks.
              </div>
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <CfgSection icon={Box} title="System" color="#a78bfa">
                {deployConfig.system ? (
                  <>
                    {deployConfig.system.packages && <CfgRow label="Packages" value={Array.isArray(deployConfig.system.packages) ? deployConfig.system.packages.join(", ") : String(deployConfig.system.packages)} />}
                    {deployConfig.system.firewall && Array.isArray(deployConfig.system.firewall) && <CfgRow label="Firewall" value={deployConfig.system.firewall.map((r: any) => `${r.port}/${r.proto || "tcp"}`).join(", ")} />}
                    {deployConfig.system.users && Array.isArray(deployConfig.system.users) && <CfgRow label="Users" value={deployConfig.system.users.map((u: any) => u.name).join(", ")} />}
                    {deployConfig.system.services?.enable && <CfgRow label="Enable" value={deployConfig.system.services.enable.join(", ")} />}
                  </>
                ) : <CfgEmpty text="No system config" />}
              </CfgSection>

              <CfgSection icon={Hammer} title="Install & Build" color="#f2c94c">
                {(deployConfig.install?.command || deployConfig.build?.command) ? (
                  <>
                    {deployConfig.install?.command && <CfgRow label="Install" value={deployConfig.install.command} />}
                    {deployConfig.build?.command && <CfgRow label="Build" value={deployConfig.build.command} />}
                    {deployConfig.build?.steps && Array.isArray(deployConfig.build.steps) && <CfgRow label="Steps" value={deployConfig.build.steps.map((s: any) => s.name).join(", ")} />}
                  </>
                ) : <CfgEmpty text="Auto-detect" />}
              </CfgSection>

              <CfgSection icon={Server} title="Services" color="#3b82f6">
                {deployConfig.services && Object.keys(deployConfig.services).length > 0 ? (
                  Object.entries(deployConfig.services).map(([name, svc]: [string, any]) => (
                    <div key={name} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "var(--font-xs)", marginBottom: 3 }}>
                      <span style={{ fontWeight: 600, fontFamily: "monospace", minWidth: 60 }}>{name}</span>
                      <span style={{ color: "var(--muted-foreground)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{svc.command || "—"}</span>
                      {svc.port && <span style={{ fontSize: 10, background: "rgba(59,130,246,0.1)", color: "#3b82f6", padding: "1px 5px", borderRadius: 3 }}>:{svc.port}</span>}
                      {svc.depends_on && <span style={{ fontSize: 10, color: "var(--muted-foreground)" }}>dep:{Array.isArray(svc.depends_on) ? svc.depends_on.join(",") : svc.depends_on}</span>}
                    </div>
                  ))
                ) : <CfgEmpty text="Legacy: nso-app restart" />}
              </CfgSection>

              <CfgSection icon={Globe} title="Nginx & Domains" color="#02b8cc">
                {deployConfig.nginx ? (
                  <>
                    <CfgRow label="Type" value={deployConfig.nginx.type || "proxy"} />
                    {deployConfig.nginx.proxy?.target && <CfgRow label="Target" value={deployConfig.nginx.proxy.target} />}
                    {deployConfig.nginx.proxy?.websocket && <CfgRow label="WebSocket" value="enabled" />}
                  </>
                ) : <CfgEmpty text="No nginx config" />}
                {deployConfig.domains && Array.isArray(deployConfig.domains) && deployConfig.domains.length > 0 && (
                  <div style={{ marginTop: 4 }}>
                    {deployConfig.domains.map((d: any, i: number) => (
                      <div key={i} style={{ fontSize: "var(--font-xs)", display: "flex", gap: 4, alignItems: "center", marginBottom: 2 }}>
                        <span style={{ fontFamily: "monospace" }}>{d.name}</span>
                        {d.ssl && <span style={{ fontSize: 10, background: "rgba(76,183,130,0.1)", color: "#4cb782", padding: "1px 4px", borderRadius: 3 }}>SSL</span>}
                      </div>
                    ))}
                  </div>
                )}
              </CfgSection>

              <CfgSection icon={Heart} title="Health Check" color="#4cb782">
                {deployConfig.health ? (
                  <>
                    <CfgRow label="Strategy" value={deployConfig.health.strategy || "none"} />
                    {deployConfig.health.http && (
                      <>
                        <CfgRow label="URL" value={deployConfig.health.http.url || ""} />
                        <CfgRow label="Expect" value={`${deployConfig.health.http.status || 200}`} />
                        <CfgRow label="Retries" value={`${deployConfig.health.http.retries || 5} x ${deployConfig.health.http.interval || 3}s`} />
                      </>
                    )}
                  </>
                ) : <CfgEmpty text="No health check" />}
              </CfgSection>

              <CfgSection icon={Database} title="Data" color="#f97316">
                {deployConfig.data ? (
                  <>
                    {deployConfig.data.migrate?.command && <CfgRow label="Migrate" value={`${deployConfig.data.migrate.command} (${deployConfig.data.migrate.on_fail || "abort"})`} />}
                    {deployConfig.data.seed?.command && <CfgRow label="Seed" value={`${deployConfig.data.seed.command} (${deployConfig.data.seed.only_if || "always"})`} />}
                  </>
                ) : <CfgEmpty text="No data config" />}
              </CfgSection>

              <CfgSection icon={Zap} title="Hooks" color="#e879f9">
                {deployConfig.hooks ? (
                  <>
                    {deployConfig.hooks.pre_deploy && Array.isArray(deployConfig.hooks.pre_deploy) && deployConfig.hooks.pre_deploy.map((h: any, i: number) => (
                      <div key={`pre-${i}`} style={{ fontSize: "var(--font-xs)", display: "flex", gap: 4, marginBottom: 2 }}>
                        <span style={{ color: "#f2c94c", fontSize: 10, minWidth: 30 }}>PRE</span>
                        <span style={{ fontFamily: "monospace" }}>{h.name}</span>
                        <span style={{ color: "var(--muted-foreground)", fontSize: 10 }}>({h.on_fail || "ignore"})</span>
                      </div>
                    ))}
                    {deployConfig.hooks.post_deploy && Array.isArray(deployConfig.hooks.post_deploy) && deployConfig.hooks.post_deploy.map((h: any, i: number) => (
                      <div key={`post-${i}`} style={{ fontSize: "var(--font-xs)", display: "flex", gap: 4, marginBottom: 2 }}>
                        <span style={{ color: "#4cb782", fontSize: 10, minWidth: 30 }}>POST</span>
                        <span style={{ fontFamily: "monospace" }}>{h.name}</span>
                        <span style={{ color: "var(--muted-foreground)", fontSize: 10 }}>({h.on_fail || "ignore"})</span>
                      </div>
                    ))}
                    {(!deployConfig.hooks.pre_deploy?.length && !deployConfig.hooks.post_deploy?.length) && <CfgEmpty text="No hooks defined" />}
                  </>
                ) : <CfgEmpty text="No hooks" />}
              </CfgSection>

              <CfgSection icon={Key} title="Secrets Required" color="#f85149">
                {secretRefs.length > 0 ? (
                  secretRefs.map((ref) => {
                    const configured = projectSecrets.includes(ref);
                    return (
                      <div key={ref} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "var(--font-xs)", marginBottom: 3 }}>
                        {configured
                          ? <CheckCircle2 className="h-3 w-3" style={{ color: "#4cb782", flexShrink: 0 }} />
                          : <AlertTriangle className="h-3 w-3" style={{ color: "#f2c94c", flexShrink: 0 }} />
                        }
                        <span style={{ fontFamily: "monospace" }}>{ref}</span>
                        <span style={{ fontSize: 10, color: configured ? "#4cb782" : "#f2c94c" }}>{configured ? "configured" : "missing"}</span>
                      </div>
                    );
                  })
                ) : <CfgEmpty text="No secret references" />}
              </CfgSection>
            </div>
          )}
        </div>
      )}

      {/* Tab: Deploy Log */}
      {activeTab === "log" && (
        <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
          <div style={{ padding: "6px 12px", background: "var(--sidebar-background)", display: "flex", alignItems: "center", gap: 6, borderBottom: "1px solid var(--border)" }}>
            <Terminal className="h-3 w-3" style={{ color: "var(--color-teal)" }} />
            <span style={{ fontSize: "var(--font-xs)", fontWeight: 600 }}>Deploy Log</span>
            <span style={{ marginLeft: "auto", fontSize: "var(--font-xxs)", color: "var(--muted-foreground)" }}>{logs.length} entries</span>
            {logs.length > 0 && (
              <button className="panel-btn-sm" onClick={() => { setLogs([]); setPipelinePhases([]); }} style={{ marginLeft: 4 }}>Clear</button>
            )}
          </div>
          <div
            ref={logRef}
            className="terminal-output"
            style={{ height: 400, fontSize: 11 }}
          >
            {logs.length === 0 ? (
              <div className="terminal-muted" style={{ textAlign: "center", paddingTop: 80 }}>Run an action to see deploy logs here</div>
            ) : (
              logs.map((entry, i) => (
                <div key={i} style={{ marginBottom: 4, display: "flex", gap: 8 }}>
                  <span className="terminal-muted" style={{ flexShrink: 0 }}>{entry.time}</span>
                  <span style={{ color: actionColor(entry.action), flexShrink: 0 }}>[{entry.action}]</span>
                  <span className={entry.ok ? "" : "terminal-error"}>{entry.message}</span>
                </div>
              ))
            )}
            {running && (
              <div style={{ display: "flex", gap: 8, color: "var(--blue-accent)" }}>
                <span className="terminal-muted">{new Date().toLocaleTimeString("en-GB", { hour12: false })}</span>
                <span>Running {running}...</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Helper components ──

function CfgSection({ icon: Icon, title, color, children }: { icon: any; title: string; color: string; children: React.ReactNode }) {
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 6 }}>
        <Icon className="h-3.5 w-3.5" style={{ color, flexShrink: 0 }} />
        <span style={{ fontSize: "var(--font-xs)", fontWeight: 600 }}>{title}</span>
      </div>
      {children}
    </div>
  );
}

function CfgRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "var(--font-xs)", marginBottom: 3 }}>
      <span style={{ color: "var(--muted-foreground)" }}>{label}</span>
      <span style={{ fontFamily: "monospace", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textAlign: "right" }}>{value}</span>
    </div>
  );
}

function CfgEmpty({ text }: { text: string }) {
  return <div style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)", fontStyle: "italic" }}>{text}</div>;
}

function actionColor(action: string): string {
  switch (action) {
    case "pack": return "var(--color-purple)";
    case "push": return "var(--color-blue)";
    case "deploy": return "var(--color-green)";
    case "ship": return "var(--color-teal)";
    case "rollback": return "var(--color-yellow)";
    case "phase": return "#e879f9";
    case "error": return "var(--terminal-error)";
    default: return "var(--terminal-muted)";
  }
}

