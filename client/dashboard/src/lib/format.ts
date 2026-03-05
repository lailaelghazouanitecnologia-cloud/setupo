export function formatSize(bytes?: number): string {
  if (!bytes) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

export function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const secs = Math.floor(Math.max(0, diff) / 1000);
  if (secs < 60) return secs < 5 ? "just now" : `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function formatNum(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function fmtCents(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  return `${sign}$${(Math.abs(cents) / 100).toFixed(2)}`;
}

export function stateColor(state: string): string {
  if (state === "ready" || state === "active" || state === "running") return "var(--color-green)";
  if (state === "creating" || state === "installing" || state === "deploying") return "var(--color-yellow)";
  if (state === "stopped") return "var(--muted-foreground)";
  return "var(--color-red)";
}

export function stateBadgeClass(state: string): string {
  if (state === "ready" || state === "active" || state === "running") return "green";
  if (state === "creating" || state === "installing" || state === "deploying") return "yellow";
  return "red";
}
