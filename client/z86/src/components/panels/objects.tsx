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
      .catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [activeBucket, prefix]);

  if (!activeBucket) {
    return (
      <div className="panel">
        <div className="panel-line">
          <div className="empty-outer"><div className="empty-inner">
            <p>Select a bucket to browse objects</p>
            <button className="btn-secondary" onClick={() => setPanel("buckets")}>Go to Buckets</button>
          </div></div>
        </div>
      </div>
    );
  }

  const upload = async (files: FileList | null) => {
    if (!files || !activeBucket) return;
    setUploading(true);
    for (const file of Array.from(files)) {
      const key = prefix ? `${prefix}${file.name}` : file.name;
      try { await dashApi.uploadObject(activeBucket, key, file); }
      catch (err: any) { alert(`Upload failed: ${err.message}`); }
    }
    setUploading(false); load();
  };

  const deleteObj = async (key: string) => {
    if (!confirm(`Delete "${key}"?`)) return;
    try { await dashApi.deleteObject(activeBucket, key); load(); }
    catch (err: any) { alert(err.message); }
  };

  return (
    <div className="panel">
      <div className="panel-line panel-line-header">
        <span className="panel-title">
          <button className="btn-back" onClick={() => setPanel("buckets")}>←</button>
          {activeBucket}
        </span>
        <span className="panel-suffix">
          <input ref={fileRef} type="file" multiple style={{ display: "none" }} onChange={(e) => upload(e.target.files)} />
          <button className="btn-primary" onClick={() => fileRef.current?.click()} disabled={uploading}>
            {uploading ? "Uploading..." : "Upload"}
          </button>
        </span>
      </div>

      <div className="panel-line">
        <div className="filter-outer">
          <div className="filter-inner">
            <input type="text" value={prefix} onChange={e => setPrefix(e.target.value)} placeholder="Filter by prefix..." className="filter-input" />
            <span className="filter-suffix">{objects.length} objects</span>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="panel-loading">Loading...</div>
      ) : objects.length === 0 ? (
        <div className="panel-line">
          <div className="empty-outer"><div className="empty-inner">
            <span className="empty-icon">☁</span>
            <p>No objects{prefix ? ` matching "${prefix}"` : ""}</p>
            <button className="btn-secondary" onClick={() => fileRef.current?.click()}>Upload files</button>
          </div></div>
        </div>
      ) : (
        <div className="panel-line panel-line-table">
          <div className="table-outer">
            <div className="table-header-row">
              <span className="table-th" style={{ flex: 2 }}>Key</span>
              <span className="table-th">Size</span>
              <span className="table-th">Type</span>
              <span className="table-th">Modified</span>
              <span className="table-th" style={{ width: 60 }} />
            </div>
            {objects.map((o: any) => (
              <div key={o.key} className="table-row">
                <div className="table-row-inner">
                  <span className="table-td table-td-mono" style={{ flex: 2 }}>{o.key}</span>
                  <span className="table-td">{formatBytes(o.size)}</span>
                  <span className="table-td table-td-muted">{o.content_type}</span>
                  <span className="table-td">{new Date(o.updated_at).toLocaleDateString()}</span>
                  <span className="table-td" style={{ width: 60 }}>
                    <button className="btn-danger-sm" onClick={() => deleteObj(o.key)}>Delete</button>
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
