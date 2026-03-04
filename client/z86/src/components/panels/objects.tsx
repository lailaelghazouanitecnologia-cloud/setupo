"use client";
import { useEffect, useState, useRef } from "react";
import { dashApi } from "@/lib/api";
import { useZ86Store } from "@/stores/z86-store";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

export function ObjectsPanel() {
  const { activeBucket, setPanel } = useZ86Store();
  const [objects, setObjects] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [prefix, setPrefix] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => {
    if (!activeBucket) return;
    setLoading(true);
    dashApi.listObjects(activeBucket, prefix)
      .then((r) => setObjects(r.objects || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [activeBucket, prefix]);

  if (!activeBucket) {
    return (
      <div className="panel">
        <div className="panel-empty">
          <p>Select a bucket to browse objects</p>
          <button className="btn-secondary" onClick={() => setPanel("buckets")}>Go to Buckets</button>
        </div>
      </div>
    );
  }

  const upload = async (files: FileList | null) => {
    if (!files || !activeBucket) return;
    setUploading(true);
    for (const file of Array.from(files)) {
      const key = prefix ? `${prefix}${file.name}` : file.name;
      try {
        await dashApi.uploadObject(activeBucket, key, file);
      } catch (err: any) {
        alert(`Upload failed: ${err.message}`);
      }
    }
    setUploading(false);
    load();
  };

  const deleteObj = async (key: string) => {
    if (!confirm(`Delete "${key}"?`)) return;
    try {
      await dashApi.deleteObject(activeBucket, key);
      load();
    } catch (err: any) {
      alert(err.message);
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <div className="panel-header-left">
          <button className="btn-back" onClick={() => setPanel("buckets")}>&larr;</button>
          <h1>{activeBucket}</h1>
        </div>
        <div className="panel-header-right">
          <input
            ref={fileRef}
            type="file"
            multiple
            style={{ display: "none" }}
            onChange={(e) => upload(e.target.files)}
          />
          <button
            className="btn-primary"
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? "Uploading..." : "Upload"}
          </button>
        </div>
      </div>

      <div className="filter-bar">
        <input
          type="text"
          value={prefix}
          onChange={e => setPrefix(e.target.value)}
          placeholder="Filter by prefix..."
          className="filter-input"
        />
        <span className="filter-count">{objects.length} objects</span>
      </div>

      {loading ? (
        <div className="panel-loading">Loading...</div>
      ) : objects.length === 0 ? (
        <div className="panel-empty">
          <span className="empty-icon">☁</span>
          <p>No objects{prefix ? ` matching "${prefix}"` : ""}</p>
          <button className="btn-secondary" onClick={() => fileRef.current?.click()}>Upload files</button>
        </div>
      ) : (
        <div className="table-wrapper">
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
              {objects.map((o: any) => (
                <tr key={o.key}>
                  <td className="obj-key">{o.key}</td>
                  <td>{formatBytes(o.size)}</td>
                  <td className="obj-type">{o.content_type}</td>
                  <td>{new Date(o.updated_at).toLocaleDateString()}</td>
                  <td>
                    <button className="btn-danger-sm" onClick={() => deleteObj(o.key)}>Delete</button>
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
