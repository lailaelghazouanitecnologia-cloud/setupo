"use client";
import { useZ86Store } from "@/stores/z86-store";
import { OverviewPanel } from "./panels/overview";
import { BucketsPanel } from "./panels/buckets";
import { ObjectsPanel } from "./panels/objects";
import { KeysPanel } from "./panels/keys";
import { UsagePanel } from "./panels/usage";
import { SettingsPanel } from "./panels/settings";

const NAV_ITEMS: { id: any; label: string; icon: string }[] = [
  { id: "overview", label: "Overview", icon: "⊞" },
  { id: "buckets", label: "Buckets", icon: "◫" },
  { id: "keys", label: "API Keys", icon: "⚿" },
  { id: "usage", label: "Usage", icon: "◔" },
  { id: "settings", label: "Settings", icon: "⚙" },
];

export function DashboardLayout() {
  const { user, panel, setPanel, logout } = useZ86Store();

  const renderPanel = () => {
    switch (panel) {
      case "overview": return <OverviewPanel />;
      case "buckets": return <BucketsPanel />;
      case "objects": return <ObjectsPanel />;
      case "keys": return <KeysPanel />;
      case "usage": return <UsagePanel />;
      case "settings": return <SettingsPanel />;
      default: return <OverviewPanel />;
    }
  };

  return (
    <div className="dash">
      <nav className="dash-sidebar">
        <div className="dash-sidebar-header">
          <svg width="20" height="20" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="8" y="8" width="84" height="84" rx="16" stroke="currentColor" strokeWidth="6" />
            <rect x="24" y="28" width="52" height="10" rx="5" fill="currentColor" opacity={0.3} />
            <rect x="24" y="45" width="52" height="10" rx="5" fill="currentColor" opacity={0.6} />
            <rect x="24" y="62" width="52" height="10" rx="5" fill="currentColor" />
          </svg>
          <span>z86</span>
        </div>
        <div className="dash-sidebar-nav">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              className={`dash-nav-item ${panel === item.id ? "active" : ""}`}
              onClick={() => setPanel(item.id)}
            >
              <span className="dash-nav-icon">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </div>
        <div className="dash-sidebar-footer">
          <div className="dash-user-info">
            <span className="dash-user-avatar">{(user?.name || user?.email || "?")[0].toUpperCase()}</span>
            <div className="dash-user-details">
              <span className="dash-user-name">{user?.name || "User"}</span>
              <span className="dash-user-email">{user?.email}</span>
            </div>
          </div>
          <button className="dash-logout" onClick={logout} title="Sign out">↗</button>
        </div>
      </nav>
      <main className="dash-main">
        {renderPanel()}
      </main>
    </div>
  );
}
