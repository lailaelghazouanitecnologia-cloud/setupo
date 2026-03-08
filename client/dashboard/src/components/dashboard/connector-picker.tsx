"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  Github, Cloud, MessageSquare, Cable,
  Plus, Settings2, ChevronRight, ChevronDown,
  X, Loader2, Check, Circle, Eye, EyeOff,
} from "lucide-react";
import {
  listAddons, installAddon, updateAddon,
  testConnector, getConnectorStatus,
  type AddonInfo,
} from "@/lib/api/client";
import { useDashboardStore } from "@/stores/dashboard-store";

/* ═══════════════════════════════════════════
   CONNECTOR PICKER — Dropdown + Setup Modal
   ═══════════════════════════════════════════ */

/* ── Connector definitions ── */

interface ConnectorDef {
  id: string;
  name: string;
  description: string;
  icon: React.ElementType;
  fields: { key: string; label: string; placeholder: string; secret?: boolean }[];
  steps: string[];
}

const CONNECTORS: ConnectorDef[] = [
  {
    id: "github",
    name: "GitHub",
    description: "Connect repositories, trigger deploys on push, and sync code directly.",
    icon: Github,
    fields: [
      { key: "token", label: "Personal Access Token", placeholder: "ghp_xxxxxxxxxxxx", secret: true },
    ],
    steps: ["Authorize Account", "Select Repositories"],
  },
  {
    id: "s3",
    name: "Amazon S3",
    description: "External S3-compatible object storage for files, assets, and backups.",
    icon: Cloud,
    fields: [
      { key: "endpoint", label: "Endpoint URL", placeholder: "https://xxx.r2.cloudflarestorage.com" },
      { key: "access_key", label: "Access Key", placeholder: "AKIA...", secret: true },
      { key: "secret_key", label: "Secret Key", placeholder: "wJalr...", secret: true },
      { key: "bucket", label: "Bucket Name", placeholder: "my-bucket" },
    ],
    steps: ["Enter Credentials", "Verify Connection"],
  },
  {
    id: "slack",
    name: "Slack",
    description: "Deploy notifications, alerts, and status updates to Slack channels.",
    icon: MessageSquare,
    fields: [
      { key: "bot_token", label: "Bot Token", placeholder: "xoxb-xxxx", secret: true },
      { key: "webhook_url", label: "Webhook URL (optional)", placeholder: "https://hooks.slack.com/services/..." },
    ],
    steps: ["Enter Token", "Test Connection"],
  },
];

/* ═══════════════════════════════════════════
   MAIN EXPORT — Connector Button + Popover
   ═══════════════════════════════════════════ */

export function ConnectorPicker({ projectId }: { projectId: string }) {
  const [open, setOpen] = useState(false);
  const [setupConnector, setSetupConnector] = useState<ConnectorDef | null>(null);
  const [connectorStates, setConnectorStates] = useState<Record<string, AddonInfo>>({});
  const [loading, setLoading] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);
  const setActiveView = useDashboardStore((s) => s.setActiveView);

  // Close dropdown on outside click (only when dropdown is open, not modal)
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Load connector states
  const loadStates = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const res = await listAddons(projectId, "connector");
      const map: Record<string, AddonInfo> = {};
      for (const a of res.addons || []) {
        if (a.installed) map[a.addon_id] = a;
      }
      setConnectorStates(map);
    } catch {}
    setLoading(false);
  }, [projectId]);

  useEffect(() => {
    if (open) loadStates();
  }, [open, loadStates]);

  const handleToggle = async (connectorId: string, enabled: boolean) => {
    try {
      await updateAddon(projectId, connectorId, { enabled }, "connector");
      setConnectorStates((prev) => ({
        ...prev,
        [connectorId]: { ...prev[connectorId], enabled },
      }));
    } catch {}
  };

  const handleConnectorClick = (def: ConnectorDef) => {
    const state = connectorStates[def.id];
    // Open setup modal for both new and existing connectors
    setOpen(false);
    setSetupConnector(def);
  };

  const handleSetupComplete = () => {
    setSetupConnector(null);
    setOpen(true);
    loadStates();
  };

  return (
    <div className="cp-root" ref={popoverRef}>
      {/* Trigger button */}
      <button
        className={`cp-trigger ${open ? "active" : ""}`}
        onClick={() => { setOpen(!open); setSetupConnector(null); }}
        title="Connectors"
      >
        <Cable className="h-4 w-4" />
      </button>

      {/* Dropdown list */}
      {open && !setupConnector && (
        <div className="cp-dropdown">
          <div className="cp-dropdown-header">
            <span className="cp-dropdown-title">Connectors</span>
            <button className="cp-dropdown-close" onClick={() => setOpen(false)}>
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="cp-list">
            {loading ? (
              <div className="cp-list-loading">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading...
              </div>
            ) : (
              CONNECTORS.map((def) => {
                const state = connectorStates[def.id];
                const installed = state?.installed;
                const enabled = state?.enabled;
                const Icon = def.icon;

                return (
                  <div key={def.id}>
                    <div
                      className="cp-item"
                      onClick={() => handleConnectorClick(def)}
                    >
                      <div className="cp-item-left">
                        <div className="cp-item-icon">
                          <Icon className="h-4 w-4" />
                        </div>
                        <span className="cp-item-name">{def.name}</span>
                      </div>
                      {installed ? (
                        <button
                          className="cp-toggle"
                          onClick={(e) => { e.stopPropagation(); handleToggle(def.id, !enabled); }}
                        >
                          <div className={`cp-toggle-track ${enabled ? "on" : ""}`}>
                            <span className="cp-toggle-thumb" />
                          </div>
                        </button>
                      ) : (
                        <span className="cp-item-action">Connect</span>
                      )}
                    </div>

                    {/* Sub-items for connected connectors */}
                    {installed && def.id === "github" && (
                      <div className="cp-subitem" onClick={() => handleConnectorClick(def)}>
                        <div className="cp-subitem-icon">
                          <ChevronRight className="h-3.5 w-3.5" style={{ transform: "rotate(90deg) scaleX(-1)" }} />
                        </div>
                        <span className="cp-subitem-name">Repositories</span>
                        <ChevronRight className="h-3.5 w-3.5 cp-subitem-arrow" />
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>

          {/* Footer */}
          <div className="cp-footer">
            <div className="cp-footer-item" onClick={() => { setOpen(false); setActiveView("addons"); }}>
              <div className="cp-footer-icon">
                <Settings2 className="h-4 w-4" />
              </div>
              <span className="cp-footer-label">Manage connectors</span>
            </div>
          </div>
        </div>
      )}

      {/* Setup modal */}
      {setupConnector && (
        <ConnectorSetupModal
          connector={setupConnector}
          projectId={projectId}
          existingState={connectorStates[setupConnector.id]}
          onClose={() => setSetupConnector(null)}
          onComplete={handleSetupComplete}
        />
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════
   SETUP MODAL — Full-screen overlay
   ═══════════════════════════════════════════ */

function ConnectorSetupModal({
  connector,
  projectId,
  existingState,
  onClose,
  onComplete,
}: {
  connector: ConnectorDef;
  projectId: string;
  existingState?: AddonInfo;
  onClose: () => void;
  onComplete: () => void;
}) {
  const Icon = connector.icon;
  const [step, setStep] = useState(0); // 0 = config form, 1 = testing
  const [values, setValues] = useState<Record<string, string>>(() => {
    const v: Record<string, string> = {};
    const existingConfig = existingState?.config || {};
    const cfg = typeof existingConfig === "string" ? (() => { try { return JSON.parse(existingConfig); } catch { return {}; } })() : existingConfig;
    for (const f of connector.fields) v[f.key] = (cfg as any)[f.key] || "";
    return v;
  });
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [error, setError] = useState("");

  const allFilled = connector.fields
    .filter((f) => !f.placeholder.includes("optional"))
    .every((f) => values[f.key]?.trim());

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      const config: Record<string, string> = {};
      for (const f of connector.fields) {
        if (values[f.key]?.trim()) config[f.key] = values[f.key].trim();
      }
      if (existingState?.installed) {
        await updateAddon(projectId, connector.id, { config }, "connector");
      } else {
        await installAddon(projectId, connector.id, "connector", config);
      }
      setStep(1);
      // Auto-test
      setTesting(true);
      try {
        const res = await testConnector(projectId, connector.id);
        setTestResult(res);
      } catch (e: any) {
        setTestResult({ ok: false, message: e.message || "Test failed" });
      }
      setTesting(false);
    } catch (e: any) {
      setError(e.message || "Failed to save");
    }
    setSaving(false);
  };

  return (
    <div className="cp-modal-overlay" onClick={onClose}>
      <div className="cp-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header close */}
        <div className="cp-modal-header">
          <button className="cp-modal-close" onClick={onClose}>
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="cp-modal-body">
          {/* Icon + title */}
          <div className="cp-modal-hero">
            <div className="cp-modal-icon-box">
              <Icon className="h-10 w-10" />
            </div>
            <div className="cp-modal-title">{connector.name}</div>
            <div className="cp-modal-desc">{connector.description}</div>
          </div>

          {/* Steps indicator */}
          <div className="cp-steps">
            {connector.steps.map((s, i) => (
              <React.Fragment key={i}>
                <div className="cp-step">
                  {i < step ? (
                    <div className="cp-step-done">
                      <Check className="h-3.5 w-3.5" />
                    </div>
                  ) : i === step ? (
                    <div className="cp-step-active">
                      <Circle className="h-3 w-3" />
                    </div>
                  ) : (
                    <Circle className="h-4 w-4 cp-step-pending" />
                  )}
                  <span className={`cp-step-label ${i <= step ? "active" : ""}`}>{s}</span>
                </div>
                {i < connector.steps.length - 1 && <div className="cp-step-line" />}
              </React.Fragment>
            ))}
          </div>

          {/* Step 0: Config form */}
          {step === 0 && (
            <div className="cp-form">
              {connector.fields.map((f) => (
                <div key={f.key} className="cp-field">
                  <label className="cp-field-label">{f.label}</label>
                  <div className="cp-field-input-wrap">
                    <input
                      type={f.secret && !showSecrets[f.key] ? "password" : "text"}
                      value={values[f.key]}
                      onChange={(e) => setValues((prev) => ({ ...prev, [f.key]: e.target.value }))}
                      placeholder={f.placeholder}
                      className="cp-field-input"
                      autoComplete="off"
                    />
                    {f.secret && (
                      <button
                        className="cp-field-eye"
                        onClick={() => setShowSecrets((prev) => ({ ...prev, [f.key]: !prev[f.key] }))}
                        type="button"
                      >
                        {showSecrets[f.key] ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                      </button>
                    )}
                  </div>
                </div>
              ))}

              {error && <div className="cp-form-error">{error}</div>}

              <div className="cp-form-actions">
                <button className="cp-btn-secondary" onClick={onClose}>
                  Cancel
                </button>
                <button
                  className="cp-btn-primary"
                  disabled={!allFilled || saving}
                  onClick={handleSave}
                >
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : "Connect"}
                </button>
              </div>
            </div>
          )}

          {/* Step 1: Test results */}
          {step === 1 && (
            <div className="cp-test">
              {testing ? (
                <div className="cp-test-loading">
                  <Loader2 className="h-5 w-5 animate-spin" />
                  <span>Testing connection...</span>
                </div>
              ) : testResult ? (
                <div className={`cp-test-result ${testResult.ok ? "ok" : "fail"}`}>
                  {testResult.ok ? (
                    <Check className="h-5 w-5" />
                  ) : (
                    <X className="h-5 w-5" />
                  )}
                  <span>{testResult.message}</span>
                </div>
              ) : null}

              <div className="cp-form-actions">
                <button className="cp-btn-secondary" onClick={() => setStep(0)}>
                  Back
                </button>
                <button className="cp-btn-primary" onClick={onComplete}>
                  {testResult?.ok ? "Done" : "Close"}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Show details toggle */}
        <button className="cp-details-toggle">
          <span>Show Details</span>
          <ChevronDown className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
