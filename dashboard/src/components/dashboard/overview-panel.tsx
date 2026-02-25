"use client";

import { Server, Cpu, HardDrive, Activity } from "lucide-react";

export function OverviewPanel({ apiHealth, agentHealth }: { apiHealth: any; agentHealth: any }) {
  return (
    <div className="animate-fade-in">
      {/* Stats cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 24 }}>
        <StatCard
          icon={<Server className="h-3.5 w-3.5" />}
          label="API"
          value={apiHealth ? "Online" : "Offline"}
          detail={apiHealth ? `v${apiHealth.version}` : "—"}
          color={apiHealth ? "var(--color-green)" : "var(--color-red)"}
        />
        <StatCard
          icon={<Activity className="h-3.5 w-3.5" />}
          label="Agent"
          value={agentHealth ? "Online" : "Offline"}
          detail={agentHealth ? `v${agentHealth.version}` : "—"}
          color={agentHealth ? "var(--color-green)" : "var(--color-red)"}
        />
        <StatCard
          icon={<Cpu className="h-3.5 w-3.5" />}
          label="Platform"
          value={apiHealth?.platform || "—"}
          detail={apiHealth ? `Uptime: ${Math.round(apiHealth.uptime_seconds / 60)}m` : "—"}
          color="var(--color-blue)"
        />
        <StatCard
          icon={<HardDrive className="h-3.5 w-3.5" />}
          label="Features"
          value={agentHealth?.features?.length || 0}
          detail={agentHealth?.features?.join(", ") || "—"}
          color="var(--color-purple)"
        />
      </div>

      {/* Service details */}
      {apiHealth && (
        <div className="note-block" style={{ marginBottom: 16 }}>
          <div style={{ fontSize: "var(--font-lg)", fontWeight: 500, marginBottom: 8 }}>API Health</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: "var(--font-sm)" }}>
            <Detail label="Status" value={apiHealth.status} />
            <Detail label="Version" value={apiHealth.version} />
            <Detail label="Uptime" value={`${Math.round(apiHealth.uptime_seconds)}s`} />
            <Detail label="Platform" value={apiHealth.platform} />
          </div>
        </div>
      )}

      {agentHealth && (
        <div className="note-block">
          <div style={{ fontSize: "var(--font-lg)", fontWeight: 500, marginBottom: 8 }}>Agent Capabilities</div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {agentHealth.features?.map((f: string) => (
              <span key={f} className="pill">
                <span className="pill-dot" style={{ background: "var(--color-teal)" }} />
                {f}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ icon, label, value, detail, color }: {
  icon: React.ReactNode; label: string; value: any; detail: string; color: string;
}) {
  return (
    <div className="note-block" style={{ padding: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
        <div style={{ color }}>{icon}</div>
        <span style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)" }}>{label}</span>
      </div>
      <div style={{ fontSize: 18, fontWeight: 600, color }}>{String(value)}</div>
      <div style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)", marginTop: 2 }}>{detail}</div>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span style={{ color: "var(--muted-foreground)" }}>{label}: </span>
      <span className="w">{value}</span>
    </div>
  );
}
