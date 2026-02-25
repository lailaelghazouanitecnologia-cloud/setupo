"use client";

import { useState, useRef, useEffect } from "react";
import { Terminal, Play } from "lucide-react";
import { execCommand } from "@/lib/api/client";

interface HistoryEntry {
  command: string;
  stdout: string;
  stderr: string;
  exit_code: number;
  timed_out: boolean;
}

export function TerminalPanel() {
  const [command, setCommand] = useState("");
  const [cwd, setCwd] = useState("/opt/setupo");
  const [running, setRunning] = useState(false);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const outputRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [history]);

  const handleExec = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!command.trim() || running) return;
    setRunning(true);
    try {
      const res = await execCommand(command, cwd);
      setHistory((h) => [...h, { command, ...res }]);
    } catch (err: any) {
      setHistory((h) => [...h, {
        command,
        stdout: "",
        stderr: err.message || "Request failed",
        exit_code: -1,
        timed_out: false,
      }]);
    }
    setCommand("");
    setRunning(false);
  };

  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 180px)" }}>
      {/* CWD */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)" }}>Working dir:</span>
        <input
          value={cwd}
          onChange={(e) => setCwd(e.target.value)}
          style={{
            flex: 1,
            padding: "4px 8px",
            background: "var(--input)",
            border: "1px solid var(--border)",
            borderRadius: 4,
            fontSize: "var(--font-sm)",
            color: "var(--foreground)",
            fontFamily: "var(--font-mono)",
            outline: "none",
          }}
        />
      </div>

      {/* Output */}
      <div
        ref={outputRef}
        style={{
          flex: 1,
          background: "oklch(0.13 0.005 286)",
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: 12,
          fontFamily: "var(--font-mono)",
          fontSize: "var(--font-sm)",
          color: "#e0e0e0",
          overflowY: "auto",
          marginBottom: 8,
        }}
      >
        {history.length === 0 ? (
          <div style={{ color: "var(--muted-foreground)", display: "flex", alignItems: "center", gap: 8 }}>
            <Terminal className="h-4 w-4" />
            <span>Agent terminal — execute commands on your VPS</span>
          </div>
        ) : (
          history.map((entry, i) => (
            <div key={i} style={{ marginBottom: 12 }}>
              <div style={{ color: "#4cb782" }}>
                <span style={{ color: "#3b82f6" }}>setupo</span>
                <span style={{ color: "#737373" }}>:</span>
                <span style={{ color: "#02b8cc" }}>{cwd}</span>
                <span style={{ color: "#737373" }}>$ </span>
                {entry.command}
              </div>
              {entry.stdout && <pre style={{ margin: "4px 0", whiteSpace: "pre-wrap", wordBreak: "break-all" }}>{entry.stdout}</pre>}
              {entry.stderr && <pre style={{ margin: "4px 0", color: "#e5484d", whiteSpace: "pre-wrap" }}>{entry.stderr}</pre>}
              {entry.exit_code !== 0 && (
                <div style={{ color: "#e5484d", fontSize: "var(--font-xs)" }}>
                  Exit code: {entry.exit_code}{entry.timed_out ? " (timed out)" : ""}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Input */}
      <form onSubmit={handleExec} style={{ display: "flex", gap: 8 }}>
        <div style={{
          display: "flex", alignItems: "center", gap: 6,
          flex: 1,
          padding: "6px 10px",
          background: "var(--input)",
          border: "1px solid var(--border)",
          borderRadius: 6,
        }}>
          <span style={{ color: "var(--color-green)", fontFamily: "var(--font-mono)", fontSize: "var(--font-sm)" }}>$</span>
          <input
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            placeholder={running ? "Running..." : "Enter command..."}
            disabled={running}
            style={{
              flex: 1,
              background: "transparent",
              border: "none",
              outline: "none",
              fontFamily: "var(--font-mono)",
              fontSize: "var(--font-sm)",
              color: "var(--foreground)",
            }}
            autoFocus
          />
        </div>
        <button
          type="submit"
          disabled={running}
          style={{
            padding: "6px 14px",
            background: "var(--primary)",
            color: "var(--primary-foreground)",
            border: "none",
            borderRadius: 6,
            cursor: running ? "wait" : "pointer",
            display: "flex",
            alignItems: "center",
            gap: 4,
            fontSize: "var(--font-sm)",
          }}
        >
          <Play className="h-3 w-3" /> Run
        </button>
      </form>
    </div>
  );
}
