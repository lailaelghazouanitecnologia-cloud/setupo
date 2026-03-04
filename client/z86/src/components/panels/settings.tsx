"use client";
import { useState } from "react";
import { authApi } from "@/lib/api";
import { useZ86Store } from "@/stores/z86-store";

export function SettingsPanel() {
  const { user, setUser } = useZ86Store();
  const [name, setName] = useState(user?.name || "");
  const [email, setEmail] = useState(user?.email || "");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [currentPwd, setCurrentPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [pwdMsg, setPwdMsg] = useState("");
  const [pwdSaving, setPwdSaving] = useState(false);

  const saveProfile = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true); setMsg("");
    try {
      const updated = await authApi.updateProfile({ name, email });
      setUser({ ...user!, ...updated }); setMsg("Profile updated");
    } catch (err: any) { setMsg(err.message); }
    finally { setSaving(false); }
  };

  const changePassword = async (e: React.FormEvent) => {
    e.preventDefault(); setPwdSaving(true); setPwdMsg("");
    try {
      await authApi.changePassword(currentPwd, newPwd);
      setPwdMsg("Password changed"); setCurrentPwd(""); setNewPwd("");
    } catch (err: any) { setPwdMsg(err.message); }
    finally { setPwdSaving(false); }
  };

  return (
    <div className="panel" style={{ maxWidth: 640 }}>
      {/* ── Header ── */}
      <div className="panel-line panel-line-header">
        <h1 className="panel-title">Settings</h1>
      </div>

      {/* ── Profile ── */}
      <div className="stg-section">
        <div className="stg-section-hdr">
          <span className="stg-section-label">Profile</span>
          <span className="stg-section-desc">Update your account information</span>
        </div>
        <form onSubmit={saveProfile} className="stg-form">
          <label className="stg-field">
            <span className="stg-field-label">Name</span>
            <input type="text" value={name} onChange={e => setName(e.target.value)} placeholder="Your name" />
          </label>
          <label className="stg-field">
            <span className="stg-field-label">Email</span>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="you@example.com" />
          </label>
          {msg && <p className={msg.includes("updated") ? "stg-msg-ok" : "stg-msg-err"}>{msg}</p>}
          <div className="stg-actions">
            <button type="submit" className="btn-primary" disabled={saving}>{saving ? "Saving..." : "Save changes"}</button>
          </div>
        </form>
      </div>

      {/* ── Change Password ── */}
      <div className="stg-section">
        <div className="stg-section-hdr">
          <span className="stg-section-label">Password</span>
          <span className="stg-section-desc">Update your account password</span>
        </div>
        <form onSubmit={changePassword} className="stg-form">
          <label className="stg-field">
            <span className="stg-field-label">Current password</span>
            <input type="password" value={currentPwd} onChange={e => setCurrentPwd(e.target.value)} required />
          </label>
          <label className="stg-field">
            <span className="stg-field-label">New password</span>
            <input type="password" value={newPwd} onChange={e => setNewPwd(e.target.value)} required minLength={8} />
          </label>
          {pwdMsg && <p className={pwdMsg.includes("changed") ? "stg-msg-ok" : "stg-msg-err"}>{pwdMsg}</p>}
          <div className="stg-actions">
            <button type="submit" className="btn-primary" disabled={pwdSaving}>{pwdSaving ? "Changing..." : "Change password"}</button>
          </div>
        </form>
      </div>

      {/* ── S3 Endpoint ── */}
      <div className="stg-section">
        <div className="stg-section-hdr">
          <span className="stg-section-label">S3 Endpoint</span>
          <span className="stg-section-desc">Connection details for your S3 client</span>
        </div>
        <div className="stg-kv-list">
          <div className="stg-kv"><span className="stg-kv-key">Endpoint URL</span><code className="stg-kv-val">https://s3.z86.dev</code></div>
          <div className="stg-kv"><span className="stg-kv-key">Region</span><code className="stg-kv-val">auto</code></div>
          <div className="stg-kv"><span className="stg-kv-key">Path Style</span><code className="stg-kv-val">true</code></div>
        </div>
      </div>

      {/* ── Plan ── */}
      <div className="stg-section stg-section-last">
        <div className="stg-section-hdr">
          <span className="stg-section-label">Plan</span>
          <span className="stg-section-desc">Your current subscription</span>
        </div>
        <div className="stg-plan">
          <div className="stg-plan-name">{user?.plan || "free"}</div>
          <div className="stg-plan-desc">
            {user?.plan === "pro" ? "100 GB storage, 50 buckets, 10 access keys, priority support" :
             user?.plan === "enterprise" ? "Unlimited storage, dedicated infrastructure, SLA guarantee" :
             "1 GB storage, 3 buckets, 2 access keys, unlimited egress"}
          </div>
          <div className="stg-plan-tags">
            {(user?.plan === "pro" ? ["100 GB", "50 buckets", "10 keys"] :
              user?.plan === "enterprise" ? ["unlimited", "dedicated", "SLA"] :
              ["1 GB", "3 buckets", "2 keys"]).map(t => (
              <span key={t} className="stg-plan-tag">{t}</span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
