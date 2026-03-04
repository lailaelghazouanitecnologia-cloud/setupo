"use client";

import { useState, useEffect, useCallback } from "react";
import { useZ86Store } from "@/stores/z86-store";
import { getMe, getProjects, getStorageInfo, provisionStorage } from "@/lib/api/client";
import type { DashboardView } from "@/types/dashboard";
import {
  Database,
  FolderOpen,
  Key,
  BarChart3,
  Settings,
  LogOut,
  Menu,
  Sun,
  Moon,
  ChevronDown,
  LayoutDashboard,
} from "lucide-react";
import { OverviewPanel } from "./overview-panel";
import { BucketsPanel } from "./buckets-panel";
import { ObjectsPanel } from "./objects-panel";
import { KeysPanel } from "./keys-panel";
import { UsagePanel } from "./usage-panel";
import { SettingsPanel } from "./settings-panel";

const Z86Logo = ({ size = 18 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="8" y="8" width="84" height="84" rx="16" stroke="currentColor" strokeWidth="6" />
    <rect x="24" y="28" width="52" height="10" rx="5" fill="currentColor" opacity="0.3" />
    <rect x="24" y="45" width="52" height="10" rx="5" fill="currentColor" opacity="0.6" />
    <rect x="24" y="62" width="52" height="10" rx="5" fill="currentColor" />
  </svg>
);

const NAV_ITEMS: { view: DashboardView; label: string; icon: typeof Database }[] = [
  { view: "overview", label: "Overview", icon: LayoutDashboard },
  { view: "buckets", label: "Buckets", icon: Database },
  { view: "objects", label: "Object Browser", icon: FolderOpen },
  { view: "keys", label: "Access Keys", icon: Key },
  { view: "usage", label: "Usage", icon: BarChart3 },
  { view: "settings", label: "Settings", icon: Settings },
];

export function DashboardLayout() {
  const store = useZ86Store();
  const [storageInfo, setStorageInfo] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const init = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      // Get user info
      const me = await getMe();
      store.setUser(me.email, me.role);

      // Find or use stored project
      let projectId = store.projectId;
      if (!projectId) {
        const projects = await getProjects();
        if (projects.length > 0) {
          projectId = projects[0].id;
          store.setProjectId(projectId);
        }
      }

      if (projectId) {
        try {
          const info = await getStorageInfo(projectId);
          setStorageInfo(info);
          store.setBucketName(info.bucket);
          store.setAccessKeyId(info.access_key_id);
        } catch {
          // Storage not provisioned yet — auto-provision
          try {
            const info = await provisionStorage(projectId);
            setStorageInfo(info);
            store.setBucketName(info.bucket);
            store.setAccessKeyId(info.access_key_id);
          } catch (provErr: any) {
            setError("Could not provision storage: " + provErr.message);
          }
        }
      }
    } catch (err: any) {
      if (err.message?.includes("401")) {
        store.logout();
        return;
      }
      setError(err.message);
    }
    setLoading(false);
  }, []);

  useEffect(() => { init(); }, [init]);

  const renderPanel = () => {
    if (loading) return <div className="panel-loading">Loading...</div>;
    if (error) return <div className="panel-error">{error}</div>;

    switch (store.activeView) {
      case "overview": return <OverviewPanel storageInfo={storageInfo} />;
      case "buckets": return <BucketsPanel />;
      case "objects": return <ObjectsPanel />;
      case "keys": return <KeysPanel />;
      case "usage": return <UsagePanel />;
      case "settings": return <SettingsPanel />;
      default: return <OverviewPanel storageInfo={storageInfo} />;
    }
  };

  return (
    <div className="dash-root">
      {/* Sidebar */}
      <aside className={`dash-sidebar ${store.sidebarOpen ? "open" : "closed"}`}>
        <div className="dash-sidebar-header">
          <Z86Logo />
          <span className="dash-sidebar-brand">z86</span>
        </div>

        <div className="dash-sidebar-nav">
          {NAV_ITEMS.map(({ view, label, icon: Icon }) => (
            <button
              key={view}
              className={`dash-nav-item ${store.activeView === view ? "active" : ""}`}
              onClick={() => store.setActiveView(view)}
            >
              <Icon size={15} />
              <span>{label}</span>
            </button>
          ))}
        </div>

        <div className="dash-sidebar-footer">
          <div className="dash-user-info">
            <span className="dash-user-email">{store.userEmail}</span>
          </div>
          <button className="dash-nav-item" onClick={() => store.logout()}>
            <LogOut size={15} />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="dash-main">
        <header className="dash-header">
          <div className="dash-header-left">
            <button className="dash-menu-btn" onClick={() => store.toggleSidebar()}>
              <Menu size={16} />
            </button>
            <h1 className="dash-header-title">
              {NAV_ITEMS.find((n) => n.view === store.activeView)?.label || "Overview"}
            </h1>
          </div>
          <div className="dash-header-right">
            {store.bucketName && (
              <span className="dash-bucket-badge">
                <Database size={12} />
                {store.bucketName}
              </span>
            )}
            <button
              className="dash-theme-btn"
              onClick={() => store.setTheme(store.theme === "dark" ? "light" : "dark")}
            >
              {store.theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
            </button>
          </div>
        </header>

        <div className="dash-content">
          {renderPanel()}
        </div>
      </div>
    </div>
  );
}
