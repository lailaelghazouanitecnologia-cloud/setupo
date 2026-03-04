"use client";

import { useState, useEffect } from "react";
import { useZ86Store } from "@/stores/z86-store";
import { getZ86Overview } from "@/lib/api/client";
import { Database, HardDrive, Key, FileBox, Activity } from "lucide-react";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

export function OverviewPanel({ storageInfo }: { storageInfo: any }) {
  const store = useZ86Store();
  const isAdmin = store.userRole === "admin";
  const [overview, setOverview] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isAdmin) {
      setLoading(true);
      getZ86Overview()
        .then(setOverview)
        .catch(() => {})
        .finally(() => setLoading(false));
    }
  }, [isAdmin]);

  const stats = overview?.stats;

  return (
    <div className="panel">
      <div className="panel-section">
        <h2 className="panel-title">Storage Overview</h2>

        <div className="stat-grid">
          <div className="stat-card">
            <div className="stat-icon"><Database size={18} /></div>
            <div className="stat-info">
              <span className="stat-value">{stats?.total_buckets ?? (storageInfo?.bucket ? 1 : 0)}</span>
              <span className="stat-label">Buckets</span>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon"><FileBox size={18} /></div>
            <div className="stat-info">
              <span className="stat-value">{stats?.total_objects ?? "—"}</span>
              <span className="stat-label">Objects</span>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon"><HardDrive size={18} /></div>
            <div className="stat-info">
              <span className="stat-value">{stats ? formatBytes(stats.total_size_bytes) : "—"}</span>
              <span className="stat-label">Data Stored</span>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon"><Key size={18} /></div>
            <div className="stat-info">
              <span className="stat-value">{stats?.total_keys ?? (storageInfo?.access_key_id ? 1 : 0)}</span>
              <span className="stat-label">Access Keys</span>
            </div>
          </div>
        </div>
      </div>

      {storageInfo && (
        <div className="panel-section">
          <h3 className="panel-subtitle">Connection Details</h3>
          <div className="detail-grid">
            <div className="detail-row">
              <span className="detail-label">Endpoint</span>
              <code className="detail-value">{storageInfo.endpoint || "https://z86.dev"}</code>
            </div>
            <div className="detail-row">
              <span className="detail-label">Bucket</span>
              <code className="detail-value">{storageInfo.bucket}</code>
            </div>
            <div className="detail-row">
              <span className="detail-label">Access Key ID</span>
              <code className="detail-value">{storageInfo.access_key_id}</code>
            </div>
            <div className="detail-row">
              <span className="detail-label">Status</span>
              <span className={`status-badge ${storageInfo.status === "active" ? "status-active" : "status-inactive"}`}>
                <Activity size={10} />
                {storageInfo.status || "active"}
              </span>
            </div>
          </div>
        </div>
      )}

      <div className="panel-section">
        <h3 className="panel-subtitle">Quick Start</h3>
        <div className="code-block">
          <div className="code-title">Configure AWS CLI</div>
          <pre className="code-content">{`aws configure set aws_access_key_id ${storageInfo?.access_key_id || "<your-access-key>"}
aws configure set aws_secret_access_key <your-secret-key>
aws configure set default.region us-east-1

# Upload a file
aws s3 cp ./file.txt s3://${storageInfo?.bucket || "<bucket>"}/file.txt \\
  --endpoint-url https://z86.dev

# List objects
aws s3 ls s3://${storageInfo?.bucket || "<bucket>"}/ \\
  --endpoint-url https://z86.dev`}</pre>
        </div>
      </div>

      {isAdmin && overview?.buckets && overview.buckets.length > 0 && (
        <div className="panel-section">
          <h3 className="panel-subtitle">All Buckets</h3>
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Objects</th>
                <th>Size</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {overview.buckets.map((b: any) => (
                <tr key={b.name}>
                  <td><code>{b.name}</code></td>
                  <td>{b.object_count}</td>
                  <td>{formatBytes(b.total_size)}</td>
                  <td>{new Date(b.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
