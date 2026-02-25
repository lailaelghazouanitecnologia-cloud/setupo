"use client";

import { useState } from "react";
import { RefreshCw, Play, Square, RotateCcw } from "lucide-react";
import { manageService, execCommand } from "@/lib/api/client";

const SERVICES = ["setupo", "setupo-agent", "nginx"];

export function SettingsPanel() {
  const [results, setResults] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState<string | null>(null);
  const [sysInfo, setSysInfo] = useState<string | null>(null);

  const handleService = async (action: string, name: string) => {
    setLoading(`${name}-${action}`);
    try {
      const res = await manageService(action, name);
      setResults((prev) => ({ ...prev, [name]: res }));
    } catch (err: any) {
      setResults((prev) => ({ ...prev, [name]: { error: err.message } }));
    }
    setLoading(null);
  };

  const fetchSysInfo = async () => {
    setLoading("sysinfo");
    try {
      const res = await execCommand("echo '=== OS ===' && cat /etc/os-release | head -3 && echo '=== Memory ===' && free -h | head -2 && echo '=== Disk ===' && df -h / | tail -1 && echo '=== CPU ===' && nproc && echo '=== Uptime ===' && uptime", "/opt/setupo", 10);
      setSysInfo(res.stdout);
    } catch {}
    setLoading(null);
  };

  return (
    <div className="animate-fade-in">
      {/* Services */}
      <div style={{ fontSize: "var(--font-lg)", fontWeight: 500, marginBottom: 12 }}>Services</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 24 }}>
        {SERVICES.map((svc) => (
          <div key={svc} className="note-block" style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 500, fontSize: "var(--font-md)" }}>{svc}</div>
              {results[svc] && (
                <div style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)", marginTop: 2 }}>
                  {results[svc].error
                    ? <span style={{ color: "var(--color-red)" }}>{results[svc].error}</span>
                    : <>Exit: {results[svc].exit_code} {results[svc].active !== undefined && (results[svc].active ? " — Active" : " — Inactive")}</>
                  }
                </div>
              )}
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              <button
                className="ibtn"
                title="Status"
                onClick={() => handleService("status", svc)}
                disabled={loading === `${svc}-status`}
              >
                <RefreshCw className="h-3.5 w-3.5" />
              </button>
              <button
                className="ibtn"
                title="Start"
                onClick={() => handleService("start", svc)}
                style={{ color: "var(--color-green)" }}
              >
                <Play className="h-3.5 w-3.5" />
              </button>
              <button
                className="ibtn"
                title="Stop"
                onClick={() => handleService("stop", svc)}
                style={{ color: "var(--color-red)" }}
              >
                <Square className="h-3.5 w-3.5" />
              </button>
              <button
                className="ibtn"
                title="Restart"
                onClick={() => handleService("restart", svc)}
                style={{ color: "var(--color-yellow)" }}
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* System info */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <span style={{ fontSize: "var(--font-lg)", fontWeight: 500 }}>System Info</span>
        <button className="task-btn" style={{ width: "auto", padding: "0 12px", marginBottom: 0 }} onClick={fetchSysInfo}>
          {loading === "sysinfo" ? "Loading..." : "Fetch"}
        </button>
      </div>
      {sysInfo && (
        <pre style={{
          background: "oklch(0.13 0.005 286)",
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: 12,
          fontFamily: "var(--font-mono)",
          fontSize: "var(--font-sm)",
          color: "#e0e0e0",
          whiteSpace: "pre-wrap",
        }}>
          {sysInfo}
        </pre>
      )}
    </div>
  );
}
