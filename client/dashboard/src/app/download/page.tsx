"use client";

import { useState } from "react";

const NsoLogo = ({ size = 32 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="currentColor">
    <path d="M1.225 61.523c-.222-.949.908-1.546 1.597-.857L39.334 97.178c.689.689.092 1.819-.857 1.597C20.052 94.452 5.548 79.949 1.225 61.523zM.002 46.889a1.073 1.073 0 01.29.761L52.35 99.709c.2.2.477.307.76.289a43.36 43.36 0 006.963-.926c.764-.157 1.03-1.096.478-1.648L2.576 39.449c-.552-.552-1.491-.287-1.648.478a43.36 43.36 0 00-.926 6.962zM4.211 29.705a.993.993 0 01.208 1.1l64.776 64.776c.29.29.726.374 1.1.208a43.1 43.1 0 005.186-2.684c.552-.328.637-1.087.183-1.541L8.436 24.337c-.454-.454-1.213-.369-1.541.183a43.1 43.1 0 00-2.684 5.186zM12.659 18.074c-.37-.37-.393-.964-.044-1.354A49.93 49.93 0 0149.952 0C77.593 0 100 22.407 100 50.048a49.93 49.93 0 01-16.72 37.338c-.39.349-.984.326-1.354-.044L12.659 18.074z" />
  </svg>
);

const ExternalLinkIcon = () => (
  <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor" xmlns="http://www.w3.org/2000/svg" style={{ flexShrink: 0 }}>
    <path d="M13.4998 6.0004C13.776 6.0004 13.9998 6.22425 13.9998 6.5004V11.5004C13.9996 11.7764 13.7758 12.0004 13.4998 12.0004C13.2239 12.0003 13 11.7763 12.9998 11.5004V7.70743L6.85334 13.8539C6.6581 14.0489 6.3415 14.049 6.14631 13.8539C5.95114 13.6587 5.95132 13.3422 6.14631 13.1469L12.2928 7.0004H8.49983C8.22388 7.00032 8.00004 6.77631 7.99983 6.5004C7.99983 6.2243 8.22375 6.00047 8.49983 6.0004H13.4998Z" />
  </svg>
);

const TerminalIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
    <path d="M5.14648 7.14648C5.34175 6.95122 5.65825 6.95122 5.85352 7.14648L8.35352 9.64648C8.44728 9.74025 8.5 9.86739 8.5 10C8.5 10.0994 8.47037 10.1958 8.41602 10.2773L8.35352 10.3535L5.85352 12.8535C5.65825 13.0488 5.34175 13.0488 5.14648 12.8535C4.95122 12.6583 4.95122 12.3417 5.14648 12.1465L7.29297 10L5.14648 7.85352C4.95122 7.65825 4.95122 7.34175 5.14648 7.14648Z" />
    <path d="M14.5 12C14.7761 12 15 12.2239 15 12.5C15 12.7761 14.7761 13 14.5 13H9.5C9.22386 13 9 12.7761 9 12.5C9 12.2239 9.22386 12 9.5 12H14.5Z" />
    <path fillRule="evenodd" clipRule="evenodd" d="M16.5 4C17.3284 4 18 4.67157 18 5.5V14.5C18 15.3284 17.3284 16 16.5 16H3.5C2.67157 16 2 15.3284 2 14.5V5.5C2 4.67157 2.67157 4 3.5 4H16.5ZM3.5 5C3.22386 5 3 5.22386 3 5.5V14.5C3 14.7761 3.22386 15 3.5 15H16.5C16.7761 15 17 14.7761 17 14.5V5.5C17 5.22386 16.7761 5 16.5 5H3.5Z" />
  </svg>
);

const DownloadIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
    <path d="M16.5 13C16.7761 13 17 13.2239 17 13.5V15.5C17 16.3284 16.3284 17 15.5 17H4.5C3.67157 17 3 16.3284 3 15.5V13.5C3 13.2239 3.22386 13 3.5 13C3.77614 13 4 13.2239 4 13.5V15.5C4 15.7761 4.22386 16 4.5 16H15.5C15.7761 16 16 15.7761 16 15.5V13.5C16 13.2239 16.2239 13 16.5 13ZM10 3C10.2761 3 10.5 3.22386 10.5 3.5V12.1855L13.626 8.66797C13.8094 8.46166 14.1256 8.44275 14.332 8.62598C14.5383 8.80936 14.5573 9.12563 14.374 9.33203L10.374 13.832L10.2949 13.9033C10.21 13.9654 10.107 14 10 14C9.85718 14 9.72086 13.9388 9.62598 13.832L5.62598 9.33203L5.56738 9.25C5.45079 9.04872 5.48735 8.78653 5.66797 8.62598C5.84854 8.46567 6.1127 8.46039 6.29883 8.59961L6.37402 8.66797L9.5 12.1855V3.5C9.5 3.22386 9.72386 3 10 3Z" />
  </svg>
);

const ServerIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="2" width="20" height="8" rx="2" ry="2" />
    <rect x="2" y="14" width="20" height="8" rx="2" ry="2" />
    <line x1="6" y1="6" x2="6.01" y2="6" />
    <line x1="6" y1="18" x2="6.01" y2="18" />
  </svg>
);

const GlobeIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <line x1="2" y1="12" x2="22" y2="12" />
    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
  </svg>
);

const CloseIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
    <path d="M15.1465 4.14642C15.3418 3.95121 15.6583 3.95118 15.8536 4.14642C16.0487 4.34168 16.0488 4.65822 15.8536 4.85346L10.7071 9.99997L15.8536 15.1465C16.0487 15.3417 16.0488 15.6583 15.8536 15.8535C15.6828 16.0244 15.4187 16.0461 15.2247 15.918L15.1465 15.8535L10 10.707L4.85352 15.8535C4.65827 16.0486 4.34168 16.0486 4.14648 15.8535C3.95129 15.6583 3.95142 15.3418 4.14648 15.1465L9.293 9.99997L4.14648 4.85346C3.95142 4.65818 3.95129 4.34162 4.14648 4.14642C4.34168 3.95128 4.65825 3.95138 4.85352 4.14642L10 9.29294L15.1465 4.14642Z" />
  </svg>
);

function CodeBlock({ code, id, copied, onCopy }: { code: string; id: string; copied: string | null; onCopy: (text: string, id: string) => void }) {
  return (
    <div style={{
      background: "#0d0d0d",
      border: "1px solid #1f1f1f",
      borderRadius: 12,
      padding: "14px 18px",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: "1rem",
    }}>
      <code style={{ color: "#4ade80", fontSize: "0.9rem", whiteSpace: "nowrap", overflow: "auto", fontFamily: "monospace" }}>
        {code}
      </code>
      <button
        onClick={() => onCopy(code, id)}
        style={{
          background: copied === id ? "#22c55e" : "transparent",
          color: copied === id ? "#fff" : "#888",
          border: "0.5px solid #333",
          borderRadius: 8,
          padding: "6px 14px",
          cursor: "pointer",
          fontSize: "0.82rem",
          fontWeight: 600,
          whiteSpace: "nowrap",
          transition: "all 0.15s ease",
        }}
      >
        {copied === id ? "Copied!" : "Copy"}
      </button>
    </div>
  );
}

export default function DownloadPage() {
  const [copied, setCopied] = useState<string | null>(null);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div style={{
      position: "fixed",
      inset: 0,
      zIndex: 50,
      display: "flex",
      flexDirection: "column",
      background: "#0a0a0a",
      color: "#e0e0e0",
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    }}>
      <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "auto" }}>
        {/* Close button */}
        <div style={{ position: "sticky", top: 0, zIndex: 10, display: "flex", justifyContent: "space-between", alignItems: "center", padding: "16px 24px" }}>
          <a href="/" style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "#fff", textDecoration: "none" }}>
            <NsoLogo size={28} />
            <span style={{ fontSize: "1.1rem", fontWeight: 600 }}>NSO</span>
          </a>
          <a
            href="/"
            style={{
              width: 32, height: 32, borderRadius: 8,
              display: "flex", alignItems: "center", justifyContent: "center",
              color: "#666", cursor: "pointer", textDecoration: "none",
              transition: "all 0.3s cubic-bezier(0.165, 0.85, 0.45, 1)",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.color = "#fff"; e.currentTarget.style.background = "rgba(255,255,255,0.05)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = "#666"; e.currentTarget.style.background = "transparent"; }}
            aria-label="Close"
          >
            <CloseIcon />
          </a>
        </div>

        {/* Content */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "0 32px 64px" }}>
          <h2 style={{
            fontSize: "1.8rem",
            fontWeight: 700,
            color: "#fff",
            textAlign: "center",
            marginBottom: 40,
            maxWidth: 500,
            lineHeight: 1.3,
          }}>
            Deploy and manage your apps, everywhere
          </h2>

          <div style={{
            width: "100%",
            maxWidth: 900,
            display: "grid",
            gridTemplateColumns: "1fr",
            gap: 20,
          }}>
            {/* === Quick Install Card (full width) === */}
            <div style={{
              borderRadius: 32,
              overflow: "hidden",
              background: "#111",
              border: "0.5px solid #222",
              boxShadow: "0 4px 20px rgba(0,0,0,0.15)",
              padding: 10,
              gridColumn: "1 / -1",
            }}>
              <div style={{
                borderRadius: 24,
                border: "0.5px solid #222",
                background: "linear-gradient(162deg, rgba(74, 222, 128, 0) 33%, rgba(74, 222, 128, 0.12) 90%), #0f0f0f",
                overflow: "hidden",
                padding: 28,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <h3 style={{ fontSize: "1.15rem", fontWeight: 700, color: "#fff" }}>Quick Install</h3>
                  <span style={{
                    display: "inline-flex", alignItems: "center",
                    background: "rgba(74, 222, 128, 0.15)", color: "#4ade80",
                    height: 24, padding: "0 8px", borderRadius: 8, fontSize: "0.75rem", fontWeight: 600,
                  }}>One command</span>
                </div>
                <p style={{ color: "#888", fontSize: "0.9rem", marginBottom: 20 }}>
                  Set up the NSO agent on any Ubuntu/Debian server instantly.
                </p>
                <CodeBlock code="curl -fsSL https://nso.dev/install | bash" id="quick" copied={copied} onCopy={copyToClipboard} />
                <div style={{ marginTop: 16 }}>
                  <p style={{ color: "#666", fontSize: "0.82rem", marginBottom: 8 }}>With API key (auto-register):</p>
                  <CodeBlock code="curl -fsSL https://nso.dev/install | bash -s -- --token sk_live_YOUR_KEY" id="token" copied={copied} onCopy={copyToClipboard} />
                </div>
              </div>
            </div>

            {/* Two-column grid for the rest */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: 20 }}>

              {/* === Agent Card === */}
              <div style={{
                borderRadius: 32, overflow: "hidden",
                background: "#111", border: "0.5px solid #222",
                boxShadow: "0 4px 20px rgba(0,0,0,0.15)", padding: 10,
              }}>
                <div style={{ borderRadius: 24, border: "0.5px solid #222", background: "#0f0f0f", overflow: "hidden" }}>
                  <div style={{ padding: "28px 28px 20px" }}>
                    <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "#fff", marginBottom: 8 }}>NSO Agent</h3>
                    <p style={{ color: "#888", fontSize: "0.9rem", marginBottom: 20 }}>
                      Manages deploys, files, and processes on each VPS.
                    </p>

                    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                      {[
                        { icon: <ServerIcon />, label: "Server Agent", href: "/api/download/agent", action: "Download" },
                        { icon: <TerminalIcon />, label: "CLI Tool", href: "/api/download/cli", action: "Download" },
                      ].map((item) => (
                        <div key={item.label} style={{
                          display: "flex", alignItems: "center", justifyContent: "space-between",
                          padding: "14px 0", borderTop: "1px solid #1a1a1a",
                        }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <span style={{ color: "#888", width: 20, height: 20, display: "flex", alignItems: "center", justifyContent: "center" }}>{item.icon}</span>
                            <span style={{ color: "#fff", fontSize: "0.9rem" }}>{item.label}</span>
                          </div>
                          <a href={item.href} style={{
                            display: "inline-flex", alignItems: "center", gap: 4,
                            background: "transparent", border: "0.5px solid #333",
                            borderRadius: 8, padding: "6px 14px",
                            color: "#fff", textDecoration: "none",
                            fontSize: "0.85rem", fontWeight: 600,
                            transition: "all 0.1s ease",
                          }}
                          onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.05)"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
                          >
                            {item.action} <DownloadIcon />
                          </a>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Terminal preview */}
                  <div style={{ padding: "0 20px 20px" }}>
                    <div style={{
                      borderRadius: 12, overflow: "hidden",
                      boxShadow: "0 2px 16px rgba(0,0,0,0.3)", border: "1px solid #1f1f1f",
                    }}>
                      <div style={{ background: "#1a1a1a", padding: "8px 12px", display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#ff5f57", border: "1px solid rgba(0,0,0,0.1)" }} />
                        <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#febc2e", border: "1px solid rgba(0,0,0,0.1)" }} />
                        <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#28c840", border: "1px solid rgba(0,0,0,0.1)" }} />
                      </div>
                      <div style={{ background: "#0d0d0d", padding: "12px 16px", fontFamily: "monospace", fontSize: "0.8rem", lineHeight: 1.8 }}>
                        <p><span style={{ color: "#4ade80" }}>&gt;</span> <span style={{ color: "#e0e0e0" }}>nso ship my-workspace inst_xxx</span></p>
                        <p style={{ color: "#888" }}>Packing workspace... done</p>
                        <p style={{ color: "#888" }}>Pushing to R2... done</p>
                        <p style={{ color: "#4ade80" }}>Deployed v1.2.0 successfully</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* === Dashboard Card === */}
              <div style={{
                borderRadius: 32, overflow: "hidden",
                background: "#111", border: "0.5px solid #222",
                boxShadow: "0 4px 20px rgba(0,0,0,0.15)", padding: 10,
              }}>
                <div style={{ borderRadius: 24, border: "0.5px solid #222", background: "#0f0f0f", overflow: "hidden" }}>
                  <div style={{ padding: "28px 28px 20px" }}>
                    <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "#fff", marginBottom: 8 }}>Dashboard</h3>
                    <p style={{ color: "#888", fontSize: "0.9rem", marginBottom: 20 }}>
                      Manage projects, instances, deploys, and billing from the web.
                    </p>

                    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                      {[
                        { icon: <GlobeIcon />, label: "Web Dashboard", href: "/", action: "Open" },
                        { icon: <ServerIcon />, label: "Admin Panel", href: "https://sonfazt.nso.dev", action: "Open", external: true },
                      ].map((item) => (
                        <div key={item.label} style={{
                          display: "flex", alignItems: "center", justifyContent: "space-between",
                          padding: "14px 0", borderTop: "1px solid #1a1a1a",
                        }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <span style={{ color: "#888", width: 20, height: 20, display: "flex", alignItems: "center", justifyContent: "center" }}>{item.icon}</span>
                            <span style={{ color: "#fff", fontSize: "0.9rem" }}>{item.label}</span>
                          </div>
                          <a href={item.href} target={item.external ? "_blank" : undefined} style={{
                            display: "inline-flex", alignItems: "center", gap: 4,
                            background: "transparent", border: "0.5px solid #333",
                            borderRadius: 8, padding: "6px 14px",
                            color: "#fff", textDecoration: "none",
                            fontSize: "0.85rem", fontWeight: 600,
                            transition: "all 0.1s ease",
                          }}
                          onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.05)"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
                          >
                            {item.action} {item.external && <ExternalLinkIcon />}
                          </a>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* What gets installed */}
                  <div style={{ padding: "0 20px 20px" }}>
                    <p style={{ color: "#666", fontSize: "0.78rem", fontWeight: 600, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.05em" }}>Included in install</p>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                      {[
                        { name: "Nginx", desc: "Reverse proxy + SSL" },
                        { name: "Node.js 20", desc: "LTS runtime" },
                        { name: "Python 3", desc: "Venv support" },
                        { name: "Firewall", desc: "UFW configured" },
                      ].map((item) => (
                        <div key={item.name} style={{
                          background: "#141414", border: "1px solid #1a1a1a",
                          borderRadius: 10, padding: "10px 12px",
                        }}>
                          <div style={{ fontWeight: 600, color: "#fff", fontSize: "0.82rem" }}>{item.name}</div>
                          <div style={{ color: "#666", fontSize: "0.75rem" }}>{item.desc}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* === Options Card (full width) === */}
            <div style={{
              borderRadius: 32, overflow: "hidden",
              background: "#111", border: "0.5px solid #222",
              boxShadow: "0 4px 20px rgba(0,0,0,0.15)", padding: 10,
            }}>
              <div style={{ borderRadius: 24, border: "0.5px solid #222", background: "#0f0f0f", overflow: "hidden", padding: 28 }}>
                <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "#fff", marginBottom: 16 }}>Install Options</h3>
                <div style={{ display: "grid", gap: 0 }}>
                  {[
                    ["--token TOKEN", "API key (sk_live_...) to auto-register with platform"],
                    ["--domain DOMAIN", "Domain for this server (auto-detected if not set)"],
                    ["--host URL", "NSO platform URL (default: https://nso.dev)"],
                    ["--email EMAIL", "Admin email for SSL certificates"],
                    ["--password PASS", "Agent password (auto-generated if not set)"],
                    ["--central", "Install as central server with PostgreSQL"],
                  ].map(([flag, desc]) => (
                    <div key={flag} style={{
                      display: "flex", alignItems: "center", gap: 16,
                      padding: "12px 0", borderTop: "1px solid #1a1a1a",
                    }}>
                      <code style={{ color: "#4ade80", fontSize: "0.85rem", fontFamily: "monospace", minWidth: 180, flexShrink: 0 }}>{flag}</code>
                      <span style={{ color: "#888", fontSize: "0.85rem" }}>{desc}</span>
                    </div>
                  ))}
                </div>

                {/* Requirements */}
                <div style={{ marginTop: 20, padding: "16px 0 0", borderTop: "1px solid #1a1a1a" }}>
                  <p style={{ color: "#666", fontSize: "0.78rem", fontWeight: 600, marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.05em" }}>Requirements</p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {["Ubuntu 20.04+ / Debian 11+", "Root access (sudo)", "1 GB RAM min", "Ports 80, 443 open"].map((req) => (
                      <span key={req} style={{
                        background: "#141414", border: "1px solid #1a1a1a",
                        borderRadius: 8, padding: "6px 12px",
                        color: "#888", fontSize: "0.8rem",
                      }}>{req}</span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div style={{
        borderTop: "1px solid #1a1a1a",
        padding: "12px 24px",
        textAlign: "center",
        color: "#444",
        fontSize: "0.8rem",
        flexShrink: 0,
      }}>
        NSO v0.3.0
      </div>
    </div>
  );
}
