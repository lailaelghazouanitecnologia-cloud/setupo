"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  Rocket, RefreshCw, Send, Square, Loader,
  MessageSquare, Plus, Trash2, ChevronDown, ChevronRight,
  Wrench, CheckCircle2, XCircle, AlertTriangle, Bot,
  Server,
} from "lucide-react";
import { useDashboardStore } from "@/stores/dashboard-store";
import {
  createDeployThread, listDeployThreads, getDeployThread,
  deleteDeployThread, streamDeployAgent,
  type DeployThread, type DeployMessage,
} from "@/lib/api/client";

/* ═══════════════════════════════════════════
   DEPLOY PANEL — AI Agent Chat
   ═══════════════════════════════════════════ */

export function DeployPanel() {
  const activeProject = useDashboardStore((s) => s.activeProject);
  const projectId = activeProject?.id || "";

  if (!projectId) {
    return (
      <div className="panel-empty">
        <Rocket className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-title">No project selected</div>
        <div className="panel-empty-sub">Select a project from the sidebar to deploy.</div>
      </div>
    );
  }

  return <DeployAgentChat projectId={projectId} />;
}

/* ═══════════════════════════════════════════
   AGENT CHAT
   ═══════════════════════════════════════════ */

interface StreamEvent {
  type: string;
  content?: string;
  reasoning?: string;
  id?: string;
  name?: string;
  arguments?: any;
  result?: string;
  error?: string;
  final_text?: string;
  steps?: number;
  step?: number;
  run_id?: string;
}

interface ChatMsg {
  id: string;
  role: "user" | "assistant" | "tool_call" | "tool_result";
  content: string;
  toolName?: string;
  toolArgs?: any;
  toolResult?: string;
  isError?: boolean;
}

function DeployAgentChat({ projectId }: { projectId: string }) {
  const [threads, setThreads] = useState<DeployThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [streamReasoning, setStreamReasoning] = useState("");
  const [activeToolCall, setActiveToolCall] = useState<{ name: string; args?: any } | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const abortRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, streamText, scrollToBottom]);

  // Load threads
  useEffect(() => {
    setLoading(true);
    setActiveThreadId(null);
    setMessages([]);
    listDeployThreads(projectId)
      .then((r) => {
        setThreads(r.threads || []);
        if (r.threads?.length > 0) setActiveThreadId(r.threads[0].id);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId]);

  // Load messages when thread changes
  useEffect(() => {
    if (!activeThreadId) { setMessages([]); return; }
    getDeployThread(projectId, activeThreadId)
      .then((t) => {
        const msgs = (t.messages || []).flatMap(dbMsgToChat);
        setMessages(msgs);
      })
      .catch(() => {});
  }, [activeThreadId, projectId]);

  const createThread = async () => {
    try {
      const t = await createDeployThread(projectId);
      setThreads((prev) => [t, ...prev]);
      setActiveThreadId(t.id);
      setMessages([]);
    } catch (e: any) {
      setError(e.message || "Failed to create thread");
    }
  };

  const deleteThread = async (id: string) => {
    try {
      await deleteDeployThread(projectId, id);
      setThreads((prev) => prev.filter((t) => t.id !== id));
      if (activeThreadId === id) {
        const remaining = threads.filter((t) => t.id !== id);
        setActiveThreadId(remaining.length > 0 ? remaining[0].id : null);
      }
    } catch {}
  };

  const stopStreaming = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  };

  const sendMessage = async () => {
    const content = input.trim();
    if (!content || streaming) return;
    if (!activeThreadId) {
      // Auto-create thread
      try {
        const t = await createDeployThread(projectId);
        setThreads((prev) => [t, ...prev]);
        setActiveThreadId(t.id);
        await doStream(t.id, content);
      } catch (e: any) {
        setError(e.message || "Failed to create thread");
      }
      return;
    }
    await doStream(activeThreadId, content);
  };

  const doStream = async (threadId: string, content: string) => {
    setInput("");
    setError("");
    setStreamText("");
    setStreamReasoning("");
    setActiveToolCall(null);
    setStreaming(true);

    // Add user message
    const userMsg: ChatMsg = { id: `u_${Date.now()}`, role: "user", content };
    setMessages((prev) => [...prev, userMsg]);

    const { eventSource, response } = streamDeployAgent(projectId, threadId, content);
    abortRef.current = eventSource;

    try {
      const resp = await response;
      if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        throw new Error(`Server error ${resp.status}: ${text}`);
      }

      const reader = resp.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";
      let accText = "";
      let accReasoning = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6).trim();
          if (data === "[DONE]") continue;

          let event: StreamEvent;
          try { event = JSON.parse(data); } catch { continue; }

          switch (event.type) {
            case "text_chunk":
              if (event.content) {
                accText += event.content;
                setStreamText(accText);
              }
              break;

            case "reasoning_chunk":
            case "thinking":
              if (event.reasoning || event.content) {
                accReasoning += event.reasoning || event.content || "";
                setStreamReasoning(accReasoning);
              }
              break;

            case "tool_call":
              setActiveToolCall({ name: event.name || "tool", args: event.arguments });
              // Flush any pending text
              if (accText) {
                setMessages((prev) => [...prev, { id: `a_${Date.now()}`, role: "assistant", content: accText }]);
                accText = "";
                setStreamText("");
              }
              setMessages((prev) => [...prev, {
                id: `tc_${event.id || Date.now()}`,
                role: "tool_call",
                content: `Calling ${event.name}...`,
                toolName: event.name,
                toolArgs: event.arguments,
              }]);
              break;

            case "tool_result":
              setActiveToolCall(null);
              setMessages((prev) => [...prev, {
                id: `tr_${event.id || Date.now()}`,
                role: "tool_result",
                content: event.result || "",
                toolName: event.name,
                toolResult: event.result,
              }]);
              break;

            case "error":
              setError(event.error || "Unknown error");
              break;

            case "status":
              if (event.final_text && !accText) {
                accText = event.final_text;
              }
              break;
          }
        }
      }

      // Finalize assistant message
      if (accText) {
        setMessages((prev) => [...prev, { id: `a_${Date.now()}`, role: "assistant", content: accText }]);
      }
    } catch (err: any) {
      if (err.name !== "AbortError") {
        setError(err.message || "Stream failed");
      }
    } finally {
      setStreaming(false);
      setStreamText("");
      setStreamReasoning("");
      setActiveToolCall(null);
      abortRef.current = null;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  if (loading) {
    return (
      <div className="panel-empty">
        <Loader className="h-6 w-6 animate-spin" style={{ color: "var(--muted-foreground)", opacity: 0.5 }} />
        <div className="panel-empty-sub">Loading deploy agent...</div>
      </div>
    );
  }

  return (
    <div className="agent-chat">
      {/* Thread sidebar */}
      <div className="agent-threads">
        <div className="agent-threads-header">
          <span className="agent-threads-title">Threads</span>
          <button className="btn-icon" onClick={createThread} title="New thread">
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="agent-threads-list">
          {threads.length === 0 ? (
            <div style={{ padding: "20px 10px", textAlign: "center", fontSize: "var(--font-xxs)", color: "var(--muted-foreground)" }}>
              No threads yet
            </div>
          ) : threads.map((t) => (
            <div
              key={t.id}
              className={`agent-thread-item ${activeThreadId === t.id ? "active" : ""}`}
              onClick={() => setActiveThreadId(t.id)}
            >
              <MessageSquare className="h-3 w-3" style={{ flexShrink: 0, opacity: 0.5 }} />
              <span className="agent-thread-title">{t.title || "New deploy"}</span>
              <button
                className="agent-thread-delete"
                onClick={(e) => { e.stopPropagation(); deleteThread(t.id); }}
                title="Delete"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Chat area */}
      <div className="agent-main">
        <div className="agent-messages">
          {messages.length === 0 && !streaming && (
            <div className="agent-empty">
              <Bot className="h-10 w-10" style={{ opacity: 0.15 }} />
              <div className="agent-empty-title">NSO Deploy Agent</div>
              <div className="agent-empty-sub">
                Tell me what you want to deploy. I can analyze your workspace, generate configs, build, and ship your project.
              </div>
              <div className="agent-suggestions">
                {["Deploy my app", "Analyze workspace", "Show instances", "Generate deploy.toml"].map((s) => (
                  <button key={s} className="agent-suggestion" onClick={() => { setInput(s); }}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <div key={msg.id} className={`agent-msg agent-msg-${msg.role}`}>
              {msg.role === "user" && (
                <div className="agent-msg-user-bubble">{msg.content}</div>
              )}
              {msg.role === "assistant" && (
                <div className="agent-msg-assistant">
                  <SimpleMarkdown text={msg.content} />
                </div>
              )}
              {msg.role === "tool_call" && (
                <ToolCallCard name={msg.toolName || ""} args={msg.toolArgs} />
              )}
              {msg.role === "tool_result" && (
                <ToolResultCard name={msg.toolName || ""} result={msg.toolResult || ""} />
              )}
            </div>
          ))}

          {/* Streaming state */}
          {streaming && (
            <div className="agent-msg agent-msg-assistant">
              {streamReasoning && (
                <div className="agent-reasoning">
                  <span className="agent-reasoning-label">Thinking...</span>
                  <div className="agent-reasoning-text">{streamReasoning}</div>
                </div>
              )}
              {activeToolCall && (
                <ToolCallCard name={activeToolCall.name} args={activeToolCall.args} isStreaming />
              )}
              {streamText ? (
                <div className="agent-msg-assistant">
                  <SimpleMarkdown text={streamText} />
                  <span className="agent-cursor" />
                </div>
              ) : !activeToolCall && !streamReasoning && (
                <div className="agent-thinking">
                  <Loader className="h-3.5 w-3.5 animate-spin" />
                  <span>Thinking...</span>
                </div>
              )}
            </div>
          )}

          {error && (
            <div className="agent-error">
              <AlertTriangle className="h-3.5 w-3.5" />
              <span>{error}</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="agent-input-area">
          <div className="agent-input-wrap">
            <textarea
              ref={textareaRef}
              className="agent-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Tell the agent what to deploy..."
              disabled={streaming}
              rows={1}
            />
            <div className="agent-input-actions">
              {streaming ? (
                <button className="agent-send-btn" onClick={stopStreaming} title="Stop">
                  <Square className="h-3.5 w-3.5" />
                </button>
              ) : (
                <button
                  className="agent-send-btn"
                  onClick={sendMessage}
                  disabled={!input.trim()}
                  title="Send"
                >
                  <Send className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   TOOL CARDS
   ═══════════════════════════════════════════ */

const TOOL_LABELS: Record<string, string> = {
  analyze_project: "Analyzing project",
  generate_deploy_config: "Generating deploy.toml",
  list_workspaces: "Listing workspaces",
  list_instances: "Listing instances",
  run_build: "Building project",
  run_ship: "Shipping to instance",
  claim_subdomain: "Claiming subdomain",
  check_deploy_status: "Checking deploy status",
  read_workspace_file: "Reading file",
  write_workspace_file: "Writing file",
  run_validation: "Running validation",
  list_ai_apps: "Listing AI apps",
  start_ai_app: "Starting AI app",
  advance_ai_app: "Advancing AI app",
};

function ToolCallCard({ name, args, isStreaming }: { name: string; args?: any; isStreaming?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const label = TOOL_LABELS[name] || name;

  return (
    <div className="agent-tool-card">
      <div className="agent-tool-header" onClick={() => setExpanded(!expanded)}>
        <div className="agent-tool-status">
          {isStreaming
            ? <Loader className="h-3 w-3 animate-spin" style={{ color: "var(--color-teal)" }} />
            : <Wrench className="h-3 w-3" style={{ color: "var(--color-teal)" }} />
          }
        </div>
        <span className="agent-tool-label">{label}</span>
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
      </div>
      {expanded && args && (
        <pre className="agent-tool-args">{typeof args === "string" ? args : JSON.stringify(args, null, 2)}</pre>
      )}
    </div>
  );
}

function ToolResultCard({ name, result }: { name: string; result: string }) {
  const [expanded, setExpanded] = useState(false);
  let parsed: any = null;
  try { parsed = JSON.parse(result); } catch {}
  const isOk = parsed?.ok !== false;

  return (
    <div className={`agent-tool-card ${isOk ? "" : "agent-tool-error"}`}>
      <div className="agent-tool-header" onClick={() => setExpanded(!expanded)}>
        <div className="agent-tool-status">
          {isOk
            ? <CheckCircle2 className="h-3 w-3" style={{ color: "var(--color-green)" }} />
            : <XCircle className="h-3 w-3" style={{ color: "var(--color-red)" }} />
          }
        </div>
        <span className="agent-tool-label">{TOOL_LABELS[name] || name} — {isOk ? "done" : "failed"}</span>
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
      </div>
      {expanded && (
        <pre className="agent-tool-args">{parsed ? JSON.stringify(parsed, null, 2) : result}</pre>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════
   SIMPLE MARKDOWN
   ═══════════════════════════════════════════ */

function SimpleMarkdown({ text }: { text: string }) {
  // Basic markdown: code blocks, bold, inline code, links
  const parts = text.split(/(```[\s\S]*?```)/g);
  return (
    <div className="agent-markdown">
      {parts.map((part, i) => {
        if (part.startsWith("```") && part.endsWith("```")) {
          const inner = part.slice(3, -3);
          const newline = inner.indexOf("\n");
          const code = newline >= 0 ? inner.slice(newline + 1) : inner;
          return <pre key={i} className="agent-code-block">{code}</pre>;
        }
        return (
          <span key={i} dangerouslySetInnerHTML={{
            __html: part
              .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
              .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
              .replace(/`([^`]+)`/g, '<code class="agent-inline-code">$1</code>')
              .replace(/\n/g, "<br/>")
          }} />
        );
      })}
    </div>
  );
}

/* ═══════════════════════════════════════════
   HELPERS
   ═══════════════════════════════════════════ */

function dbMsgToChat(m: DeployMessage): ChatMsg[] {
  const msgs: ChatMsg[] = [];
  if (m.role === "user") {
    msgs.push({ id: m.id, role: "user", content: m.content });
  } else if (m.role === "assistant") {
    // Parse tool_calls if present
    let toolCalls: any[] = [];
    try { toolCalls = JSON.parse(m.tool_calls || "[]"); } catch {}
    for (const tc of toolCalls) {
      msgs.push({
        id: `tc_${tc.id || m.id}`,
        role: "tool_call",
        content: `Called ${tc.function?.name || "tool"}`,
        toolName: tc.function?.name,
        toolArgs: tc.function?.arguments ? safeParse(tc.function.arguments) : undefined,
      });
    }
    if (m.content) {
      msgs.push({ id: m.id, role: "assistant", content: m.content });
    }
  } else if (m.role === "tool") {
    let results: any[] = [];
    try { results = JSON.parse(m.tool_results || "[]"); } catch {}
    for (const tr of results) {
      msgs.push({
        id: `tr_${tr.id || m.id}`,
        role: "tool_result",
        content: tr.result || tr.output || "",
        toolName: tr.name,
        toolResult: tr.result || tr.output || "",
      });
    }
    if (results.length === 0 && m.content) {
      msgs.push({ id: m.id, role: "tool_result", content: m.content, toolResult: m.content });
    }
  }
  return msgs;
}

function safeParse(s: string | object): any {
  if (typeof s === "object") return s;
  try { return JSON.parse(s); } catch { return s; }
}
