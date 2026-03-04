"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import { useZ86Store } from "@/stores/z86-store";
import { LoginForm, RegisterForm } from "@/components/auth-form";
import { DashboardLayout } from "@/components/dashboard-layout";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

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
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      // Animate each section on scroll
      gsap.utils.toArray<HTMLElement>(".lp-section, .lp-hero").forEach((section) => {
        gsap.from(section.children, {
          y: 40, opacity: 0, duration: 0.8, stagger: 0.1, ease: "power3.out",
          scrollTrigger: {
            trigger: section,
            scroller: scrollRef.current,
            start: "top 80%",
            toggleActions: "play none none none",
          },
        });
      });

      // Animate feature items
      gsap.utils.toArray<HTMLElement>(".lp-item-outer").forEach((item, i) => {
        gsap.from(item, {
          x: -30, opacity: 0, duration: 0.5, delay: i * 0.06, ease: "power2.out",
          scrollTrigger: {
            trigger: item,
            scroller: scrollRef.current,
            start: "top 85%",
            toggleActions: "play none none none",
          },
        });
      });

      // Animate pricing cards
      gsap.utils.toArray<HTMLElement>(".lp-price-outer").forEach((card, i) => {
        gsap.from(card, {
          y: 50, opacity: 0, duration: 0.6, delay: i * 0.1, ease: "power3.out",
          scrollTrigger: {
            trigger: card,
            scroller: scrollRef.current,
            start: "top 85%",
            toggleActions: "play none none none",
          },
        });
      });

      // Fixed panel title
      gsap.from(".lp-fixed-title", { y: 20, opacity: 0, duration: 1, delay: 0.3, ease: "power3.out" });
      gsap.from(".lp-fixed-terminal", { y: 20, opacity: 0, duration: 0.8, delay: 0.6, ease: "power3.out" });
      gsap.from(".lp-fixed-actions", { y: 10, opacity: 0, duration: 0.6, delay: 0.8, ease: "power3.out" });
    });

    return () => ctx.revert();
  }, []);

  return (
    <div className="lp">
      {/* ── Fixed left panel (36%) ── */}
      <div className="lp-fixed">
        <NoiseBackground />
        <div className="lp-fixed-inner">
          <div className="lp-fixed-top">
            <Z86Logo width={80} height={32} />
          </div>
          <div className="lp-fixed-center">
            <h2 className="lp-fixed-title">
              Affordable,<br />scalable<br />infrastructure<br />you control.
            </h2>
          </div>
          <div className="lp-fixed-bottom">
            <div className="lp-fixed-terminal">
              <div className="lp-terminal-body">
                <div><span className="t-prompt">$</span> <span className="t-cmd">aws s3 cp</span> <span className="t-arg">./data.tar.gz</span> <span className="t-flag">s3://bucket/</span></div>
                <div><span className="t-out">upload: ./data.tar.gz → s3://bucket/data.tar.gz</span></div>
                <div><span className="t-prompt">$</span> <span className="t-cursor" /></div>
              </div>
            </div>
            <div className="lp-fixed-actions">
              <button className="landing-btn landing-btn-primary" onClick={onRegister} style={{ flex: 1, justifyContent: "center" }}>Get started</button>
              <button className="landing-btn landing-btn-secondary" onClick={onLogin} style={{ flex: 1, justifyContent: "center" }}>Sign in</button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Scrollable right panel (64%) ── */}
      <div className="lp-scroll" ref={scrollRef}>
        {/* Header */}
        <header className="lp-header">
          <div className="lp-header-inner">
            <div className="lp-header-left">
              <Z86Logo width={40} height={16} />
            </div>
            <nav className="lp-header-nav">
              <button className="lp-nav-link" onClick={() => document.getElementById("features")?.scrollIntoView({ behavior: "smooth" })}>Features</button>
              <button className="lp-nav-link" onClick={() => document.getElementById("how")?.scrollIntoView({ behavior: "smooth" })}>How it works</button>
              <button className="lp-nav-link" onClick={() => document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" })}>Pricing</button>
            </nav>
            <div className="lp-header-right">
              <button className="lp-nav-link" onClick={onLogin}>Sign in</button>
              <button className="landing-btn landing-btn-primary landing-btn-sm" onClick={onRegister}>Get started</button>
            </div>
          </div>
        </header>

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

function NoiseBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.parentElement!.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    const cw = canvas.width;
    const ch = canvas.height;
    const img = ctx.createImageData(cw, ch);
    const px = img.data;
    for (let i = 0; i < px.length; i += 4) {
      const v = Math.floor(Math.random() * 18);
      px[i] = v; px[i + 1] = v; px[i + 2] = v; px[i + 3] = 30;
    }
    ctx.putImageData(img, 0, 0);
  }, []);
  return <canvas ref={canvasRef} className="lp-noise" />;
}

function Z86Logo({ width = 72, height = 28 }: { width?: number; height?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const cw = canvas.width;
    const ch = canvas.height;
    // text mask
    const off = document.createElement("canvas");
    off.width = cw; off.height = ch;
    const oCtx = off.getContext("2d")!;
    oCtx.fillStyle = "#fff";
    const fontSize = Math.round(ch * 0.75);
    oCtx.font = `900 ${fontSize}px "Arial Black","Impact",sans-serif`;
    oCtx.textAlign = "center";
    oCtx.textBaseline = "middle";
    oCtx.fillText("z86", cw / 2, ch / 2 + 1);
    const mask = oCtx.getImageData(0, 0, cw, ch);
    // draw scan-lines
    ctx.clearRect(0, 0, cw, ch);
    const img = ctx.createImageData(cw, ch);
    const px = img.data;
    const lineSpacing = Math.max(2, Math.round(ch / 40));
    const lineWidth = Math.max(1, Math.round(lineSpacing * 0.57));
    for (let y = 0; y < ch; y++) {
      if ((y % lineSpacing) >= lineWidth) continue;
      const t = y / ch;
      const base = 255 - Math.floor(t * 180);
      for (let x = 0; x < cw; x++) {
        const idx = (y * cw + x) * 4;
        if (mask.data[idx + 3] < 128) continue;
        const noise = (Math.random() - 0.5) * 50;
        const v = Math.max(0, Math.min(255, base + noise));
        px[idx] = v; px[idx + 1] = v; px[idx + 2] = v; px[idx + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }, []);
  useEffect(() => { draw(); }, [draw]);
  // use 2x resolution for retina
  return <canvas ref={canvasRef} width={width * 2} height={height * 2} style={{ width, height }} />;
}
