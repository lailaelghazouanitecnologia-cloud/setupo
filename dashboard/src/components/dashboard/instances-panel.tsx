"use client";

import { useState } from "react";
import {
  Server, RefreshCw, Play, Square, RotateCcw,
  Activity, Monitor,
} from "lucide-react";
import { execCommand, manageService } from "@/lib/api/client";

type Tab = "instances" | "services";

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
  const [loading, setLoading] = useState(false);
  const [instances, setInstances] = useState<any[]>([]);
  const [fetched, setFetched] = useState(false);

  const fetchInstances = async () => {
    setLoading(true);
    try {
      const res = await execCommand(
        "curl -sf https://api.vultr.com/v2/instances -H \"Authorization: Bearer $VULTR_API_KEY\" | python3 -m json.tool",
        "/opt/setupo", 30,
      );
      if (res.exit_code === 0 && res.stdout) {
        const data = JSON.parse(res.stdout);
        setInstances(data.instances || []);
      }
    } catch {}
    setLoading(false);
    setFetched(true);
  };

  if (!fetched) {
    return (
      <div className="panel-empty">
        <Server className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-title">Cloud Instances</div>
        <div className="panel-empty-sub">Fetch live data from your cloud provider</div>
        <button className="panel-btn" onClick={fetchInstances} disabled={loading}>
          {loading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Server className="h-3.5 w-3.5" />}
          <span>{loading ? "Fetching..." : "Load instances"}</span>
        </button>
      </div>
    );
  }

  if (instances.length === 0) {
    return (
      <div className="panel-empty">
        <Server className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-title">No instances</div>
        <div className="panel-empty-sub">No VPS instances found</div>
        <button className="panel-btn" onClick={fetchInstances}>
          <RefreshCw className="h-3.5 w-3.5" />
          <span>Retry</span>
        </button>
      </div>
    );
  }

  return (
    <div style={{ padding: "16px 0" }}>
      <div className="panel-header-row" style={{ padding: "0 0 12px" }}>
        <span className="panel-count">{instances.length} instance{instances.length !== 1 ? "s" : ""}</span>
        <button className="panel-btn-sm" onClick={fetchInstances} disabled={loading}>
          <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>
      <div className="inst-table">
        <div className="inst-thead">
          <span className="inst-th" style={{ flex: 2 }}>Name</span>
          <span className="inst-th">Status</span>
          <span className="inst-th">IP</span>
          <span className="inst-th">Region</span>
          <span className="inst-th">CPU</span>
          <span className="inst-th">RAM</span>
        </div>
        {instances.map((inst: any) => (
          <div key={inst.id} className="inst-row">
            <div className="inst-cell" style={{ flex: 2, gap: 8 }}>
              <div className="inst-dot" style={{ background: inst.power_status === "running" ? "var(--color-green)" : "var(--color-red)" }} />
              <div>
                <div className="inst-name">{inst.label || inst.id}</div>
                <div className="inst-os">{inst.os}</div>
              </div>
            </div>
            <div className="inst-cell">
              <span className={`inst-badge ${inst.status === "active" ? "green" : "yellow"}`}>{inst.status}</span>
            </div>
            <div className="inst-cell inst-mono">{inst.main_ip}</div>
            <div className="inst-cell">{inst.region}</div>
            <div className="inst-cell">{inst.vcpu_count} vCPU</div>
            <div className="inst-cell">{inst.ram >= 1024 ? `${(inst.ram / 1024).toFixed(0)} GB` : `${inst.ram} MB`}</div>
          </div>
        ))}
      </div>
    </div>
  );
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
            <span>{sysLoading ? "Loading" : "Fetch"}</span>
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
            <span>Click Fetch to load system information</span>
          </div>
        )}
      </div>
    </div>
  );
}
