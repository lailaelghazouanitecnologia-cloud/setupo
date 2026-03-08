"use client";

import { useState } from "react";

const NsoLogo = ({ size = 32 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="currentColor">
    <path d="M1.225 61.523c-.222-.949.908-1.546 1.597-.857L39.334 97.178c.689.689.092 1.819-.857 1.597C20.052 94.452 5.548 79.949 1.225 61.523zM.002 46.889a1.073 1.073 0 01.29.761L52.35 99.709c.2.2.477.307.76.289a43.36 43.36 0 006.963-.926c.764-.157 1.03-1.096.478-1.648L2.576 39.449c-.552-.552-1.491-.287-1.648.478a43.36 43.36 0 00-.926 6.962zM4.211 29.705a.993.993 0 01.208 1.1l64.776 64.776c.29.29.726.374 1.1.208a43.1 43.1 0 005.186-2.684c.552-.328.637-1.087.183-1.541L8.436 24.337c-.454-.454-1.213-.369-1.541.183a43.1 43.1 0 00-2.684 5.186zM12.659 18.074c-.37-.37-.393-.964-.044-1.354A49.93 49.93 0 0149.952 0C77.593 0 100 22.407 100 50.048a49.93 49.93 0 01-16.72 37.338c-.39.349-.984.326-1.354-.044L12.659 18.074z" />
  </svg>
);

export default function DownloadPage() {
  const [copied, setCopied] = useState<string | null>(null);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div style={{
      minHeight: "100vh",
      background: "#0a0a0a",
      color: "#e0e0e0",
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    }}>
      {/* Nav */}
      <nav style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "1rem 2rem",
        borderBottom: "1px solid #1a1a1a",
      }}>
        <a href="/" style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "#fff", textDecoration: "none" }}>
          <NsoLogo />
          <span style={{ fontSize: "1.2rem", fontWeight: 600 }}>NSO</span>
        </a>
        <div style={{ display: "flex", gap: "1rem" }}>
          <a href="/" style={{ color: "#888", textDecoration: "none" }}>Dashboard</a>
          <a href="/download" style={{ color: "#fff", textDecoration: "none" }}>Download</a>
        </div>
      </nav>

      {/* Hero */}
      <div style={{ maxWidth: 800, margin: "0 auto", padding: "3rem 2rem" }}>
        <h1 style={{ fontSize: "2.5rem", fontWeight: 700, marginBottom: "0.5rem", color: "#fff" }}>
          Install NSO
        </h1>
        <p style={{ fontSize: "1.1rem", color: "#888", marginBottom: "3rem" }}>
          Set up the NSO agent on any Ubuntu/Debian server in one command.
        </p>

        {/* Quick Install */}
        <section style={{ marginBottom: "3rem" }}>
          <h2 style={{ fontSize: "1.3rem", fontWeight: 600, color: "#fff", marginBottom: "1rem" }}>
            Quick Install
          </h2>
          <div style={{
            background: "#111",
            border: "1px solid #222",
            borderRadius: 8,
            padding: "1rem 1.5rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "1rem",
          }}>
            <code style={{ color: "#4ade80", fontSize: "0.95rem", whiteSpace: "nowrap", overflow: "auto" }}>
              curl -fsSL https://nso.dev/install | bash
            </code>
            <button
              onClick={() => copyToClipboard("curl -fsSL https://nso.dev/install | bash", "quick")}
              style={{
                background: copied === "quick" ? "#22c55e" : "#222",
                color: "#fff",
                border: "1px solid #333",
                borderRadius: 6,
                padding: "0.4rem 0.8rem",
                cursor: "pointer",
                fontSize: "0.85rem",
                whiteSpace: "nowrap",
              }}
            >
              {copied === "quick" ? "Copied!" : "Copy"}
            </button>
          </div>
        </section>

        {/* With options */}
        <section style={{ marginBottom: "3rem" }}>
          <h2 style={{ fontSize: "1.3rem", fontWeight: 600, color: "#fff", marginBottom: "1rem" }}>
            With API Key (auto-register)
          </h2>
          <p style={{ color: "#888", marginBottom: "1rem", fontSize: "0.95rem" }}>
            Pass your project API key to automatically link the instance to your NSO account.
          </p>
          <div style={{
            background: "#111",
            border: "1px solid #222",
            borderRadius: 8,
            padding: "1rem 1.5rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "1rem",
          }}>
            <code style={{ color: "#4ade80", fontSize: "0.95rem", overflow: "auto" }}>
              curl -fsSL https://nso.dev/install | bash -s -- --token sk_live_YOUR_KEY
            </code>
            <button
              onClick={() => copyToClipboard("curl -fsSL https://nso.dev/install | bash -s -- --token sk_live_YOUR_KEY", "token")}
              style={{
                background: copied === "token" ? "#22c55e" : "#222",
                color: "#fff",
                border: "1px solid #333",
                borderRadius: 6,
                padding: "0.4rem 0.8rem",
                cursor: "pointer",
                fontSize: "0.85rem",
                whiteSpace: "nowrap",
              }}
            >
              {copied === "token" ? "Copied!" : "Copy"}
            </button>
          </div>
        </section>

        {/* What it does */}
        <section style={{ marginBottom: "3rem" }}>
          <h2 style={{ fontSize: "1.3rem", fontWeight: 600, color: "#fff", marginBottom: "1rem" }}>
            What gets installed
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            {[
              { title: "NSO Agent", desc: "Manages deploys, files, processes on your server" },
              { title: "NSO CLI", desc: "Command-line tool for shipping and managing workspaces" },
              { title: "Nginx", desc: "Reverse proxy with auto-SSL via Let's Encrypt" },
              { title: "Node.js 20", desc: "LTS runtime for JavaScript/TypeScript apps" },
              { title: "Python 3", desc: "Runtime with venv for Python apps" },
              { title: "Firewall", desc: "UFW configured to allow only SSH, HTTP, HTTPS" },
            ].map((item) => (
              <div key={item.title} style={{
                background: "#111",
                border: "1px solid #1a1a1a",
                borderRadius: 8,
                padding: "1rem",
              }}>
                <div style={{ fontWeight: 600, color: "#fff", marginBottom: "0.3rem" }}>{item.title}</div>
                <div style={{ color: "#888", fontSize: "0.9rem" }}>{item.desc}</div>
              </div>
            ))}
          </div>
        </section>

        {/* Options */}
        <section style={{ marginBottom: "3rem" }}>
          <h2 style={{ fontSize: "1.3rem", fontWeight: 600, color: "#fff", marginBottom: "1rem" }}>
            Options
          </h2>
          <div style={{
            background: "#111",
            border: "1px solid #222",
            borderRadius: 8,
            overflow: "hidden",
          }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #222" }}>
                  <th style={{ padding: "0.8rem 1rem", textAlign: "left", color: "#888" }}>Flag</th>
                  <th style={{ padding: "0.8rem 1rem", textAlign: "left", color: "#888" }}>Description</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["--token TOKEN", "API key (sk_live_...) to auto-register with platform"],
                  ["--domain DOMAIN", "Domain for this server (auto-detected if not set)"],
                  ["--host URL", "NSO platform URL (default: https://nso.dev)"],
                  ["--email EMAIL", "Admin email for SSL certificates"],
                  ["--password PASS", "Agent password (auto-generated if not set)"],
                ].map(([flag, desc]) => (
                  <tr key={flag} style={{ borderBottom: "1px solid #1a1a1a" }}>
                    <td style={{ padding: "0.6rem 1rem" }}>
                      <code style={{ color: "#4ade80" }}>{flag}</code>
                    </td>
                    <td style={{ padding: "0.6rem 1rem", color: "#888" }}>{desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Downloads */}
        <section style={{ marginBottom: "3rem" }}>
          <h2 style={{ fontSize: "1.3rem", fontWeight: 600, color: "#fff", marginBottom: "1rem" }}>
            Manual Downloads
          </h2>
          <div style={{ display: "flex", gap: "1rem" }}>
            <a
              href="/api/download/agent"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.5rem",
                background: "#111",
                border: "1px solid #222",
                borderRadius: 8,
                padding: "0.8rem 1.5rem",
                color: "#fff",
                textDecoration: "none",
                fontSize: "0.95rem",
              }}
            >
              <span>&#8615;</span> nso-agent.tar.gz
            </a>
            <a
              href="/api/download/cli"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.5rem",
                background: "#111",
                border: "1px solid #222",
                borderRadius: 8,
                padding: "0.8rem 1.5rem",
                color: "#fff",
                textDecoration: "none",
                fontSize: "0.95rem",
              }}
            >
              <span>&#8615;</span> nso-cli.tar.gz
            </a>
          </div>
        </section>

        {/* Requirements */}
        <section>
          <h2 style={{ fontSize: "1.3rem", fontWeight: 600, color: "#fff", marginBottom: "1rem" }}>
            Requirements
          </h2>
          <ul style={{ color: "#888", lineHeight: 2, paddingLeft: "1.5rem" }}>
            <li>Ubuntu 20.04+ or Debian 11+ (x86_64)</li>
            <li>Root access (sudo)</li>
            <li>1 GB RAM minimum (2 GB recommended)</li>
            <li>Ports 80, 443 open for web traffic</li>
          </ul>
        </section>
      </div>

      {/* Footer */}
      <footer style={{
        borderTop: "1px solid #1a1a1a",
        padding: "2rem",
        textAlign: "center",
        color: "#555",
        fontSize: "0.85rem",
      }}>
        NSO v0.3.0
      </footer>
    </div>
  );
}
