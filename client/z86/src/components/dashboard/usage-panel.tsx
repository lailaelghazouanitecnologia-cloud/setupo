"use client";

import { useState, useEffect } from "react";
import { useZ86Store } from "@/stores/z86-store";
import { getZ86Overview } from "@/lib/api/client";
import { HardDrive, Database, FileBox, BarChart3 } from "lucide-react";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

export function UsagePanel() {
  const store = useZ86Store();
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (store.userRole === "admin") {
      getZ86Overview()
        .then((d) => setStats(d.stats))
        .catch(() => {})
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [store.userRole]);

  if (loading) return <div className="panel"><div className="panel-loading">Loading...</div></div>;

  if (!stats) {
    return (
      <div className="panel">
        <div className="panel-section">
          <h2 className="panel-title">Usage</h2>
          <div className="panel-empty">
            <BarChart3 size={32} />
            <p>Usage metrics are available for admin accounts</p>
          </div>
        </div>
      </div>
    );
  }

  const diskPct = stats.disk_used_bytes && stats.total_size_bytes
    ? ((stats.total_size_bytes / stats.disk_used_bytes) * 100).toFixed(1)
    : "0";

  return (
    <div className="panel">
      <div className="panel-section">
        <h2 className="panel-title">Usage</h2>

        <div className="stat-grid">
          <div className="stat-card">
            <div className="stat-icon"><Database size={18} /></div>
            <div className="stat-info">
              <span className="stat-value">{stats.total_buckets}</span>
              <span className="stat-label">Buckets</span>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon"><FileBox size={18} /></div>
            <div className="stat-info">
              <span className="stat-value">{stats.total_objects}</span>
              <span className="stat-label">Objects</span>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon"><HardDrive size={18} /></div>
            <div className="stat-info">
              <span className="stat-value">{formatBytes(stats.total_size_bytes)}</span>
              <span className="stat-label">Data Stored</span>
            </div>
          </div>
        </div>

        <div className="usage-bar-container">
          <div className="usage-bar-header">
            <span>Storage Used</span>
            <span>{formatBytes(stats.total_size_bytes)} / {formatBytes(stats.disk_used_bytes)}</span>
          </div>
          <div className="usage-bar">
            <div className="usage-bar-fill" style={{ width: `${Math.min(parseFloat(diskPct), 100)}%` }} />
          </div>
        </div>
      </div>
    </div>
  );
}
