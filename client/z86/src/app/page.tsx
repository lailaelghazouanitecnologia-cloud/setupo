"use client";

const NSO_URL = "https://nso.dev";

const Z86Logo = ({ size = 28 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="8" y="8" width="84" height="84" rx="16" stroke="currentColor" strokeWidth="6" />
    <rect x="24" y="28" width="52" height="10" rx="5" fill="currentColor" opacity="0.3" />
    <rect x="24" y="45" width="52" height="10" rx="5" fill="currentColor" opacity="0.6" />
    <rect x="24" y="62" width="52" height="10" rx="5" fill="currentColor" />
  </svg>
);

export default function Home() {
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
            <a className="landing-nav-link" href={NSO_URL}>
              Sign in
            </a>
            <span className="landing-slash" />
            <a className="landing-btn landing-btn-primary" href={NSO_URL} style={{ marginLeft: 2 }}>
              Get started
            </a>
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
                <a className="landing-btn landing-btn-primary" href={NSO_URL}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                  Start storing
                </a>
                <a className="landing-btn landing-btn-secondary" href={NSO_URL}>
                  Sign in via NSO
                </a>
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

        {/* ── Features ── */}
        <section className="landing-capabilities" id="features">
          <div className="landing-container">
            <div className="landing-cap-layout">
              <div className="landing-cap-intro">
                <div className="landing-s-label">Features</div>
                <h2 className="landing-s-title">Everything you need from object storage</h2>
                <p>z86 is a self-hosted, S3-compatible object storage service. Managed as a project within the NSO platform.</p>
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
                    <p className="landing-cap-p">Create, rotate, and revoke access keys from the NSO dashboard. Scope keys to specific buckets for fine-grained access control.</p>
                  </div>
                  <div className="landing-cap-tags">
                    <span className="landing-tag">HMAC keys</span>
                    <span className="landing-tag">bucket scoping</span>
                  </div>
                </div>
                <div className="landing-cap-item">
                  <span className="landing-cap-num">04</span>
                  <div>
                    <h3 className="landing-cap-h">Managed via NSO</h3>
                    <p className="landing-cap-p">z86 is an NSO project. Browse buckets, manage objects, monitor usage, and configure storage &mdash; all from the NSO dashboard.</p>
                  </div>
                  <div className="landing-cap-tags">
                    <span className="landing-tag">NSO dashboard</span>
                    <span className="landing-tag">admin panel</span>
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
                    <h3 className="landing-cap-h">.zar Integration</h3>
                    <p className="landing-cap-p">NSO&apos;s .zar package system stores deploy artifacts directly on z86. Pack, push, deploy &mdash; all backed by z86 storage.</p>
                  </div>
                  <div className="landing-cap-tags">
                    <span className="landing-tag">.zar</span>
                    <span className="landing-tag">deploy</span>
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
                <h3>Sign in to NSO</h3>
                <p>Log in to your NSO account at nso.dev. z86 storage is provisioned automatically for your project.</p>
                <div className="landing-how-code">
                  <span className="t-prompt">$</span> <span className="t-cmd">nso login</span>
                </div>
              </div>
              <div className="landing-how-card">
                <div className="landing-how-num">02</div>
                <h3>Configure</h3>
                <p>Point any S3 client to s3.z86.dev. Use your access key and secret key from the NSO dashboard. No region selection, no complex IAM.</p>
                <div className="landing-how-code">
                  <span className="t-prompt">$</span> <span className="t-cmd">aws configure</span> <span className="t-flag">--endpoint</span> <span className="t-arg">s3.z86.dev</span>
                </div>
              </div>
              <div className="landing-how-card">
                <div className="landing-how-num">03</div>
                <h3>Store &amp; retrieve</h3>
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
                  <li>NSO dashboard</li>
                </ul>
                <a className="landing-btn landing-btn-secondary" href={NSO_URL} style={{ width: "100%", justifyContent: "center" }}>
                  Get started free
                </a>
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
                <a className="landing-btn landing-btn-primary" href={NSO_URL} style={{ width: "100%", justifyContent: "center" }}>
                  Start with Pro
                </a>
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
                <a className="landing-btn landing-btn-secondary" href={NSO_URL} style={{ width: "100%", justifyContent: "center" }}>
                  Contact us
                </a>
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
                  <p>Sign in to NSO and get z86 storage provisioned for your project. No credit card required.</p>
                </div>
                <div className="landing-cta-actions">
                  <a className="landing-btn landing-btn-primary" href={NSO_URL}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                    Go to NSO
                  </a>
                  <a className="landing-btn landing-btn-secondary" href="https://docs.nso.dev/z86" target="_blank" rel="noopener noreferrer">
                    Documentation
                  </a>
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
              <a href={NSO_URL} target="_blank" rel="noopener noreferrer">NSO Platform</a>
            </div>
            <span className="landing-footer-copy">&copy; 2026 z86 &mdash; an NSO project</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
