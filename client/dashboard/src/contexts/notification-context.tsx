"use client";

import React, { createContext, useContext, useCallback, useState, type ReactNode } from "react";

// ── Types ──────────────────────────────────────────────────

export type ToastType = "success" | "error" | "info" | "warning";

export interface Toast {
  id: string;
  type: ToastType;
  message: string;
  duration?: number;
}

interface NotificationState {
  toasts: Toast[];
}

interface NotificationActions {
  toast: (type: ToastType, message: string, duration?: number) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
  warning: (message: string) => void;
  dismiss: (id: string) => void;
  clearAll: () => void;
}

type NotificationContextValue = NotificationState & NotificationActions;

// ── Context ────────────────────────────────────────────────

const NotificationContext = createContext<NotificationContextValue | null>(null);

export function useNotification(): NotificationContextValue {
  const ctx = useContext(NotificationContext);
  if (!ctx) throw new Error("useNotification must be used within <NotificationProvider>");
  return ctx;
}

// ── Provider ───────────────────────────────────────────────

let toastCounter = 0;

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const addToast = useCallback((type: ToastType, message: string, duration = 4000) => {
    const id = `toast_${++toastCounter}`;
    const toast: Toast = { id, type, message, duration };
    setToasts((t) => [...t, toast]);
    if (duration > 0) {
      setTimeout(() => dismiss(id), duration);
    }
  }, [dismiss]);

  const value: NotificationContextValue = {
    toasts,
    toast: addToast,
    success: useCallback((msg: string) => addToast("success", msg), [addToast]),
    error: useCallback((msg: string) => addToast("error", msg, 6000), [addToast]),
    info: useCallback((msg: string) => addToast("info", msg), [addToast]),
    warning: useCallback((msg: string) => addToast("warning", msg, 5000), [addToast]),
    dismiss,
    clearAll: useCallback(() => setToasts([]), []),
  };

  return (
    <NotificationContext.Provider value={value}>
      {children}
      {/* Toast container */}
      {toasts.length > 0 && (
        <div className="toast-container">
          {toasts.map((t) => (
            <div key={t.id} className={`toast toast-${t.type}`}>
              <span className="toast-msg">{t.message}</span>
              <button className="toast-close" onClick={() => dismiss(t.id)}>&times;</button>
            </div>
          ))}
        </div>
      )}
    </NotificationContext.Provider>
  );
}
