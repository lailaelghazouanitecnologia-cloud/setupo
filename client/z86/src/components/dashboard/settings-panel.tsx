"use client";

import { useZ86Store } from "@/stores/z86-store";
import { Sun, Moon, Monitor } from "lucide-react";
import type { Theme } from "@/stores/z86-store";

export function SettingsPanel() {
  const store = useZ86Store();

  const themes: { value: Theme; label: string; icon: typeof Sun }[] = [
    { value: "light", label: "Light", icon: Sun },
    { value: "dark", label: "Dark", icon: Moon },
    { value: "auto", label: "System", icon: Monitor },
  ];

  return (
    <div className="panel">
      <div className="panel-section">
        <h2 className="panel-title">Settings</h2>

        <div className="settings-group">
          <h3 className="panel-subtitle">Theme</h3>
          <div className="theme-options">
            {themes.map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                className={`theme-option ${store.theme === value ? "active" : ""}`}
                onClick={() => store.setTheme(value)}
              >
                <Icon size={16} />
                <span>{label}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="settings-group">
          <h3 className="panel-subtitle">Account</h3>
          <div className="detail-grid">
            <div className="detail-row">
              <span className="detail-label">Email</span>
              <span className="detail-value">{store.userEmail}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Role</span>
              <span className="detail-value">{store.userRole}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Project ID</span>
              <code className="detail-value">{store.projectId || "—"}</code>
            </div>
          </div>
        </div>

        <div className="settings-group">
          <h3 className="panel-subtitle">Danger Zone</h3>
          <button className="btn-danger-outline" onClick={() => store.logout()}>
            Sign out
          </button>
        </div>
      </div>
    </div>
  );
}
