"use client";

import { useState, useEffect, useCallback } from "react";
import {
  User, Globe, Lock, Loader2, Check, AlertCircle, Search,
} from "lucide-react";
import {
  getMe, updateProfile, changePassword,
  getSubdomain, checkSubdomain, claimSubdomain,
} from "@/lib/api/client";
import { useDashboardStore } from "@/stores/dashboard-store";

function ProfileSection() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [originalName, setOriginalName] = useState("");
  const [originalEmail, setOriginalEmail] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const setUser = useDashboardStore((s) => s.setUser);

  const load = useCallback(async () => {
    try {
      const me = await getMe();
      setName(me.name);
      setEmail(me.email);
      setOriginalName(me.name);
      setOriginalEmail(me.email);
    } catch (err: any) {
      setError(err.message || "Failed to load profile");
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSave = async () => {
    setSaving(true);
    setError("");
    setMsg("");
    const updates: { name?: string; email?: string } = {};
    if (name !== originalName) updates.name = name;
    if (email !== originalEmail) updates.email = email;
    if (!Object.keys(updates).length) {
      setSaving(false);
      return;
    }
    try {
      await updateProfile(updates);
      setOriginalName(name);
      setOriginalEmail(email);
      if (updates.email) setUser(email, "user");
      setMsg("Profile updated");
    } catch (err: any) {
      setError(err.message || "Update failed");
    }
    setSaving(false);
  };

  const dirty = name !== originalName || email !== originalEmail;

  if (loading) {
    return (
      <div className="panel-empty">
        <Loader2 className="h-5 w-5 animate-spin" style={{ color: "var(--muted-foreground)" }} />
      </div>
    );
  }

  return (
    <div className="settings-section">
      <div className="settings-section-header">
        <User className="h-4 w-4" />
        <span>Profile</span>
      </div>
      <div className="settings-fields">
        <div className="settings-field">
          <label className="settings-label">Display name</label>
          <input
            className="settings-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
          />
        </div>
        <div className="settings-field">
          <label className="settings-label">Email</label>
          <input
            className="settings-input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </div>
      </div>
      {error && <div className="settings-error">{error}</div>}
      {msg && <div className="settings-success">{msg}</div>}
      <button className="settings-save" onClick={handleSave} disabled={!dirty || saving}>
        {saving ? "Saving..." : "Save changes"}
      </button>
    </div>
  );
}

function SubdomainSection() {
  const [current, setCurrent] = useState<string | null>(null);
  const [currentDomain, setCurrentDomain] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [checking, setChecking] = useState(false);
  const [available, setAvailable] = useState<boolean | null>(null);
  const [previewDomain, setPreviewDomain] = useState<string | null>(null);
  const [claiming, setClaiming] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await getSubdomain();
      setCurrent(res.subdomain);
      setCurrentDomain(res.domain);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCheck = async () => {
    if (!input.trim()) return;
    setChecking(true);
    setError("");
    setAvailable(null);
    setPreviewDomain(null);
    try {
      const res = await checkSubdomain(input.trim().toLowerCase());
      setAvailable(res.available);
      setPreviewDomain(res.domain);
    } catch (err: any) {
      setError(err.message || "Check failed");
    }
    setChecking(false);
  };

  const handleClaim = async () => {
    setClaiming(true);
    setError("");
    setMsg("");
    try {
      const res = await claimSubdomain(input.trim().toLowerCase());
      setCurrent(res.subdomain);
      setCurrentDomain(res.domain);
      setMsg(`Subdomain claimed: ${res.domain}`);
      setInput("");
      setAvailable(null);
    } catch (err: any) {
      setError(err.message || "Claim failed");
    }
    setClaiming(false);
  };

  if (loading) {
    return (
      <div className="panel-empty">
        <Loader2 className="h-5 w-5 animate-spin" style={{ color: "var(--muted-foreground)" }} />
      </div>
    );
  }

  return (
    <div className="settings-section">
      <div className="settings-section-header">
        <Globe className="h-4 w-4" />
        <span>Free Subdomain</span>
      </div>

      {current ? (
        <div className="settings-subdomain-active">
          <div className="settings-subdomain-badge">
            <Check className="h-3.5 w-3.5" />
            <span>Active</span>
          </div>
          <code className="settings-subdomain-domain">{currentDomain}</code>
        </div>
      ) : (
        <>
          <p className="settings-hint">
            Claim a free <code>yourname.nso.dev</code> subdomain. One per account, choose wisely.
          </p>
          <div className="settings-subdomain-form">
            <div className="settings-subdomain-input-wrap">
              <input
                className="settings-input"
                value={input}
                onChange={(e) => {
                  setInput(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""));
                  setAvailable(null);
                  setPreviewDomain(null);
                }}
                placeholder="yourname"
                maxLength={32}
              />
              <span className="settings-subdomain-suffix">.nso.dev</span>
            </div>
            <button
              className="settings-check-btn"
              onClick={handleCheck}
              disabled={!input.trim() || input.trim().length < 3 || checking}
            >
              {checking ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
              <span>{checking ? "Checking..." : "Check"}</span>
            </button>
          </div>

          {available === true && (
            <div className="settings-subdomain-result available">
              <Check className="h-3.5 w-3.5" />
              <span><strong>{previewDomain}</strong> is available</span>
              <button className="settings-claim-btn" onClick={handleClaim} disabled={claiming}>
                {claiming ? "Claiming..." : "Claim"}
              </button>
            </div>
          )}
          {available === false && (
            <div className="settings-subdomain-result taken">
              <AlertCircle className="h-3.5 w-3.5" />
              <span><strong>{input}.nso.dev</strong> is taken</span>
            </div>
          )}
        </>
      )}

      {error && <div className="settings-error">{error}</div>}
      {msg && <div className="settings-success">{msg}</div>}
    </div>
  );
}

function PasswordSection() {
  const [current, setCurrent] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const handleChange = async () => {
    if (newPw !== confirm) {
      setError("Passwords don't match");
      return;
    }
    if (newPw.length < 6) {
      setError("Password must be at least 6 characters");
      return;
    }
    setSaving(true);
    setError("");
    setMsg("");
    try {
      await changePassword(current, newPw);
      setMsg("Password changed");
      setCurrent("");
      setNewPw("");
      setConfirm("");
    } catch (err: any) {
      setError(err.message || "Password change failed");
    }
    setSaving(false);
  };

  const valid = current && newPw && confirm && newPw === confirm && newPw.length >= 6;

  return (
    <div className="settings-section">
      <div className="settings-section-header">
        <Lock className="h-4 w-4" />
        <span>Change Password</span>
      </div>
      <div className="settings-fields">
        <div className="settings-field">
          <label className="settings-label">Current password</label>
          <input
            className="settings-input"
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            placeholder="Current password"
            autoComplete="current-password"
          />
        </div>
        <div className="settings-field">
          <label className="settings-label">New password</label>
          <input
            className="settings-input"
            type="password"
            value={newPw}
            onChange={(e) => setNewPw(e.target.value)}
            placeholder="Min. 6 characters"
            autoComplete="new-password"
          />
        </div>
        <div className="settings-field">
          <label className="settings-label">Confirm new password</label>
          <input
            className="settings-input"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Confirm password"
            autoComplete="new-password"
          />
        </div>
      </div>
      {error && <div className="settings-error">{error}</div>}
      {msg && <div className="settings-success">{msg}</div>}
      <button className="settings-save" onClick={handleChange} disabled={!valid || saving}>
        {saving ? "Changing..." : "Change password"}
      </button>
    </div>
  );
}

export function SettingsPanel() {
  return (
    <div className="settings-panel">
      <ProfileSection />
      <SubdomainSection />
      <PasswordSection />
    </div>
  );
}
