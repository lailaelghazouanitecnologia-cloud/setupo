"use client";

import { useState, useEffect } from "react";
import { useZ86Store } from "@/stores/z86-store";
import { login, register } from "@/lib/api/client";
import { DashboardLayout } from "@/components/dashboard/dashboard-layout";

type PageView = "landing" | "login" | "register";

const Z86Logo = ({ size = 28 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="8" y="8" width="84" height="84" rx="16" stroke="currentColor" strokeWidth="6" />
    <rect x="24" y="28" width="52" height="10" rx="5" fill="currentColor" opacity="0.3" />
    <rect x="24" y="45" width="52" height="10" rx="5" fill="currentColor" opacity="0.6" />
    <rect x="24" y="62" width="52" height="10" rx="5" fill="currentColor" />
  </svg>
);

function LandingPage({ onNavigate }: { onNavigate: (view: PageView) => void }) {
  return (
    <div className="landing-page">
      <nav className="landing-nav">
        <div className="landing-nav-inner">
          <div className="landing-nav-left">
            <Z86Logo size={18} />
            <span className="landing-nav-brand">z86</span>
          </div>
          <div className="landing-nav-right">
            <div className="landing-nav-links">
              <button className="landing-nav-link" onClick={() => document.getElementById("features")?.scrollIntoView({ behavior: "smooth" })}>
                Features
              </button>
              <span className="landing-slash">/</span>
              <button className="landing-nav-link" onClick={() => document.getElementById("how")?.scrollIntoView({ behavior: "smooth" })}>
                How it works
              </button>
              <span className="landing-slash">/</span>
              <button className="landing-nav-link" onClick={() => document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" })}>
                Pricing
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
                S3-compatible &mdash; drop-in replacement
              </div>
              <h1 className="landing-hero-title">Object storage<br />without the complexity</h1>
              <p className="landing-hero-sub">
                S3-compatible API. No egress fees. No vendor lock-in. Store files, assets, backups, and deploy artifacts on infrastructure you control.
              </p>
              <div className="landing-hero-actions">
                <button className="landing-btn landing-btn-primary" onClick={() => onNavigate("register")}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                  Start storing
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
                <span className="landing-terminal-title">~/my-app</span>
              </div>
              <div className="landing-terminal-body">
                <div><span className="t-comment"># Works with any S3 client — aws cli, boto3, minio, etc.</span></div>
                <div><span className="t-prompt">$</span> <span className="t-cmd">aws s3 cp</span> <span className="t-arg">./backup.tar.gz</span> <span className="t-flag">s3://my-bucket/backups/</span></div>
                <div><span className="t-out">upload: ./backup.tar.gz → s3://my-bucket/backups/backup.tar.gz</span></div>
                <div style={{ height: 6 }} />
                <div><span className="t-prompt">$</span> <span className="t-cmd">aws s3 ls</span> <span className="t-flag">s3://my-bucket/</span> <span className="t-flag">--endpoint-url</span> <span className="t-arg">https://z86.dev</span></div>
                <div><span className="t-out">2026-03-04  backups/</span></div>
                <div><span className="t-out">2026-03-04  assets/</span></div>
                <div><span className="t-out">2026-03-04  deploys/</span></div>
                <div style={{ height: 6 }} />
                <div><span className="t-prompt">$</span> <span className="t-cmd">curl</span> <span className="t-flag">-I</span> <span className="t-arg">https://z86.dev/my-bucket/assets/logo.png</span></div>
                <div><span className="t-out">HTTP/2 200</span> <span className="t-ok">OK</span></div>
                <div><span className="t-out">content-length: 24576</span></div>
                <div><span className="t-out">etag: &quot;a1b2c3d4e5f6...&quot;</span></div>
                <div><span className="t-prompt">$</span> <span className="t-cursor" /></div>
              </div>
            </div>
          </div>
        </section>

        {/* ── Features ── */}
        <section className="landing-capabilities" id="features">
          <div className="landing-container">
            <div className="landing-cap-layout">
              <div className="landing-cap-intro">
                <div className="landing-s-label">Features</div>
                <h2 className="landing-s-title">Everything you need from object storage</h2>
                <p>z86 is a self-hosted, S3-compatible object storage service. Use any S3 client or SDK to store and retrieve objects.</p>
              </div>
              <div className="landing-cap-list">
                <div className="landing-cap-item">
                  <span className="landing-cap-num">01</span>
                  <div>
                    <h3 className="landing-cap-h">S3-Compatible API</h3>
                    <p className="landing-cap-p">PUT, GET, DELETE, HEAD, LIST &mdash; all the standard S3 operations. Use aws-cli, boto3, minio, or any S3 SDK. Just change the endpoint URL.</p>
                  </div>
                  <div className="landing-cap-tags">
                    <span className="landing-tag">AWS4-HMAC</span>
                    <span className="landing-tag">REST API</span>
                  </div>
                </div>
                <div className="landing-cap-item">
                  <span className="landing-cap-num">02</span>
                  <div>
                    <h3 className="landing-cap-h">Zero Egress Fees</h3>
                    <p className="landing-cap-p">Download your data as much as you want. No bandwidth charges, no surprise bills. Your storage, your rules.</p>
                  </div>
                  <div className="landing-cap-tags">
                    <span className="landing-tag">free egress</span>
                    <span className="landing-tag">predictable</span>
                  </div>
                </div>
                <div className="landing-cap-item">
                  <span className="landing-cap-num">03</span>
                  <div>
                    <h3 className="landing-cap-h">Access Key Management</h3>
                    <p className="landing-cap-p">Create, rotate, and revoke access keys from the dashboard. Scope keys to specific buckets for fine-grained access control.</p>
                  </div>
                  <div className="landing-cap-tags">
                    <span className="landing-tag">HMAC keys</span>
                    <span className="landing-tag">bucket scoping</span>
                  </div>
                </div>
                <div className="landing-cap-item">
                  <span className="landing-cap-num">04</span>
                  <div>
                    <h3 className="landing-cap-h">Dashboard</h3>
                    <p className="landing-cap-p">Browse buckets, upload files, manage objects, and monitor storage usage from a clean web interface. No CLI required.</p>
                  </div>
                  <div className="landing-cap-tags">
                    <span className="landing-tag">web UI</span>
                    <span className="landing-tag">file browser</span>
                  </div>
                </div>
                <div className="landing-cap-item">
                  <span className="landing-cap-num">05</span>
                  <div>
                    <h3 className="landing-cap-h">SHA-256 Integrity</h3>
                    <p className="landing-cap-p">Every object is checksummed on upload. Verify integrity at any time. No silent data corruption.</p>
                  </div>
                  <div className="landing-cap-tags">
                    <span className="landing-tag">checksums</span>
                    <span className="landing-tag">integrity</span>
                  </div>
                </div>
                <div className="landing-cap-item">
                  <span className="landing-cap-num">06</span>
                  <div>
                    <h3 className="landing-cap-h">NSO Integration</h3>
                    <p className="landing-cap-p">Seamlessly integrated with the NSO platform. .zar packages, deploy artifacts, and project assets are automatically stored on z86.</p>
                  </div>
                  <div className="landing-cap-tags">
                    <span className="landing-tag">NSO</span>
                    <span className="landing-tag">.zar</span>
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
            <h2 className="landing-s-title">Three steps to start storing</h2>
            <div className="landing-how-grid">
              <div className="landing-how-card">
                <div className="landing-how-num">01</div>
                <h3>Create account</h3>
                <p>Sign up and get your storage bucket provisioned automatically. Access keys are generated and ready to use.</p>
                <div className="landing-how-code">
                  <span className="t-prompt">$</span> <span className="t-cmd">z86 login</span>
                </div>
              </div>
              <div className="landing-how-card">
                <div className="landing-how-num">02</div>
                <h3>Configure</h3>
                <p>Point any S3 client to z86.dev. Use your access key and secret key. That&apos;s it &mdash; no region selection, no complex IAM.</p>
                <div className="landing-how-code">
                  <span className="t-prompt">$</span> <span className="t-cmd">aws configure</span> <span className="t-flag">--endpoint</span> <span className="t-arg">z86.dev</span>
                </div>
              </div>
              <div className="landing-how-card">
                <div className="landing-how-num">03</div>
                <h3>Store & retrieve</h3>
                <p>Upload objects, list buckets, download files. Same S3 API you already know. Works with every tool and SDK.</p>
                <div className="landing-how-code">
                  <span className="t-prompt">$</span> <span className="t-cmd">aws s3 cp</span> <span className="t-arg">file.zip</span> <span className="t-flag">s3://bucket/</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── Pricing ── */}
        <section className="landing-pricing" id="pricing">
          <div className="landing-container">
            <div className="landing-s-label">Pricing</div>
            <h2 className="landing-s-title">Simple, predictable pricing</h2>
            <div className="landing-pricing-grid">
              <div className="landing-pricing-card">
                <div className="landing-pricing-tier">Free</div>
                <div className="landing-pricing-price">$0<span>/mo</span></div>
                <ul className="landing-pricing-features">
                  <li>1 GB storage</li>
                  <li>1 bucket</li>
                  <li>Unlimited egress</li>
                  <li>S3-compatible API</li>
                  <li>Web dashboard</li>
                </ul>
                <button className="landing-btn landing-btn-secondary" onClick={() => onNavigate("register")} style={{ width: "100%" }}>
                  Get started free
                </button>
              </div>
              <div className="landing-pricing-card landing-pricing-featured">
                <div className="landing-pricing-tier">Pro</div>
                <div className="landing-pricing-price">$5<span>/mo</span></div>
                <ul className="landing-pricing-features">
                  <li>100 GB storage</li>
                  <li>Unlimited buckets</li>
                  <li>Unlimited egress</li>
                  <li>Multiple access keys</li>
                  <li>Priority support</li>
                </ul>
                <button className="landing-btn landing-btn-primary" onClick={() => onNavigate("register")} style={{ width: "100%" }}>
                  Start with Pro
                </button>
              </div>
              <div className="landing-pricing-card">
                <div className="landing-pricing-tier">Enterprise</div>
                <div className="landing-pricing-price">Custom</div>
                <ul className="landing-pricing-features">
                  <li>Unlimited storage</li>
                  <li>Dedicated infrastructure</li>
                  <li>SLA guarantee</li>
                  <li>Custom integrations</li>
                  <li>White-glove onboarding</li>
                </ul>
                <button className="landing-btn landing-btn-secondary" style={{ width: "100%" }}>
                  Contact us
                </button>
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
                  <h2>Start storing in minutes</h2>
                  <p>Create an account and get your first bucket. No credit card required.</p>
                </div>
                <div className="landing-cta-actions">
                  <button className="landing-btn landing-btn-primary" onClick={() => onNavigate("register")}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                    Create free account
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

      <footer className="landing-footer">
        <div className="landing-container">
          <div className="landing-footer-inner">
            <div className="landing-footer-links">
              <button onClick={() => document.getElementById("features")?.scrollIntoView({ behavior: "smooth" })}>Features</button>
              <button onClick={() => document.getElementById("how")?.scrollIntoView({ behavior: "smooth" })}>How it works</button>
              <button onClick={() => document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" })}>Pricing</button>
              <a href="https://nso.dev" target="_blank" rel="noopener noreferrer">NSO Platform</a>
            </div>
            <span className="landing-footer-copy">&copy; 2026 z86</span>
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
  const setToken = useZ86Store((s) => s.setToken);
  const setUser = useZ86Store((s) => s.setUser);

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
          <Z86Logo />
          <span className="login-brand">z86</span>
        </div>
        <p className="login-subtitle">Sign in to your storage</p>
        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-field">
            <label className="login-label">Email</label>
            <input className="login-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required autoComplete="email" />
          </div>
          <div className="login-field">
            <label className="login-label">Password</label>
            <input className="login-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" required autoComplete="current-password" />
          </div>
          {error && <p className="login-error">{error}</p>}
          <button type="submit" disabled={loading} className="login-submit">{loading ? "Signing in..." : "Sign in"}</button>
        </form>
        <div className="login-footer">
          <span>Don&apos;t have an account? <button className="login-link" onClick={() => onNavigate("register")}>Create one</button></span>
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
  const setToken = useZ86Store((s) => s.setToken);
  const setUser = useZ86Store((s) => s.setUser);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await register(email, password, name);
      setUser(res.email, res.role);
      setToken(res.token);
    } catch (err: any) {
      if (err.message?.includes("409")) setError("Email already registered");
      else if (err.message?.includes("400")) setError("Invalid email or password too short (min 6 chars)");
      else setError("Registration failed. Please try again.");
    }
    setLoading(false);
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-header">
          <Z86Logo />
          <span className="login-brand">z86</span>
        </div>
        <p className="login-subtitle">Create your storage account</p>
        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-field">
            <label className="login-label">Name</label>
            <input className="login-input" type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" autoComplete="name" />
          </div>
          <div className="login-field">
            <label className="login-label">Email</label>
            <input className="login-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required autoComplete="email" />
          </div>
          <div className="login-field">
            <label className="login-label">Password</label>
            <input className="login-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Min. 6 characters" required minLength={6} autoComplete="new-password" />
          </div>
          {error && <p className="login-error">{error}</p>}
          <button type="submit" disabled={loading} className="login-submit">{loading ? "Creating account..." : "Create account"}</button>
        </form>
        <div className="login-footer">
          <span>Already have an account? <button className="login-link" onClick={() => onNavigate("login")}>Sign in</button></span>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  const token = useZ86Store((s) => s.token);
  const [mounted, setMounted] = useState(false);
  const [view, setView] = useState<PageView>("landing");

  useEffect(() => { setMounted(true); }, []);

  if (!mounted) return null;

  if (token) return <DashboardLayout />;

  if (view === "login") return <LoginPage onNavigate={setView} />;
  if (view === "register") return <RegisterPage onNavigate={setView} />;
  return <LandingPage onNavigate={setView} />;
}
