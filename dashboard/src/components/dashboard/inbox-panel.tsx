"use client";

import { useState } from "react";
import { Mail, Bell, AlertCircle, CheckCircle, Info, Clock } from "lucide-react";

interface InboxItem {
  id: string;
  type: "info" | "warning" | "success" | "alert";
  title: string;
  message: string;
  time: string;
  read: boolean;
}

const MOCK_ITEMS: InboxItem[] = [
  {
    id: "1",
    type: "success",
    title: "Deployment complete",
    message: "NSO API v1.2.0 deployed successfully to production",
    time: "2m ago",
    read: false,
  },
  {
    id: "2",
    type: "info",
    title: "System update available",
    message: "A new system update is available for your VPS instance",
    time: "1h ago",
    read: false,
  },
  {
    id: "3",
    type: "warning",
    title: "High memory usage",
    message: "Instance memory usage exceeded 85% threshold",
    time: "3h ago",
    read: true,
  },
  {
    id: "4",
    type: "alert",
    title: "SSL certificate expiring",
    message: "Certificate for zarnetti.com expires in 14 days",
    time: "1d ago",
    read: true,
  },
];

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

export function InboxPanel() {
  const [items, setItems] = useState<InboxItem[]>(MOCK_ITEMS);
  const [filter, setFilter] = useState<"all" | "unread">("all");

  const markRead = (id: string) => {
    setItems((prev) => prev.map((item) => (item.id === id ? { ...item, read: true } : item)));
  };

  const markAllRead = () => {
    setItems((prev) => prev.map((item) => ({ ...item, read: true })));
  };

  const filtered = filter === "unread" ? items.filter((i) => !i.read) : items;
  const unreadCount = items.filter((i) => !i.read).length;

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
          <button className="panel-btn-sm" onClick={markAllRead}>
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
            const Icon = TYPE_ICONS[item.type];
            return (
              <div
                key={item.id}
                className={`inbox-item ${!item.read ? "unread" : ""}`}
                onClick={() => markRead(item.id)}
              >
                <div className="inbox-icon" style={{ color: TYPE_COLORS[item.type] }}>
                  <Icon className="h-4 w-4" />
                </div>
                <div className="inbox-content">
                  <div className="inbox-title">{item.title}</div>
                  <div className="inbox-message">{item.message}</div>
                </div>
                <div className="inbox-time">
                  <Clock className="h-3 w-3" />
                  <span>{item.time}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
