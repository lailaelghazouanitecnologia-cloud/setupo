"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  FolderOpen, FileText, ChevronRight, ChevronDown,
  Save, Trash2, Pencil, Eye, Download, Copy, Check, Image,
  FileCode, FileJson, File, RefreshCw, Plus, X,
} from "lucide-react";
import { listFiles, readFile, writeFile, deleteFile, getFileTree } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import type { FSItem } from "@/types/dashboard";

/* ═══════════════════════════════════════════
   FILE TYPE UTILITIES
   ═══════════════════════════════════════════ */
type FileKind = "code" | "image" | "markdown" | "json" | "text" | "binary";

const CODE_EXTS = new Set([
  "py", "rs", "go", "js", "ts", "tsx", "jsx", "c", "cpp", "h", "hpp",
  "java", "rb", "php", "swift", "kt", "scala", "zig", "lua", "sh", "bash",
  "zsh", "fish", "ps1", "bat", "cmd", "css", "scss", "less", "html", "xml",
  "svg", "vue", "svelte", "astro", "sql", "graphql", "proto", "r", "pl",
  "ex", "exs", "erl", "hs", "ml", "ocaml", "nim", "dart", "v", "asm",
  "nix", "tf", "hcl", "Makefile", "Dockerfile", "Vagrantfile",
]);
const IMAGE_EXTS = new Set(["png", "jpg", "jpeg", "gif", "webp", "bmp", "ico", "svg"]);
const JSON_EXTS = new Set(["json", "jsonl", "jsonc"]);
const MD_EXTS = new Set(["md", "mdx", "markdown"]);
const BINARY_EXTS = new Set(["zip", "tar", "gz", "bz2", "xz", "7z", "rar", "bin", "exe", "dll", "so", "dylib", "wasm", "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "mp3", "mp4", "wav", "avi", "mkv", "mov"]);
const CONFIG_FILES = new Set(["Makefile", "Dockerfile", "Vagrantfile", "Procfile", "Gemfile", "Rakefile", ".gitignore", ".dockerignore", ".env", ".env.local", ".editorconfig"]);

function getExt(name: string): string {
  const idx = name.lastIndexOf(".");
  return idx > 0 ? name.slice(idx + 1).toLowerCase() : "";
}

function getFileKind(name: string): FileKind {
  if (CONFIG_FILES.has(name)) return "code";
  const ext = getExt(name);
  if (!ext) return "text";
  if (CODE_EXTS.has(ext)) return "code";
  if (IMAGE_EXTS.has(ext)) return "image";
  if (JSON_EXTS.has(ext)) return "json";
  if (MD_EXTS.has(ext)) return "markdown";
  if (BINARY_EXTS.has(ext)) return "binary";
  if (["toml", "yaml", "yml", "ini", "cfg", "conf", "env", "lock"].includes(ext)) return "code";
  if (["txt", "log", "csv", "tsv", "rst"].includes(ext)) return "text";
  return "text";
}

function getFileIcon(name: string, type: string) {
  if (type === "dir") return <FolderOpen className="fs-icon" style={{ color: "var(--color-blue)" }} />;
  const kind = getFileKind(name);
  switch (kind) {
    case "code": return <FileCode className="fs-icon" style={{ color: "var(--color-teal)" }} />;
    case "image": return <Image className="fs-icon" style={{ color: "var(--color-purple)" }} />;
    case "json": return <FileJson className="fs-icon" style={{ color: "var(--color-yellow)" }} />;
    case "markdown": return <FileText className="fs-icon" style={{ color: "var(--muted-foreground)" }} />;
    default: return <File className="fs-icon" style={{ color: "var(--muted-foreground)" }} />;
  }
}

function formatSize(bytes?: number): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTime(ts?: number): string {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function getLang(name: string): string {
  const ext = getExt(name);
  const map: Record<string, string> = {
    py: "Python", rs: "Rust", go: "Go", js: "JavaScript", ts: "TypeScript",
    tsx: "TSX", jsx: "JSX", html: "HTML", css: "CSS", scss: "SCSS",
    json: "JSON", yaml: "YAML", yml: "YAML", toml: "TOML", md: "Markdown",
    sh: "Shell", bash: "Bash", sql: "SQL", java: "Java", rb: "Ruby",
    php: "PHP", swift: "Swift", kt: "Kotlin", c: "C", cpp: "C++",
    h: "C Header", zig: "Zig", lua: "Lua", xml: "XML", svg: "SVG",
    conf: "Config", ini: "INI", dockerfile: "Dockerfile",
  };
  if (CONFIG_FILES.has(name)) return name;
  return map[ext] || ext.toUpperCase() || "Text";
}

/* ═══════════════════════════════════════════
   TREE NODE (recursive)
   ═══════════════════════════════════════════ */
interface TreeEntry {
  name: string;
  path: string;
  type: string;
  size?: number;
  modified?: number;
  permissions?: string;
  children?: TreeEntry[];
}

function TreeNode({
  entry,
  depth,
  selectedPath,
  onSelect,
  onToggle,
  expandedDirs,
}: {
  entry: TreeEntry;
  depth: number;
  selectedPath: string | null;
  onSelect: (entry: TreeEntry) => void;
  onToggle: (path: string) => void;
  expandedDirs: Set<string>;
}) {
  const isDir = entry.type === "dir";
  const isExpanded = expandedDirs.has(entry.path);
  const isSelected = selectedPath === entry.path;

  return (
    <>
      <button
        className={cn("fs-tree-node", isSelected && "selected")}
        style={{ paddingLeft: 8 + depth * 14 }}
        onClick={() => {
          if (isDir) onToggle(entry.path);
          onSelect(entry);
        }}
      >
        {isDir ? (
          isExpanded
            ? <ChevronDown className="fs-chevron" />
            : <ChevronRight className="fs-chevron" />
        ) : (
          <span className="fs-chevron" />
        )}
        {getFileIcon(entry.name, entry.type)}
        <span className="fs-tree-name">{entry.name}</span>
      </button>
      {isDir && isExpanded && entry.children?.map((child) => (
        <TreeNode
          key={child.path}
          entry={child}
          depth={depth + 1}
          selectedPath={selectedPath}
          onSelect={onSelect}
          onToggle={onToggle}
          expandedDirs={expandedDirs}
        />
      ))}
    </>
  );
}

/* ═══════════════════════════════════════════
   CODE VIEWER / EDITOR
   ═══════════════════════════════════════════ */
function CodeViewer({
  content,
  fileName,
  editing,
  onChange,
}: {
  content: string;
  fileName: string;
  editing: boolean;
  onChange: (val: string) => void;
}) {
  const lines = content.split("\n");
  const lineCount = lines.length;
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lineNumRef = useRef<HTMLDivElement>(null);

  const syncScroll = () => {
    if (textareaRef.current && lineNumRef.current) {
      lineNumRef.current.scrollTop = textareaRef.current.scrollTop;
    }
  };

  if (editing) {
    return (
      <div className="fs-code-container">
        <div className="fs-code-header">
          <span className="fs-code-lang">{getLang(fileName)}</span>
          <span className="fs-code-lines">{lineCount} lines</span>
        </div>
        <div className="fs-code-body editing">
          <div className="fs-line-numbers" ref={lineNumRef}>
            {lines.map((_, i) => (
              <div key={i} className="fs-line-num">{i + 1}</div>
            ))}
          </div>
          <textarea
            ref={textareaRef}
            className="fs-code-textarea"
            value={content}
            onChange={(e) => onChange(e.target.value)}
            onScroll={syncScroll}
            spellCheck={false}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="fs-code-container">
      <div className="fs-code-header">
        <span className="fs-code-lang">{getLang(fileName)}</span>
        <span className="fs-code-lines">{lineCount} lines</span>
      </div>
      <div className="fs-code-body">
        <div className="fs-line-numbers">
          {lines.map((_, i) => (
            <div key={i} className="fs-line-num">{i + 1}</div>
          ))}
        </div>
        <pre className="fs-code-pre"><code>{content}</code></pre>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   IMAGE VIEWER
   ═══════════════════════════════════════════ */
function ImageViewer({
  entry,
  content,
}: {
  entry: TreeEntry;
  content: string | null;
}) {
  const ext = getExt(entry.name);
  const mimeMap: Record<string, string> = {
    png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg",
    gif: "image/gif", webp: "image/webp", svg: "image/svg+xml",
    bmp: "image/bmp", ico: "image/x-icon",
  };
  const mime = mimeMap[ext] || "image/png";

  // If content is SVG (text), render directly
  const isSvg = ext === "svg" && content && content.trim().startsWith("<");
  // Try to render as base64 data URI if content exists
  const isBase64 = content && !isSvg && !content.includes("\n\n");
  const dataUri = isBase64 ? `data:${mime};base64,${content}` : null;

  return (
    <div className="fs-image-viewer">
      <div className="fs-image-preview">
        {isSvg ? (
          <div
            className="fs-image-svg"
            dangerouslySetInnerHTML={{ __html: content! }}
          />
        ) : dataUri ? (
          <img src={dataUri} alt={entry.name} className="fs-image-img" />
        ) : (
          <div className="fs-image-placeholder">
            <Image className="h-8 w-8" style={{ color: "var(--muted-foreground)" }} />
            <span>Preview not available</span>
          </div>
        )}
      </div>
      <div className="fs-metadata-grid">
        <div className="fs-meta-row">
          <span className="fs-meta-label">Filename</span>
          <span className="fs-meta-value">{entry.name}</span>
        </div>
        <div className="fs-meta-row">
          <span className="fs-meta-label">Type</span>
          <span className="fs-meta-value">{mime}</span>
        </div>
        <div className="fs-meta-row">
          <span className="fs-meta-label">Size</span>
          <span className="fs-meta-value">{formatSize(entry.size)}</span>
        </div>
        <div className="fs-meta-row">
          <span className="fs-meta-label">Modified</span>
          <span className="fs-meta-value">{formatTime(entry.modified)}</span>
        </div>
        {entry.permissions && (
          <div className="fs-meta-row">
            <span className="fs-meta-label">Permissions</span>
            <span className="fs-meta-value fs-mono">{entry.permissions}</span>
          </div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   MARKDOWN VIEWER
   ═══════════════════════════════════════════ */
function MarkdownViewer({ content }: { content: string }) {
  // Simple markdown-to-html: headings, bold, italic, code, links, lists
  const html = content
    .replace(/^### (.+)$/gm, '<h3 style="font-size:var(--font-lg);font-weight:600;margin:12px 0 4px">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 style="font-size:16px;font-weight:600;margin:16px 0 6px">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 style="font-size:18px;font-weight:600;margin:20px 0 8px">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, '<code class="code-inline">$1</code>')
    .replace(/^\- (.+)$/gm, '<li style="margin-left:16px;list-style:disc">$1</li>')
    .replace(/^\d+\. (.+)$/gm, '<li style="margin-left:16px;list-style:decimal">$1</li>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" style="color:var(--color-blue);text-decoration:underline">$1</a>')
    .replace(/\n\n/g, "<br/><br/>")
    .replace(/\n/g, "<br/>");

  return (
    <div className="fs-markdown" dangerouslySetInnerHTML={{ __html: html }} />
  );
}

/* ═══════════════════════════════════════════
   JSON VIEWER
   ═══════════════════════════════════════════ */
function JsonViewer({ content }: { content: string }) {
  let formatted = content;
  try {
    formatted = JSON.stringify(JSON.parse(content), null, 2);
  } catch { /* keep raw */ }
  return <CodeViewer content={formatted} fileName="data.json" editing={false} onChange={() => {}} />;
}

/* ═══════════════════════════════════════════
   BREADCRUMB
   ═══════════════════════════════════════════ */
function Breadcrumb({
  path,
  onNavigate,
}: {
  path: string;
  onNavigate: (path: string) => void;
}) {
  const parts = path.split("/").filter(Boolean);
  return (
    <div className="fs-breadcrumb">
      <button className="fs-breadcrumb-part" onClick={() => onNavigate("/")}>
        /
      </button>
      {parts.map((part, i) => {
        const fullPath = "/" + parts.slice(0, i + 1).join("/");
        return (
          <React.Fragment key={fullPath}>
            <span className="fs-breadcrumb-sep">/</span>
            <button className="fs-breadcrumb-part" onClick={() => onNavigate(fullPath)}>
              {part}
            </button>
          </React.Fragment>
        );
      })}
    </div>
  );
}

/* ═══════════════════════════════════════════
   MAIN FILES PANEL
   ═══════════════════════════════════════════ */
export function FilesPanel() {
  const [rootPath, setRootPath] = useState("/opt/setupo");
  const [tree, setTree] = useState<TreeEntry[]>([]);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set(["/opt/setupo"]));
  const [selectedEntry, setSelectedEntry] = useState<TreeEntry | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [editBuffer, setEditBuffer] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);
  const [treeLoading, setTreeLoading] = useState(false);

  // Load tree
  const loadTree = useCallback(async (path: string) => {
    setTreeLoading(true);
    try {
      const res = await getFileTree(path, 2);
      if (res.children) {
        setTree(res.children);
      } else if (res.items) {
        setTree(res.items);
      }
    } catch {
      // Fallback: use listFiles
      try {
        const res = await listFiles(path);
        setTree((res.items || []).map((item: any) => ({
          ...item,
          children: item.type === "dir" ? [] : undefined,
        })));
      } catch { setTree([]); }
    }
    setTreeLoading(false);
  }, []);

  useEffect(() => { loadTree(rootPath); }, [rootPath, loadTree]);

  // Load dir children
  const loadDirChildren = async (dirPath: string) => {
    try {
      const res = await getFileTree(dirPath, 1);
      const children = res.children || res.items || [];
      setTree((prev) => updateTreeChildren(prev, dirPath, children));
    } catch {
      try {
        const res = await listFiles(dirPath);
        setTree((prev) => updateTreeChildren(prev, dirPath, res.items || []));
      } catch {}
    }
  };

  function updateTreeChildren(nodes: TreeEntry[], targetPath: string, children: TreeEntry[]): TreeEntry[] {
    return nodes.map((node) => {
      if (node.path === targetPath) {
        return { ...node, children };
      }
      if (node.children) {
        return { ...node, children: updateTreeChildren(node.children, targetPath, children) };
      }
      return node;
    });
  }

  // Toggle dir expand
  const toggleDir = async (path: string) => {
    setExpandedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) { next.delete(path); } else { next.add(path); }
      return next;
    });
    // Load children if needed
    const node = findNode(tree, path);
    if (node && node.type === "dir" && (!node.children || node.children.length === 0)) {
      await loadDirChildren(path);
    }
  };

  function findNode(nodes: TreeEntry[], path: string): TreeEntry | null {
    for (const n of nodes) {
      if (n.path === path) return n;
      if (n.children) {
        const found = findNode(n.children, path);
        if (found) return found;
      }
    }
    return null;
  }

  // Select file/dir
  const selectEntry = async (entry: TreeEntry) => {
    setSelectedEntry(entry);
    setEditing(false);
    setFileContent(null);

    if (entry.type === "file") {
      const kind = getFileKind(entry.name);
      if (kind === "binary") return; // Don't try to read binary

      setLoading(true);
      try {
        const res = await readFile(entry.path);
        setFileContent(res.content);
        setEditBuffer(res.content);
        // Update size from response
        if (res.size) entry.size = res.size;
      } catch {
        setFileContent(null);
      }
      setLoading(false);
    }
  };

  // Save file
  const handleSave = async () => {
    if (!selectedEntry) return;
    setSaving(true);
    try {
      await writeFile(selectedEntry.path, editBuffer);
      setFileContent(editBuffer);
      setEditing(false);
    } catch (err: any) {
      alert(`Save failed: ${err.message}`);
    }
    setSaving(false);
  };

  // Delete file
  const handleDelete = async () => {
    if (!selectedEntry) return;
    if (!confirm(`Delete ${selectedEntry.name}?`)) return;
    try {
      await deleteFile(selectedEntry.path);
      setSelectedEntry(null);
      setFileContent(null);
      loadTree(rootPath);
    } catch (err: any) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  // Copy content
  const handleCopy = () => {
    if (fileContent) {
      navigator.clipboard.writeText(fileContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // Start editing
  const startEditing = () => {
    setEditBuffer(fileContent || "");
    setEditing(true);
  };

  // Cancel editing
  const cancelEdit = () => {
    setEditing(false);
    setEditBuffer(fileContent || "");
  };

  // Navigate from breadcrumb
  const navigateToPath = (path: string) => {
    setRootPath(path);
    setExpandedDirs(new Set([path]));
    setSelectedEntry(null);
    setFileContent(null);
  };

  // Determine what to render
  const kind = selectedEntry ? getFileKind(selectedEntry.name) : null;
  const isViewableFile = selectedEntry?.type === "file" && kind !== "binary";
  const isEditableFile = isViewableFile && (kind === "code" || kind === "text" || kind === "json" || kind === "markdown");

  return (
    <div className="fs-panel">
      {/* ─── File Tree Sidebar ─── */}
      <div className="fs-tree">
        <div className="fs-tree-header">
          <Breadcrumb path={rootPath} onNavigate={navigateToPath} />
          <button className="ibtn" onClick={() => loadTree(rootPath)} aria-label="Refresh">
            <RefreshCw className={cn("h-3 w-3", treeLoading && "animate-spin")} />
          </button>
        </div>
        <div className="fs-tree-list">
          {tree.length === 0 && !treeLoading && (
            <div className="fs-tree-empty">Empty</div>
          )}
          {tree.map((entry) => (
            <TreeNode
              key={entry.path}
              entry={entry}
              depth={0}
              selectedPath={selectedEntry?.path || null}
              onSelect={selectEntry}
              onToggle={toggleDir}
              expandedDirs={expandedDirs}
            />
          ))}
        </div>
      </div>

      {/* ─── File Viewer ─── */}
      <div className="fs-viewer">
        {!selectedEntry ? (
          <div className="fs-viewer-empty">
            <FolderOpen className="h-8 w-8" style={{ color: "var(--muted-foreground)", opacity: 0.4 }} />
            <span>Select a file to preview</span>
          </div>
        ) : selectedEntry.type === "dir" ? (
          <div className="fs-viewer-empty">
            <FolderOpen className="h-8 w-8" style={{ color: "var(--color-blue)", opacity: 0.5 }} />
            <span className="fs-viewer-empty-name">{selectedEntry.name}</span>
            <span>Directory</span>
          </div>
        ) : loading ? (
          <div className="fs-viewer-empty">
            <span>Loading...</span>
          </div>
        ) : (
          <>
            {/* Toolbar */}
            <div className="fs-toolbar">
              <div className="fs-toolbar-left">
                {getFileIcon(selectedEntry.name, selectedEntry.type)}
                <span className="fs-toolbar-name">{selectedEntry.name}</span>
                {selectedEntry.size != null && (
                  <span className="fs-toolbar-meta">{formatSize(selectedEntry.size)}</span>
                )}
                {selectedEntry.permissions && (
                  <span className="fs-toolbar-meta fs-mono">{selectedEntry.permissions}</span>
                )}
              </div>
              <div className="fs-toolbar-actions">
                {editing ? (
                  <>
                    <button className="fs-btn primary" onClick={handleSave} disabled={saving}>
                      <Save className="h-3 w-3" />
                      <span>{saving ? "Saving..." : "Save"}</span>
                    </button>
                    <button className="fs-btn" onClick={cancelEdit}>
                      <X className="h-3 w-3" />
                      <span>Cancel</span>
                    </button>
                  </>
                ) : (
                  <>
                    {isEditableFile && (
                      <button className="fs-btn" onClick={startEditing}>
                        <Pencil className="h-3 w-3" />
                        <span>Edit</span>
                      </button>
                    )}
                    {fileContent && (
                      <button className="fs-btn" onClick={handleCopy}>
                        {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                        <span>{copied ? "Copied" : "Copy"}</span>
                      </button>
                    )}
                    <button className="fs-btn danger" onClick={handleDelete}>
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Content */}
            <div className="fs-content">
              {kind === "binary" ? (
                <div className="fs-viewer-empty">
                  <File className="h-8 w-8" style={{ color: "var(--muted-foreground)" }} />
                  <span className="fs-viewer-empty-name">{selectedEntry.name}</span>
                  <span>Binary file — preview not available</span>
                  <div className="fs-metadata-grid" style={{ marginTop: 12 }}>
                    <div className="fs-meta-row">
                      <span className="fs-meta-label">Size</span>
                      <span className="fs-meta-value">{formatSize(selectedEntry.size)}</span>
                    </div>
                    <div className="fs-meta-row">
                      <span className="fs-meta-label">Modified</span>
                      <span className="fs-meta-value">{formatTime(selectedEntry.modified)}</span>
                    </div>
                  </div>
                </div>
              ) : kind === "image" ? (
                <ImageViewer entry={selectedEntry} content={fileContent} />
              ) : kind === "markdown" && !editing && fileContent ? (
                <MarkdownViewer content={fileContent} />
              ) : kind === "json" && !editing && fileContent ? (
                <JsonViewer content={fileContent} />
              ) : fileContent != null ? (
                <CodeViewer
                  content={editing ? editBuffer : fileContent}
                  fileName={selectedEntry.name}
                  editing={editing}
                  onChange={setEditBuffer}
                />
              ) : (
                <div className="fs-viewer-empty">
                  <span>Could not load file content</span>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
