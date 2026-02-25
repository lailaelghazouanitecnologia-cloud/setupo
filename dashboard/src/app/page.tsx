"use client";

import { useState, useEffect } from "react";
import { useDashboardStore } from "@/stores/dashboard-store";
import { login } from "@/lib/api/client";
import { DashboardLayout } from "@/components/dashboard/dashboard-layout";

function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const setToken = useDashboardStore((s) => s.setToken);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await login(email, password);
      setToken(res.token);
    } catch (err: any) {
      setError("Invalid email or password");
    }
    setLoading(false);
  };

  return (
    <div style={{
      height: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "var(--background)",
    }}>
      <div style={{
        width: 340,
        padding: 32,
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderRadius: 12,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 24 }}>
          <svg width="20" height="20" viewBox="0 0 100 100" fill="currentColor">
            <path d="M1.225 61.523c-.222-.949.908-1.546 1.597-.857L39.334 97.178c.689.689.092 1.819-.857 1.597C20.052 94.452 5.548 79.949 1.225 61.523zM.002 46.889a1.073 1.073 0 01.29.761L52.35 99.709c.2.2.477.307.76.289a43.36 43.36 0 006.963-.926c.764-.157 1.03-1.096.478-1.648L2.576 39.449c-.552-.552-1.491-.287-1.648.478a43.36 43.36 0 00-.926 6.962zM4.211 29.705a.993.993 0 01.208 1.1l64.776 64.776c.29.29.726.374 1.1.208a43.1 43.1 0 005.186-2.684c.552-.328.637-1.087.183-1.541L8.436 24.337c-.454-.454-1.213-.369-1.541.183a43.1 43.1 0 00-2.684 5.186zM12.659 18.074c-.37-.37-.393-.964-.044-1.354A49.93 49.93 0 0149.952 0C77.593 0 100 22.407 100 50.048a49.93 49.93 0 01-16.72 37.338c-.39.349-.984.326-1.354-.044L12.659 18.074z" />
          </svg>
          <span style={{ fontSize: 18, fontWeight: 600 }}>setupo</span>
        </div>
        <p style={{ fontSize: "var(--font-sm)", color: "var(--muted-foreground)", marginBottom: 20 }}>
          Sign in to manage your infrastructure
        </p>
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)", display: "block", marginBottom: 4 }}>
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{
                width: "100%",
                padding: "7px 10px",
                background: "var(--input)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                fontSize: "var(--font-md)",
                color: "var(--foreground)",
                outline: "none",
                boxSizing: "border-box",
              }}
              placeholder="admin@example.com"
              required
            />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)", display: "block", marginBottom: 4 }}>
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{
                width: "100%",
                padding: "7px 10px",
                background: "var(--input)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                fontSize: "var(--font-md)",
                color: "var(--foreground)",
                outline: "none",
                boxSizing: "border-box",
              }}
              placeholder="Password"
              required
            />
          </div>
          {error && (
            <p style={{ fontSize: "var(--font-xs)", color: "var(--color-red)", marginBottom: 10 }}>{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%",
              padding: "8px",
              background: "var(--primary)",
              color: "var(--primary-foreground)",
              border: "none",
              borderRadius: 6,
              fontSize: "var(--font-sm)",
              fontWeight: 500,
              cursor: loading ? "wait" : "pointer",
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default function Home() {
  const token = useDashboardStore((s) => s.token);
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  if (!mounted) return null;

  if (!token) return <LoginPage />;
  return <DashboardLayout />;
}
