import { useEffect, useState, useCallback, useRef } from "react";
import {
  listServices,
  createService,
  stopService,
  restartService,
  deleteService,
  getServiceLogs,
  type Service,
  type CreateServiceInput,
} from "../lib/api";
import { cn } from "../lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { Label } from "../components/ui/label";
import { ScrollArea } from "../components/ui/scroll-area";
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
  Play,
  Square,
  RotateCcw,
  Trash2,
  Plus,
  Terminal,
  ChevronDown,
  ChevronUp,
  Server,
  Loader2,
} from "lucide-react";

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { variant: "highlight" | "destructive" | "secondary" | "outline"; label: string }> = {
    running: { variant: "highlight", label: "running" },
    stopped: { variant: "secondary", label: "stopped" },
    failed: { variant: "destructive", label: "failed" },
    starting: { variant: "outline", label: "starting" },
  };
  const info = map[status] || { variant: "outline" as const, label: status };
  return <Badge variant={info.variant} className="text-xs">{info.label}</Badge>;
}

function ServiceRow({
  svc,
  onRefresh,
}: {
  svc: Service;
  onRefresh: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchLogs = useCallback(async () => {
    try {
      const data = await getServiceLogs(svc.name, 200);
      setLogs(data.logs);
    } catch {
      // ignore
    }
  }, [svc.name]);

  useEffect(() => {
    if (expanded) {
      setLogsLoading(true);
      fetchLogs().finally(() => setLogsLoading(false));
      pollingRef.current = setInterval(fetchLogs, 3000);
    } else {
      if (pollingRef.current) clearInterval(pollingRef.current);
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [expanded, fetchLogs]);

  useEffect(() => {
    if (expanded) {
      logEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, expanded]);

  const act = async (action: string) => {
    setActionLoading(action);
    try {
      if (action === "stop") await stopService(svc.name);
      if (action === "restart") await restartService(svc.name);
      if (action === "delete") {
        await deleteService(svc.name);
      }
      onRefresh();
    } catch {
      // ignore
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="rounded-lg border bg-card overflow-hidden">
      {/* Row header */}
      <div className="flex items-center gap-3 px-4 py-3">
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-muted-foreground hover:text-foreground transition-colors"
        >
          {expanded ? (
            <ChevronUp className="h-4 w-4" />
          ) : (
            <ChevronDown className="h-4 w-4" />
          )}
        </button>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-foreground truncate">
              {svc.name}
            </span>
            <StatusBadge status={svc.status} />
          </div>
          <p className="text-xs text-muted-foreground font-mono truncate mt-0.5">
            {svc.command}
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs text-muted-foreground shrink-0">
          {svc.port && (
            <Badge variant="outline" className="font-mono text-xs">
              :{svc.port}
            </Badge>
          )}
          {svc.pid && (
            <span className="font-mono">PID {svc.pid}</span>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {svc.status === "running" && (
            <>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => act("stop")}
                disabled={actionLoading !== null}
                title="Stop"
              >
                {actionLoading === "stop" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Square className="h-3.5 w-3.5" />
                )}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => act("restart")}
                disabled={actionLoading !== null}
                title="Restart"
              >
                {actionLoading === "restart" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RotateCcw className="h-3.5 w-3.5" />
                )}
              </Button>
            </>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-destructive hover:text-destructive"
            onClick={() => act("delete")}
            disabled={actionLoading !== null}
            title="Delete"
          >
            {actionLoading === "delete" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Trash2 className="h-3.5 w-3.5" />
            )}
          </Button>
        </div>
      </div>

      {/* Expandable logs */}
      {expanded && (
        <div className="border-t">
          <div className="flex items-center gap-2 px-4 py-2 bg-background/50">
            <Terminal className="h-3 w-3 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">
              Logs ({logs.length} lines)
            </span>
          </div>
          <ScrollArea className="h-56">
            <div className="p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap bg-background/30">
              {logsLoading ? (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Loading logs...
                </div>
              ) : logs.length === 0 ? (
                <span className="text-muted-foreground">No log output</span>
              ) : (
                logs.map((line, i) => (
                  <div key={i} className="text-foreground/80 hover:text-foreground hover:bg-accent/30 px-1 -mx-1 rounded">
                    {line}
                  </div>
                ))
              )}
              <div ref={logEndRef} />
            </div>
          </ScrollArea>
        </div>
      )}
    </div>
  );
}

export default function Services() {
  const [services, setServices] = useState<Service[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<CreateServiceInput>({
    name: "",
    command: "",
    working_dir: "",
    port: undefined,
  });
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    listServices()
      .then((d) => setServices(d.services))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  const handleCreate = async () => {
    if (!form.name.trim() || !form.command.trim()) return;
    setCreating(true);
    setError("");
    try {
      const input: CreateServiceInput = {
        name: form.name.trim(),
        command: form.command.trim(),
      };
      if (form.working_dir?.trim()) input.working_dir = form.working_dir.trim();
      if (form.port) input.port = form.port;
      await createService(input);
      setDialogOpen(false);
      setForm({ name: "", command: "", working_dir: "", port: undefined });
      refresh();
    } catch (e: any) {
      setError(e.message || "Failed to create service");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Services</h2>
          <p className="text-sm text-muted-foreground">
            Manage running processes and services
          </p>
        </div>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button size="sm" className="gap-1.5">
              <Plus className="h-4 w-4" />
              New Service
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Create Service</DialogTitle>
              <DialogDescription>
                Start a new background process or service.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div className="space-y-2">
                <Label>Name</Label>
                <Input
                  placeholder="my-service"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label>Command</Label>
                <Input
                  placeholder="python app.py"
                  value={form.command}
                  onChange={(e) => setForm({ ...form, command: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label>Working Directory</Label>
                <Input
                  placeholder="/home/user/project (optional)"
                  value={form.working_dir || ""}
                  onChange={(e) =>
                    setForm({ ...form, working_dir: e.target.value })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label>Port</Label>
                <Input
                  type="number"
                  placeholder="8080 (optional)"
                  value={form.port ?? ""}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      port: e.target.value ? parseInt(e.target.value) : undefined,
                    })
                  }
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
                onClick={handleCreate}
                disabled={!form.name.trim() || !form.command.trim() || creating}
              >
                {creating ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Creating...
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4" />
                    Create
                  </>
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Service List */}
      {loading ? (
        <div className="flex items-center justify-center h-32">
          <div className="flex items-center gap-2 text-muted-foreground text-sm">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading services...
          </div>
        </div>
      ) : services.length === 0 ? (
        <Card className="py-12">
          <CardContent className="flex flex-col items-center gap-3">
            <Server className="h-10 w-10 text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground">No services yet</p>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setDialogOpen(true)}
              className="gap-1.5"
            >
              <Plus className="h-4 w-4" />
              Create your first service
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {services.map((svc) => (
            <ServiceRow key={svc.id} svc={svc} onRefresh={refresh} />
          ))}
        </div>
      )}
    </div>
  );
}
