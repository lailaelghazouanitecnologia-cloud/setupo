"use client";
import { useEffect, useState } from "react";
import { dashApi } from "@/lib/api";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

export function UsagePanel() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    dashApi.usage()
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="panel"><div className="panel-loading">Loading...</div></div>;
  if (!data) return <div className="panel"><div className="panel-loading">Failed to load</div></div>;

  return (
    <div className="panel">
      <div className="panel-header">
        <h1>Usage</h1>
      </div>

      <div className="usage-overview">
        <div className="usage-main-card">
          <div className="usage-main-header">
            <span>Storage Usage</span>
            <span className="usage-main-pct">{data.usage_pct}%</span>
          </div>
          <div className="usage-bar large">
            <div
              className="usage-bar-fill"
              style={{ width: `${Math.min(data.usage_pct, 100)}%` }}
            />
          </div>
          <div className="usage-main-footer">
            <span>{formatBytes(data.total_storage)} used</span>
            <span>{formatBytes(data.storage_limit)} limit</span>
          </div>
        </div>
      </div>

      {data.buckets && data.buckets.length > 0 && (
        <div className="usage-breakdown">
          <h2>By Bucket</h2>
          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Bucket</th>
                  <th>Objects</th>
                  <th>Size</th>
                  <th>% of Total</th>
                </tr>
              </thead>
              <tbody>
                {data.buckets.map((b: any) => {
                  const pct = data.total_storage > 0
                    ? Math.round((b.size / data.total_storage) * 100)
                    : 0;
                  return (
                    <tr key={b.bucket}>
                      <td>{b.bucket}</td>
                      <td>{b.objects}</td>
                      <td>{formatBytes(b.size)}</td>
                      <td>
                        <div className="usage-bar-inline">
                          <div className="usage-bar-fill" style={{ width: `${pct}%` }} />
                        </div>
                        <span>{pct}%</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
