"use client";
import { useEffect, useState, useRef } from "react";
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

/* ═══════════════════════════════════════
   LANDING — Split: dark left + white right
   Editorial style, serif headings, list layouts
   ═══════════════════════════════════════ */

function LandingPage({ onLogin, onRegister }: { onLogin: () => void; onRegister: () => void }) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // IntersectionObserver scroll reveal
  useEffect(() => {
    const root = scrollRef.current;
    if (!root) return;
    const els = root.querySelectorAll<HTMLElement>(".fi");
    const ob = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (!e.isIntersecting) return;
        // Stagger items within same parent
        let delay = 0;
        const t = e.target as HTMLElement;
        if (t.classList.contains("I")) {
          const siblings = Array.from(t.parentElement?.querySelectorAll(".I") || []);
          delay = siblings.indexOf(t) * 45;
        }
        setTimeout(() => t.classList.add("v"), delay);
        ob.unobserve(t);
      });
    }, { threshold: 0.08, root });
    els.forEach((el) => ob.observe(el));
    return () => ob.disconnect();
  }, []);

  return (
    <div className="LP">
      {/* ── LEFT — dark fixed panel ── */}
      <aside className="L">
        <ShaderBackground />
        <div className="L-top">
          <Z86Logo size={44} />
        </div>
        <div className="L-center">
          <h2 className="L-heading">Affordable,<br />scalable<br />infrastructure<br />you control.</h2>
        </div>
        <div className="L-bottom">
          <div className="L-terminal">
            <div><span className="L-o">$</span> <span className="L-c">aws s3 cp</span> <span className="L-a">./data.tar.gz</span> <span className="L-a">s3://bucket/</span></div>
            <div><span className="L-o">upload: ./data.tar.gz → s3://bucket/data.tar.gz</span></div>
            <div><span className="L-o">$</span> <span className="L-cur" /></div>
          </div>
          <div className="L-actions">
            <button className="L-btn L-btn-light" onClick={onRegister}>Get started</button>
            <button className="L-btn L-btn-ghost" onClick={onLogin}>Sign in</button>
          </div>
        </div>
      </aside>

      {/* ── RIGHT — clean white scroll ── */}
      <main className="R" ref={scrollRef}>
        {/* Header */}
        <header className="H">
          <div className="H-in">
            <nav className="H-nav">
              <button className="H-a" onClick={() => document.getElementById("ft")?.scrollIntoView({ behavior: "smooth" })}>Features</button>
              <button className="H-a" onClick={() => document.getElementById("hw")?.scrollIntoView({ behavior: "smooth" })}>How it works</button>
              <button className="H-a" onClick={() => document.getElementById("pr")?.scrollIntoView({ behavior: "smooth" })}>Pricing</button>
            </nav>
            <div className="H-r">
              <button className="H-a" onClick={onLogin}>Sign in</button>
              <button className="H-btn" onClick={onRegister}>Get started</button>
            </div>
          </div>
        </header>

        {/* Page info — hero */}
        <div className="PI">
          <p className="PI-sub">S3-compatible storage</p>
          <h1 className="PI-title">Object storage<br />without the<br />complexity</h1>
          <p className="PI-desc">No egress fees. No vendor lock-in. Store files, assets and backups on infrastructure you control.</p>
        </div>

        {/* Features */}
        <section className="S" id="ft">
          <div className="S-hdr"><span className="S-label">Features</span><span className="S-n">06</span></div>
          {[
            { n: "01", h: "S3-Compatible API", p: "PUT, GET, DELETE, HEAD, LIST — use aws-cli, boto3, or any S3 SDK.", tags: ["AWS4-HMAC", "REST"] },
            { n: "02", h: "Zero Egress Fees", p: "Download as much as you want. No bandwidth charges.", tags: ["Free egress"] },
            { n: "03", h: "Dashboard", p: "Browse buckets, manage keys, track usage from the web.", tags: ["Web UI"] },
            { n: "04", h: "Access Keys", p: "Create, rotate, revoke HMAC keys. Scope to buckets.", tags: ["HMAC", "Scoping"] },
            { n: "05", h: "SHA-256 Integrity", p: "Every object checksummed on upload.", tags: ["Checksums"] },
            { n: "06", h: "Self-Hosted", p: "Your data stays on your infrastructure.", tags: ["Privacy"] },
          ].map((f) => (
            <div key={f.n} className="I fi">
              <span className="I-l">
                <span className="I-num">{f.n}</span>
                <span className="I-body">
                  <span className="I-h">{f.h}</span>
                  <span className="I-p">{f.p}</span>
                </span>
              </span>
              <span className="I-r">
                {f.tags.map(t => <span key={t} className="I-tag">{t}</span>)}
              </span>
            </div>
          ))}
        </section>

        {/* How it works */}
        <section className="S" id="hw">
          <div className="S-hdr"><span className="S-label">How it works</span><span className="S-n">03</span></div>
          {[
            { n: "01", h: "Create an account", p: "Sign up at z86.dev. Free tier, 1 GB, no credit card.", cmd: "$ open https://z86.dev" },
            { n: "02", h: "Get your keys", p: "Create an access key, point any S3 client to s3.z86.dev.", cmd: "$ aws configure --endpoint s3.z86.dev" },
            { n: "03", h: "Store & retrieve", p: "Upload, list, download. Same API you already know.", cmd: "$ aws s3 cp file.zip s3://bucket/" },
          ].map((s) => (
            <div key={s.n} className="ST fi">
              <span className="ST-num">{s.n}</span>
              <div className="ST-body">
                <div className="ST-h">{s.h}</div>
                <div className="ST-p">{s.p}</div>
                <span className="ST-code">{s.cmd}</span>
              </div>
            </div>
          ))}
        </section>

        {/* Pricing */}
        <section className="S" id="pr">
          <div className="S-hdr"><span className="S-label">Pricing</span><span className="S-n">03</span></div>
          {[
            { tier: "Free", price: "$0", per: "/mo", tags: ["1 GB", "3 buckets", "2 keys", "unlimited egress"], btn: "Get started free", action: onRegister, featured: false },
            { tier: "Pro", price: "$5", per: "/mo", tags: ["100 GB", "50 buckets", "10 keys", "priority support"], btn: "Start with Pro", action: onRegister, featured: true },
            { tier: "Enterprise", price: "Custom", per: "", tags: ["unlimited", "dedicated infra", "SLA", "white-glove"], btn: "Contact us", action: onLogin, featured: false },
          ].map((p) => (
            <div key={p.tier} className={`PR fi${p.featured ? " PR-feat" : ""}`}>
              <div className="PR-top">
                <span className="PR-tier">{p.tier}</span>
                <span className="PR-amt">{p.price}{p.per && <span>{p.per}</span>}</span>
              </div>
              <div className="PR-tags">
                {p.tags.map(t => <span key={t} className="PR-tag">{t}</span>)}
              </div>
              <button className="PR-btn" onClick={p.action}>
                <span>{p.btn}</span>
                <span className="PR-arr">&rarr;</span>
              </button>
            </div>
          ))}
        </section>

        {/* Footer */}
        <footer className="F">
          <div className="F-man">S3-compatible object storage. Fast, simple, and on your terms. No egress fees, no vendor lock-in, no complexity.</div>
          <nav className="F-bars">
            <div className="F-bar F-bl"><a className="F-em" href="mailto:hello@z86.dev">hello@z86.dev</a></div>
            <div className="F-bar F-br">
              <span className="F-cp">&copy; 2026 z86</span>
              <a className="F-lk" href="#">Terms</a>
              <a className="F-lk" href="#">Privacy</a>
              <a className="F-lk" href="#">Docs</a>
            </div>
          </nav>
        </footer>
      </main>
    </div>
  );
}

/* ═══════════════════════════════════════
   SHADER — subtle noise fog, slow drift
   ═══════════════════════════════════════ */
function ShaderBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", { alpha: false, antialias: false });
    if (!gl) return;

    function resize() {
      canvas!.width = canvas!.clientWidth * 2;
      canvas!.height = canvas!.clientHeight * 2;
      gl!.viewport(0, 0, canvas!.width, canvas!.height);
    }
    resize();
    window.addEventListener("resize", resize);

    const vsSrc = `attribute vec2 p;void main(){gl_Position=vec4(p,0,1);}`;
    const fsSrc = `
precision mediump float;
uniform float t;
uniform vec2 r;
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float noise(vec2 p){
  vec2 i=floor(p),f=fract(p);
  f=f*f*(3.0-2.0*f);
  return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),
             mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x),f.y);
}
void main(){
  vec2 uv=gl_FragCoord.xy/r;
  float n=noise(uv*2.5+vec2(t*0.04,t*0.03));
  float n2=noise(uv*4.0+vec2(-t*0.03,t*0.05)+3.0);
  float fog=mix(n,n2,0.5);
  vec3 base=vec3(0.065,0.06,0.055);
  vec3 col=base+fog*0.04;
  float grain=hash(uv*r+t*100.0)*0.025;
  col+=grain;
  gl_FragColor=vec4(col,1.0);
}`;

    function sh(type: number, src: string) {
      const s = gl!.createShader(type)!;
      gl!.shaderSource(s, src);
      gl!.compileShader(s);
      return s;
    }
    const pg = gl.createProgram()!;
    gl.attachShader(pg, sh(gl.VERTEX_SHADER, vsSrc));
    gl.attachShader(pg, sh(gl.FRAGMENT_SHADER, fsSrc));
    gl.linkProgram(pg);
    gl.useProgram(pg);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const pLoc = gl.getAttribLocation(pg, "p");
    gl.enableVertexAttribArray(pLoc);
    gl.vertexAttribPointer(pLoc, 2, gl.FLOAT, false, 0, 0);

    const ut = gl.getUniformLocation(pg, "t");
    const ur = gl.getUniformLocation(pg, "r");

    const loop = (now: number) => {
      gl!.uniform1f(ut, now * 0.001);
      gl!.uniform2f(ur, canvas!.width, canvas!.height);
      gl!.drawArrays(gl!.TRIANGLE_STRIP, 0, 4);
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(rafRef.current);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={canvasRef} className="L-shader" />;
}

/* ═══════════════════════════════════════
   LOGO — clean square mark + wordmark
   ═══════════════════════════════════════ */
function Z86Logo({ size = 32, color = "light" }: { size?: number; color?: "light" | "dark" }) {
  const fg = color === "light" ? "rgba(255,255,255,0.9)" : "#1a1917";
  const accent = "#2dd4bf";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
        <rect x="1" y="1" width="30" height="30" rx="6" stroke={accent} strokeWidth="2" />
        <text x="16" y="22" textAnchor="middle" fontFamily="Georgia, serif" fontSize="18" fontWeight="400" fill={fg}>Z</text>
      </svg>
      <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: "0.03em", color: fg }}>z86</span>
    </div>
  );
}
