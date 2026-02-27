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
      <nav className="landing-nav">
        <div className="landing-nav-left">
          <NsoLogo size={22} />
          <span className="landing-nav-brand">NSO</span>
        </div>
        <div className="landing-nav-right">
          <button className="landing-nav-link" onClick={() => onNavigate("login")}>Sign in</button>
          <button className="landing-btn-primary" onClick={() => onNavigate("register")}>Get started</button>
        </div>
      </nav>

      <section className="landing-hero">
        <div className="landing-hero-badge">Deploy anywhere</div>
        <h1 className="landing-hero-title">Infrastructure for modern apps</h1>
        <p className="landing-hero-sub">
          Deploy, manage, and scale your applications with zero configuration.
          Get a free <code className="code-inline">yourname.nso.dev</code> subdomain instantly.
        </p>
        <div className="landing-hero-actions">
          <button className="landing-btn-primary landing-btn-lg" onClick={() => onNavigate("register")}>
            Start building
          </button>
          <button className="landing-btn-secondary landing-btn-lg" onClick={() => onNavigate("login")}>
            Sign in
          </button>
        </div>
      </section>

      <section className="landing-features">
        <div className="landing-feature-card">
          <div className="landing-feature-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/>
            </svg>
          </div>
          <h3 className="landing-feature-title">Instant VPS</h3>
          <p className="landing-feature-desc">Launch cloud instances in seconds with pre-configured environments.</p>
        </div>
        <div className="landing-feature-card">
          <div className="landing-feature-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
            </svg>
          </div>
          <h3 className="landing-feature-title">.zar Modules</h3>
          <p className="landing-feature-desc">Package and deploy modules as .zar archives. Real-time updates from our marketplace.</p>
        </div>
        <div className="landing-feature-card">
          <div className="landing-feature-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
            </svg>
          </div>
          <h3 className="landing-feature-title">Free Subdomain</h3>
          <p className="landing-feature-desc">Every project gets a free <code className="code-inline">*.nso.dev</code> domain, ready to use.</p>
        </div>
      </section>

      <footer className="landing-footer">
        <span>NSO &mdash; Network Service Orchestration</span>
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
