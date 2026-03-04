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
    dashApi.usage().then(setData).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="panel"><div className="panel-loading">Loading...</div></div>;
  if (!data) return <div className="panel"><div className="panel-loading">Failed to load</div></div>;

  return (
    <div className="panel">
      <div className="panel-line panel-line-header">
        <span className="panel-title">Usage</span>
      </div>

      <div className="panel-line">
        <div className="bar-outer bar-outer-large">
          <div className="bar-inner">
            <div className="bar-header">
              <span>Storage Usage</span>
              <span className="bar-pct-large">{data.usage_pct}%</span>
            </div>
            <div className="bar-track bar-track-large">
              <div className="bar-fill" style={{ width: `${Math.min(data.usage_pct, 100)}%` }} />
            </div>
            <div className="bar-footer">
              <span>{formatBytes(data.total_storage)} used</span>
              <span>{formatBytes(data.storage_limit)} limit</span>
            </div>
          </div>
        </div>
      </div>

      {data.buckets && data.buckets.length > 0 && (
        <div className="panel-line panel-line-table">
          <div className="list-header">
            <span>By Bucket</span>
            <span className="list-header-suffix">{String(data.buckets.length).padStart(2, "0")}</span>
          </div>
          <div className="table-outer">
            <div className="table-header-row">
              <span className="table-th" style={{ flex: 2 }}>Bucket</span>
              <span className="table-th">Objects</span>
              <span className="table-th">Size</span>
              <span className="table-th">% of Total</span>
            </div>
            {data.buckets.map((b: any) => {
              const pct = data.total_storage > 0 ? Math.round((b.size / data.total_storage) * 100) : 0;
              return (
                <div key={b.bucket} className="table-row">
                  <div className="table-row-inner">
                    <span className="table-td" style={{ flex: 2 }}>{b.bucket}</span>
                    <span className="table-td">{b.objects}</span>
                    <span className="table-td">{formatBytes(b.size)}</span>
                    <span className="table-td">
                      <span className="bar-inline"><span className="bar-fill" style={{ width: `${pct}%` }} /></span>
                      {pct}%
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
