"use client";
import { useState } from "react";
import { authApi } from "@/lib/api";
import { useZ86Store } from "@/stores/z86-store";

export function LoginForm() {
  const { setToken, setUser, setView } = useZ86Store();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { token, user } = await authApi.login(email, password);
      setToken(token);
      setUser(user);
      setView("dashboard");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <AuthBranding />
      <div className="auth-right">
        <div className="auth-card">
          <div className="auth-header">
            <h1>Welcome back</h1>
            <p>Sign in to your z86 dashboard</p>
          </div>
          <form onSubmit={submit} className="auth-form">
            {error && <div className="auth-error">{error}</div>}
            <label>
              <span>Email</span>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" required autoFocus />
            </label>
            <label>
              <span>Password</span>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Your password" required />
            </label>
            <button type="submit" className="auth-submit" disabled={loading}>
              {loading ? "Signing in..." : "Sign in"}
            </button>
          </form>
          <div className="auth-footer">
            Don&apos;t have an account?{" "}
            <button onClick={() => setView("register")}>Create one</button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function RegisterForm() {
  const { setToken, setUser, setView } = useZ86Store();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { token, user } = await authApi.register(email, password, name);
      setToken(token);
      setUser(user);
      setView("dashboard");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <AuthBranding />
      <div className="auth-right">
        <div className="auth-card">
          <div className="auth-header">
            <h1>Create your account</h1>
            <p>Start storing objects in minutes</p>
          </div>
          <form onSubmit={submit} className="auth-form">
            {error && <div className="auth-error">{error}</div>}
            <label>
              <span>Name</span>
              <input type="text" value={name} onChange={e => setName(e.target.value)} placeholder="Your name" autoFocus />
            </label>
            <label>
              <span>Email</span>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" required />
            </label>
            <label>
              <span>Password</span>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="At least 8 characters" required minLength={8} />
            </label>
            <button type="submit" className="auth-submit" disabled={loading}>
              {loading ? "Creating account..." : "Create account"}
            </button>
          </form>
          <div className="auth-footer">
            Already have an account?{" "}
            <button onClick={() => setView("login")}>Sign in</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function AuthBranding() {
  return (
    <aside className="auth-left">
      <div className="auth-left-noise" />
      <div className="auth-left-brand">
        <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
          <rect x="1" y="1" width="30" height="30" rx="6" stroke="#2dd4bf" strokeWidth="2" />
          <text x="16" y="22" textAnchor="middle" fontFamily="Georgia, serif" fontSize="18" fontWeight="400" fill="rgba(255,255,255,0.9)">Z</text>
        </svg>
        <span>z86</span>
      </div>
      <div className="auth-left-center">
        <h2 className="auth-left-heading">Object storage<br />on your terms.</h2>
        <p className="auth-left-sub">S3-compatible. No egress fees. No vendor lock-in. Your data stays on your infrastructure.</p>
        <div className="auth-left-features">
          <div className="auth-left-feat"><span className="auth-left-feat-dot" />S3-compatible API</div>
          <div className="auth-left-feat"><span className="auth-left-feat-dot" />Zero egress fees</div>
          <div className="auth-left-feat"><span className="auth-left-feat-dot" />Dashboard &amp; access keys</div>
          <div className="auth-left-feat"><span className="auth-left-feat-dot" />Free tier &mdash; 1 GB</div>
        </div>
      </div>
      <div className="auth-left-bottom">z86.dev</div>
    </aside>
  );
}
