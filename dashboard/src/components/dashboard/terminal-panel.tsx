"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { X, Plus, ChevronDown } from "lucide-react";
import { execCommand } from "@/lib/api/client";

interface HistoryEntry {
  command: string;
  stdout: string;
  stderr: string;
  exit_code: number;
  timed_out: boolean;
  cwd: string;
}

export function TerminalPanel() {
  const [command, setCommand] = useState("");
  const [cwd, setCwd] = useState("/opt/setupo");
  const [running, setRunning] = useState(false);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [cmdHistory, setCmdHistory] = useState<string[]>([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const outputRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [history, running]);

  // Focus input on click anywhere in terminal
  const focusInput = useCallback(() => {
    inputRef.current?.focus();
  }, []);

  const handleExec = async (e: React.FormEvent) => {
    e.preventDefault();
    const cmd = command.trim();
    if (!cmd || running) return;

    // Handle cd command locally
    if (cmd.startsWith("cd ")) {
      const target = cmd.slice(3).trim();
      const newCwd = target.startsWith("/") ? target : `${cwd}/${target}`.replace(/\/+/g, "/");
      setCwd(newCwd);
      setHistory((h) => [...h, { command: cmd, stdout: "", stderr: "", exit_code: 0, timed_out: false, cwd }]);
      setCommand("");
      setCmdHistory((h) => [cmd, ...h]);
      setHistoryIdx(-1);
      return;
    }

    // Handle clear
    if (cmd === "clear") {
      setHistory([]);
      setCommand("");
      return;
    }

    setCmdHistory((h) => [cmd, ...h]);
    setHistoryIdx(-1);
    setRunning(true);
    setCommand("");

    try {
      const res = await execCommand(cmd, cwd);
      setHistory((h) => [...h, { command: cmd, ...res, cwd }]);
    } catch (err: any) {
      setHistory((h) => [...h, {
        command: cmd,
        stdout: "",
        stderr: err.message || "Connection failed",
        exit_code: -1,
        timed_out: false,
        cwd,
      }]);
    }
    setRunning(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (cmdHistory.length > 0) {
        const next = Math.min(historyIdx + 1, cmdHistory.length - 1);
        setHistoryIdx(next);
        setCommand(cmdHistory[next]);
      }
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (historyIdx > 0) {
        const next = historyIdx - 1;
        setHistoryIdx(next);
        setCommand(cmdHistory[next]);
      } else {
        setHistoryIdx(-1);
        setCommand("");
      }
    }
  };

  return (
    <div className="term-container" onClick={focusInput}>
      {/* Tab bar */}
      <div className="term-tabs">
        <div className="term-tab active">
          <span className="term-tab-icon">{">"}_</span>
          <span>bash</span>
          <span className="term-tab-path">{cwd.split("/").pop()}</span>
        </div>
        <div className="term-tab-actions">
          <button className="term-tab-btn" title="New terminal"><Plus className="h-3.5 w-3.5" /></button>
        </div>
      </div>

      {/* Output area */}
      <div className="term-output" ref={outputRef}>
        {history.length === 0 && !running && (
          <div className="term-welcome">
            <span className="term-welcome-text">NSO Terminal</span>
            <span className="term-welcome-sub">Connected to {cwd}</span>
          </div>
        )}

        {history.map((entry, i) => (
          <div key={i} className="term-entry">
            <div className="term-prompt-line">
              <span className="term-user">nso</span>
              <span className="term-sep">:</span>
              <span className="term-cwd">{entry.cwd}</span>
              <span className="term-dollar">$</span>
              <span className="term-cmd">{entry.command}</span>
            </div>
            {entry.stdout && (
              <pre className="term-stdout">{entry.stdout}</pre>
            )}
            {entry.stderr && (
              <pre className="term-stderr">{entry.stderr}</pre>
            )}
            {entry.exit_code !== 0 && !entry.stderr && (
              <div className="term-exit">Process exited with code {entry.exit_code}{entry.timed_out ? " (timed out)" : ""}</div>
            )}
          </div>
        ))}

        {/* Active prompt */}
        <form onSubmit={handleExec} className="term-input-line">
          <span className="term-user">nso</span>
          <span className="term-sep">:</span>
          <span className="term-cwd">{cwd}</span>
          <span className="term-dollar">$</span>
          <input
            ref={inputRef}
            className="term-input"
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={running}
            autoFocus
            spellCheck={false}
            autoComplete="off"
          />
          {running && <span className="term-spinner" />}
        </form>
      </div>
    </div>
  );
}
