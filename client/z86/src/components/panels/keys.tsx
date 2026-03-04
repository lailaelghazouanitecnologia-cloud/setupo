"use client";
import { useEffect, useState } from "react";
import { dashApi } from "@/lib/api";

export function KeysPanel() {
  const [keys, setKeys] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [label, setLabel] = useState("");
  const [allowedBuckets, setAllowedBuckets] = useState("");
  const [creating, setCreating] = useState(false);
  const [newKey, setNewKey] = useState<any>(null);
  const [error, setError] = useState("");

  const load = () => { setLoading(true); dashApi.listKeys().then(setKeys).catch(() => {}).finally(() => setLoading(false)); };
  useEffect(() => { load(); }, []);

  const create = async (e: React.FormEvent) => {
    e.preventDefault(); setError(""); setCreating(true);
    try {
      const result = await dashApi.createKey(label, allowedBuckets);
      setNewKey(result); setLabel(""); setAllowedBuckets(""); setShowCreate(false); load();
    } catch (err: any) { setError(err.message); }
    finally { setCreating(false); }
  };

  const revoke = async (id: string) => {
    if (!confirm("Revoke this key? It will stop working immediately.")) return;
    try { await dashApi.deleteKey(id); load(); } catch (err: any) { alert(err.message); }
  };

  return (
    <div className="panel">
      <div className="panel-line panel-line-header">
        <span className="panel-title">API Keys</span>
        <span className="panel-suffix">
          <button className="btn-primary" onClick={() => { setShowCreate(!showCreate); setNewKey(null); }}>
            {showCreate ? "Cancel" : "+ Create"}
          </button>
        </span>
      </div>

      {newKey && (
        <div className="panel-line">
          <div className="banner-outer banner-success">
            <div className="banner-inner">
              <div className="banner-header">
                <span>Key created — save your secret now</span>
              </div>
              <p className="banner-sub">This is the only time the secret key will be shown.</p>
              <div className="key-display">
                <div className="key-row">
                  <span className="key-label">Access Key ID</span>
                  <code className="key-value">{newKey.access_key_id}</code>
                </div>
                <div className="key-row">
                  <span className="key-label">Secret Access Key</span>
                  <code className="key-value">{newKey.secret_access_key}</code>
                </div>
              </div>
              <button className="btn-secondary" onClick={() => {
                navigator.clipboard.writeText(`Access Key: ${newKey.access_key_id}\nSecret Key: ${newKey.secret_access_key}`);
              }}>Copy to clipboard</button>
            </div>
          </div>
        </div>
      )}

      {showCreate && (
        <div className="panel-line">
          <form onSubmit={create} className="form-outer">
            <div className="form-inner">
              {error && <div className="form-error">{error}</div>}
              <label className="form-label">
                <span>Label (optional)</span>
                <input type="text" value={label} onChange={e => setLabel(e.target.value)} placeholder="e.g. Production, CI/CD" autoFocus />
              </label>
              <label className="form-label">
                <span>Allowed buckets (optional, comma-separated)</span>
                <input type="text" value={allowedBuckets} onChange={e => setAllowedBuckets(e.target.value)} placeholder="Leave empty for all buckets" />
              </label>
              <button type="submit" className="btn-primary" disabled={creating}>{creating ? "Creating..." : "Create Key"}</button>
            </div>
          </form>
        </div>
      )}

      {loading ? (
        <div className="panel-loading">Loading...</div>
      ) : keys.length === 0 ? (
        <div className="panel-line">
          <div className="empty-outer"><div className="empty-inner">
            <span className="empty-icon">⚿</span>
            <p>No API keys yet</p>
            <button className="btn-secondary" onClick={() => setShowCreate(true)}>Create your first key</button>
          </div></div>
        </div>
      ) : (
        <div className="panel-line panel-line-table">
          <div className="table-outer">
            <div className="table-header-row">
              <span className="table-th" style={{ flex: 2 }}>Access Key ID</span>
              <span className="table-th">Label</span>
              <span className="table-th">Status</span>
              <span className="table-th">Created</span>
              <span className="table-th" style={{ width: 60 }} />
            </div>
            {keys.map((k: any) => (
              <div key={k.id} className={`table-row${!k.active ? " table-row-disabled" : ""}`}>
                <div className="table-row-inner">
                  <span className="table-td table-td-mono" style={{ flex: 2 }}>{k.access_key_id}</span>
                  <span className="table-td">{k.label || "—"}</span>
                  <span className="table-td">
                    <span className={`status-badge ${k.active ? "active" : "revoked"}`}>
                      {k.active ? "Active" : "Revoked"}
                    </span>
                  </span>
                  <span className="table-td">{new Date(k.created_at).toLocaleDateString()}</span>
                  <span className="table-td" style={{ width: 60 }}>
                    {k.active && <button className="btn-danger-sm" onClick={() => revoke(k.id)}>Revoke</button>}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
