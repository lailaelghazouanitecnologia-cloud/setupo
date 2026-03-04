"use client";

import { useState, useEffect } from "react";
import { useZ86Store } from "@/stores/z86-store";
import { getZ86Buckets } from "@/lib/api/client";
import type { Z86BucketInfo } from "@/lib/api/client";
import { Database, RefreshCw } from "lucide-react";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

export function BucketsPanel() {
  const store = useZ86Store();
  const [buckets, setBuckets] = useState<Z86BucketInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getZ86Buckets();
      setBuckets(data);
    } catch (err: any) {
      setError(err.message);
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  return (
    <div className="panel">
      <div className="panel-section">
        <div className="panel-header-row">
          <h2 className="panel-title">Buckets</h2>
          <button className="btn-icon" onClick={load} title="Refresh">
            <RefreshCw size={14} className={loading ? "spin" : ""} />
          </button>
        </div>

        {error && <div className="panel-error">{error}</div>}

        {!loading && buckets.length === 0 && !error && (
          <div className="panel-empty">
            <Database size={32} />
            <p>No buckets yet</p>
          </div>
        )}

        {buckets.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Objects</th>
                <th>Size</th>
                <th>Region</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {buckets.map((b) => (
                <tr
                  key={b.name}
                  className="clickable-row"
                  onClick={() => {
                    store.setBucketName(b.name);
                    store.setActiveView("objects");
                  }}
                >
                  <td>
                    <div className="cell-with-icon">
                      <Database size={13} />
                      <code>{b.name}</code>
                    </div>
                  </td>
                  <td>{b.object_count}</td>
                  <td>{formatBytes(b.total_size)}</td>
                  <td>{b.region}</td>
                  <td>{new Date(b.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
