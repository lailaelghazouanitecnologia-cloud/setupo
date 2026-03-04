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
      // Fixed panel entrance
      gsap.from(".lp-fixed-title", { y: 20, opacity: 0, duration: 1, delay: 0.2, ease: "power3.out" });
      gsap.from(".lp-fixed-terminal", { y: 20, opacity: 0, duration: 0.8, delay: 0.5, ease: "power3.out" });
      gsap.from(".lp-fixed-actions", { y: 10, opacity: 0, duration: 0.6, delay: 0.7, ease: "power3.out" });

      // Scroll panel sections
      gsap.utils.toArray<HTMLElement>(".lp-section").forEach((section) => {
        gsap.from(section.children, {
          y: 30, opacity: 0, duration: 0.7, stagger: 0.06, ease: "power3.out",
          scrollTrigger: { trigger: section, scroller: scrollRef.current, start: "top 82%", toggleActions: "play none none none" },
        });
      });

      // Feature items
      gsap.utils.toArray<HTMLElement>(".lp-item-outer").forEach((item, i) => {
        gsap.from(item, {
          y: 16, opacity: 0, duration: 0.4, delay: i * 0.04, ease: "power2.out",
          scrollTrigger: { trigger: item, scroller: scrollRef.current, start: "top 88%", toggleActions: "play none none none" },
        });
      });

      // Pricing cards
      gsap.utils.toArray<HTMLElement>(".lp-price-outer").forEach((card, i) => {
        gsap.from(card, {
          y: 30, opacity: 0, duration: 0.5, delay: i * 0.06, ease: "power3.out",
          scrollTrigger: { trigger: card, scroller: scrollRef.current, start: "top 85%", toggleActions: "play none none none" },
        });
      });
    });
    return () => ctx.revert();
  }, []);

  return (
    <div className="lp">
      {/* ── Fixed left panel (36%) ── */}
      <div className="lp-fixed">
        <ShaderBackground />
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
              <button className="landing-btn landing-btn-dark" onClick={onRegister} style={{ flex: 1, justifyContent: "center" }}>Get started</button>
              <button className="landing-btn landing-btn-outline" onClick={onLogin} style={{ flex: 1, justifyContent: "center" }}>Sign in</button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Scrollable right panel (64%) — white bg ── */}
      <div className="lp-scroll" ref={scrollRef}>
        {/* Header */}
        <header className="lp-header">
          <div className="lp-header-inner">
            <nav className="lp-header-nav">
              <button className="lp-nav-link" onClick={() => document.getElementById("features")?.scrollIntoView({ behavior: "smooth" })}>Features</button>
              <button className="lp-nav-link" onClick={() => document.getElementById("how")?.scrollIntoView({ behavior: "smooth" })}>How it works</button>
              <button className="lp-nav-link" onClick={() => document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" })}>Pricing</button>
            </nav>
          </div>
        </header>

        {/* Hero */}
        <section className="lp-section lp-hero">
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
                  <button className={`landing-btn ${p.featured ? "landing-btn-primary" : "landing-btn-ghost"}`} onClick={p.action} style={{ width: "100%", justifyContent: "center" }}>
                    {p.btn}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Footer */}
        <footer className="lp-footer">
          <div className="lp-footer-manifesto">
            S3-compatible object storage. Fast, simple, and on your terms.<br />
            No egress fees, no vendor lock-in, no complexity. Just store.
          </div>
          <span className="lp-footer-copy">&copy; 2026 z86</span>
        </footer>
      </div>
    </div>
  );
}

function ShaderBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", { alpha: false, antialias: false });
    if (!gl) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const rect = canvas.parentElement!.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    gl.viewport(0, 0, canvas.width, canvas.height);

    // Vertex shader — fullscreen quad
    const vs = gl.createShader(gl.VERTEX_SHADER)!;
    gl.shaderSource(vs, `
      attribute vec2 p;
      varying vec2 uv;
      void main() {
        uv = p * 0.5 + 0.5;
        gl_Position = vec4(p, 0.0, 1.0);
      }
    `);
    gl.compileShader(vs);

    // Fragment shader — dark red bg with flowing white lines
    const fs = gl.createShader(gl.FRAGMENT_SHADER)!;
    gl.shaderSource(fs, `
      precision mediump float;
      varying vec2 uv;
      uniform float t;
      uniform vec2 res;

      // Noise helper
      float hash(vec2 p) {
        return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
      }

      float noise(vec2 p) {
        vec2 i = floor(p);
        vec2 f = fract(p);
        f = f * f * (3.0 - 2.0 * f);
        float a = hash(i);
        float b = hash(i + vec2(1.0, 0.0));
        float c = hash(i + vec2(0.0, 1.0));
        float d = hash(i + vec2(1.0, 1.0));
        return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
      }

      void main() {
        vec2 p = uv;
        float aspect = res.x / res.y;

        // Dark red base with subtle gradient
        vec3 bg1 = vec3(0.18, 0.02, 0.02);  // deep dark red
        vec3 bg2 = vec3(0.12, 0.01, 0.03);  // darker red-black
        vec3 bg = mix(bg1, bg2, uv.y * 0.8 + noise(uv * 2.0 + t * 0.05) * 0.2);

        // Flowing white lines — multiple layers
        float lines = 0.0;

        // Layer 1: horizontal flowing curves
        for (float i = 0.0; i < 8.0; i++) {
          float y0 = (i + 0.5) / 8.0;
          float wave = sin(p.x * (3.0 + i * 0.7) + t * (0.3 + i * 0.05) + i * 1.7) * 0.06;
          wave += sin(p.x * (5.0 + i * 1.3) - t * (0.2 + i * 0.03)) * 0.03;
          float d = abs(p.y - y0 - wave);
          float thickness = 0.002 + 0.001 * sin(t * 0.5 + i);
          lines += smoothstep(thickness * 2.0, thickness * 0.3, d) * (0.15 + 0.1 * sin(i * 2.0 + t * 0.4));
        }

        // Layer 2: diagonal lines moving slowly
        for (float i = 0.0; i < 5.0; i++) {
          float angle = 0.3 + i * 0.15;
          float pos = p.x * cos(angle) + p.y * sin(angle);
          float wave = sin(pos * 12.0 + t * (0.2 + i * 0.04) + i * 3.0);
          wave = smoothstep(0.92, 1.0, wave) * (0.12 + 0.06 * sin(t * 0.3 + i));
          lines += wave;
        }

        // Layer 3: subtle noise-displaced grid lines
        float n1 = noise(vec2(p.x * 3.0 + t * 0.1, p.y * 15.0));
        float grid = smoothstep(0.48, 0.5, fract(p.y * 40.0 + n1 * 0.3 + t * 0.05));
        grid *= smoothstep(0.5, 0.52, fract(p.y * 40.0 + n1 * 0.3 + t * 0.05));
        lines += grid * 0.06;

        // White lines with slight warmth
        vec3 lineColor = vec3(0.95, 0.90, 0.88);
        vec3 col = bg + lineColor * lines;

        // Vignette
        float vig = 1.0 - smoothstep(0.3, 1.5, length((uv - 0.5) * 1.6));
        col *= vig * 0.85 + 0.15;

        gl_FragColor = vec4(col, 1.0);
      }
    `);
    gl.compileShader(fs);

    const prog = gl.createProgram()!;
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    gl.useProgram(prog);

    // Fullscreen quad
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
    const pLoc = gl.getAttribLocation(prog, "p");
    gl.enableVertexAttribArray(pLoc);
    gl.vertexAttribPointer(pLoc, 2, gl.FLOAT, false, 0, 0);

    const tLoc = gl.getUniformLocation(prog, "t");
    const rLoc = gl.getUniformLocation(prog, "res");
    gl.uniform2f(rLoc, canvas.width, canvas.height);

    let start = 0;
    const render = (now: number) => {
      if (!start) start = now;
      const elapsed = (now - start) * 0.001;
      gl.uniform1f(tLoc, elapsed);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      rafRef.current = requestAnimationFrame(render);
    };
    rafRef.current = requestAnimationFrame(render);

    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  return (
    <>
      <canvas ref={canvasRef} className="lp-shader" />
      <div className="lp-shader-blur" />
    </>
  );
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
  return <canvas ref={canvasRef} width={width * 2} height={height * 2} style={{ width, height }} />;
}
