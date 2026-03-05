"use client";
import { useEffect, useState } from "react";
import { dashApi } from "@/lib/api";
import { useZ86Store } from "@/stores/z86-store";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

export function BucketsPanel() {
  const { setActiveBucket } = useZ86Store();
  const [buckets, setBuckets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);

  const load = () => {
    setLoading(true);
    dashApi.listBuckets().then(setBuckets).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(""); setCreating(true);
    try {
      await dashApi.createBucket(newName.trim().toLowerCase());
      setNewName(""); setShowCreate(false); load();
    } catch (err: any) { setError(err.message); }
    finally { setCreating(false); }
  };

  const deleteBucket = async (name: string) => {
    if (!confirm(`Delete bucket "${name}"? This cannot be undone.`)) return;
    try { await dashApi.deleteBucket(name); load(); }
    catch (err: any) { alert(err.message); }
  };

  return (
    <div className="panel">
      <div className="panel-line panel-line-header">
        <span className="panel-title">Buckets</span>
        <span className="panel-suffix">
          <button className="btn-primary" onClick={() => setShowCreate(!showCreate)}>
            {showCreate ? "Cancel" : "+ Create"}
          </button>
        </span>
      </div>

      {showCreate && (
        <div className="panel-line">
          <form onSubmit={create} className="form-outer">
            <div className="form-inner">
              {error && <div className="form-error">{error}</div>}
              <div className="form-row">
                <input type="text" value={newName} onChange={e => setNewName(e.target.value)}
                  placeholder="my-bucket" pattern="[a-z0-9][a-z0-9\.\-]{1,61}[a-z0-9]" required autoFocus />
                <button type="submit" className="btn-primary" disabled={creating}>
                  {creating ? "Creating..." : "Create"}
                </button>
              </div>
              <span className="form-hint">Lowercase alphanumeric, hyphens, dots. 3-63 chars.</span>
            </div>
          </form>
        </div>
      )}

      {loading ? (
        <div className="panel-loading">Loading...</div>
      ) : buckets.length === 0 ? (
        <div className="panel-line">
          <div className="empty-outer">
            <div className="empty-inner">
              <span className="empty-icon">◫</span>
              <p>No buckets yet</p>
              <button className="btn-secondary" onClick={() => setShowCreate(true)}>Create your first bucket</button>
            </div>
          </div>
        </div>
      ) : (
        <div className="panel-line panel-line-table">
          <div className="table-outer">
            <div className="table-header-row">
              <span className="table-th" style={{ flex: 2 }}>Name</span>
              <span className="table-th">Objects</span>
              <span className="table-th">Size</span>
              <span className="table-th">Created</span>
              <span className="table-th" style={{ width: 60 }} />
            </div>
            {buckets.map((b: any) => (
              <div key={b.name} className="table-row">
                <div className="table-row-inner">
                  <span className="table-td" style={{ flex: 2 }}>
                    <button className="link-btn" onClick={() => setActiveBucket(b.name)}>{b.name}</button>
                  </span>
                  <span className="table-td">{b.object_count}</span>
                  <span className="table-td">{formatBytes(b.total_size)}</span>
                  <span className="table-td">{new Date(b.created_at).toLocaleDateString()}</span>
                  <span className="table-td" style={{ width: 60 }}>
                    <button className="btn-danger-sm" onClick={() => deleteBucket(b.name)}>Delete</button>
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
