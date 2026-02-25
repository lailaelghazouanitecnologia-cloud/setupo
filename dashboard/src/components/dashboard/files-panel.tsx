"use client";

import { useState, useEffect } from "react";
import { FolderOpen, FileText, ArrowLeft, Save, Trash2 } from "lucide-react";
import { listFiles, readFile, writeFile, deleteFile } from "@/lib/api/client";

export function FilesPanel() {
  const [currentPath, setCurrentPath] = useState("/opt/setupo");
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [editingFile, setEditingFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [saving, setSaving] = useState(false);

  const fetchDir = async (path: string) => {
    setLoading(true);
    setEditingFile(null);
    try {
      const res = await listFiles(path);
      setItems(res.items || []);
      setCurrentPath(res.path);
    } catch {
      setItems([]);
    }
    setLoading(false);
  };

  useEffect(() => { fetchDir(currentPath); }, []);

  const openFile = async (path: string) => {
    setLoading(true);
    try {
      const res = await readFile(path);
      setEditingFile(res.path);
      setFileContent(res.content);
    } catch (err: any) {
      alert(`Cannot read: ${err.message}`);
    }
    setLoading(false);
  };

  const handleSave = async () => {
    if (!editingFile) return;
    setSaving(true);
    try {
      await writeFile(editingFile, fileContent);
    } catch (err: any) {
      alert(`Save failed: ${err.message}`);
    }
    setSaving(false);
  };

  const handleDelete = async (path: string, name: string) => {
    if (!confirm(`Delete ${name}?`)) return;
    try {
      await deleteFile(path);
      fetchDir(currentPath);
    } catch (err: any) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  const goUp = () => {
    const parent = currentPath.split("/").slice(0, -1).join("/") || "/";
    fetchDir(parent);
  };

  if (editingFile) {
    return (
      <div className="animate-fade-in">
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <button className="ibtn" onClick={() => setEditingFile(null)}><ArrowLeft className="h-3.5 w-3.5" /></button>
          <code className="code-inline">{editingFile}</code>
          <button className="task-btn" style={{ width: "auto", padding: "0 12px", marginBottom: 0 }} onClick={handleSave}>
            <Save className="h-3.5 w-3.5" /><span>{saving ? "Saving..." : "Save"}</span>
          </button>
        </div>
        <textarea
          value={fileContent}
          onChange={(e) => setFileContent(e.target.value)}
          style={{
            width: "100%",
            minHeight: 400,
            padding: 12,
            background: "var(--input)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            fontFamily: "var(--font-mono)",
            fontSize: "var(--font-sm)",
            color: "var(--foreground)",
            resize: "vertical",
            outline: "none",
            boxSizing: "border-box",
            lineHeight: 1.6,
          }}
          spellCheck={false}
        />
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <button className="ibtn" onClick={goUp}><ArrowLeft className="h-3.5 w-3.5" /></button>
        <code className="code-inline" style={{ flex: 1 }}>{currentPath}</code>
        <button className="task-btn" style={{ width: "auto", padding: "0 12px", marginBottom: 0 }} onClick={() => fetchDir(currentPath)}>
          Refresh
        </button>
      </div>

      {loading ? (
        <div style={{ fontSize: "var(--font-sm)", color: "var(--muted-foreground)", padding: 12 }}>Loading...</div>
      ) : items.length === 0 ? (
        <div className="note-block" style={{ textAlign: "center", padding: 24 }}>
          <FolderOpen className="h-6 w-6" style={{ color: "var(--muted-foreground)", margin: "0 auto 6px" }} />
          <span style={{ fontSize: "var(--font-sm)", color: "var(--muted-foreground)" }}>Empty directory</span>
        </div>
      ) : (
        <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
          {items.map((item, i) => (
            <div
              key={item.path}
              style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "6px 12px", fontSize: "var(--font-sm)",
                borderBottom: i < items.length - 1 ? "1px solid var(--border)" : "none",
                cursor: "pointer",
                transition: "background 0.1s",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "var(--accent)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "")}
              onClick={() => item.type === "dir" ? fetchDir(item.path) : openFile(item.path)}
            >
              {item.type === "dir" ? (
                <FolderOpen className="h-3.5 w-3.5" style={{ color: "var(--color-blue)", flexShrink: 0 }} />
              ) : (
                <FileText className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)", flexShrink: 0 }} />
              )}
              <span style={{ flex: 1 }}>{item.name}</span>
              {item.size != null && (
                <span style={{ color: "var(--muted-foreground)", fontSize: "var(--font-xs)" }}>
                  {item.size > 1024 ? `${(item.size / 1024).toFixed(1)}KB` : `${item.size}B`}
                </span>
              )}
              <span style={{ color: "var(--muted-foreground)", fontSize: "var(--font-xxs)", width: 70 }}>
                {item.permissions}
              </span>
              {item.type === "file" && (
                <button
                  className="ibtn"
                  onClick={(e) => { e.stopPropagation(); handleDelete(item.path, item.name); }}
                  style={{ color: "var(--color-red)" }}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
