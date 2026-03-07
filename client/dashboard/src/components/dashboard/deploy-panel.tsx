"use client";

import React, { useState, useEffect, useRef, useCallback, memo } from "react";
import {
  Rocket, Send, Square, Loader,
  MessageSquare, Plus, Trash2, ChevronDown, ChevronRight,
  CheckCircle2, XCircle, AlertTriangle, Copy, Check,
  Lightbulb, RotateCcw, Pencil, MoreHorizontal,
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
   TYPES
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
  timestamp?: string;
}

/* ═══════════════════════════════════════════
   AGENT CHAT — Main Component
   ═══════════════════════════════════════════ */

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

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }, [input]);

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

  const retryMessage = (msgId: string) => {
    const idx = messages.findIndex((m) => m.id === msgId);
    if (idx < 0) return;
    const msg = messages[idx];
    if (msg.role === "user" && activeThreadId) {
      setMessages((prev) => prev.slice(0, idx));
      doStream(activeThreadId, msg.content);
    }
  };

  const doStream = async (threadId: string, content: string) => {
    setInput("");
    setError("");
    setStreamText("");
    setStreamReasoning("");
    setActiveToolCall(null);
    setStreaming(true);

    const userMsg: ChatMsg = { id: `u_${Date.now()}`, role: "user", content, timestamp: new Date().toISOString() };
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
      <ThreadSidebar
        threads={threads}
        activeThreadId={activeThreadId}
        onSelect={setActiveThreadId}
        onCreate={createThread}
        onDelete={deleteThread}
      />

      {/* Chat area */}
      <div className="agent-main">
        <div className="agent-messages">
          {messages.length === 0 && !streaming && (
            <EmptyState onSend={(s) => { setInput(s); setTimeout(() => sendMessage(), 50); }} />
          )}

          {messages.map((msg) => (
            <MessageRow
              key={msg.id}
              msg={msg}
              onRetry={() => retryMessage(msg.id)}
            />
          ))}

          {/* Streaming state */}
          {streaming && (
            <StreamingIndicator
              streamText={streamText}
              streamReasoning={streamReasoning}
              activeToolCall={activeToolCall}
            />
          )}

          {error && (
            <div className="agent-error">
              <AlertTriangle className="h-3.5 w-3.5" />
              <span>{error}</span>
              <button className="agent-error-dismiss" onClick={() => setError("")}>Dismiss</button>
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
              placeholder="What do you want to deploy?"
              disabled={streaming}
              rows={1}
            />
            <div className="agent-input-actions">
              {streaming ? (
                <button className="agent-stop-btn" onClick={stopStreaming} title="Stop">
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
          <div className="agent-input-hint">GLM-4.7 can make mistakes. Double-check responses.</div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   THREAD SIDEBAR
   ═══════════════════════════════════════════ */

function groupThreadsByDate(threads: DeployThread[]) {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  const groups: { label: string; threads: DeployThread[] }[] = [
    { label: "Today", threads: [] },
    { label: "Yesterday", threads: [] },
    { label: "Previous", threads: [] },
  ];

  for (const t of threads) {
    const d = new Date(t.created_at);
    if (d.toDateString() === today.toDateString()) groups[0].threads.push(t);
    else if (d.toDateString() === yesterday.toDateString()) groups[1].threads.push(t);
    else groups[2].threads.push(t);
  }

  return groups.filter((g) => g.threads.length > 0);
}

const ThreadSidebar = memo(function ThreadSidebar({
  threads, activeThreadId, onSelect, onCreate, onDelete,
}: {
  threads: DeployThread[];
  activeThreadId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
}) {
  const groups = groupThreadsByDate(threads);

  return (
    <div className="agent-threads">
      <div className="agent-threads-header">
        <span className="agent-threads-title">Conversations</span>
        <button className="agent-new-btn" onClick={onCreate} title="New conversation">
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="agent-threads-list">
        {threads.length === 0 ? (
          <div className="agent-threads-empty">No conversations yet</div>
        ) : groups.map((group) => (
          <div key={group.label} className="agent-thread-group">
            <div className="agent-thread-group-label">{group.label}</div>
            {group.threads.map((t) => (
              <ThreadItem
                key={t.id}
                thread={t}
                isActive={activeThreadId === t.id}
                onSelect={onSelect}
                onDelete={onDelete}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
});

const ThreadItem = memo(function ThreadItem({
  thread, isActive, onSelect, onDelete,
}: {
  thread: DeployThread;
  isActive: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const [showMenu, setShowMenu] = useState(false);

  return (
    <div
      className={`agent-thread-item ${isActive ? "active" : ""}`}
      onClick={() => onSelect(thread.id)}
      onMouseLeave={() => setShowMenu(false)}
    >
      <span className="agent-thread-title">{thread.title || "New deploy"}</span>
      <div className="agent-thread-actions">
        <button
          className="agent-thread-menu-btn"
          onClick={(e) => { e.stopPropagation(); setShowMenu(!showMenu); }}
        >
          <MoreHorizontal className="h-3.5 w-3.5" />
        </button>
        {showMenu && (
          <div className="agent-thread-dropdown">
            <button
              className="agent-thread-dropdown-item danger"
              onClick={(e) => { e.stopPropagation(); onDelete(thread.id); setShowMenu(false); }}
            >
              <Trash2 className="h-3 w-3" /> Delete
            </button>
          </div>
        )}
      </div>
    </div>
  );
});

/* ═══════════════════════════════════════════
   EMPTY STATE
   ═══════════════════════════════════════════ */

const SUGGESTIONS = [
  "Deploy my app to production",
  "Analyze my workspace",
  "Show my instances",
  "Generate a deploy config",
];

const EmptyState = memo(function EmptyState({ onSend }: { onSend: (s: string) => void }) {
  return (
    <div className="agent-empty">
      <div className="agent-empty-title">What can I help you deploy?</div>
      <div className="agent-empty-sub">
        I can analyze your workspace, generate configs, build, and ship your project.
      </div>
      <div className="agent-suggestions">
        {SUGGESTIONS.map((s) => (
          <button key={s} className="agent-suggestion" onClick={() => onSend(s)}>
            {s}
          </button>
        ))}
      </div>
    </div>
  );
});

/* ═══════════════════════════════════════════
   MESSAGE ROW
   ═══════════════════════════════════════════ */

const MessageRow = memo(function MessageRow({
  msg, onRetry,
}: {
  msg: ChatMsg;
  onRetry: () => void;
}) {
  if (msg.role === "user") return <UserMessage msg={msg} onRetry={onRetry} />;
  if (msg.role === "assistant") return <AssistantMessage msg={msg} />;
  if (msg.role === "tool_call") return <ToolCallCard name={msg.toolName || ""} args={msg.toolArgs} />;
  if (msg.role === "tool_result") return <ToolResultCard name={msg.toolName || ""} result={msg.toolResult || ""} />;
  return null;
});

/* ═══════════════════════════════════════════
   USER MESSAGE
   ═══════════════════════════════════════════ */

function UserMessage({ msg, onRetry }: { msg: ChatMsg; onRetry: () => void }) {
  return (
    <div className="agent-msg agent-msg-user">
      <div className="agent-user-row">
        <div className="agent-user-bubble">{msg.content}</div>
        <div className="agent-msg-actions">
          <ActionBtn icon={<RotateCcw className="h-3 w-3" />} title="Retry" onClick={onRetry} />
          <CopyBtn text={msg.content} />
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   ASSISTANT MESSAGE
   ═══════════════════════════════════════════ */

function AssistantMessage({ msg }: { msg: ChatMsg }) {
  return (
    <div className="agent-msg agent-msg-assistant-row">
      <div className="agent-assistant-content">
        <ChatMarkdown text={msg.content} />
      </div>
      <div className="agent-msg-actions">
        <CopyBtn text={msg.content} />
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   STREAMING INDICATOR
   ═══════════════════════════════════════════ */

const StreamingIndicator = memo(function StreamingIndicator({
  streamText, streamReasoning, activeToolCall,
}: {
  streamText: string;
  streamReasoning: string;
  activeToolCall: { name: string; args?: any } | null;
}) {
  return (
    <div className="agent-msg agent-msg-assistant-row">
      {streamReasoning && (
        <ReasoningSection content={streamReasoning} isStreaming />
      )}
      {activeToolCall && (
        <ToolCallCard name={activeToolCall.name} args={activeToolCall.args} isStreaming />
      )}
      {streamText ? (
        <div className="agent-assistant-content">
          <ChatMarkdown text={streamText} />
          <span className="agent-cursor" />
        </div>
      ) : !activeToolCall && !streamReasoning ? (
        <div className="agent-thinking">
          <div className="agent-bounce">
            <span /><span /><span />
          </div>
          <span>Thinking...</span>
        </div>
      ) : null}
    </div>
  );
});

/* ═══════════════════════════════════════════
   REASONING SECTION (collapsible <details>)
   ═══════════════════════════════════════════ */

function ReasoningSection({ content, isStreaming, defaultOpen = true }: {
  content: string;
  isStreaming?: boolean;
  defaultOpen?: boolean;
}) {
  return (
    <details className="agent-reasoning" open={defaultOpen}>
      <summary className="agent-reasoning-summary">
        <Lightbulb className="h-3.5 w-3.5" />
        <span>{isStreaming ? "Thinking..." : "Thought process"}</span>
      </summary>
      <div className="agent-reasoning-body">
        <ChatMarkdown text={content} />
        {isStreaming && <span className="agent-cursor" />}
      </div>
    </details>
  );
}

/* ═══════════════════════════════════════════
   TOOL CARDS
   ═══════════════════════════════════════════ */

const TOOL_LABELS: Record<string, string> = {
  analyze_project: "Analyze Project",
  generate_deploy_config: "Generate Config",
  list_workspaces: "List Workspaces",
  list_instances: "List Instances",
  run_build: "Build Project",
  run_ship: "Ship to Instance",
  claim_subdomain: "Claim Subdomain",
  check_deploy_status: "Check Status",
  read_workspace_file: "Read File",
  write_workspace_file: "Write File",
  run_validation: "Run Validation",
  list_ai_apps: "List AI Apps",
  start_ai_app: "Start AI App",
  advance_ai_app: "Advance AI App",
};

function ToolCallCard({ name, args, isStreaming }: { name: string; args?: any; isStreaming?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const label = TOOL_LABELS[name] || name;

  // Get first arg preview
  let preview = "";
  if (args) {
    const obj = typeof args === "string" ? safeParse(args) : args;
    if (typeof obj === "object" && obj !== null) {
      const firstVal = Object.values(obj)[0];
      if (typeof firstVal === "string") preview = firstVal.length > 40 ? firstVal.slice(0, 40) + "..." : firstVal;
    }
  }

  return (
    <div className="agent-tool-pill">
      <div className="agent-tool-pill-header" onClick={() => setExpanded(!expanded)}>
        <span className={`agent-tool-dot ${isStreaming ? "streaming" : "done"}`} />
        <span className="agent-tool-pill-label">{label}</span>
        {preview && <span className="agent-tool-preview">{preview}</span>}
        {isStreaming && <Loader className="h-3 w-3 animate-spin" style={{ color: "var(--muted-foreground)" }} />}
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
      </div>
      {expanded && args && (
        <div className="agent-tool-detail">
          <div className="agent-tool-detail-label">Arguments</div>
          <pre className="agent-tool-json">{typeof args === "string" ? args : JSON.stringify(args, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

function ToolResultCard({ name, result }: { name: string; result: string }) {
  const [expanded, setExpanded] = useState(false);
  let parsed: any = null;
  try { parsed = JSON.parse(result); } catch {}
  const isOk = parsed?.ok !== false;
  const label = TOOL_LABELS[name] || name;

  return (
    <div className="agent-tool-pill">
      <div className="agent-tool-pill-header" onClick={() => setExpanded(!expanded)}>
        <span className={`agent-tool-dot ${isOk ? "success" : "error"}`} />
        <span className="agent-tool-pill-label">{label}</span>
        <span className="agent-tool-status-text">{isOk ? "Done" : "Failed"}</span>
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
      </div>
      {expanded && (
        <div className="agent-tool-detail">
          <div className="agent-tool-detail-label">Result</div>
          <pre className="agent-tool-json">{parsed ? JSON.stringify(parsed, null, 2) : result}</pre>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════
   REUSABLE ACTION BUTTONS
   ═══════════════════════════════════════════ */

function ActionBtn({ icon, title, onClick }: { icon: React.ReactNode; title: string; onClick: () => void }) {
  return (
    <button className="agent-action-btn" title={title} onClick={onClick}>
      {icon}
    </button>
  );
}

function CopyBtn({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <button className="agent-action-btn" title="Copy" onClick={copy}>
      {copied ? <Check className="h-3 w-3" style={{ color: "var(--color-green)" }} /> : <Copy className="h-3 w-3" />}
    </button>
  );
}

/* ═══════════════════════════════════════════
   CHAT MARKDOWN (richer than SimpleMarkdown)
   ═══════════════════════════════════════════ */

const ChatMarkdown = memo(function ChatMarkdown({ text }: { text: string }) {
  const parts = text.split(/(```[\s\S]*?```)/g);
  return (
    <div className="agent-md">
      {parts.map((part, i) => {
        if (part.startsWith("```") && part.endsWith("```")) {
          const inner = part.slice(3, -3);
          const nl = inner.indexOf("\n");
          const lang = nl >= 0 ? inner.slice(0, nl).trim() : "";
          const code = nl >= 0 ? inner.slice(nl + 1) : inner;
          return <CodeBlock key={i} code={code} lang={lang} />;
        }
        // Process inline markdown
        const html = part
          .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
          .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
          .replace(/\*(.*?)\*/g, "<em>$1</em>")
          .replace(/`([^`]+)`/g, '<code class="agent-icode">$1</code>')
          .replace(/^### (.+)$/gm, '<h4 class="agent-md-h">$1</h4>')
          .replace(/^## (.+)$/gm, '<h3 class="agent-md-h">$1</h3>')
          .replace(/^# (.+)$/gm, '<h2 class="agent-md-h">$1</h2>')
          .replace(/^[-*] (.+)$/gm, '<li class="agent-md-li">$1</li>')
          .replace(/^\d+\. (.+)$/gm, '<li class="agent-md-li agent-md-ol">$1</li>')
          .replace(/\n/g, "<br/>");
        return <span key={i} dangerouslySetInnerHTML={{ __html: html }} />;
      })}
    </div>
  );
});

function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="agent-codeblock">
      <div className="agent-codeblock-header">
        <span className="agent-codeblock-lang">{lang || "text"}</span>
        <button className="agent-codeblock-copy" onClick={copy}>
          {copied ? <><Check className="h-3 w-3" /> Copied</> : <><Copy className="h-3 w-3" /> Copy</>}
        </button>
      </div>
      <pre className="agent-codeblock-pre"><code>{code}</code></pre>
    </div>
  );
}

/* ═══════════════════════════════════════════
   HELPERS
   ═══════════════════════════════════════════ */

function dbMsgToChat(m: DeployMessage): ChatMsg[] {
  const msgs: ChatMsg[] = [];
  if (m.role === "user") {
    msgs.push({ id: m.id, role: "user", content: m.content, timestamp: m.created_at });
  } else if (m.role === "assistant") {
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
