"use client";

import { useState, useEffect } from "react";
import { useDashboardStore } from "@/stores/dashboard-store";
import { login, register } from "@/lib/api/client";
import { DashboardLayout } from "@/components/dashboard/dashboard-layout";

type PageView = "landing" | "login" | "register";

const NsoLogo = ({ size = 28 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="currentColor">
    <path d="M1.225 61.523c-.222-.949.908-1.546 1.597-.857L39.334 97.178c.689.689.092 1.819-.857 1.597C20.052 94.452 5.548 79.949 1.225 61.523zM.002 46.889a1.073 1.073 0 01.29.761L52.35 99.709c.2.2.477.307.76.289a43.36 43.36 0 006.963-.926c.764-.157 1.03-1.096.478-1.648L2.576 39.449c-.552-.552-1.491-.287-1.648.478a43.36 43.36 0 00-.926 6.962zM4.211 29.705a.993.993 0 01.208 1.1l64.776 64.776c.29.29.726.374 1.1.208a43.1 43.1 0 005.186-2.684c.552-.328.637-1.087.183-1.541L8.436 24.337c-.454-.454-1.213-.369-1.541.183a43.1 43.1 0 00-2.684 5.186zM12.659 18.074c-.37-.37-.393-.964-.044-1.354A49.93 49.93 0 0149.952 0C77.593 0 100 22.407 100 50.048a49.93 49.93 0 01-16.72 37.338c-.39.349-.984.326-1.354-.044L12.659 18.074z" />
  </svg>
);

function LandingPage({ onNavigate }: { onNavigate: (view: PageView) => void }) {
  return (
    <div className="landing-page">
      {/* ── Nav ── */}
      <nav className="landing-nav">
        <div className="landing-nav-inner">
          <div className="landing-nav-left">
            <NsoLogo size={16} />
            <span className="landing-nav-brand">NSO</span>
          </div>
          <div className="landing-nav-right">
            <div className="landing-nav-links">
              <button className="landing-nav-link" onClick={() => document.getElementById("capabilities")?.scrollIntoView({ behavior: "smooth" })}>
                Platform
              </button>
              <span className="landing-slash">/</span>
              <button className="landing-nav-link" onClick={() => document.getElementById("how")?.scrollIntoView({ behavior: "smooth" })}>
                How it works
              </button>
            </div>
            <span className="landing-slash" style={{ margin: "0 16px" }} />
            <button className="landing-nav-link" onClick={() => onNavigate("login")}>
              Sign in
            </button>
            <span className="landing-slash" />
            <button className="landing-btn landing-btn-primary" onClick={() => onNavigate("register")} style={{ marginLeft: 2 }}>
              Get started
            </button>
          </div>
        </div>
      </nav>

      <main>
        {/* ── Hero ── */}
        <section className="landing-hero">
          <div className="landing-container">
            <div className="landing-hero-top">
              <div className="landing-hero-badge">
                <span className="landing-hero-badge-dot" />
                Free subdomains &mdash; yourname.nso.dev
              </div>
              <h1 className="landing-hero-title">Deploy and manage cloud infrastructure</h1>
              <p className="landing-hero-sub">
                Launch VPS instances, package workspaces as .zar modules, manage secrets, and deploy &mdash; all from a single control plane. No SSH required.
              </p>
              <div className="landing-hero-actions">
                <button className="landing-btn landing-btn-primary" onClick={() => onNavigate("register")}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
                  Start building
                </button>
                <button className="landing-btn landing-btn-secondary" onClick={() => onNavigate("login")}>
                  Sign in
                </button>
              </div>
            </div>
            <div className="landing-terminal">
              <div className="landing-terminal-bar">
                <span className="landing-terminal-dot" />
                <span className="landing-terminal-dot" />
                <span className="landing-terminal-dot" />
                <span className="landing-terminal-title">~/projects/api</span>
              </div>
              <div className="landing-terminal-body">
                <div><span className="t-prompt">$</span> <span className="t-cmd">nso ship</span> <span className="t-flag">--workspace</span> <span className="t-arg">backend</span></div>
                <div><span className="t-out">packing workspace...</span> <span className="t-ok">done</span></div>
                <div><span className="t-out">pushing .zar to R2 storage</span></div>
                <div><span className="t-out">deploying to instance inst_a3f21e4...</span> <span className="t-ok">live</span></div>
                <div style={{ height: 6 }} />
                <div><span className="t-prompt">$</span> <span className="t-cmd">nso inst ls</span></div>
                <div><span className="t-out">inst_a3f21e4  staging   running  192.168.1.10</span></div>
                <div><span className="t-out">inst_b7c44f2  prod      running  192.168.1.20</span></div>
                <div style={{ height: 6 }} />
                <div><span className="t-prompt">$</span> <span className="t-cmd">nso exec</span> <span className="t-flag">--instance</span> <span className="t-arg">staging</span> <span className="t-cmd">&quot;systemctl status app&quot;</span></div>
                <div><span className="t-out">active (running) since 2min ago</span> <span className="t-ok">healthy</span></div>
                <div><span className="t-prompt">$</span> <span className="t-cursor" /></div>
              </div>
            </div>
          </div>
        </section>

        {/* ── Capabilities ── */}
        <section className="landing-capabilities" id="capabilities">
          <div className="landing-container">
            <div className="landing-cap-layout">
              <div className="landing-cap-intro">
                <div className="landing-s-label">Platform</div>
                <h2 className="landing-s-title">Everything you need to ship fast</h2>
                <p>NSO replaces the patchwork of tools you use to manage infrastructure. Instances, workspaces, secrets, deploys &mdash; all in one place.</p>
              </div>
              <div className="landing-cap-list">
                <div className="landing-cap-item">
                  <span className="landing-cap-num">01</span>
                  <div>
                    <h3 className="landing-cap-h">Instant VPS Provisioning</h3>
                    <p className="landing-cap-p">Launch cloud instances in seconds with cloud-init provisioning. Pre-configured with nginx, SSL, Python, Node.js, and all the tooling you need.</p>
                  </div>
                  <div className="landing-cap-tags">
                    <span className="landing-tag">Vultr</span>
                    <span className="landing-tag">Debian</span>
                    <span className="landing-tag">cloud-init</span>
                  </div>
                </div>
                <div className="landing-cap-item">
                  <span className="landing-cap-num">02</span>
                  <div>
                    <h3 className="landing-cap-h">.zar Package System</h3>
                    <p className="landing-cap-p">Package workspaces into .zar archives. Push to R2 storage, deploy to any instance. Branch, version, and roll back with confidence.</p>
                  </div>
                  <div className="landing-cap-tags">
                    <span className="landing-tag">R2</span>
                    <span className="landing-tag">versioning</span>
                    <span className="landing-tag">rollback</span>
                  </div>
                </div>
                <div className="landing-cap-item">
                  <span className="landing-cap-num">03</span>
                  <div>
                    <h3 className="landing-cap-h">Remote Execution</h3>
                    <p className="landing-cap-p">Execute commands on remote instances via HTTP relay. No SSH keys to manage. Stream output, manage systemd services, browse files.</p>
                  </div>
                  <div className="landing-cap-tags">
                    <span className="landing-tag">HTTP</span>
                    <span className="landing-tag">no SSH</span>
                  </div>
                </div>
                <div className="landing-cap-item">
                  <span className="landing-cap-num">04</span>
                  <div>
                    <h3 className="landing-cap-h">Secrets Management</h3>
                    <p className="landing-cap-p">Manage environment variables and secrets through the API. Auto-grouped into buckets: auth, providers, storage, system, and custom.</p>
                  </div>
                  <div className="landing-cap-tags">
                    <span className="landing-tag">env vars</span>
                    <span className="landing-tag">buckets</span>
                  </div>
                </div>
                <div className="landing-cap-item">
                  <span className="landing-cap-num">05</span>
                  <div>
                    <h3 className="landing-cap-h">Plugin Ecosystem</h3>
                    <p className="landing-cap-p">Extend your projects with plugins for monitoring, backups, CI/CD, logging, DNS management, and cron jobs. Install and configure from the dashboard.</p>
                  </div>
                  <div className="landing-cap-tags">
                    <span className="landing-tag">modular</span>
                    <span className="landing-tag">extensible</span>
                  </div>
                </div>
                <div className="landing-cap-item">
                  <span className="landing-cap-num">06</span>
                  <div>
                    <h3 className="landing-cap-h">Free Subdomains</h3>
                    <p className="landing-cap-p">Every user gets a free *.nso.dev subdomain. Automatic DNS configuration via Cloudflare. SSL certificates provisioned automatically.</p>
                  </div>
                  <div className="landing-cap-tags">
                    <span className="landing-tag">DNS</span>
                    <span className="landing-tag">SSL</span>
                    <span className="landing-tag">Cloudflare</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── How it works ── */}
        <section className="landing-how" id="how">
          <div className="landing-container">
            <div className="landing-s-label">How it works</div>
            <h2 className="landing-s-title">Three steps to production</h2>
            <div className="landing-how-grid">
              <div className="landing-how-card">
                <div className="landing-how-num">01</div>
                <h3>Create</h3>
                <p>Create an instance from the dashboard or CLI. NSO provisions the VPS, configures nginx, installs dependencies, and sets up SSL automatically.</p>
                <div className="landing-how-code">
                  <span className="t-prompt">$</span> <span className="t-cmd">nso inst create</span> <span className="t-flag">--type</span> <span className="t-arg">setup</span>
                </div>
              </div>
              <div className="landing-how-card">
                <div className="landing-how-num">02</div>
                <h3>Ship</h3>
                <p>Pack your workspace into a .zar archive, push it to cloud storage, and deploy to the instance. All in a single command.</p>
                <div className="landing-how-code">
                  <span className="t-prompt">$</span> <span className="t-cmd">nso ship</span> <span className="t-flag">--workspace</span> <span className="t-arg">api</span>
                </div>
              </div>
              <div className="landing-how-card">
                <div className="landing-how-num">03</div>
                <h3>Manage</h3>
                <p>Monitor, execute commands, manage secrets, and roll back deployments from the dashboard. No SSH needed &mdash; everything goes through the agent.</p>
                <div className="landing-how-code">
                  <span className="t-prompt">$</span> <span className="t-cmd">nso exec</span> <span className="t-flag">--remote</span> <span className="t-arg">prod</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── CTA ── */}
        <section className="landing-cta">
          <div className="landing-container">
            <div className="landing-cta-card">
              <div className="landing-cta-inner">
                <div>
                  <h2>Get started in minutes</h2>
                  <p>Create an account and launch your first instance. Free subdomain included.</p>
                </div>
                <div className="landing-cta-actions">
                  <button className="landing-btn landing-btn-primary" onClick={() => onNavigate("register")}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
                    Create account
                  </button>
                  <button className="landing-btn landing-btn-secondary" onClick={() => onNavigate("login")}>
                    Sign in
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* ── Footer ── */}
      <footer className="landing-footer">
        <div className="landing-container">
          <div className="landing-footer-inner">
            <div className="landing-footer-links">
              <button onClick={() => document.getElementById("capabilities")?.scrollIntoView({ behavior: "smooth" })}>Platform</button>
              <button onClick={() => document.getElementById("how")?.scrollIntoView({ behavior: "smooth" })}>How it works</button>
            </div>
            <span className="landing-footer-copy">&copy; 2026 NSO</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

function LoginPage({ onNavigate }: { onNavigate: (view: PageView) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const setToken = useDashboardStore((s) => s.setToken);
  const setUser = useDashboardStore((s) => s.setUser);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await login(email, password);
      setUser(res.email, res.role);
      setToken(res.token);
    } catch (err: any) {
      setError(err.message?.includes("401") ? "Invalid email or password" : "Connection error");
    }
    setLoading(false);
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-header">
          <NsoLogo />
          <span className="login-brand">NSO</span>
        </div>
        <p className="login-subtitle">Sign in to your account</p>
        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-field">
            <label className="login-label">Email</label>
            <input
              className="login-input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoComplete="email"
            />
          </div>
          <div className="login-field">
            <label className="login-label">Password</label>
            <input
              className="login-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              required
              autoComplete="current-password"
            />
          </div>
          {error && <p className="login-error">{error}</p>}
          <button type="submit" disabled={loading} className="login-submit">
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>
        <div className="login-footer">
          <span>
            Don&apos;t have an account?{" "}
            <button className="login-link" onClick={() => onNavigate("register")}>Create one</button>
          </span>
        </div>
      </div>
    </div>
  );
}

function RegisterPage({ onNavigate }: { onNavigate: (view: PageView) => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const setToken = useDashboardStore((s) => s.setToken);
  const setUser = useDashboardStore((s) => s.setUser);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await register(email, password, name);
      setUser(res.email, res.role);
      setToken(res.token);
    } catch (err: any) {
      if (err.message?.includes("409")) {
        setError("Email already registered");
      } else if (err.message?.includes("400")) {
        setError("Invalid email or password too short (min 6 chars)");
      } else {
        setError("Registration failed. Please try again.");
      }
    }
    setLoading(false);
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-header">
          <NsoLogo />
          <span className="login-brand">NSO</span>
        </div>
        <p className="login-subtitle">Create your account</p>
        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-field">
            <label className="login-label">Name</label>
            <input
              className="login-input"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your name"
              autoComplete="name"
            />
          </div>
          <div className="login-field">
            <label className="login-label">Email</label>
            <input
              className="login-input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoComplete="email"
            />
          </div>
          <div className="login-field">
            <label className="login-label">Password</label>
            <input
              className="login-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Min. 6 characters"
              required
              minLength={6}
              autoComplete="new-password"
            />
          </div>
          {error && <p className="login-error">{error}</p>}
          <button type="submit" disabled={loading} className="login-submit">
            {loading ? "Creating account..." : "Create account"}
          </button>
        </form>
        <div className="login-footer">
          <span>
            Already have an account?{" "}
            <button className="login-link" onClick={() => onNavigate("login")}>Sign in</button>
          </span>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  const token = useDashboardStore((s) => s.token);
  const [mounted, setMounted] = useState(false);
  const [view, setView] = useState<PageView>("landing");

  useEffect(() => { setMounted(true); }, []);

  if (!mounted) return null;

  // Authenticated — show dashboard
  if (token) return <DashboardLayout />;

  // Public pages
  if (view === "login") return <LoginPage onNavigate={setView} />;
  if (view === "register") return <RegisterPage onNavigate={setView} />;
  return <LandingPage onNavigate={setView} />;
}
