"use client";

import { useState } from "react";
import { Server, RefreshCw, Globe, Cpu, MemoryStick, HardDrive } from "lucide-react";
import { execCommand } from "@/lib/api/client";

export function InstancesPanel() {
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
        <div className="panel-empty-title">Instances</div>
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
        <div className="panel-empty-sub">No VPS instances found on this account</div>
        <button className="panel-btn" onClick={fetchInstances}>
          <RefreshCw className="h-3.5 w-3.5" />
          <span>Retry</span>
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="panel-header-row">
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
              <div
                className="inst-dot"
                style={{ background: inst.power_status === "running" ? "var(--color-green)" : "var(--color-red)" }}
              />
              <div>
                <div className="inst-name">{inst.label || inst.id}</div>
                <div className="inst-os">{inst.os}</div>
              </div>
            </div>
            <div className="inst-cell">
              <span className={`inst-badge ${inst.status === "active" ? "green" : "yellow"}`}>
                {inst.status}
              </span>
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
