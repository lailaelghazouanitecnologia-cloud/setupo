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
      <div className="auth-card">
        <div className="auth-header">
          <Z86Logo />
          <h1>Sign in to z86</h1>
          <p>Object storage dashboard</p>
        </div>
        <form onSubmit={submit} className="auth-form">
          {error && <div className="auth-error">{error}</div>}
          <label>
            <span>Email</span>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} required autoFocus />
          </label>
          <label>
            <span>Password</span>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} required />
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
      <div className="auth-card">
        <div className="auth-header">
          <Z86Logo />
          <h1>Create your z86 account</h1>
          <p>Start storing objects in minutes</p>
        </div>
        <form onSubmit={submit} className="auth-form">
          {error && <div className="auth-error">{error}</div>}
          <label>
            <span>Name</span>
            <input type="text" value={name} onChange={e => setName(e.target.value)} autoFocus />
          </label>
          <label>
            <span>Email</span>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} required />
          </label>
          <label>
            <span>Password</span>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} placeholder="At least 8 characters" />
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
  );
}

function Z86Logo() {
  return (
    <svg width="32" height="32" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="8" y="8" width="84" height="84" rx="16" stroke="currentColor" strokeWidth="6" />
      <rect x="24" y="28" width="52" height="10" rx="5" fill="currentColor" opacity={0.3} />
      <rect x="24" y="45" width="52" height="10" rx="5" fill="currentColor" opacity={0.6} />
      <rect x="24" y="62" width="52" height="10" rx="5" fill="currentColor" />
    </svg>
  );
}
