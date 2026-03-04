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

  const load = () => {
    setLoading(true);
    dashApi.listKeys()
      .then(setKeys)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setCreating(true);
    try {
      const result = await dashApi.createKey(label, allowedBuckets);
      setNewKey(result);
      setLabel("");
      setAllowedBuckets("");
      setShowCreate(false);
      load();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  const revoke = async (id: string) => {
    if (!confirm("Revoke this key? It will stop working immediately.")) return;
    try {
      await dashApi.deleteKey(id);
      load();
    } catch (err: any) {
      alert(err.message);
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <h1>API Keys</h1>
        <button className="btn-primary" onClick={() => { setShowCreate(!showCreate); setNewKey(null); }}>
          {showCreate ? "Cancel" : "+ Create Key"}
        </button>
      </div>

      {newKey && (
        <div className="key-created-banner">
          <h3>Key created — save your secret key now!</h3>
          <p>This is the only time the secret key will be shown.</p>
          <div className="key-display">
            <div><span className="key-label">Access Key ID</span><code>{newKey.access_key_id}</code></div>
            <div><span className="key-label">Secret Access Key</span><code>{newKey.secret_access_key}</code></div>
          </div>
          <button className="btn-secondary" onClick={() => {
            navigator.clipboard.writeText(`Access Key: ${newKey.access_key_id}\nSecret Key: ${newKey.secret_access_key}`);
          }}>Copy to clipboard</button>
        </div>
      )}

      {showCreate && (
        <form onSubmit={create} className="create-form">
          {error && <div className="form-error">{error}</div>}
          <label>
            <span>Label (optional)</span>
            <input type="text" value={label} onChange={e => setLabel(e.target.value)} placeholder="e.g. Production, CI/CD" autoFocus />
          </label>
          <label>
            <span>Allowed buckets (optional, comma-separated)</span>
            <input type="text" value={allowedBuckets} onChange={e => setAllowedBuckets(e.target.value)} placeholder="Leave empty for all buckets" />
          </label>
          <button type="submit" className="btn-primary" disabled={creating}>
            {creating ? "Creating..." : "Create Key"}
          </button>
        </form>
      )}

      {loading ? (
        <div className="panel-loading">Loading...</div>
      ) : keys.length === 0 ? (
        <div className="panel-empty">
          <span className="empty-icon">⚿</span>
          <p>No API keys yet</p>
          <button className="btn-secondary" onClick={() => setShowCreate(true)}>Create your first key</button>
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Access Key ID</th>
                <th>Label</th>
                <th>Status</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k: any) => (
                <tr key={k.id} className={!k.active ? "row-disabled" : ""}>
                  <td><code>{k.access_key_id}</code></td>
                  <td>{k.label || "—"}</td>
                  <td>
                    <span className={`status-badge ${k.active ? "active" : "revoked"}`}>
                      {k.active ? "Active" : "Revoked"}
                    </span>
                  </td>
                  <td>{new Date(k.created_at).toLocaleDateString()}</td>
                  <td>
                    {k.active && (
                      <button className="btn-danger-sm" onClick={() => revoke(k.id)}>Revoke</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
