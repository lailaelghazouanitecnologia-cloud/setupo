import { Routes, Route, NavLink, Navigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { hasToken, getHealth } from "./lib/api";
import { cn } from "./lib/utils";
import Dashboard from "./pages/Dashboard";
import Services from "./pages/Services";
import Workspaces from "./pages/Workspaces";
import Files from "./pages/Files";
import Terminal from "./pages/Terminal";
import Login from "./pages/Login";
import {
  LayoutDashboard,
  Server,
  FolderGit2,
  FileCode,
  TerminalSquare,
  LogOut,
} from "lucide-react";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/services", label: "Services", icon: Server },
  { to: "/workspaces", label: "Workspaces", icon: FolderGit2 },
  { to: "/files", label: "Files", icon: FileCode },
  { to: "/terminal", label: "Terminal", icon: TerminalSquare },
];

export default function App() {
  const [authed, setAuthed] = useState(hasToken());
  const [online, setOnline] = useState(false);

  useEffect(() => {
    if (!authed) return;
    const check = () =>
      getHealth()
        .then(() => setOnline(true))
        .catch(() => setOnline(false));
    check();
    const id = setInterval(check, 10_000);
    return () => clearInterval(id);
  }, [authed]);

  const handleLogout = () => {
    localStorage.removeItem("mms_token");
    setAuthed(false);
  };

  if (!authed) {
    return <Login onLogin={() => setAuthed(true)} />;
  }

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="w-[220px] bg-sidebar border-r border-sidebar-border flex flex-col shrink-0">
        {/* Brand */}
        <div className="px-5 py-4 border-b border-sidebar-border">
          <h1 className="text-base font-bold text-sidebar-primary tracking-widest">
            mms
          </h1>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            micro module system
          </p>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-3 px-3 space-y-0.5">
          {NAV.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                    isActive
                      ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                      : "text-muted-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
                  )
                }
              >
                <Icon className="h-4 w-4 shrink-0" />
                {item.label}
              </NavLink>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="px-3 py-3 border-t border-sidebar-border space-y-2">
          {/* Status indicator */}
          <div className="flex items-center gap-2 px-3 py-1.5">
            <span
              className={cn(
                "inline-block w-2 h-2 rounded-full",
                online ? "bg-green-400" : "bg-red-400"
              )}
            />
            <span className="text-xs text-muted-foreground">
              {online ? "Online" : "Offline"}
            </span>
          </div>

          {/* Logout button */}
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-muted-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-foreground transition-colors w-full"
          >
            <LogOut className="h-4 w-4 shrink-0" />
            Sign Out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <div className="h-full p-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/services" element={<Services />} />
            <Route path="/workspaces" element={<Workspaces />} />
            <Route path="/files" element={<Files />} />
            <Route path="/terminal" element={<Terminal />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
