"use client";
import { useZ86Store } from "@/stores/z86-store";
import { OverviewPanel } from "./panels/overview";
import { BucketsPanel } from "./panels/buckets";
import { ObjectsPanel } from "./panels/objects";
import { KeysPanel } from "./panels/keys";
import { UsagePanel } from "./panels/usage";
import { SettingsPanel } from "./panels/settings";

type PanelId = "overview" | "buckets" | "keys" | "usage" | "settings";
const NAV_ITEMS: { id: PanelId; label: string; icon: string }[] = [
  { id: "overview", label: "Overview", icon: "⊞" },
  { id: "buckets", label: "Buckets", icon: "◫" },
  { id: "keys", label: "Keys", icon: "⚿" },
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
      <div className="dash-inner">
        <nav className="dash-sidebar">
          <div className="dash-sidebar-inner">
            {/* ── top line: brand ── */}
            <div className="dash-line dash-line-brand">
              <span className="dash-brand">
                <svg width="18" height="18" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <rect x="8" y="8" width="84" height="84" rx="16" stroke="currentColor" strokeWidth="6" />
                  <rect x="24" y="28" width="52" height="10" rx="5" fill="currentColor" opacity={0.3} />
                  <rect x="24" y="45" width="52" height="10" rx="5" fill="currentColor" opacity={0.6} />
                  <rect x="24" y="62" width="52" height="10" rx="5" fill="currentColor" />
                </svg>
                <span>z86</span>
              </span>
            </div>

            {/* ── nav line: items ── */}
            <div className="dash-line dash-line-nav">
              {NAV_ITEMS.map((item) => (
                <button
                  key={item.id}
                  className={`dash-btn${panel === item.id ? " dash-btn-active" : ""}`}
                  onClick={() => setPanel(item.id)}
                >
                  <span className="dash-btn-label">
                    <span className="dash-btn-icon">{item.icon}</span>
                    <span>{item.label}</span>
                  </span>
                </button>
              ))}
            </div>

            <div className="dash-spacer" />

            {/* ── bottom line: user ── */}
            <div className="dash-line dash-line-user">
              <div className="dash-btn dash-btn-user">
                <span className="dash-btn-label">
                  <span className="dash-avatar">
                    {(user?.name || user?.email || "?")[0].toUpperCase()}
                  </span>
                  <span className="dash-user-text">
                    <span className="dash-user-name">{user?.name || "User"}</span>
                    <span className="dash-user-email">{user?.email}</span>
                  </span>
                </span>
                <span className="dash-btn-suffix">
                  <button className="dash-logout" onClick={logout} title="Sign out">↗</button>
                </span>
              </div>
            </div>
          </div>
        </nav>

        <main className="dash-content">
          <div className="dash-content-inner">
            {renderPanel()}
          </div>
        </main>
      </div>
    </div>
  );
}
