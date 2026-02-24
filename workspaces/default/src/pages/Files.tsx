import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import {
  listDir,
  readFile,
  writeFile,
  deleteFile,
  mkDir,
  type FSItem,
} from "../lib/api";
import { cn } from "../lib/utils";
import { Card, CardContent } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../components/ui/dialog";
import {
  File,
  Folder,
  ChevronRight,
  Save,
  Plus,
  Trash2,
  ArrowLeft,
  Loader2,
  FolderPlus,
  FilePlus,
  X,
  Home,
} from "lucide-react";

function formatSize(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return "-";
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let val = bytes;
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i++;
  }
  return `${val.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatDate(ts: number | null): string {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function Files() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = useState<FSItem[]>([]);
  const [currentPath, setCurrentPath] = useState(searchParams.get("path") || "");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Editor state
  const [editingFile, setEditingFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [fileOriginal, setFileOriginal] = useState("");
  const [saving, setSaving] = useState(false);
  const [fileLoading, setFileLoading] = useState(false);

  // Create dialog state
  const [createDialog, setCreateDialog] = useState<"file" | "dir" | null>(null);
  const [createName, setCreateName] = useState("");
  const [creating, setCreating] = useState(false);

  // Delete dialog state
  const [deleteTarget, setDeleteTarget] = useState<FSItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  const navigate = useCallback(
    (path: string) => {
      setCurrentPath(path);
      setSearchParams(path ? { path } : {});
      setEditingFile(null);
    },
    [setSearchParams]
  );

  const fetchDir = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await listDir(currentPath || undefined);
      setItems(data.items);
      // Update current path from server response in case of normalization
      if (data.path && data.path !== currentPath) {
        setCurrentPath(data.path);
      }
    } catch (e: any) {
      setError(e.message || "Failed to list directory");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [currentPath]);

  useEffect(() => {
    fetchDir();
  }, [fetchDir]);

  // Sync URL params to state
  useEffect(() => {
    const p = searchParams.get("path") || "";
    if (p !== currentPath) {
      setCurrentPath(p);
    }
  }, [searchParams]);

  const openItem = (item: FSItem) => {
    if (item.type === "dir") {
      navigate(item.path);
    } else {
      openFile(item.path);
    }
  };

  const openFile = async (path: string) => {
    setFileLoading(true);
    try {
      const data = await readFile(path);
      setEditingFile(path);
      setFileContent(data.content);
      setFileOriginal(data.content);
    } catch (e: any) {
      setError(e.message || "Failed to read file");
    } finally {
      setFileLoading(false);
    }
  };

  const handleSave = async () => {
    if (!editingFile) return;
    setSaving(true);
    try {
      await writeFile(editingFile, fileContent);
      setFileOriginal(fileContent);
    } catch (e: any) {
      setError(e.message || "Failed to save file");
    } finally {
      setSaving(false);
    }
  };

  const goUp = () => {
    if (!currentPath) return;
    const parts = currentPath.replace(/\/$/, "").split("/");
    parts.pop();
    navigate(parts.join("/") || "/");
  };

  const handleCreate = async () => {
    if (!createName.trim()) return;
    setCreating(true);
    try {
      const path = currentPath
        ? `${currentPath.replace(/\/$/, "")}/${createName.trim()}`
        : createName.trim();

      if (createDialog === "dir") {
        await mkDir(path);
      } else {
        await writeFile(path, "");
      }
      setCreateDialog(null);
      setCreateName("");
      fetchDir();
    } catch (e: any) {
      setError(e.message || "Failed to create");
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteFile(deleteTarget.path);
      setDeleteTarget(null);
      if (editingFile === deleteTarget.path) {
        setEditingFile(null);
      }
      fetchDir();
    } catch (e: any) {
      setError(e.message || "Failed to delete");
    } finally {
      setDeleting(false);
    }
  };

  // Build breadcrumb
  const breadcrumbs = currentPath
    ? currentPath
        .replace(/\/$/, "")
        .split("/")
        .filter(Boolean)
    : [];

  const isDirty = editingFile && fileContent !== fileOriginal;

  // Sort items: dirs first, then files, alphabetical
  const sorted = [...items].sort((a, b) => {
    if (a.type === "dir" && b.type !== "dir") return -1;
    if (a.type !== "dir" && b.type === "dir") return 1;
    return a.name.localeCompare(b.name);
  });

  return (
    <div className="h-full flex flex-col space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Files</h2>
          <p className="text-sm text-muted-foreground">Browse and edit files</p>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            className="gap-1 text-xs"
            onClick={() => setCreateDialog("file")}
          >
            <FilePlus className="h-3.5 w-3.5" />
            New File
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="gap-1 text-xs"
            onClick={() => setCreateDialog("dir")}
          >
            <FolderPlus className="h-3.5 w-3.5" />
            New Dir
          </Button>
        </div>
      </div>

      {/* Breadcrumb */}
      <div className="flex items-center gap-1 text-sm overflow-x-auto">
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2 shrink-0"
          onClick={() => navigate("")}
        >
          <Home className="h-3.5 w-3.5" />
        </Button>
        {currentPath && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 shrink-0"
            onClick={goUp}
          >
            <ArrowLeft className="h-3.5 w-3.5" />
          </Button>
        )}
        {breadcrumbs.map((part, i) => {
          const path = "/" + breadcrumbs.slice(0, i + 1).join("/");
          return (
            <div key={i} className="flex items-center shrink-0">
              <ChevronRight className="h-3 w-3 text-muted-foreground mx-0.5" />
              <button
                onClick={() => navigate(path)}
                className={cn(
                  "px-1.5 py-0.5 rounded text-xs hover:bg-accent transition-colors",
                  i === breadcrumbs.length - 1
                    ? "text-foreground font-medium"
                    : "text-muted-foreground"
                )}
              >
                {part}
              </button>
            </div>
          );
        })}
      </div>

      {error && (
        <div className="flex items-center justify-between rounded-lg border border-destructive/50 bg-destructive/10 px-3 py-2">
          <p className="text-sm text-destructive">{error}</p>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={() => setError("")}
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex gap-4 min-h-0">
        {/* File list */}
        <Card className={cn("flex-1 py-0 gap-0 overflow-hidden", editingFile && "max-w-sm")}>
          <ScrollArea className="h-full">
            {loading ? (
              <div className="flex items-center justify-center h-32">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : sorted.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-32 gap-2">
                <Folder className="h-8 w-8 text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground">Empty directory</p>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {sorted.map((item) => (
                  <div
                    key={item.path}
                    className={cn(
                      "flex items-center gap-3 px-3 py-2 hover:bg-accent/30 cursor-pointer transition-colors group",
                      editingFile === item.path && "bg-accent/50"
                    )}
                    onClick={() => openItem(item)}
                  >
                    {item.type === "dir" ? (
                      <Folder className="h-4 w-4 text-blue-400 shrink-0" />
                    ) : (
                      <File className="h-4 w-4 text-muted-foreground shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <span className="text-sm text-foreground truncate block">
                        {item.name}
                      </span>
                    </div>
                    <span className="text-xs text-muted-foreground shrink-0 hidden sm:block">
                      {formatSize(item.size)}
                    </span>
                    <span className="text-xs text-muted-foreground shrink-0 hidden md:block">
                      {formatDate(item.modified)}
                    </span>
                    <span className="text-xs text-muted-foreground font-mono shrink-0 hidden lg:block">
                      {item.permissions}
                    </span>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteTarget(item);
                      }}
                    >
                      <Trash2 className="h-3 w-3 text-destructive" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </Card>

        {/* Editor panel */}
        {editingFile && (
          <Card className="flex-1 py-0 gap-0 overflow-hidden flex flex-col min-w-0">
            {/* Editor header */}
            <div className="flex items-center justify-between px-3 py-2 border-b bg-background/50">
              <div className="flex items-center gap-2 min-w-0">
                <File className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                <span className="text-xs text-foreground truncate font-mono">
                  {editingFile.split("/").pop()}
                </span>
                {isDirty && (
                  <Badge variant="secondary" className="text-[10px] px-1.5">
                    modified
                  </Badge>
                )}
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1 text-xs"
                  onClick={handleSave}
                  disabled={saving || !isDirty}
                >
                  {saving ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Save className="h-3 w-3" />
                  )}
                  Save
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={() => setEditingFile(null)}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>

            {/* Editor body */}
            {fileLoading ? (
              <div className="flex-1 flex items-center justify-center">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <textarea
                value={fileContent}
                onChange={(e) => setFileContent(e.target.value)}
                className="flex-1 w-full resize-none bg-transparent text-sm text-foreground font-mono p-3 outline-none leading-relaxed"
                spellCheck={false}
                onKeyDown={(e) => {
                  // Ctrl/Cmd + S to save
                  if ((e.ctrlKey || e.metaKey) && e.key === "s") {
                    e.preventDefault();
                    handleSave();
                  }
                  // Handle Tab key for indentation
                  if (e.key === "Tab") {
                    e.preventDefault();
                    const start = e.currentTarget.selectionStart;
                    const end = e.currentTarget.selectionEnd;
                    const val = e.currentTarget.value;
                    setFileContent(
                      val.substring(0, start) + "  " + val.substring(end)
                    );
                    requestAnimationFrame(() => {
                      e.currentTarget.selectionStart = start + 2;
                      e.currentTarget.selectionEnd = start + 2;
                    });
                  }
                }}
              />
            )}
          </Card>
        )}
      </div>

      {/* Create dialog */}
      <Dialog
        open={createDialog !== null}
        onOpenChange={(open) => {
          if (!open) {
            setCreateDialog(null);
            setCreateName("");
          }
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {createDialog === "dir" ? "Create Directory" : "Create File"}
            </DialogTitle>
            <DialogDescription>
              {createDialog === "dir"
                ? "Enter the name for the new directory."
                : "Enter the name for the new file."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label>Name</Label>
            <Input
              placeholder={createDialog === "dir" ? "new-folder" : "new-file.txt"}
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setCreateDialog(null);
                setCreateName("");
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              disabled={!createName.trim() || creating}
            >
              {creating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete dialog */}
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete {deleteTarget?.type === "dir" ? "Directory" : "File"}</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete{" "}
              <span className="font-mono text-foreground">{deleteTarget?.name}</span>?
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
