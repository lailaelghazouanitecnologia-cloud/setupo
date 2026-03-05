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
      <div className="panel-line panel-line-header">
        <span className="panel-title">Overview</span>
        <span className="panel-suffix">{user?.plan || "free"}</span>
      </div>

      <div className="panel-line panel-line-stats">
        <button className="stat-outer" onClick={() => setPanel("buckets")}>
          <div className="stat-inner">
            <span className="stat-label">Buckets</span>
            <span className="stat-value">{data.buckets}</span>
          </div>
        </button>
        <div className="stat-outer">
          <div className="stat-inner">
            <span className="stat-label">Objects</span>
            <span className="stat-value">{data.objects.toLocaleString()}</span>
          </div>
        </div>
        <div className="stat-outer">
          <div className="stat-inner">
            <span className="stat-label">Storage</span>
            <span className="stat-value">{formatBytes(data.storage_used)}</span>
          </div>
        </div>
        <button className="stat-outer" onClick={() => setPanel("keys")}>
          <div className="stat-inner">
            <span className="stat-label">Keys</span>
            <span className="stat-value">{data.keys}</span>
          </div>
        </button>
      </div>

      <div className="panel-line panel-line-bar">
        <div className="bar-outer">
          <div className="bar-inner">
            <div className="bar-header">
              <span>Storage</span>
              <span>{formatBytes(data.storage_used)} / {formatBytes(data.storage_limit)}</span>
            </div>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${Math.min(usagePct, 100)}%` }} />
            </div>
            <span className="bar-pct">{usagePct}%</span>
          </div>
        </div>
      </div>

      {buckets.length > 0 && (
        <div className="panel-line panel-line-list">
          <div className="list-header">
            <span>Buckets</span>
            <span className="list-header-suffix">{String(buckets.length).padStart(2, "0")}</span>
          </div>
          {buckets.map((b: any) => (
            <button key={b.name} className="list-item-outer" onClick={() => setActiveBucket(b.name)}>
              <div className="list-item-inner">
                <span className="list-item-label">
                  <span className="list-item-icon">◫</span>
                  <span>{b.name}</span>
                </span>
                <span className="list-item-suffix">{b.object_count} obj · {formatBytes(b.total_size)}</span>
              </div>
            </button>
          ))}
        </div>
      )}

      <div className="panel-line panel-line-code">
        <div className="code-outer">
          <div className="code-header">
            <span>Quick Start</span>
          </div>
          <div className="code-inner">
            <div><span className="t-comment"># Configure your S3 client</span></div>
            <div><span className="t-prompt">$</span> <span className="t-cmd">aws configure set</span> <span className="t-flag">--profile z86</span></div>
            <div><span className="t-prompt">$</span> <span className="t-cmd">aws s3 ls</span> <span className="t-flag">--endpoint-url</span> <span className="t-arg">https://s3.z86.dev</span> <span className="t-flag">--profile z86</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}
