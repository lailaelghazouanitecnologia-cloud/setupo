import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  listWorkspaces,
  cloneWorkspace,
  pullWorkspace,
  deleteWorkspace,
  type Workspace,
} from "../lib/api";
import { cn } from "../lib/utils";
import { Card, CardContent } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { Label } from "../components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogTrigger,
} from "../components/ui/dialog";
import {
  FolderGit2,
  GitBranch,
  RefreshCw,
  Trash2,
  Plus,
  ExternalLink,
  Loader2,
  FolderOpen,
  Clock,
} from "lucide-react";

function formatRelativeTime(ts: number): string {
  if (!ts) return "unknown";
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function Workspaces() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [cloning, setCloning] = useState(false);
  const [pullLoading, setPullLoading] = useState<string | null>(null);
  const [deleteLoading, setDeleteLoading] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ repo: "", branch: "main", name: "" });
  const navigate = useNavigate();

  const refresh = useCallback(() => {
    listWorkspaces()
      .then((d) => setWorkspaces(d.workspaces))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleClone = async () => {
    if (!form.repo.trim()) return;
    setCloning(true);
    setError("");
    try {
      await cloneWorkspace(
        form.repo.trim(),
        form.branch.trim() || "main",
        form.name.trim() || undefined
      );
      setDialogOpen(false);
      setForm({ repo: "", branch: "main", name: "" });
      refresh();
    } catch (e: any) {
      setError(e.message || "Clone failed");
    } finally {
      setCloning(false);
    }
  };

  const handlePull = async (name: string) => {
    setPullLoading(name);
    try {
      await pullWorkspace(name);
      refresh();
    } catch {
      // ignore
    } finally {
      setPullLoading(null);
    }
  };

  const handleDelete = async (name: string) => {
    setDeleteLoading(name);
    try {
      await deleteWorkspace(name);
      refresh();
    } catch {
      // ignore
    } finally {
      setDeleteLoading(null);
    }
  };

  const openFiles = (ws: Workspace) => {
    navigate(`/files?path=${encodeURIComponent(ws.path)}`);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Workspaces</h2>
          <p className="text-sm text-muted-foreground">
            Manage code repositories and project directories
          </p>
        </div>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button size="sm" className="gap-1.5">
              <Plus className="h-4 w-4" />
              Clone Repo
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Clone Repository</DialogTitle>
              <DialogDescription>
                Clone a git repository into a new workspace.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div className="space-y-2">
                <Label>Repository URL</Label>
                <Input
                  placeholder="https://github.com/user/repo.git"
                  value={form.repo}
                  onChange={(e) => setForm({ ...form, repo: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label>Branch</Label>
                <Input
                  placeholder="main"
                  value={form.branch}
                  onChange={(e) => setForm({ ...form, branch: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label>Name (optional)</Label>
                <Input
                  placeholder="Auto-detected from repo URL"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </div>

              {error && (
                <p className="text-sm text-destructive">{error}</p>
              )}
            </div>

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setDialogOpen(false)}
              >
                Cancel
              </Button>
              <Button
                onClick={handleClone}
                disabled={!form.repo.trim() || cloning}
              >
                {cloning ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Cloning...
                  </>
                ) : (
                  <>
                    <FolderGit2 className="h-4 w-4" />
                    Clone
                  </>
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Workspace List */}
      {loading ? (
        <div className="flex items-center justify-center h-32">
          <div className="flex items-center gap-2 text-muted-foreground text-sm">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading workspaces...
          </div>
        </div>
      ) : workspaces.length === 0 ? (
        <Card className="py-12">
          <CardContent className="flex flex-col items-center gap-3">
            <FolderGit2 className="h-10 w-10 text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground">No workspaces yet</p>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setDialogOpen(true)}
              className="gap-1.5"
            >
              <Plus className="h-4 w-4" />
              Clone your first repo
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {workspaces.map((ws) => (
            <Card key={ws.name} className="py-0 gap-0 overflow-hidden">
              {/* Clickable workspace card body */}
              <button
                onClick={() => openFiles(ws)}
                className="w-full text-left px-4 py-4 hover:bg-accent/30 transition-colors"
              >
                <div className="flex items-start gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-purple-500/10 shrink-0 mt-0.5">
                    <FolderGit2 className="h-4 w-4 text-purple-400" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-foreground truncate">
                        {ws.name}
                      </span>
                      {ws.is_git && (
                        <Badge variant="secondary" className="text-[10px] px-1.5">
                          git
                        </Badge>
                      )}
                    </div>
                    {ws.repo && (
                      <p className="text-xs text-muted-foreground truncate mt-1">
                        {ws.repo}
                      </p>
                    )}
                    <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                      {ws.branch && (
                        <span className="flex items-center gap-1">
                          <GitBranch className="h-3 w-3" />
                          {ws.branch}
                        </span>
                      )}
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {formatRelativeTime(ws.modified)}
                      </span>
                    </div>
                  </div>
                  <ExternalLink className="h-3.5 w-3.5 text-muted-foreground/50 shrink-0 mt-1" />
                </div>
              </button>

              {/* Actions */}
              <div className="flex items-center gap-1 px-4 py-2 border-t bg-background/30">
                {ws.is_git && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 gap-1 text-xs"
                    onClick={() => handlePull(ws.name)}
                    disabled={pullLoading === ws.name}
                  >
                    {pullLoading === ws.name ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <RefreshCw className="h-3 w-3" />
                    )}
                    Pull
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1 text-xs"
                  onClick={() => openFiles(ws)}
                >
                  <FolderOpen className="h-3 w-3" />
                  Files
                </Button>
                <div className="flex-1" />
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1 text-xs text-destructive hover:text-destructive"
                  onClick={() => handleDelete(ws.name)}
                  disabled={deleteLoading === ws.name}
                >
                  {deleteLoading === ws.name ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Trash2 className="h-3 w-3" />
                  )}
                  Delete
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
