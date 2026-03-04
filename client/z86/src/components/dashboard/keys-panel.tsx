"use client";

import { useState } from "react";
import { useZ86Store } from "@/stores/z86-store";
import { rotateStorageKey } from "@/lib/api/client";
import { Key, RefreshCw, Eye, EyeOff, Copy, Check, AlertTriangle } from "lucide-react";

export function KeysPanel() {
  const store = useZ86Store();
  const [newKey, setNewKey] = useState<{ access_key_id: string; secret_access_key: string } | null>(null);
  const [showSecret, setShowSecret] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [copied, setCopied] = useState("");
  const [error, setError] = useState("");

  const handleRotate = async () => {
    if (!store.projectId) return;
    if (!confirm("Rotate access key? The old key will stop working immediately.")) return;
    setRotating(true);
    setError("");
    try {
      const res = await rotateStorageKey(store.projectId);
      setNewKey(res);
      store.setAccessKeyId(res.access_key_id);
      setShowSecret(true);
    } catch (err: any) {
      setError(err.message);
    }
    setRotating(false);
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(""), 2000);
  };

  return (
    <div className="panel">
      <div className="panel-section">
        <h2 className="panel-title">Access Keys</h2>

        <div className="detail-grid">
          <div className="detail-row">
            <span className="detail-label">Access Key ID</span>
            <div className="detail-value-row">
              <code className="detail-value">{newKey?.access_key_id || store.accessKeyId || "—"}</code>
              {(newKey?.access_key_id || store.accessKeyId) && (
                <button
                  className="btn-icon"
                  onClick={() => copyToClipboard(newKey?.access_key_id || store.accessKeyId || "", "akid")}
                  title="Copy"
                >
                  {copied === "akid" ? <Check size={13} /> : <Copy size={13} />}
                </button>
              )}
            </div>
          </div>

          {newKey && (
            <div className="detail-row">
              <span className="detail-label">Secret Access Key</span>
              <div className="detail-value-row">
                <code className="detail-value">
                  {showSecret ? newKey.secret_access_key : "••••••••••••••••••••••••••••••"}
                </code>
                <button className="btn-icon" onClick={() => setShowSecret(!showSecret)} title={showSecret ? "Hide" : "Show"}>
                  {showSecret ? <EyeOff size={13} /> : <Eye size={13} />}
                </button>
                <button
                  className="btn-icon"
                  onClick={() => copyToClipboard(newKey.secret_access_key, "sk")}
                  title="Copy"
                >
                  {copied === "sk" ? <Check size={13} /> : <Copy size={13} />}
                </button>
              </div>
            </div>
          )}
        </div>

        {newKey && (
          <div className="warning-box">
            <AlertTriangle size={14} />
            <span>Save your secret key now. It won&apos;t be shown again.</span>
          </div>
        )}

        {error && <div className="panel-error">{error}</div>}

        <div style={{ marginTop: 16 }}>
          <button className="btn-primary" onClick={handleRotate} disabled={rotating}>
            <RefreshCw size={14} className={rotating ? "spin" : ""} />
            {rotating ? "Rotating..." : "Rotate Key"}
          </button>
        </div>
      </div>

      <div className="panel-section">
        <h3 className="panel-subtitle">Using your keys</h3>
        <div className="code-block">
          <div className="code-title">Environment Variables</div>
          <pre className="code-content">{`export AWS_ACCESS_KEY_ID="${newKey?.access_key_id || store.accessKeyId || "<your-key>"}"
export AWS_SECRET_ACCESS_KEY="${newKey ? (showSecret ? newKey.secret_access_key : "********") : "<your-secret>"}"
export AWS_ENDPOINT_URL="https://z86.dev"`}</pre>
        </div>
        <div className="code-block">
          <div className="code-title">Python (boto3)</div>
          <pre className="code-content">{`import boto3

s3 = boto3.client(
    "s3",
    endpoint_url="https://z86.dev",
    aws_access_key_id="${newKey?.access_key_id || store.accessKeyId || "<key>"}",
    aws_secret_access_key="<secret>",
)

s3.put_object(Bucket="${store.bucketName || "<bucket>"}", Key="hello.txt", Body=b"Hello z86!")`}</pre>
        </div>
      </div>
    </div>
  );
}
