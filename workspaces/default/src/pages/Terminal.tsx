import { useEffect, useRef } from "react";
import { Terminal as XTerm } from "xterm";
import { FitAddon } from "xterm-addon-fit";
import { WebLinksAddon } from "xterm-addon-web-links";
import "xterm/css/xterm.css";

export default function Terminal() {
  const termRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<XTerm | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);

  useEffect(() => {
    if (!termRef.current) return;

    const term = new XTerm({
      theme: {
        background: "oklch(0.145 0.005 285)",
        foreground: "#e0e0e0",
        cursor: "#b4a9fe",
        selectionBackground: "rgba(124, 111, 247, 0.3)",
        black: "#1a1a2e",
        red: "#ff5c5c",
        green: "#4ade80",
        yellow: "#facc15",
        blue: "#60a5fa",
        magenta: "#c084fc",
        cyan: "#22d3ee",
        white: "#e0e0e0",
        brightBlack: "#4a4a6a",
        brightRed: "#ff7a7a",
        brightGreen: "#6ee7a0",
        brightYellow: "#fde047",
        brightBlue: "#93bbfd",
        brightMagenta: "#d8b4fe",
        brightCyan: "#67e8f9",
        brightWhite: "#ffffff",
      },
      fontSize: 13,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
      cursorBlink: true,
      cursorStyle: "bar",
      allowProposedApi: true,
      scrollback: 5000,
      convertEol: true,
    });

    const fitAddon = new FitAddon();
    const webLinksAddon = new WebLinksAddon();
    term.loadAddon(fitAddon);
    term.loadAddon(webLinksAddon);
    term.open(termRef.current);

    // Delay initial fit to ensure container is rendered
    requestAnimationFrame(() => {
      fitAddon.fit();
    });

    // Connect WebSocket
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const token = localStorage.getItem("mms_token") || "";
    const ws = new WebSocket(
      `${proto}//${window.location.host}/ws/shell?token=${encodeURIComponent(token)}`
    );
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      // Send initial resize
      ws.send(
        JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows })
      );
    };

    ws.onmessage = (e) => {
      if (e.data instanceof ArrayBuffer) {
        term.write(new Uint8Array(e.data));
      } else {
        term.write(e.data);
      }
    };

    ws.onclose = () => {
      term.write("\r\n\x1b[31m[Connection closed]\x1b[0m\r\n");
    };

    ws.onerror = () => {
      term.write("\r\n\x1b[31m[Connection error]\x1b[0m\r\n");
    };

    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(data);
      }
    });

    term.onResize(({ cols, rows }) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "resize", cols, rows }));
      }
    });

    // Handle window resize
    const onResize = () => {
      try {
        fitAddon.fit();
      } catch {
        // ignore fit errors during teardown
      }
    };
    window.addEventListener("resize", onResize);

    // Also observe the container for size changes
    const observer = new ResizeObserver(() => {
      requestAnimationFrame(() => {
        try {
          fitAddon.fit();
        } catch {
          // ignore
        }
      });
    });
    observer.observe(termRef.current);

    xtermRef.current = term;
    wsRef.current = ws;
    fitAddonRef.current = fitAddon;

    return () => {
      window.removeEventListener("resize", onResize);
      observer.disconnect();
      ws.close();
      term.dispose();
    };
  }, []);

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Terminal</h2>
          <p className="text-xs text-muted-foreground">System shell</p>
        </div>
      </div>
      <div className="flex-1 rounded-lg border bg-card overflow-hidden min-h-0">
        <div ref={termRef} className="h-full w-full" />
      </div>
    </div>
  );
}
