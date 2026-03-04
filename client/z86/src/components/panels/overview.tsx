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

export function OverviewPanel() {
  const { user, setPanel, setActiveBucket } = useZ86Store();
  const [data, setData] = useState<any>(null);
  const [buckets, setBuckets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([dashApi.overview(), dashApi.listBuckets()])
      .then(([ov, bk]) => { setData(ov); setBuckets(bk); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="panel-loading">Loading...</div>;
  if (!data) return <div className="panel-loading">Failed to load</div>;

  const usagePct = data.storage_limit > 0
    ? Math.round((data.storage_used / data.storage_limit) * 100)
    : 0;

  return (
    <div className="panel">
      <div className="panel-header">
        <h1>Overview</h1>
        <span className="panel-badge">{user?.plan || "free"}</span>
      </div>

      <div className="stats-grid">
        <div className="stat-card" onClick={() => setPanel("buckets")}>
          <span className="stat-label">Buckets</span>
          <span className="stat-value">{data.buckets}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Objects</span>
          <span className="stat-value">{data.objects.toLocaleString()}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Storage Used</span>
          <span className="stat-value">{formatBytes(data.storage_used)}</span>
        </div>
        <div className="stat-card" onClick={() => setPanel("keys")}>
          <span className="stat-label">Active Keys</span>
          <span className="stat-value">{data.keys}</span>
        </div>
      </div>

      <div className="usage-bar-section">
        <div className="usage-bar-header">
          <span>Storage</span>
          <span>{formatBytes(data.storage_used)} / {formatBytes(data.storage_limit)}</span>
        </div>
        <div className="usage-bar">
          <div className="usage-bar-fill" style={{ width: `${Math.min(usagePct, 100)}%` }} />
        </div>
        <span className="usage-bar-pct">{usagePct}% used</span>
      </div>

      {buckets.length > 0 && (
        <div className="recent-section">
          <h2>Buckets</h2>
          <div className="bucket-list">
            {buckets.map((b: any) => (
              <button key={b.name} className="bucket-item" onClick={() => setActiveBucket(b.name)}>
                <span className="bucket-icon">◫</span>
                <div className="bucket-info">
                  <span className="bucket-name">{b.name}</span>
                  <span className="bucket-meta">{b.object_count} objects &middot; {formatBytes(b.total_size)}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="quickstart-section">
        <h2>Quick Start</h2>
        <div className="quickstart-code">
          <div><span className="t-comment"># Configure your S3 client</span></div>
          <div><span className="t-prompt">$</span> <span className="t-cmd">aws configure set</span> <span className="t-flag">--profile z86</span></div>
          <div><span className="t-prompt">$</span> <span className="t-cmd">aws s3 ls</span> <span className="t-flag">--endpoint-url</span> <span className="t-arg">https://s3.z86.dev</span> <span className="t-flag">--profile z86</span></div>
        </div>
      </div>
    </div>
  );
}
