"use client";

import { useState } from "react";
import { Server, Globe, Cpu, MemoryStick } from "lucide-react";
import { execCommand } from "@/lib/api/client";

export function InstancesPanel() {
  const [loading, setLoading] = useState(false);
  const [instances, setInstances] = useState<any[]>([]);
  const [fetched, setFetched] = useState(false);

  const fetchInstances = async () => {
    setLoading(true);
    try {
      const res = await execCommand("curl -sf https://api.vultr.com/v2/instances -H \"Authorization: Bearer $VULTR_API_KEY\" | python3 -m json.tool", "/opt/setupo", 30);
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
      <div className="animate-fade-in">
        <button className="task-btn" style={{ maxWidth: 200 }} onClick={fetchInstances}>
          <Server className="h-3.5 w-3.5" /><span>{loading ? "Loading..." : "Load instances"}</span>
        </button>
        <p style={{ fontSize: "var(--font-sm)", color: "var(--muted-foreground)" }}>
          Fetches live instance data from Vultr API via the agent.
        </p>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
        <span className="pill">
          <span className="pill-dot" style={{ background: "var(--color-teal)" }} />
          {instances.length} instances
        </span>
        <button className="task-btn" style={{ width: "auto", padding: "0 12px" }} onClick={fetchInstances}>
          Refresh
        </button>
      </div>

      {instances.length === 0 ? (
        <div className="note-block" style={{ textAlign: "center", padding: 32 }}>
          <Server className="h-8 w-8" style={{ color: "var(--muted-foreground)", margin: "0 auto 8px" }} />
          <div style={{ fontSize: "var(--font-md)", color: "var(--muted-foreground)" }}>No instances found</div>
        </div>
      ) : (
        instances.map((inst) => (
          <div key={inst.id} className="note-block" style={{ marginBottom: 10 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{
                  width: 8, height: 8, borderRadius: "50%",
                  background: inst.power_status === "running" ? "var(--color-green)" : "var(--color-red)",
                }} />
                <span style={{ fontWeight: 500, fontSize: "var(--font-md)" }}>{inst.label || inst.id}</span>
              </div>
              <span className="pill">
                <span className="pill-dot" style={{ background: inst.status === "active" ? "var(--color-green)" : "var(--color-yellow)" }} />
                {inst.status}
              </span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 8, fontSize: "var(--font-sm)", color: "var(--muted-foreground)" }}>
              <div><Globe className="h-3 w-3 inline mr-1" />{inst.main_ip}</div>
              <div><Server className="h-3 w-3 inline mr-1" />{inst.region}</div>
              <div><Cpu className="h-3 w-3 inline mr-1" />{inst.vcpu_count} vCPU</div>
              <div><MemoryStick className="h-3 w-3 inline mr-1" />{inst.ram}MB</div>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
