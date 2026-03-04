"use client";

import { useState, useEffect, useCallback } from "react";
import { useZ86Store } from "@/stores/z86-store";
import { getZ86BucketObjects, deleteZ86Object } from "@/lib/api/client";
import type { Z86ObjectInfo } from "@/lib/api/client";
import { File, Folder, Trash2, RefreshCw, Search, ChevronRight, Database } from "lucide-react";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

export function ObjectsPanel() {
  const store = useZ86Store();
  const bucket = store.bucketName;
  const [objects, setObjects] = useState<Z86ObjectInfo[]>([]);
  const [prefix, setPrefix] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!bucket) return;
    setLoading(true);
    setError("");
    try {
      const data = await getZ86BucketObjects(bucket, prefix);
      setObjects(data);
    } catch (err: any) {
      setError(err.message);
    }
    setLoading(false);
  }, [bucket, prefix]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async (key: string) => {
    if (!bucket || !confirm(`Delete ${key}?`)) return;
    try {
      await deleteZ86Object(bucket, key);
      load();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const navigatePrefix = (p: string) => {
    setPrefix(p);
    setSearchInput(p);
  };

  const prefixParts = prefix.split("/").filter(Boolean);

  if (!bucket) {
    return (
      <div className="panel">
        <div className="panel-empty">
          <Database size={32} />
          <p>Select a bucket first</p>
          <button className="btn-sm" onClick={() => store.setActiveView("buckets")}>Go to Buckets</button>
        </div>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-section">
        <div className="panel-header-row">
          <h2 className="panel-title">
            <Database size={16} />
            {bucket}
          </h2>
          <button className="btn-icon" onClick={load} title="Refresh">
            <RefreshCw size={14} className={loading ? "spin" : ""} />
          </button>
        </div>

        {/* Breadcrumb */}
        <div className="breadcrumb">
          <button className="breadcrumb-item" onClick={() => navigatePrefix("")}>root</button>
          {prefixParts.map((part, i) => (
            <span key={i} className="breadcrumb-segment">
              <ChevronRight size={12} />
              <button
                className="breadcrumb-item"
                onClick={() => navigatePrefix(prefixParts.slice(0, i + 1).join("/") + "/")}
              >
                {part}
              </button>
            </span>
          ))}
        </div>

        {/* Search */}
        <div className="search-bar">
          <Search size={14} />
          <input
            className="search-input"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && setPrefix(searchInput)}
            placeholder="Filter by prefix..."
          />
        </div>

        {error && <div className="panel-error">{error}</div>}

        {!loading && objects.length === 0 && !error && (
          <div className="panel-empty">
            <File size={24} />
            <p>No objects{prefix ? ` with prefix "${prefix}"` : ""}</p>
          </div>
        )}

        {objects.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>Key</th>
                <th>Size</th>
                <th>Type</th>
                <th>Modified</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {objects.map((obj) => {
                const isDir = obj.key.endsWith("/");
                return (
                  <tr key={obj.key}>
                    <td>
                      <div className="cell-with-icon">
                        {isDir ? <Folder size={13} /> : <File size={13} />}
                        {isDir ? (
                          <button className="link-btn" onClick={() => navigatePrefix(obj.key)}>{obj.key}</button>
                        ) : (
                          <code>{obj.key}</code>
                        )}
                      </div>
                    </td>
                    <td>{formatBytes(obj.size)}</td>
                    <td><span className="type-badge">{obj.content_type}</span></td>
                    <td>{new Date(obj.updated_at).toLocaleString()}</td>
                    <td>
                      <button className="btn-icon btn-danger" onClick={() => handleDelete(obj.key)} title="Delete">
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
