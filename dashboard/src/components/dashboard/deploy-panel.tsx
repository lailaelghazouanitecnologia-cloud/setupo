"use client";

import { useState, useEffect, useRef } from "react";
import {
  Rocket, RefreshCw, Package, Upload, Play,
  RotateCcw, GitBranch, CheckCircle, XCircle,
  Clock, ChevronDown, Server, Loader,
} from "lucide-react";
import {
  listProjects, listWorkspaces, listInstances,
  zarPack, zarPush, zarDeploy, zarShip, zarRollback,
  zarVersions, getDeployStatus, getDeploySnapshots,
} from "@/lib/api/client";

type DeployAction = "pack" | "push" | "deploy" | "ship" | "rollback";

interface LogEntry {
  time: string;
  action: DeployAction | "info" | "error";
  message: string;
  ok: boolean;
  detail?: any;
}

export function DeployPanel() {
  const [projects, setProjects] = useState<any[]>([]);
  const [projectId, setProjectId] = useState("");
  const [workspaces, setWorkspaces] = useState<any[]>([]);
  const [instances, setInstances] = useState<any[]>([]);
  const [selectedWs, setSelectedWs] = useState("");
  const [selectedInstance, setSelectedInstance] = useState("");
  const [branch, setBranch] = useState("main");
  const [branches, setBranches] = useState<string[]>([]);
  const [versions, setVersions] = useState<string[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [running, setRunning] = useState<DeployAction | null>(null);
  const [deployStatus, setDeployStatus] = useState<any>(null);
  const [snapshots, setSnapshots] = useState<any[]>([]);
  const logRef = useRef<HTMLDivElement>(null);

  // Scroll log to bottom
  useEffect(() => {
    logRef.current?.scrollTo(0, logRef.current.scrollHeight);
  }, [logs]);

  // Load projects on mount
  useEffect(() => {
    (async () => {
      try {
        const res = await listProjects();
        const projs = res.projects || [];
        setProjects(projs);
        if (projs.length > 0) setProjectId(projs[0].id);
      } catch {}
    })();
    // Load deploy status from agent
    getDeployStatus().then(setDeployStatus).catch(() => {});
    getDeploySnapshots().then((r) => setSnapshots(r.snapshots || [])).catch(() => {});
  }, []);

  // Load workspaces + instances when project changes
  useEffect(() => {
    if (!projectId) return;
    (async () => {
      try {
        const [wsRes, instRes] = await Promise.all([
          listWorkspaces(projectId),
          listInstances(projectId),
        ]);
        const wsList = wsRes.workspaces || [];
        const instList = instRes.instances || [];
        setWorkspaces(wsList);
        setInstances(instList);
        if (wsList.length > 0 && !selectedWs) setSelectedWs(wsList[0].name);
        if (instList.length > 0 && !selectedInstance) setSelectedInstance(instList[0].id);
      } catch {}
    })();
  }, [projectId]);

  // Load versions/branches when workspace or branch changes
  useEffect(() => {
    if (!projectId || !selectedWs) return;
    zarVersions(projectId, selectedWs, branch)
      .then((r) => {
        setVersions(r.versions || []);
        setBranches(r.branches || []);
      })
      .catch(() => {});
  }, [projectId, selectedWs, branch]);

  const addLog = (action: LogEntry["action"], message: string, ok: boolean, detail?: any) => {
    const time = new Date().toLocaleTimeString("en-GB", { hour12: false });
    setLogs((l) => [...l, { time, action, message, ok, detail }]);
  };

  const runAction = async (action: DeployAction) => {
    if (running || !projectId || !selectedWs) return;
    setRunning(action);
    addLog("info", `Starting ${action}...`, true);

    try {
      let result: any;
      switch (action) {
        case "pack":
          result = await zarPack(projectId, selectedWs);
          addLog("pack", `Packed ${selectedWs} — ${formatSize(result.size)}, v${result.manifest?.version}`, true, result);
          break;
        case "push":
          result = await zarPush(projectId, selectedWs, branch);
          addLog("push", `Pushed v${result.version} to R2 (${branch}) — ${formatSize(result.size)}`, true, result);
          break;
        case "deploy":
          if (!selectedInstance) { addLog("error", "Select an instance first", false); break; }
          result = await zarDeploy(projectId, selectedWs, { branch, instance_id: selectedInstance });
          addLog("deploy", `Deployed ${selectedWs} to ${selectedInstance} — snapshot: ${result.snapshot || "n/a"}`, true, result);
          break;
        case "ship":
          if (!selectedInstance) { addLog("error", "Select an instance first", false); break; }
          result = await zarShip(projectId, selectedWs, { branch, instance_id: selectedInstance });
          addLog("ship", `Shipped ${selectedWs} v${result.version} to ${selectedInstance}`, true, result);
          break;
        case "rollback":
          if (!selectedInstance) { addLog("error", "Select an instance first", false); break; }
          result = await zarRollback(projectId, selectedWs, selectedInstance);
          addLog("rollback", `Rolled back ${selectedWs} on ${selectedInstance}`, true, result);
          break;
      }
      // Refresh versions after mutating actions
      if (["push", "ship"].includes(action)) {
        zarVersions(projectId, selectedWs, branch)
          .then((r) => { setVersions(r.versions || []); setBranches(r.branches || []); })
          .catch(() => {});
      }
      // Refresh deploy status after deploy/ship/rollback
      if (["deploy", "ship", "rollback"].includes(action)) {
        getDeployStatus().then(setDeployStatus).catch(() => {});
        getDeploySnapshots().then((r) => setSnapshots(r.snapshots || [])).catch(() => {});
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

  return (
    <div>
      {/* Config bar */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {/* Project */}
        {projects.length > 1 && (
          <select className="deploy-select" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        )}
        {/* Workspace */}
        <div className="deploy-field">
          <Package className="h-3 w-3" style={{ color: "var(--color-teal)" }} />
          <select className="deploy-select" value={selectedWs} onChange={(e) => setSelectedWs(e.target.value)}>
            <option value="">Workspace...</option>
            {workspaces.map((ws) => <option key={ws.name} value={ws.name}>{ws.name}</option>)}
          </select>
        </div>
        {/* Branch */}
        <div className="deploy-field">
          <GitBranch className="h-3 w-3" style={{ color: "var(--color-purple)" }} />
          <select className="deploy-select" value={branch} onChange={(e) => setBranch(e.target.value)}>
            <option value="main">main</option>
            {branches.filter((b) => b !== "main").map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </div>
        {/* Instance */}
        <div className="deploy-field">
          <Server className="h-3 w-3" style={{ color: "var(--color-blue)" }} />
          <select className="deploy-select" value={selectedInstance} onChange={(e) => setSelectedInstance(e.target.value)}>
            <option value="">Instance...</option>
            {instances.map((inst) => (
              <option key={inst.id} value={inst.id}>
                {inst.label || inst.domain || inst.ip || inst.id}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Action buttons */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
        <button className="deploy-action-btn" onClick={() => runAction("pack")} disabled={!!running || !selectedWs}>
          {running === "pack" ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Package className="h-3.5 w-3.5" />}
          <span>Pack</span>
        </button>
        <button className="deploy-action-btn" onClick={() => runAction("push")} disabled={!!running || !selectedWs}>
          {running === "push" ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
          <span>Push</span>
        </button>
        <button className="deploy-action-btn" onClick={() => runAction("deploy")} disabled={!!running || !selectedWs || !selectedInstance}>
          {running === "deploy" ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
          <span>Deploy</span>
        </button>
        <button className="deploy-action-btn teal" onClick={() => runAction("ship")} disabled={!!running || !selectedWs || !selectedInstance}>
          {running === "ship" ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Rocket className="h-3.5 w-3.5" />}
          <span>Ship</span>
        </button>
        <button className="deploy-action-btn yellow" onClick={() => runAction("rollback")} disabled={!!running || !selectedWs || !selectedInstance}>
          {running === "rollback" ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
          <span>Rollback</span>
        </button>
      </div>

      {/* Two-column layout: log + status */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 280px", gap: 12 }}>
        {/* Deploy log */}
        <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
          <div style={{ padding: "6px 12px", background: "var(--sidebar-bg)", display: "flex", alignItems: "center", gap: 6, borderBottom: "1px solid var(--border)" }}>
            <Rocket className="h-3 w-3" style={{ color: "var(--color-teal)" }} />
            <span style={{ fontSize: "var(--font-xs)", fontWeight: 600 }}>Deploy Log</span>
            <span style={{ marginLeft: "auto", fontSize: "var(--font-xxs)", color: "var(--muted-foreground)" }}>
              {logs.length} entries
            </span>
            {logs.length > 0 && (
              <button className="panel-btn-sm" onClick={() => setLogs([])} style={{ marginLeft: 4 }}>
                Clear
              </button>
            )}
          </div>
          <div
            ref={logRef}
            style={{ height: 320, overflowY: "auto", padding: 12, fontFamily: "monospace", fontSize: 11, background: "#0d1117", color: "#c9d1d9" }}
          >
            {logs.length === 0 ? (
              <div style={{ color: "#484f58", textAlign: "center", paddingTop: 60 }}>
                Select a workspace and run an action to see deploy logs here
              </div>
            ) : (
              logs.map((entry, i) => (
                <div key={i} style={{ marginBottom: 4, display: "flex", gap: 8 }}>
                  <span style={{ color: "#484f58", flexShrink: 0 }}>{entry.time}</span>
                  <span style={{ color: actionColor(entry.action), flexShrink: 0 }}>
                    [{entry.action}]
                  </span>
                  <span style={{ color: entry.ok ? "#c9d1d9" : "#f85149" }}>
                    {entry.message}
                  </span>
                </div>
              ))
            )}
            {running && (
              <div style={{ display: "flex", gap: 8, color: "#58a6ff" }}>
                <span style={{ color: "#484f58" }}>{new Date().toLocaleTimeString("en-GB", { hour12: false })}</span>
                <span>Running {running}...</span>
              </div>
            )}
          </div>
        </div>

        {/* Status sidebar */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {/* Current deploy */}
          <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12 }}>
            <div style={{ fontSize: "var(--font-xxs)", fontWeight: 600, color: "var(--muted-foreground)", textTransform: "uppercase", letterSpacing: "0.03em", marginBottom: 8 }}>
              Current Deploy
            </div>
            {deployStatus ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {[
                  { label: "State", value: deployStatus.state || "—" },
                  { label: "Workspace", value: deployStatus.workspace || "—" },
                  { label: "Version", value: deployStatus.version || "—" },
                  { label: "Deployed", value: deployStatus.deployed_at ? new Date(deployStatus.deployed_at).toLocaleString() : "—" },
                ].map((item) => (
                  <div key={item.label} style={{ display: "flex", justifyContent: "space-between", fontSize: "var(--font-xs)" }}>
                    <span style={{ color: "var(--muted-foreground)" }}>{item.label}</span>
                    <span style={{ fontWeight: 500, fontFamily: "monospace" }}>{item.value}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)" }}>No deploy info</div>
            )}
          </div>

          {/* Versions */}
          <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12 }}>
            <div style={{ fontSize: "var(--font-xxs)", fontWeight: 600, color: "var(--muted-foreground)", textTransform: "uppercase", letterSpacing: "0.03em", marginBottom: 8 }}>
              Versions ({branch})
            </div>
            {versions.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 3, maxHeight: 120, overflowY: "auto" }}>
                {versions.map((v) => (
                  <div key={v} style={{ fontSize: "var(--font-xs)", fontFamily: "monospace", color: "var(--foreground)" }}>
                    {v}
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)" }}>
                {selectedWs ? "No versions yet" : "Select a workspace"}
              </div>
            )}
          </div>

          {/* Snapshots */}
          <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <div style={{ fontSize: "var(--font-xxs)", fontWeight: 600, color: "var(--muted-foreground)", textTransform: "uppercase", letterSpacing: "0.03em" }}>
                Snapshots
              </div>
              <button className="panel-btn-sm" onClick={() => getDeploySnapshots().then((r) => setSnapshots(r.snapshots || [])).catch(() => {})}>
                <RefreshCw className="h-3 w-3" />
              </button>
            </div>
            {snapshots.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 3, maxHeight: 100, overflowY: "auto" }}>
                {snapshots.map((s: any, i: number) => (
                  <div key={i} style={{ fontSize: "var(--font-xs)", fontFamily: "monospace", color: "var(--foreground)", display: "flex", alignItems: "center", gap: 6 }}>
                    <Clock className="h-3 w-3" style={{ color: "var(--muted-foreground)", flexShrink: 0 }} />
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {typeof s === "string" ? s : s.name || s.id || JSON.stringify(s)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)" }}>No snapshots</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function actionColor(action: string): string {
  switch (action) {
    case "pack": return "#a78bfa";
    case "push": return "#3b82f6";
    case "deploy": return "#4cb782";
    case "ship": return "#02b8cc";
    case "rollback": return "#f2c94c";
    case "error": return "#f85149";
    default: return "#484f58";
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
