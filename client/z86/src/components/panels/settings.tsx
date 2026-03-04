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
    <div className="settings">
      <div className="settings-header">
        <h1>Settings</h1>
      </div>

      <div className="settings-body">
        {/* ── Profile ── */}
        <section className="settings-section">
          <h2>Profile</h2>
          <form onSubmit={saveProfile} className="settings-form">
            <div className="settings-field">
              <label htmlFor="s-name">Name</label>
              <input id="s-name" type="text" value={name} onChange={e => setName(e.target.value)} placeholder="Your name" />
            </div>
            <div className="settings-field">
              <label htmlFor="s-email">Email</label>
              <input id="s-email" type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="you@example.com" />
            </div>
            {msg && <p className="settings-msg">{msg}</p>}
            <div>
              <button type="submit" className="settings-btn" disabled={saving}>{saving ? "Saving..." : "Save"}</button>
            </div>
          </form>
        </section>

        {/* ── Change Password ── */}
        <section className="settings-section">
          <h2>Change Password</h2>
          <form onSubmit={changePassword} className="settings-form">
            <div className="settings-field">
              <label htmlFor="s-curpwd">Current password</label>
              <input id="s-curpwd" type="password" value={currentPwd} onChange={e => setCurrentPwd(e.target.value)} required />
            </div>
            <div className="settings-field">
              <label htmlFor="s-newpwd">New password</label>
              <input id="s-newpwd" type="password" value={newPwd} onChange={e => setNewPwd(e.target.value)} required minLength={8} />
            </div>
            {pwdMsg && <p className="settings-msg">{pwdMsg}</p>}
            <div>
              <button type="submit" className="settings-btn" disabled={pwdSaving}>{pwdSaving ? "Changing..." : "Change Password"}</button>
            </div>
          </form>
        </section>

        {/* ── S3 Endpoint ── */}
        <section className="settings-section">
          <h2>S3 Endpoint</h2>
          <div className="settings-form">
            <div className="settings-row">
              <span>Endpoint URL</span>
              <code>https://s3.z86.dev</code>
            </div>
            <div className="settings-row">
              <span>Region</span>
              <code>auto</code>
            </div>
            <div className="settings-row">
              <span>Path Style</span>
              <code>true</code>
            </div>
          </div>
        </section>

        {/* ── Plan ── */}
        <section className="settings-section settings-section-last">
          <h2>Plan</h2>
          <div className="settings-form">
            <div className="settings-plan">
              <span className="settings-plan-name">{user?.plan || "free"}</span>
              <span className="settings-plan-desc">
                {user?.plan === "pro" ? "100 GB storage, unlimited buckets" :
                 user?.plan === "enterprise" ? "Unlimited storage, dedicated infra" :
                 "1 GB storage, 3 buckets, 2 keys"}
              </span>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
