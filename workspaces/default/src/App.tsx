import { Routes, Route, NavLink, Navigate } from "react-router-dom";
import { Box, Flex, Text, Badge } from "@radix-ui/themes";
import { useEffect, useState } from "react";
import { hasToken, getHealth } from "./lib/api";
import Overview from "./pages/Overview";
import Capsules from "./pages/Capsules";
import Environments from "./pages/Environments";
import Terminal from "./pages/Terminal";
import Protocol from "./pages/Protocol";
import Login from "./pages/Login";

const NAV = [
  { to: "/", label: "Overview" },
  { to: "/capsules", label: "Capsules" },
  { to: "/environments", label: "Environments" },
  { to: "/terminal", label: "Terminal" },
  { to: "/protocol", label: "Protocol" },
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

  if (!authed) {
    return (
      <Login
        onLogin={() => {
          setAuthed(true);
        }}
      />
    );
  }

  return (
    <Flex className="h-screen">
      {/* Sidebar */}
      <Box className="w-52 bg-[var(--color-bg2)] border-r border-[var(--color-border)] flex flex-col shrink-0">
        <Box className="p-4 border-b border-[var(--color-border)]">
          <Text size="5" weight="bold" className="text-[var(--color-accent2)] tracking-widest">
            mms
          </Text>
          <Text size="1" className="block text-[var(--color-dim)]">
            micro module system
          </Text>
        </Box>

        <nav className="flex-1 py-2">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `block px-4 py-2 text-sm border-l-2 transition-colors ${
                  isActive
                    ? "border-[var(--color-accent)] bg-[var(--color-bg3)] text-[var(--color-accent2)]"
                    : "border-transparent text-[var(--color-dim)] hover:bg-[var(--color-bg3)]"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <Box className="p-3 border-t border-[var(--color-border)] text-xs flex items-center gap-2">
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              online ? "bg-green-400" : "bg-red-400"
            }`}
          />
          <Text size="1" className="text-[var(--color-dim)]">
            {online ? "Online" : "Offline"}
          </Text>
        </Box>
      </Box>

      {/* Main */}
      <Box className="flex-1 overflow-y-auto p-6 bg-[var(--color-bg)]">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/capsules" element={<Capsules />} />
          <Route path="/environments" element={<Environments />} />
          <Route path="/terminal" element={<Terminal />} />
          <Route path="/protocol" element={<Protocol />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </Box>
    </Flex>
  );
}
