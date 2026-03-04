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
    <div className="panel">
      <div className="panel-line panel-line-header">
        <span className="panel-title">Settings</span>
      </div>

      <div className="panel-line">
        <div className="section-outer">
          <div className="section-inner">
            <div className="section-header"><span>Profile</span></div>
            <form onSubmit={saveProfile} className="form-inner">
              <label className="form-label"><span>Name</span>
                <input type="text" value={name} onChange={e => setName(e.target.value)} />
              </label>
              <label className="form-label"><span>Email</span>
                <input type="email" value={email} onChange={e => setEmail(e.target.value)} required />
              </label>
              {msg && <div className="form-msg">{msg}</div>}
              <button type="submit" className="btn-primary" disabled={saving}>{saving ? "Saving..." : "Save"}</button>
            </form>
          </div>
        </div>
      </div>

      <div className="panel-line">
        <div className="section-outer">
          <div className="section-inner">
            <div className="section-header"><span>Change Password</span></div>
            <form onSubmit={changePassword} className="form-inner">
              <label className="form-label"><span>Current Password</span>
                <input type="password" value={currentPwd} onChange={e => setCurrentPwd(e.target.value)} required />
              </label>
              <label className="form-label"><span>New Password</span>
                <input type="password" value={newPwd} onChange={e => setNewPwd(e.target.value)} required minLength={8} />
              </label>
              {pwdMsg && <div className="form-msg">{pwdMsg}</div>}
              <button type="submit" className="btn-primary" disabled={pwdSaving}>{pwdSaving ? "Changing..." : "Change Password"}</button>
            </form>
          </div>
        </div>
      </div>

      <div className="panel-line">
        <div className="section-outer">
          <div className="section-inner">
            <div className="section-header"><span>S3 Endpoint</span></div>
            <div className="info-list">
              <div className="info-row"><span>Endpoint URL</span><code>https://s3.z86.dev</code></div>
              <div className="info-row"><span>Region</span><code>auto</code></div>
              <div className="info-row"><span>Path Style</span><code>true</code></div>
            </div>
          </div>
        </div>
      </div>

      <div className="panel-line">
        <div className="section-outer">
          <div className="section-inner">
            <div className="section-header"><span>Plan</span></div>
            <div className="plan-outer">
              <div className="plan-inner">
                <span className="plan-name">{user?.plan || "free"}</span>
                <span className="plan-desc">
                  {user?.plan === "pro" ? "100 GB storage, unlimited buckets" :
                   user?.plan === "enterprise" ? "Unlimited storage, dedicated infra" :
                   "1 GB storage, 3 buckets, 2 keys"}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
