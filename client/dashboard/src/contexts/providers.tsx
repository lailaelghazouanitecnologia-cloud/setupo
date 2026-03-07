"use client";

import type { ReactNode } from "react";
import { AuthProvider } from "./auth-context";
import { ProjectProvider } from "./project-context";
import { NotificationProvider } from "./notification-context";

/**
 * Root provider tree — wraps the app with all context providers.
 * Order matters: Auth → Project (depends on auth) → Notification (independent)
 */
export function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <ProjectProvider>
        <NotificationProvider>
          {children}
        </NotificationProvider>
      </ProjectProvider>
    </AuthProvider>
  );
}
