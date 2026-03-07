"use client";

import type { ReactNode } from "react";
import { AdminAuthProvider } from "./admin-auth-context";
import { NotificationProvider } from "./notification-context";

/**
 * Root provider tree for admin dashboard.
 * Auth → Notification
 */
export function Providers({ children }: { children: ReactNode }) {
  return (
    <AdminAuthProvider>
      <NotificationProvider>
        {children}
      </NotificationProvider>
    </AdminAuthProvider>
  );
}
