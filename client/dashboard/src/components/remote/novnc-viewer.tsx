"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Monitor, PlugZap, Power, RefreshCw, ArrowUpRight } from "lucide-react";

type RfbInstance = {
  disconnect(): void;
  focus(): void;
  blur(): void;
  sendKey(keysym: number, code?: string, down?: boolean): void;
  sendCredentials(credentials: { password?: string }): void;
  clipboardPasteFrom(text: string): void;
  sendCtrlAltDel(): void;
  addEventListener(type: string, listener: EventListenerOrEventListenerObject): void;
  scaleViewport: boolean;
  clipViewport: boolean;
  focusOnClick: boolean;
  resizeSession: boolean;
  viewOnly: boolean;
  qualityLevel: number;
  compressionLevel: number;
};

const KEY = {
  Backspace: 0xff08,
  Enter: 0xff0d,
  Delete: 0xffff,
  Tab: 0xff09,
  Escape: 0xff1b,
  Left: 0xff51,
  Up: 0xff52,
  Right: 0xff53,
  Down: 0xff54,
  Insert: 0xff63,
  ShiftLeft: 0xffe1,
  ControlLeft: 0xffe3,
  KeyA: 0x0061,
} as const;

const SPECIAL_KEYMAP: Record<string, { keysym: number; code?: string; localKey?: string }> = {
  Backspace: { keysym: KEY.Backspace, code: "Backspace", localKey: "BackSpace" },
  Delete: { keysym: KEY.Delete, code: "Delete", localKey: "Delete" },
  Enter: { keysym: KEY.Enter, code: "Enter", localKey: "Return" },
  Tab: { keysym: KEY.Tab, code: "Tab", localKey: "Tab" },
  Escape: { keysym: KEY.Escape, code: "Escape", localKey: "Escape" },
  ArrowLeft: { keysym: KEY.Left, code: "ArrowLeft", localKey: "Left" },
  ArrowRight: { keysym: KEY.Right, code: "ArrowRight", localKey: "Right" },
  ArrowUp: { keysym: KEY.Up, code: "ArrowUp", localKey: "Up" },
  ArrowDown: { keysym: KEY.Down, code: "ArrowDown", localKey: "Down" },
};

function agentVncUrl(host: string, port: string, token: string) {
  const origin = new URL(window.location.origin);
  const protocol = origin.protocol === "https:" ? "wss:" : "ws:";
  const params = new URLSearchParams({
    token,
    host,
    port,
  });
  return `${protocol}//${origin.host}/agent/remote/vnc?${params.toString()}`;
}

async function agentRemotePost(token: string, path: string, body: Record<string, unknown>) {
  const response = await fetch(`/agent/remote/${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Remote request failed: ${response.status}`);
  }
}

export function NoVncViewer() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const rfbRef = useRef<RfbInstance | null>(null);
  const [host, setHost] = useState("127.0.0.1");
  const [port, setPort] = useState("5901");
  const [password, setPassword] = useState("");
  const [connected, setConnected] = useState(false);
  const [keyboardGrabbed, setKeyboardGrabbed] = useState(false);
  const [status, setStatus] = useState("Ready");
  const [clipboard, setClipboard] = useState("");
  const [bridgeValue, setBridgeValue] = useState("");
  const [browserUrl, setBrowserUrl] = useState("https://www.google.com");

  const isLocalTest = host.trim() === "127.0.0.1" && (Number.parseInt(port, 10) || 5901) === 5901;

  const disconnect = () => {
    if (rfbRef.current) {
      try {
        rfbRef.current.disconnect();
      } catch {}
      rfbRef.current = null;
    }
    if (containerRef.current) {
      containerRef.current.innerHTML = "";
    }
    setConnected(false);
    setKeyboardGrabbed(false);
  };

  const focusRemote = () => {
    if (!containerRef.current || !rfbRef.current) return;
    containerRef.current.focus();
    window.setTimeout(() => {
      try {
        rfbRef.current?.focus();
        setKeyboardGrabbed(true);
        setStatus(`Connected to ${host}:${port} — keyboard active`);
      } catch {}
    }, 20);
  };

  const sendKeyTap = (keysym: number, code?: string) => {
    if (!rfbRef.current) return;
    focusRemote();
    rfbRef.current.sendKey(keysym, code);
  };

  const sendChord = (steps: Array<{ keysym: number; code: string; down: boolean }>) => {
    if (!rfbRef.current) return;
    focusRemote();
    for (const step of steps) {
      rfbRef.current.sendKey(step.keysym, step.code, step.down);
    }
  };

  const sendBridgeKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (!connected) return;
    const token = typeof window !== "undefined" ? window.localStorage.getItem("nso_token") || "" : "";

      const special = SPECIAL_KEYMAP[event.key];
      if (special) {
        event.preventDefault();
        if (isLocalTest && token) {
          agentRemotePost(token, "local/key", { keys: [special.localKey || special.code || event.key] }).catch((error) => {
            setStatus(error instanceof Error ? error.message : "Could not send remote key");
          });
          return;
        }
      if (!rfbRef.current) return;
      focusRemote();
      rfbRef.current.sendKey(special.keysym, special.code);
      return;
    }

    if (event.ctrlKey || event.altKey || event.metaKey) {
      return;
    }

    if (event.key.length === 1) {
      event.preventDefault();
      if (isLocalTest && token) {
        agentRemotePost(token, "local/type", { text: event.key }).catch((error) => {
          setStatus(error instanceof Error ? error.message : "Could not type into remote session");
        });
        setBridgeValue("");
        return;
      }
      if (!rfbRef.current) return;
      focusRemote();
      rfbRef.current.sendKey(event.key.codePointAt(0) || 0, event.code);
      setBridgeValue("");
    }
  };

  const pasteClipboard = () => {
    const token = typeof window !== "undefined" ? window.localStorage.getItem("nso_token") || "" : "";
    if (isLocalTest && token && clipboard.trim()) {
      agentRemotePost(token, "local/type", { text: clipboard }).catch((error) => {
        setStatus(error instanceof Error ? error.message : "Could not paste into remote session");
      });
      return;
    }
    if (!rfbRef.current || !clipboard.trim()) return;
    focusRemote();
    rfbRef.current.clipboardPasteFrom(clipboard);
    sendChord([
      { keysym: KEY.ShiftLeft, code: "ShiftLeft", down: true },
      { keysym: KEY.Insert, code: "Insert", down: true },
      { keysym: KEY.Insert, code: "Insert", down: false },
      { keysym: KEY.ShiftLeft, code: "ShiftLeft", down: false },
    ]);
  };

  const replaceWithClipboard = () => {
    const token = typeof window !== "undefined" ? window.localStorage.getItem("nso_token") || "" : "";
    if (isLocalTest && token && clipboard.trim()) {
      agentRemotePost(token, "local/key", { keys: ["ctrl+a", "Delete"] })
        .then(() => agentRemotePost(token, "local/type", { text: clipboard }))
        .catch((error) => {
          setStatus(error instanceof Error ? error.message : "Could not replace remote text");
        });
      return;
    }
    if (!rfbRef.current || !clipboard.trim()) return;
    focusRemote();
    sendChord([
      { keysym: KEY.ControlLeft, code: "ControlLeft", down: true },
      { keysym: KEY.KeyA, code: "KeyA", down: true },
      { keysym: KEY.KeyA, code: "KeyA", down: false },
      { keysym: KEY.ControlLeft, code: "ControlLeft", down: false },
    ]);
    sendKeyTap(KEY.Delete, "Delete");
    window.setTimeout(() => pasteClipboard(), 40);
  };

  const connect = async () => {
    if (typeof window === "undefined" || !containerRef.current) return;
    const token = window.localStorage.getItem("nso_token");
    if (!token) {
      setStatus("Missing agent token");
      return;
    }

    disconnect();
    setStatus("Connecting");

    const url = agentVncUrl(host.trim(), port.trim(), token);
    const credentials = {
      password: password.trim() || (isLocalTest ? "nso-test-vnc" : ""),
    };

    try {
      const { default: RFB } = await import("@novnc/novnc/lib/rfb");
      const rfb = new RFB(containerRef.current, url, {
        credentials,
        shared: true,
      }) as unknown as RfbInstance & { resizeSession?: boolean; viewOnly?: boolean };
      rfb.scaleViewport = true;
      rfb.clipViewport = true;
      rfb.resizeSession = true;
      rfb.focusOnClick = true;
      rfb.viewOnly = false;
      rfb.qualityLevel = 4;
      rfb.compressionLevel = 1;

      rfb.addEventListener("connect", () => {
        setConnected(true);
        setStatus(`Connected to ${host}:${port}`);
        window.setTimeout(() => focusRemote(), 80);
      });

      rfb.addEventListener("disconnect", (event: Event) => {
        const detail = (event as CustomEvent<{ clean: boolean }>).detail;
        setConnected(false);
        setKeyboardGrabbed(false);
        setStatus(detail?.clean ? "Disconnected" : "Disconnected unexpectedly");
      });

      rfb.addEventListener("credentialsrequired", () => {
        setStatus("Password required");
        const nextPassword = password.trim() || (isLocalTest ? "nso-test-vnc" : "");
        if (nextPassword) {
          rfb.sendCredentials({ password: nextPassword });
        }
      });

      rfb.addEventListener("clipboard", (event: Event) => {
        const detail = (event as CustomEvent<{ text: string }>).detail;
        setClipboard(detail?.text || "");
      });

      rfbRef.current = rfb;
    } catch (err: any) {
      setStatus(err?.message || "Could not start noVNC");
    }
  };

  useEffect(() => {
    return () => disconnect();
  }, []);

  const openBrowser = () => {
    const token = typeof window !== "undefined" ? window.localStorage.getItem("nso_token") || "" : "";
    if (!token) {
      setStatus("Missing agent token");
      return;
    }
    agentRemotePost(token, "local/browser", { browser: "chromium", url: browserUrl.trim() || "https://www.google.com" })
      .then(() => setStatus("Chromium opened in the remote desktop"))
      .catch((error) => {
        setStatus(error instanceof Error ? error.message : "Could not open Chromium");
      });
  };

  useEffect(() => {
    if (!connected || !keyboardGrabbed || !isLocalTest) return;

    const token = window.localStorage.getItem("nso_token") || "";
    if (!token) return;

    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) {
        return;
      }

      const special = SPECIAL_KEYMAP[event.key];
      if (special) {
        event.preventDefault();
        agentRemotePost(token, "local/key", { keys: [special.localKey || special.code || event.key] }).catch((error) => {
          setStatus(error instanceof Error ? error.message : "Could not send remote key");
        });
        return;
      }

      if (event.ctrlKey || event.altKey || event.metaKey) {
        return;
      }

      if (event.key.length === 1) {
        event.preventDefault();
        agentRemotePost(token, "local/type", { text: event.key }).catch((error) => {
          setStatus(error instanceof Error ? error.message : "Could not type into remote session");
        });
      }
    };

    window.addEventListener("keydown", handleKeyDown, true);
    return () => window.removeEventListener("keydown", handleKeyDown, true);
  }, [connected, keyboardGrabbed, isLocalTest]);

  return (
    <main className="remote-route-shell">
      <div className="remote-route-inner">
        <section className="settings-section remote-standalone-page">
          <div className="settings-section-header">
            <span className="settings-section-title">Remote Desktop</span>
            <div style={{ display: "flex", gap: 6 }}>
              <button className="panel-btn-sm" onClick={() => window.location.reload()}>
                <RefreshCw className="h-3 w-3" />
                <span>Reload</span>
              </button>
              <button className="panel-btn-sm" onClick={() => window.open(window.location.href, "_blank", "noopener,noreferrer")}>
                <ArrowUpRight className="h-3 w-3" />
                <span>Pop out</span>
              </button>
            </div>
          </div>

          <div className="remote-panel-grid">
            <div className="remote-panel-side">
              <div className="remote-status-row">
                <span className="remote-status-label">Viewer</span>
                <span className="remote-status-value">noVNC</span>
              </div>
              <div className="remote-status-row">
                <span className="remote-status-label">State</span>
                <span className="remote-status-value">{connected ? "Connected" : "Idle"}</span>
              </div>
              <div className="remote-form-grid">
                <div>
                  <label className="form-label">Host</label>
                  <input className="proj-input" value={host} onChange={(e) => setHost(e.target.value)} />
                </div>
                <div>
                  <label className="form-label">Port</label>
                  <input className="proj-input" value={port} onChange={(e) => setPort(e.target.value)} />
                </div>
              </div>
              <div style={{ marginTop: 10 }}>
                <label className="form-label">Password</label>
                <input className="proj-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
                {isLocalTest ? <div className="remote-note" style={{ marginTop: 6 }}>Empty uses the local test password automatically.</div> : null}
              </div>
              <div style={{ display: "flex", gap: 6, marginTop: 12 }}>
                <button className="deploy-action-btn teal" onClick={connect}>
                  <PlugZap className="h-3.5 w-3.5" />
                  <span>{connected ? "Reconnect" : "Connect"}</span>
                </button>
                <button className="panel-btn-sm" onClick={disconnect} disabled={!connected}>
                  <Power className="h-3 w-3" />
                  <span>Disconnect</span>
                </button>
                <button className="panel-btn-sm" onClick={focusRemote} disabled={!connected}>
                  <span>{keyboardGrabbed ? "Keyboard on" : "Grab keyboard"}</span>
                </button>
              </div>
              <div className="remote-note">{status}</div>
              <div className="remote-compose">
                <label className="form-label">Open browser</label>
                <div className="remote-form-grid">
                  <input
                    className="proj-input"
                    value={browserUrl}
                    onChange={(e) => setBrowserUrl(e.target.value)}
                    placeholder="https://www.google.com"
                  />
                </div>
                <div className="remote-compose-actions" style={{ marginBottom: 10 }}>
                  <button className="panel-btn-sm" onClick={openBrowser} disabled={!connected || !isLocalTest}>
                    <span>Open Chromium</span>
                  </button>
                </div>
                <label className="form-label">Keyboard bridge</label>
                <input
                  className="proj-input"
                  value={bridgeValue}
                  onChange={(e) => setBridgeValue(e.target.value)}
                  onKeyDown={sendBridgeKey}
                  placeholder="Focus here and type"
                />
                <label className="form-label">Clipboard</label>
                <textarea
                  className="remote-compose-input"
                  rows={4}
                  value={clipboard}
                  onChange={(e) => setClipboard(e.target.value)}
                  placeholder="Clipboard sync with the remote machine"
                />
                <div className="remote-compose-actions">
                  <button
                    className="panel-btn-sm"
                    onClick={pasteClipboard}
                    disabled={!connected || !clipboard.trim()}
                  >
                    <span>Paste</span>
                  </button>
                  <button
                    className="panel-btn-sm"
                    onClick={replaceWithClipboard}
                    disabled={!connected || !clipboard.trim()}
                  >
                    <span>Replace</span>
                  </button>
                  <button
                    className="panel-btn-sm"
                    onClick={() => rfbRef.current?.sendCtrlAltDel()}
                    disabled={!connected}
                  >
                    <span>Ctrl+Alt+Del</span>
                  </button>
                </div>
                <div className="remote-compose-actions" style={{ marginTop: 6 }}>
                  <button className="panel-btn-sm" onClick={() => sendKeyTap(KEY.Enter, "Enter")} disabled={!connected}>
                    <span>Enter</span>
                  </button>
                  <button
                    className="panel-btn-sm"
                    onClick={() => {
                      const token = typeof window !== "undefined" ? window.localStorage.getItem("nso_token") || "" : "";
                      if (isLocalTest && token) {
                        agentRemotePost(token, "local/key", { keys: ["BackSpace"] }).catch((error) => {
                          setStatus(error instanceof Error ? error.message : "Could not send backspace");
                        });
                        return;
                      }
                      sendKeyTap(KEY.Backspace, "Backspace");
                    }}
                    disabled={!connected}
                  >
                    <span>Backspace</span>
                  </button>
                  <button
                    className="panel-btn-sm"
                    onClick={() => {
                      const token = typeof window !== "undefined" ? window.localStorage.getItem("nso_token") || "" : "";
                      if (isLocalTest && token) {
                        agentRemotePost(token, "local/key", { keys: ["Delete"] }).catch((error) => {
                          setStatus(error instanceof Error ? error.message : "Could not send delete");
                        });
                        return;
                      }
                      sendKeyTap(KEY.Delete, "Delete");
                    }}
                    disabled={!connected}
                  >
                    <span>Delete</span>
                  </button>
                  <button
                    className="panel-btn-sm"
                    onClick={() =>
                      sendChord([
                        { keysym: KEY.ControlLeft, code: "ControlLeft", down: true },
                        { keysym: KEY.KeyA, code: "KeyA", down: true },
                        { keysym: KEY.KeyA, code: "KeyA", down: false },
                        { keysym: KEY.ControlLeft, code: "ControlLeft", down: false },
                      ])
                    }
                    disabled={!connected}
                  >
                    <span>Select all</span>
                  </button>
                </div>
              </div>
            </div>

            <div className="remote-display-shell remote-novnc-shell">
              <div
                ref={containerRef}
                className="remote-novnc-target"
                tabIndex={0}
                onMouseDown={() => focusRemote()}
                onFocus={() => setKeyboardGrabbed(true)}
                onBlur={() => setKeyboardGrabbed(false)}
              />
              {!connected ? (
                <div className="settings-placeholder remote-placeholder" style={{ minHeight: 220 }}>
                  <Monitor className="h-6 w-6" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
                  <span>Open a VNC session in the dedicated viewer.</span>
                </div>
              ) : null}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
