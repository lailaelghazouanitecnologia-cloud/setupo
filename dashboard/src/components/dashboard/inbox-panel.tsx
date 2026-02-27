"use client";

import { useState, useEffect, useCallback } from "react";
import { Mail, Bell, AlertCircle, CheckCircle, Info, Clock, Loader2, Trash2 } from "lucide-react";
import {
  listNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  deleteNotification,
  type Notification,
} from "@/lib/api/client";

const TYPE_ICONS = {
  info: Info,
  warning: AlertCircle,
  success: CheckCircle,
  alert: Bell,
};

const TYPE_COLORS = {
  info: "var(--color-blue)",
  warning: "var(--color-yellow)",
  success: "var(--color-green)",
  alert: "var(--color-red)",
};

function timeAgo(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diff = Math.max(0, now - then);
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function InboxPanel() {
  const [items, setItems] = useState<Notification[]>([]);
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await listNotifications();
      setItems(res.notifications);
      setError("");
    } catch (err: any) {
      setError(err.message || "Failed to load notifications");
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleMarkRead = async (id: string) => {
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
    try {
      await markNotificationRead(id);
    } catch {}
  };

  const handleMarkAllRead = async () => {
    setItems((prev) => prev.map((n) => ({ ...n, read: true })));
    try {
      await markAllNotificationsRead();
    } catch {}
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    setItems((prev) => prev.filter((n) => n.id !== id));
    try {
      await deleteNotification(id);
    } catch {}
  };

  const filtered = filter === "unread" ? items.filter((i) => !i.read) : items;
  const unreadCount = items.filter((i) => !i.read).length;

  if (loading) {
    return (
      <div className="panel-empty">
        <Loader2 className="h-6 w-6 animate-spin" style={{ color: "var(--muted-foreground)" }} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="panel-empty">
        <AlertCircle className="h-10 w-10" style={{ color: "var(--color-red)", opacity: 0.5 }} />
        <div className="panel-empty-title">Error</div>
        <div className="panel-empty-sub">{error}</div>
        <button className="panel-btn-sm" onClick={load} style={{ marginTop: 8 }}>Retry</button>
      </div>
    );
  }

  return (
    <div>
      <div className="inbox-header">
        <div className="inbox-filters">
          <button
            className={`inbox-filter ${filter === "all" ? "active" : ""}`}
            onClick={() => setFilter("all")}
          >
            All
          </button>
          <button
            className={`inbox-filter ${filter === "unread" ? "active" : ""}`}
            onClick={() => setFilter("unread")}
          >
            Unread{unreadCount > 0 && <span className="inbox-badge">{unreadCount}</span>}
          </button>
        </div>
        {unreadCount > 0 && (
          <button className="panel-btn-sm" onClick={handleMarkAllRead}>
            Mark all read
          </button>
        )}
      </div>

      {filtered.length === 0 ? (
        <div className="panel-empty">
          <Mail className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
          <div className="panel-empty-title">No notifications</div>
          <div className="panel-empty-sub">You're all caught up</div>
        </div>
      ) : (
        <div className="inbox-list">
          {filtered.map((item) => {
            const Icon = TYPE_ICONS[item.type] || Info;
            return (
              <div
                key={item.id}
                className={`inbox-item ${!item.read ? "unread" : ""}`}
                onClick={() => handleMarkRead(item.id)}
              >
                <div className="inbox-icon" style={{ color: TYPE_COLORS[item.type] || "var(--color-blue)" }}>
                  <Icon className="h-4 w-4" />
                </div>
                <div className="inbox-content">
                  <div className="inbox-title">{item.title}</div>
                  <div className="inbox-message">{item.message}</div>
                </div>
                <div className="inbox-time">
                  <Clock className="h-3 w-3" />
                  <span>{timeAgo(item.created_at)}</span>
                </div>
                <button
                  className="inbox-delete"
                  onClick={(e) => handleDelete(e, item.id)}
                  title="Delete"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
