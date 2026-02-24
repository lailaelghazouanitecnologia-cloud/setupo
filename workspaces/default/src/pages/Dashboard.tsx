import { useEffect, useState } from "react";
import {
  getHealth,
  listServices,
  listWorkspaces,
  type Service,
  type Workspace,
} from "../lib/api";
import { cn } from "../lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import {
  Activity,
  Server,
  HardDrive,
  FolderGit2,
  Play,
  Square,
  Cpu,
  Clock,
} from "lucide-react";

interface HealthData {
  status: string;
  uptime?: number;
  cpu_percent?: number;
  memory_percent?: number;
  disk_percent?: number;
  disk_used?: number;
  disk_total?: number;
  version?: string;
}

function formatUptime(seconds?: number): string {
  if (!seconds) return "N/A";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function formatBytes(bytes?: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let val = bytes;
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i++;
  }
  return `${val.toFixed(1)} ${units[i]}`;
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  accent,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  sub?: string;
  accent?: string;
}) {
  return (
    <Card className="py-4 gap-3">
      <CardContent className="px-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-lg",
                accent || "bg-primary/10"
              )}
            >
              <Icon className={cn("h-4 w-4", accent ? "text-white" : "text-primary")} />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className="text-lg font-semibold text-foreground">{value}</p>
            </div>
          </div>
        </div>
        {sub && (
          <p className="mt-2 text-xs text-muted-foreground">{sub}</p>
        )}
      </CardContent>
    </Card>
  );
}

function ProgressBar({
  value,
  max = 100,
  className,
}: {
  value: number;
  max?: number;
  className?: string;
}) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className={cn("h-2 w-full rounded-full bg-secondary", className)}>
      <div
        className={cn(
          "h-full rounded-full transition-all duration-500",
          pct > 80 ? "bg-destructive" : pct > 60 ? "bg-yellow-500" : "bg-primary"
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export default function Dashboard() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [services, setServices] = useState<Service[]>([]);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([
      getHealth().then((d) => setHealth(d as HealthData)),
      listServices().then((d) => setServices(d.services)),
      listWorkspaces().then((d) => setWorkspaces(d.workspaces)),
    ]).finally(() => setLoading(false));
  }, []);

  const runningServices = services.filter((s) => s.status === "running");

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-2 text-muted-foreground text-sm">
          <Activity className="h-4 w-4 animate-pulse" />
          Loading dashboard...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-lg font-semibold text-foreground">Dashboard</h2>
        <p className="text-sm text-muted-foreground">System overview and quick actions</p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={Activity}
          label="System Status"
          value={health?.status === "ok" ? "Online" : "Offline"}
          sub={`Uptime: ${formatUptime(health?.uptime)}`}
          accent={health?.status === "ok" ? "bg-green-500/20" : "bg-red-500/20"}
        />
        <StatCard
          icon={Server}
          label="Services"
          value={`${runningServices.length} / ${services.length}`}
          sub={`${runningServices.length} running`}
          accent="bg-blue-500/20"
        />
        <StatCard
          icon={FolderGit2}
          label="Workspaces"
          value={workspaces.length}
          sub={`${workspaces.filter((w) => w.is_git).length} git repos`}
          accent="bg-purple-500/20"
        />
        <StatCard
          icon={Cpu}
          label="CPU Usage"
          value={health?.cpu_percent != null ? `${health.cpu_percent.toFixed(1)}%` : "N/A"}
          sub={`Memory: ${health?.memory_percent != null ? `${health.memory_percent.toFixed(1)}%` : "N/A"}`}
          accent="bg-orange-500/20"
        />
      </div>

      {/* Two column layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Services */}
        <Card className="py-4 gap-3">
          <CardHeader className="px-4 py-0">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Server className="h-4 w-4 text-muted-foreground" />
              Running Services
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4">
            {runningServices.length === 0 ? (
              <p className="text-sm text-muted-foreground">No services running</p>
            ) : (
              <div className="space-y-2">
                {runningServices.slice(0, 6).map((svc) => (
                  <div
                    key={svc.id}
                    className="flex items-center justify-between rounded-lg border bg-background/50 px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <Play className="h-3 w-3 text-green-400" />
                      <span className="text-sm font-medium text-foreground">
                        {svc.name}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      {svc.port && (
                        <Badge variant="outline" className="text-xs font-mono">
                          :{svc.port}
                        </Badge>
                      )}
                      <Badge variant="highlight" className="text-xs">
                        running
                      </Badge>
                    </div>
                  </div>
                ))}
                {runningServices.length > 6 && (
                  <p className="text-xs text-muted-foreground text-center pt-1">
                    +{runningServices.length - 6} more
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Workspaces */}
        <Card className="py-4 gap-3">
          <CardHeader className="px-4 py-0">
            <CardTitle className="flex items-center gap-2 text-sm">
              <FolderGit2 className="h-4 w-4 text-muted-foreground" />
              Workspaces
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4">
            {workspaces.length === 0 ? (
              <p className="text-sm text-muted-foreground">No workspaces</p>
            ) : (
              <div className="space-y-2">
                {workspaces.slice(0, 6).map((ws) => (
                  <div
                    key={ws.name}
                    className="flex items-center justify-between rounded-lg border bg-background/50 px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <FolderGit2 className="h-3 w-3 text-purple-400" />
                      <span className="text-sm font-medium text-foreground">
                        {ws.name}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      {ws.branch && (
                        <Badge variant="outline" className="text-xs font-mono">
                          {ws.branch}
                        </Badge>
                      )}
                      {ws.is_git && (
                        <Badge variant="secondary" className="text-xs">
                          git
                        </Badge>
                      )}
                    </div>
                  </div>
                ))}
                {workspaces.length > 6 && (
                  <p className="text-xs text-muted-foreground text-center pt-1">
                    +{workspaces.length - 6} more
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Disk Usage */}
      {health && (
        <Card className="py-4 gap-3">
          <CardHeader className="px-4 py-0">
            <CardTitle className="flex items-center gap-2 text-sm">
              <HardDrive className="h-4 w-4 text-muted-foreground" />
              Disk Usage
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4">
            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">
                  {formatBytes(health.disk_used)} / {formatBytes(health.disk_total)}
                </span>
                <span className="font-mono text-foreground">
                  {health.disk_percent != null ? `${health.disk_percent.toFixed(1)}%` : "N/A"}
                </span>
              </div>
              <ProgressBar value={health.disk_percent ?? 0} />
              <div className="flex items-center gap-4 text-xs text-muted-foreground">
                <div className="flex items-center gap-1.5">
                  <Clock className="h-3 w-3" />
                  <span>Version: {health.version || "unknown"}</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
