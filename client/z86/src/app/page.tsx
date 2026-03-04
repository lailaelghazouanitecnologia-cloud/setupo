"use client";
import { useEffect, useState } from "react";
import { useZ86Store } from "@/stores/z86-store";
import { LoginForm, RegisterForm } from "@/components/auth-form";
import { DashboardLayout } from "@/components/dashboard-layout";

export default function Home() {
  const { view, setView, token } = useZ86Store();
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);
  if (!mounted) return null;

  if (token && view !== "landing") return <DashboardLayout />;
  if (view === "login") return <LoginForm />;
  if (view === "register") return <RegisterForm />;

  return <LandingPage onLogin={() => setView("login")} onRegister={() => setView("register")} />;
}

function LandingPage({ onLogin, onRegister }: { onLogin: () => void; onRegister: () => void }) {
  return (
    <div className="lp">
      {/* ── Fixed right panel (36%) ── */}
      <div className="lp-fixed">
        <div className="lp-fixed-inner">
          <div className="lp-fixed-top">
            <Z86Logo size={32} />
            <span className="lp-brand">z86</span>
          </div>
          <div className="lp-fixed-center">
            <div className="lp-terminal">
              <div className="lp-terminal-bar">
                <span className="landing-terminal-dot" />
                <span className="landing-terminal-dot" />
                <span className="landing-terminal-dot" />
                <span className="landing-terminal-title">~/my-app</span>
              </div>
              <div className="lp-terminal-body">
                <div><span className="t-comment"># Works with any S3 client</span></div>
                <div><span className="t-prompt">$</span> <span className="t-cmd">aws s3 cp</span> <span className="t-arg">./backup.tar.gz</span> <span className="t-flag">s3://bucket/</span></div>
                <div><span className="t-out">upload: ./backup.tar.gz → s3://bucket/backup.tar.gz</span></div>
                <div style={{ height: 4 }} />
                <div><span className="t-prompt">$</span> <span className="t-cmd">aws s3 ls</span> <span className="t-flag">s3://bucket/</span></div>
                <div><span className="t-out">2026-03-04  backups/</span></div>
                <div><span className="t-out">2026-03-04  assets/</span></div>
                <div style={{ height: 4 }} />
                <div><span className="t-prompt">$</span> <span className="t-cmd">curl</span> <span className="t-flag">-I</span> <span className="t-arg">https://s3.z86.dev/bucket/logo.png</span></div>
                <div><span className="t-out">HTTP/2 200</span> <span className="t-ok">OK</span></div>
                <div><span className="t-prompt">$</span> <span className="t-cursor" /></div>
              </div>
            </div>
          </div>
          <div className="lp-fixed-bottom">
            <div className="lp-fixed-actions">
              <button className="landing-btn landing-btn-primary" onClick={onRegister} style={{ flex: 1, justifyContent: "center" }}>Get started</button>
              <button className="landing-btn landing-btn-secondary" onClick={onLogin} style={{ flex: 1, justifyContent: "center" }}>Sign in</button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Scrollable left panel (64%) ── */}
      <div className="lp-scroll">
        {/* Nav bar */}
        <nav className="lp-nav">
          <div className="lp-nav-inner">
            <div className="lp-nav-left">
              <Z86Logo size={16} />
              <span className="lp-nav-brand">z86</span>
            </div>
            <div className="lp-nav-right">
              <button className="lp-nav-link" onClick={() => document.getElementById("features")?.scrollIntoView({ behavior: "smooth" })}>Features</button>
              <button className="lp-nav-link" onClick={() => document.getElementById("how")?.scrollIntoView({ behavior: "smooth" })}>How it works</button>
              <button className="lp-nav-link" onClick={() => document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" })}>Pricing</button>
            </div>
          </div>
        </nav>

        {/* Hero */}
        <section className="lp-hero">
          <div className="lp-badge">
            <span className="lp-badge-dot" />
            S3-compatible &mdash; drop-in replacement
          </div>
          <h1 className="lp-title">Object storage<br />without the<br />complexity</h1>
          <p className="lp-sub">
            S3-compatible API. No egress fees. No vendor lock-in.<br />
            Store files, assets, backups on infrastructure you control.
          </p>
        </section>

        {/* Features */}
        <section className="lp-section" id="features">
          <div className="lp-section-header">
            <span className="lp-label">Features</span>
            <span className="lp-label-suffix">06</span>
          </div>
          {[
            { n: "01", h: "S3-Compatible API", p: "PUT, GET, DELETE, HEAD, LIST — all standard S3 operations. Use aws-cli, boto3, minio, or any S3 SDK.", tags: ["AWS4-HMAC", "REST API"] },
            { n: "02", h: "Zero Egress Fees", p: "Download your data as much as you want. No bandwidth charges, no surprise bills.", tags: ["free egress", "predictable"] },
            { n: "03", h: "Dashboard", p: "Browse buckets, upload files, manage access keys, and track usage from the web.", tags: ["web UI", "real-time"] },
            { n: "04", h: "Access Key Management", p: "Create, rotate, and revoke HMAC keys. Scope keys to specific buckets.", tags: ["HMAC keys", "scoping"] },
            { n: "05", h: "SHA-256 Integrity", p: "Every object is checksummed on upload. Verify integrity at any time.", tags: ["checksums", "integrity"] },
            { n: "06", h: "Self-Hosted", p: "Your data stays on your infrastructure. No third-party dependencies.", tags: ["self-hosted", "privacy"] },
          ].map((f) => (
            <div key={f.n} className="lp-item-outer">
              <div className="lp-item-inner">
                <span className="lp-item-left">
                  <span className="lp-item-num">{f.n}</span>
                  <span className="lp-item-content">
                    <span className="lp-item-h">{f.h}</span>
                    <span className="lp-item-p">{f.p}</span>
                  </span>
                </span>
                <span className="lp-item-suffix">
                  {f.tags.map(t => <span key={t} className="lp-tag">{t}</span>)}
                </span>
              </div>
            </div>
          ))}
        </section>

        {/* How it works */}
        <section className="lp-section" id="how">
          <div className="lp-section-header">
            <span className="lp-label">How it works</span>
            <span className="lp-label-suffix">03</span>
          </div>
          <div className="lp-steps">
            {[
              { n: "01", h: "Create an account", p: "Sign up at z86.dev. Free tier includes 1 GB with no credit card.", cmd: "$ open https://z86.dev" },
              { n: "02", h: "Get your keys", p: "Create an access key from the dashboard. Point any S3 client to s3.z86.dev.", cmd: "$ aws configure --endpoint s3.z86.dev" },
              { n: "03", h: "Store & retrieve", p: "Upload objects, list buckets, download files. Same S3 API you already know.", cmd: "$ aws s3 cp file.zip s3://bucket/" },
            ].map((s) => (
              <div key={s.n} className="lp-step-outer">
                <div className="lp-step-inner">
                  <span className="lp-step-num">{s.n}</span>
                  <h3 className="lp-step-h">{s.h}</h3>
                  <p className="lp-step-p">{s.p}</p>
                  <div className="lp-step-code">{s.cmd}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Pricing */}
        <section className="lp-section" id="pricing">
          <div className="lp-section-header">
            <span className="lp-label">Pricing</span>
            <span className="lp-label-suffix">03</span>
          </div>
          <div className="lp-pricing">
            {[
              { tier: "Free", price: "$0", per: "/mo", items: ["1 GB storage", "3 buckets", "2 access keys", "Unlimited egress", "S3-compatible API"], btn: "Get started free", action: onRegister, featured: false },
              { tier: "Pro", price: "$5", per: "/mo", items: ["100 GB storage", "50 buckets", "10 access keys", "Unlimited egress", "Priority support"], btn: "Start with Pro", action: onRegister, featured: true },
              { tier: "Enterprise", price: "Custom", per: "", items: ["Unlimited storage", "Dedicated infrastructure", "SLA guarantee", "Custom integrations", "White-glove onboarding"], btn: "Contact us", action: onLogin, featured: false },
            ].map((p) => (
              <div key={p.tier} className={`lp-price-outer${p.featured ? " lp-price-featured" : ""}`}>
                <div className="lp-price-inner">
                  <span className="lp-price-tier">{p.tier}</span>
                  <span className="lp-price-amount">{p.price}<span>{p.per}</span></span>
                  <ul className="lp-price-list">
                    {p.items.map(i => <li key={i}>{i}</li>)}
                  </ul>
                  <button className={`landing-btn ${p.featured ? "landing-btn-primary" : "landing-btn-secondary"}`} onClick={p.action} style={{ width: "100%", justifyContent: "center" }}>
                    {p.btn}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Footer — BECANE manifesto + bars */}
        <footer className="lp-footer">
          <div className="lp-footer-manifesto">
            S3-compatible object storage. Fast, simple, and on your terms. No egress fees, no vendor lock-in, no complexity. Just store.
          </div>
          <nav className="lp-footer-bars">
            <div className="lp-footer-bar lp-footer-bar-left">
              <button className="lp-footer-btn" onClick={onRegister}>
                <span>Get started</span>
              </button>
            </div>
            <div className="lp-footer-bar lp-footer-bar-right">
              <button className="lp-footer-btn" onClick={() => document.getElementById("features")?.scrollIntoView({ behavior: "smooth" })}>
                <span>Features</span>
              </button>
              <button className="lp-footer-btn" onClick={() => document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" })}>
                <span>Pricing</span>
              </button>
              <button className="lp-footer-btn" onClick={onLogin}>
                <span>Sign in</span>
              </button>
              <span className="lp-footer-copy">&copy; 2026 z86</span>
            </div>
          </nav>
        </footer>
      </div>
    </div>
  );
}

const Z86Logo = ({ size = 28 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="8" y="8" width="84" height="84" rx="16" stroke="currentColor" strokeWidth="6" />
    <rect x="24" y="28" width="52" height="10" rx="5" fill="currentColor" opacity="0.3" />
    <rect x="24" y="45" width="52" height="10" rx="5" fill="currentColor" opacity="0.6" />
    <rect x="24" y="62" width="52" height="10" rx="5" fill="currentColor" />
  </svg>
);
