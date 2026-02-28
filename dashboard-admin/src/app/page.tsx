"use client";

import { useState, useEffect } from "react";
import { useAdminStore } from "@/stores/admin-store";
import { adminLogin } from "@/lib/api/client";
import { AdminDashboard } from "@/components/admin-dashboard";

function SonfaztLogo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" fill="currentColor">
      <path d="M1.225 61.523c-.222-.949.908-1.546 1.597-.857L39.334 97.178c.689.689.092 1.819-.857 1.597C20.052 94.452 5.548 79.949 1.225 61.523zM.002 46.889a1.073 1.073 0 01.29.761L52.35 99.709c.2.2.477.307.76.289a43.36 43.36 0 006.963-.926c.764-.157 1.03-1.096.478-1.648L2.576 39.449c-.552-.552-1.491-.287-1.648.478a43.36 43.36 0 00-.926 6.962zM4.211 29.705a.993.993 0 01.208 1.1l64.776 64.776c.29.29.726.374 1.1.208a43.1 43.1 0 005.186-2.684c.552-.328.637-1.087.183-1.541L8.436 24.337c-.454-.454-1.213-.369-1.541.183a43.1 43.1 0 00-2.684 5.186zM12.659 18.074c-.37-.37-.393-.964-.044-1.354A49.93 49.93 0 0149.952 0C77.593 0 100 22.407 100 50.048a49.93 49.93 0 01-16.72 37.338c-.39.349-.984.326-1.354-.044L12.659 18.074z" />
    </svg>
  );
}

function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const setToken = useAdminStore((s) => s.setToken);
  const setUser = useAdminStore((s) => s.setUser);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await adminLogin(email, password);
      setUser(res.email);
      setToken(res.token);
    } catch (err: any) {
      if (err.message?.includes("403")) {
        setError("Admin access required — this panel is restricted to administrators");
      } else if (err.message?.includes("401")) {
        setError("Invalid email or password");
      } else {
        setError(err.message || "Connection error");
      }
    }
    setLoading(false);
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-header">
          <SonfaztLogo />
          <span className="login-brand">Sonfazt</span>
        </div>
        <p className="login-subtitle">Admin panel — restricted access</p>
        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-field">
            <label className="login-label">Email</label>
            <input
              className="login-input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@setupo.dev"
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
            {loading ? "Authenticating..." : "Sign in"}
          </button>
        </form>
        <div className="login-footer">
          <span style={{ fontSize: 11, color: "var(--muted-foreground)" }}>
            sonfazt.nso.dev — authorized personnel only
          </span>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  const token = useAdminStore((s) => s.token);
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  if (!mounted) return null;

  if (token) return <AdminDashboard />;

  return <LoginPage />;
}
