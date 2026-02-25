"use client";

import { useState } from "react";
import { RefreshCw, Play, Square, RotateCcw, Monitor } from "lucide-react";
import { manageService, execCommand } from "@/lib/api/client";

const SERVICES = [
  { name: "setupo", display: "NSO API", description: "Main REST API server" },
  { name: "setupo-agent", display: "NSO Agent", description: "Remote execution agent" },
  { name: "nginx", display: "nginx", description: "Reverse proxy & TLS" },
];

export function SettingsPanel() {
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
      const res = await execCommand(
        "cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'",
        "/opt/setupo", 5,
      );
      const mem = await execCommand("free -h | awk '/Mem:/{print $2, $3}'", "/opt/setupo", 5);
      const disk = await execCommand("df -h / | awk 'NR==2{print $2, $3, $5}'", "/opt/setupo", 5);
      const cpu = await execCommand("nproc", "/opt/setupo", 5);
      const up = await execCommand("uptime -p", "/opt/setupo", 5);

      setSysInfo({
        os: res.stdout.trim(),
        memory: mem.stdout.trim(),
        disk: disk.stdout.trim(),
        cpu: `${cpu.stdout.trim()} cores`,
        uptime: up.stdout.trim().replace("up ", ""),
      });
    } catch {}
    setSysLoading(false);
  };

  return (
    <div>
      {/* Services */}
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
                  <button
                    className="svc-btn"
                    title="Check status"
                    onClick={() => handleService("status", svc.name)}
                    disabled={loading === `${svc.name}-status`}
                  >
                    <RefreshCw className={`h-3 w-3 ${loading === `${svc.name}-status` ? "animate-spin" : ""}`} />
                  </button>
                  <button
                    className="svc-btn green"
                    title="Start"
                    onClick={() => handleService("start", svc.name)}
                  >
                    <Play className="h-3 w-3" />
                  </button>
                  <button
                    className="svc-btn red"
                    title="Stop"
                    onClick={() => handleService("stop", svc.name)}
                  >
                    <Square className="h-3 w-3" />
                  </button>
                  <button
                    className="svc-btn yellow"
                    title="Restart"
                    onClick={() => handleService("restart", svc.name)}
                  >
                    <RotateCcw className="h-3 w-3" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* System */}
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
