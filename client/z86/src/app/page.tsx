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
    <div className="landing-page">
      <nav className="landing-nav">
        <div className="landing-nav-inner">
          <div className="landing-nav-left">
            <Z86Logo size={18} />
            <span className="landing-nav-brand">z86</span>
          </div>
          <div className="landing-nav-right">
            <div className="landing-nav-links">
              <button className="landing-nav-link" onClick={() => document.getElementById("features")?.scrollIntoView({ behavior: "smooth" })}>Features</button>
              <span className="landing-slash">/</span>
              <button className="landing-nav-link" onClick={() => document.getElementById("how")?.scrollIntoView({ behavior: "smooth" })}>How it works</button>
              <span className="landing-slash">/</span>
              <button className="landing-nav-link" onClick={() => document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" })}>Pricing</button>
            </div>
            <span className="landing-slash" style={{ margin: "0 16px" }} />
            <button className="landing-nav-link" onClick={onLogin}>Sign in</button>
            <span className="landing-slash" />
            <button className="landing-btn landing-btn-primary" onClick={onRegister} style={{ marginLeft: 2 }}>Get started</button>
          </div>
        </div>
      </nav>

      <main>
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
                <button className="landing-btn landing-btn-primary" onClick={onRegister}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                  Start storing
                </button>
                <button className="landing-btn landing-btn-secondary" onClick={onLogin}>Sign in</button>
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
                <div><span className="t-prompt">$</span> <span className="t-cmd">aws s3 ls</span> <span className="t-flag">s3://my-bucket/</span> <span className="t-flag">--endpoint-url</span> <span className="t-arg">https://s3.z86.dev</span></div>
                <div><span className="t-out">2026-03-04  backups/</span></div>
                <div><span className="t-out">2026-03-04  assets/</span></div>
                <div><span className="t-out">2026-03-04  deploys/</span></div>
                <div style={{ height: 6 }} />
                <div><span className="t-prompt">$</span> <span className="t-cmd">curl</span> <span className="t-flag">-I</span> <span className="t-arg">https://s3.z86.dev/my-bucket/assets/logo.png</span></div>
                <div><span className="t-out">HTTP/2 200</span> <span className="t-ok">OK</span></div>
                <div><span className="t-out">content-length: 24576</span></div>
                <div><span className="t-out">etag: &quot;a1b2c3d4e5f6...&quot;</span></div>
                <div><span className="t-prompt">$</span> <span className="t-cursor" /></div>
              </div>
            </div>
          </div>
        </section>

        <section className="landing-capabilities" id="features">
          <div className="landing-container">
            <div className="landing-cap-layout">
              <div className="landing-cap-intro">
                <div className="landing-s-label">Features</div>
                <h2 className="landing-s-title">Everything you need from object storage</h2>
                <p>S3-compatible object storage with a built-in dashboard. Create buckets, manage keys, upload objects, and monitor usage.</p>
              </div>
              <div className="landing-cap-list">
                <div className="landing-cap-item">
                  <span className="landing-cap-num">01</span>
                  <div>
                    <h3 className="landing-cap-h">S3-Compatible API</h3>
                    <p className="landing-cap-p">PUT, GET, DELETE, HEAD, LIST &mdash; all the standard S3 operations. Use aws-cli, boto3, minio, or any S3 SDK.</p>
                  </div>
                  <div className="landing-cap-tags"><span className="landing-tag">AWS4-HMAC</span><span className="landing-tag">REST API</span></div>
                </div>
                <div className="landing-cap-item">
                  <span className="landing-cap-num">02</span>
                  <div>
                    <h3 className="landing-cap-h">Zero Egress Fees</h3>
                    <p className="landing-cap-p">Download your data as much as you want. No bandwidth charges, no surprise bills.</p>
                  </div>
                  <div className="landing-cap-tags"><span className="landing-tag">free egress</span><span className="landing-tag">predictable</span></div>
                </div>
                <div className="landing-cap-item">
                  <span className="landing-cap-num">03</span>
                  <div>
                    <h3 className="landing-cap-h">Dashboard</h3>
                    <p className="landing-cap-p">Browse buckets, upload files, manage access keys, and track usage &mdash; all from the web dashboard.</p>
                  </div>
                  <div className="landing-cap-tags"><span className="landing-tag">web UI</span><span className="landing-tag">real-time</span></div>
                </div>
                <div className="landing-cap-item">
                  <span className="landing-cap-num">04</span>
                  <div>
                    <h3 className="landing-cap-h">Access Key Management</h3>
                    <p className="landing-cap-p">Create, rotate, and revoke HMAC keys. Scope keys to specific buckets for fine-grained access control.</p>
                  </div>
                  <div className="landing-cap-tags"><span className="landing-tag">HMAC keys</span><span className="landing-tag">bucket scoping</span></div>
                </div>
                <div className="landing-cap-item">
                  <span className="landing-cap-num">05</span>
                  <div>
                    <h3 className="landing-cap-h">SHA-256 Integrity</h3>
                    <p className="landing-cap-p">Every object is checksummed on upload. Verify integrity at any time. No silent data corruption.</p>
                  </div>
                  <div className="landing-cap-tags"><span className="landing-tag">checksums</span><span className="landing-tag">integrity</span></div>
                </div>
                <div className="landing-cap-item">
                  <span className="landing-cap-num">06</span>
                  <div>
                    <h3 className="landing-cap-h">Self-Hosted</h3>
                    <p className="landing-cap-p">Your data stays on your infrastructure. No third-party dependencies, no vendor lock-in.</p>
                  </div>
                  <div className="landing-cap-tags"><span className="landing-tag">self-hosted</span><span className="landing-tag">privacy</span></div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="landing-how" id="how">
          <div className="landing-container">
            <div className="landing-s-label">How it works</div>
            <h2 className="landing-s-title">Three steps to start storing</h2>
            <div className="landing-how-grid">
              <div className="landing-how-card">
                <div className="landing-how-num">01</div>
                <h3>Create an account</h3>
                <p>Sign up at z86.dev. Free tier includes 1 GB of storage with no credit card required.</p>
                <div className="landing-how-code"><span className="t-prompt">$</span> <span className="t-cmd">open</span> <span className="t-arg">https://z86.dev</span></div>
              </div>
              <div className="landing-how-card">
                <div className="landing-how-num">02</div>
                <h3>Get your keys</h3>
                <p>Create an access key from the dashboard. Point any S3 client to s3.z86.dev.</p>
                <div className="landing-how-code"><span className="t-prompt">$</span> <span className="t-cmd">aws configure</span> <span className="t-flag">--endpoint</span> <span className="t-arg">s3.z86.dev</span></div>
              </div>
              <div className="landing-how-card">
                <div className="landing-how-num">03</div>
                <h3>Store &amp; retrieve</h3>
                <p>Upload objects, list buckets, download files. Same S3 API you already know.</p>
                <div className="landing-how-code"><span className="t-prompt">$</span> <span className="t-cmd">aws s3 cp</span> <span className="t-arg">file.zip</span> <span className="t-flag">s3://bucket/</span></div>
              </div>
            </div>
          </div>
        </section>

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
                  <li>3 buckets</li>
                  <li>2 access keys</li>
                  <li>Unlimited egress</li>
                  <li>S3-compatible API</li>
                </ul>
                <button className="landing-btn landing-btn-secondary" onClick={onRegister} style={{ width: "100%", justifyContent: "center" }}>Get started free</button>
              </div>
              <div className="landing-pricing-card landing-pricing-featured">
                <div className="landing-pricing-tier">Pro</div>
                <div className="landing-pricing-price">$5<span>/mo</span></div>
                <ul className="landing-pricing-features">
                  <li>100 GB storage</li>
                  <li>50 buckets</li>
                  <li>10 access keys</li>
                  <li>Unlimited egress</li>
                  <li>Priority support</li>
                </ul>
                <button className="landing-btn landing-btn-primary" onClick={onRegister} style={{ width: "100%", justifyContent: "center" }}>Start with Pro</button>
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
                <button className="landing-btn landing-btn-secondary" onClick={onLogin} style={{ width: "100%", justifyContent: "center" }}>Contact us</button>
              </div>
            </div>
          </div>
        </section>

        <section className="landing-cta">
          <div className="landing-container">
            <div className="landing-cta-card">
              <div className="landing-cta-inner">
                <div>
                  <h2>Start storing in minutes</h2>
                  <p>Create a free account and get 1 GB of S3-compatible object storage. No credit card required.</p>
                </div>
                <div className="landing-cta-actions">
                  <button className="landing-btn landing-btn-primary" onClick={onRegister}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                    Create free account
                  </button>
                  <button className="landing-btn landing-btn-secondary" onClick={onLogin}>Sign in</button>
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
            </div>
            <span className="landing-footer-copy">&copy; 2026 z86</span>
          </div>
        </div>
      </footer>
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
