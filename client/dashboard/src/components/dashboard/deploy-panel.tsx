"use client";

import React, { useState, useEffect, useRef, useCallback, memo } from "react";
import {
  Rocket, ArrowUp, Square, Loader2,
  MessageSquare, Plus, Trash2, ChevronDown,
  CheckCircle2, XCircle, AlertTriangle, Copy, Check,
  RotateCcw, Pencil, MoreHorizontal, X,
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
   AGENT CHAT
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
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, streamText]);

  // Auto-resize textarea
  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const ta = e.target;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }, []);

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
      .then((t) => setMessages((t.messages || []).flatMap(dbMsgToChat)))
      .catch(() => {});
  }, [activeThreadId, projectId]);

  const createThread = async () => {
    try {
      const t = await createDeployThread(projectId);
      setThreads((prev) => [t, ...prev]);
      setActiveThreadId(t.id);
      setMessages([]);
    } catch (e: any) { setError(e.message || "Failed to create thread"); }
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

  const sendMessage = async (override?: string) => {
    const content = (override || input).trim();
    if (!content || streaming) return;
    if (!activeThreadId) {
      try {
        const t = await createDeployThread(projectId);
        setThreads((prev) => [t, ...prev]);
        setActiveThreadId(t.id);
        await doStream(t.id, content);
      } catch (e: any) { setError(e.message || "Failed to create thread"); }
      return;
    }
    await doStream(activeThreadId, content);
  };

  const retryMessage = (content: string) => {
    if (activeThreadId) doStream(activeThreadId, content);
  };

  const doStream = async (threadId: string, content: string) => {
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setError("");
    setStreamText("");
    setStreamReasoning("");
    setActiveToolCall(null);
    setStreaming(true);

    setMessages((prev) => [...prev, { id: `u_${Date.now()}`, role: "user", content, timestamp: new Date().toISOString() }]);

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
              if (event.content) { accText += event.content; setStreamText(accText); }
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
                accText = ""; setStreamText("");
              }
              setMessages((prev) => [...prev, {
                id: `tc_${event.id || Date.now()}`, role: "tool_call",
                content: `Calling ${event.name}...`, toolName: event.name, toolArgs: event.arguments,
              }]);
              break;
            case "tool_result":
              setActiveToolCall(null);
              setMessages((prev) => [...prev, {
                id: `tr_${event.id || Date.now()}`, role: "tool_result",
                content: event.result || "", toolName: event.name, toolResult: event.result,
              }]);
              break;
            case "error":
              setError(event.error || "Unknown error");
              break;
            case "status":
              if (event.final_text && !accText) accText = event.final_text;
              break;
          }
        }
      }
      if (accText) {
        setMessages((prev) => [...prev, { id: `a_${Date.now()}`, role: "assistant", content: accText }]);
      }
    } catch (err: any) {
      if (err.name !== "AbortError") setError(err.message || "Stream failed");
    } finally {
      setStreaming(false);
      setStreamText(""); setStreamReasoning(""); setActiveToolCall(null);
      abortRef.current = null;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  if (loading) {
    return (
      <div className="panel-empty">
        <Loader2 className="h-6 w-6 animate-spin" style={{ color: "var(--muted-foreground)", opacity: 0.5 }} />
        <div className="panel-empty-sub">Loading deploy agent...</div>
      </div>
    );
  }

  const isEmpty = messages.length === 0 && !streaming;

  return (
    <div className="da-layout">
      {/* Thread sidebar */}
      <ThreadSidebar
        threads={threads}
        activeThreadId={activeThreadId}
        onSelect={setActiveThreadId}
        onCreate={createThread}
        onDelete={deleteThread}
      />

      {/* Chat area */}
      <main className="da-main">
        {isEmpty && !activeThreadId ? (
          /* Welcome / empty state */
          <div className="da-welcome">
            <div className="da-welcome-inner">
              <h2 className="da-welcome-title">What can I help you deploy?</h2>
              <div className="da-welcome-suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} className="da-suggestion" onClick={() => sendMessage(s)}>
                    {s}
                  </button>
                ))}
              </div>
              {/* Input inside welcome */}
              <div className="da-input-container">
                <ChatInputBox
                  input={input}
                  streaming={streaming}
                  textareaRef={textareaRef}
                  onInputChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  onSend={() => sendMessage()}
                  onStop={stopStreaming}
                />
              </div>
            </div>
          </div>
        ) : (
          <>
            {/* Messages */}
            <div ref={scrollRef} className="da-messages">
              <div className="da-messages-inner">
                {messages.map((msg) => (
                  <MessageRow key={msg.id} msg={msg} onRetry={retryMessage} />
                ))}

                {streaming && (
                  <StreamingBlock
                    text={streamText}
                    reasoning={streamReasoning}
                    toolCall={activeToolCall}
                    status={streamText ? "streaming" : "connecting"}
                  />
                )}

                {error && (
                  <div className="da-error">
                    <p className="da-error-text">{error}</p>
                    <button className="da-error-dismiss" onClick={() => setError("")}>
                      <RotateCcw className="h-3 w-3" /> Dismiss
                    </button>
                  </div>
                )}

                <div className="h-12" aria-hidden="true" />
              </div>
            </div>

            {/* Input */}
            <div className="da-input-bottom">
              <ChatInputBox
                input={input}
                streaming={streaming}
                textareaRef={textareaRef}
                onInputChange={handleInputChange}
                onKeyDown={handleKeyDown}
                onSend={() => sendMessage()}
                onStop={stopStreaming}
              />
            </div>
          </>
        )}
      </main>
    </div>
  );
}

const SUGGESTIONS = [
  "Deploy my app to production",
  "Analyze my workspace",
  "Show my instances",
  "Generate a deploy config",
];

/* ═══════════════════════════════════════════
   CHAT INPUT BOX (chatagent-style)
   ═══════════════════════════════════════════ */

function ChatInputBox({ input, streaming, textareaRef, onInputChange, onKeyDown, onSend, onStop }: {
  input: string;
  streaming: boolean;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  onInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  onSend: () => void;
  onStop: () => void;
}) {
  return (
    <div className="da-input-box">
      <div className="da-input-inner">
        <div className="da-input-content">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={onInputChange}
            onKeyDown={onKeyDown}
            placeholder="Message deploy agent..."
            disabled={streaming}
            className="da-textarea"
            rows={1}
          />
          <div className="da-toolbar">
            <div className="da-toolbar-left">
              <span className="da-model-label">gpt-oss-20b</span>
            </div>
            {streaming ? (
              <button onClick={onStop} className="da-send-btn active" title="Stop">
                <Square className="h-3.5 w-3.5" />
              </button>
            ) : (
              <button
                onClick={onSend}
                disabled={!input.trim()}
                className={`da-send-btn ${input.trim() ? "active" : ""}`}
                title="Send"
              >
                <ArrowUp className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      </div>
      <div className="da-disclaimer">AI can make mistakes. Double-check responses.</div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   THREAD SIDEBAR
   ═══════════════════════════════════════════ */

function groupByDate(threads: DeployThread[]) {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const groups: { label: string; items: DeployThread[] }[] = [];
  const t: DeployThread[] = [], y: DeployThread[] = [], o: DeployThread[] = [];
  for (const th of threads) {
    const d = new Date(th.created_at);
    if (d.toDateString() === today.toDateString()) t.push(th);
    else if (d.toDateString() === yesterday.toDateString()) y.push(th);
    else o.push(th);
  }
  if (t.length) groups.push({ label: "Today", items: t });
  if (y.length) groups.push({ label: "Yesterday", items: y });
  if (o.length) groups.push({ label: "Previous", items: o });
  return groups;
}

const ThreadSidebar = memo(function ThreadSidebar({ threads, activeThreadId, onSelect, onCreate, onDelete }: {
  threads: DeployThread[];
  activeThreadId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
}) {
  const groups = groupByDate(threads);
  return (
    <div className="da-sidebar">
      <div className="da-sidebar-header">
        <span className="da-sidebar-title">Deploy Agent</span>
        <button className="da-sidebar-new" onClick={onCreate} title="New conversation">
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="da-sidebar-list">
        {threads.length === 0 ? (
          <div className="da-sidebar-empty">
            <MessageSquare className="h-6 w-6 opacity-20 mx-auto mb-2" />
            <p>No conversations yet</p>
            <p className="da-sidebar-empty-sub">Start a new chat</p>
          </div>
        ) : (
          <div className="da-sidebar-groups">
            {groups.map((g) => (
              <div key={g.label}>
                <p className="da-group-label">{g.label}</p>
                <div className="da-group-items">
                  {g.items.map((th) => (
                    <ThreadRow key={th.id} thread={th} active={activeThreadId === th.id} onSelect={onSelect} onDelete={onDelete} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
});

function ThreadRow({ thread, active, onSelect, onDelete }: {
  thread: DeployThread; active: boolean;
  onSelect: (id: string) => void; onDelete: (id: string) => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div
      className={`da-thread ${active ? "active" : ""}`}
      onClick={() => onSelect(thread.id)}
      onMouseLeave={() => setMenuOpen(false)}
    >
      <span className="da-thread-name">{thread.title || "New deploy"}</span>
      <div className="da-thread-actions">
        <button className="da-thread-menu" onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen); }}>
          <MoreHorizontal className="h-3 w-3" />
        </button>
        {menuOpen && (
          <div className="da-dropdown">
            <button className="da-dropdown-item danger" onClick={(e) => { e.stopPropagation(); onDelete(thread.id); }}>
              <Trash2 className="h-3.5 w-3.5" /> Delete
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   MESSAGE ROW
   ═══════════════════════════════════════════ */

const MessageRow = memo(function MessageRow({ msg, onRetry }: { msg: ChatMsg; onRetry: (c: string) => void }) {
  if (msg.role === "user") return <UserMsg msg={msg} onRetry={onRetry} />;
  if (msg.role === "assistant") return <AssistantMsg msg={msg} />;
  if (msg.role === "tool_call") return <ToolPill name={msg.toolName || ""} args={msg.toolArgs} />;
  if (msg.role === "tool_result") return <ToolResultBlock name={msg.toolName || ""} result={msg.toolResult} />;
  return null;
});

/* User message — muted bubble, right-aligned */
function UserMsg({ msg, onRetry }: { msg: ChatMsg; onRetry: (c: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(msg.content);

  return (
    <div className="da-msg-user group">
      <div className="da-msg-user-col">
        {editing ? (
          <div className="da-edit-wrap">
            <textarea
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              className="da-edit-textarea"
              rows={3}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onRetry(editText.trim()); setEditing(false); }
                if (e.key === "Escape") { setEditText(msg.content); setEditing(false); }
              }}
            />
            <div className="da-edit-actions">
              <button className="da-edit-cancel" onClick={() => { setEditText(msg.content); setEditing(false); }}>Cancel</button>
              <button className="da-edit-save" onClick={() => { onRetry(editText.trim()); setEditing(false); }}>Save & Resend</button>
            </div>
          </div>
        ) : (
          <div className="da-user-bubble">
            <p className="da-user-text">{msg.content}</p>
          </div>
        )}
        <div className="da-hover-actions">
          <ActionBtn icon={RotateCcw} label="Retry" onClick={() => onRetry(msg.content)} />
          <ActionBtn icon={Pencil} label="Edit" onClick={() => { setEditText(msg.content); setEditing(true); }} />
          <CopyBtn text={msg.content} />
        </div>
      </div>
    </div>
  );
}

/* Assistant message — no bubble, just clean markdown */
function AssistantMsg({ msg }: { msg: ChatMsg }) {
  return (
    <div className="da-msg-assistant group">
      <div className="da-assistant-text">
        <ChatMarkdown text={msg.content} />
      </div>
      <div className="da-hover-actions">
        <CopyBtn text={msg.content} />
        <ActionBtn icon={RotateCcw} label="Retry" onClick={() => {}} />
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   STREAMING BLOCK
   ═══════════════════════════════════════════ */

const StreamingBlock = memo(function StreamingBlock({ text, reasoning, toolCall, status }: {
  text: string; reasoning: string;
  toolCall: { name: string; args?: any } | null;
  status: "connecting" | "streaming";
}) {
  return (
    <div className="da-msg-assistant group">
      {reasoning && <ReasoningSection content={reasoning} isStreaming />}
      {toolCall && <ToolPill name={toolCall.name} args={toolCall.args} isStreaming />}
      {text ? (
        <div className="da-assistant-text">
          <ChatMarkdown text={text} />
          <span className="da-cursor" />
        </div>
      ) : status === "connecting" ? (
        <div className="da-connecting">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>Thinking...</span>
        </div>
      ) : !toolCall && !reasoning ? (
        <div className="da-connecting">
          <span className="da-dot" /><span className="da-dot d2" /><span className="da-dot d3" />
        </div>
      ) : null}
    </div>
  );
});

/* ═══════════════════════════════════════════
   REASONING (collapsible details — exact chatagent match)
   ═══════════════════════════════════════════ */

function ReasoningSection({ content, isStreaming, defaultOpen = true }: {
  content: string; isStreaming?: boolean; defaultOpen?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultOpen || !!isStreaming);
  return (
    <div className="mb-3">
      <details open={expanded}>
        <summary
          onClick={(e) => { e.preventDefault(); setExpanded(!expanded); }}
          className="da-reasoning-summary"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="opacity-70">
            <path d="M9 21h6M12 3a6 6 0 0 1 4 10.5V17H8v-3.5A6 6 0 0 1 12 3z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <span>{isStreaming ? "Thinking..." : "Thought process"}</span>
        </summary>
        {expanded && (
          <div className="da-reasoning-body">
            <ChatMarkdown text={content} />
            {isStreaming && <span className="da-cursor" />}
          </div>
        )}
      </details>
    </div>
  );
}

/* ═══════════════════════════════════════════
   TOOL PILL (exact chatagent match — rounded-full inline pill)
   ═══════════════════════════════════════════ */

const TOOL_NAMES: Record<string, string> = {
  analyze_project: "Analyze Project", generate_deploy_config: "Generate Config",
  list_workspaces: "List Workspaces", list_instances: "List Instances",
  run_build: "Build Project", run_ship: "Ship to Instance",
  claim_subdomain: "Claim Subdomain", check_deploy_status: "Check Status",
  read_workspace_file: "Read File", write_workspace_file: "Write File",
  run_validation: "Run Validation", list_ai_apps: "List AI Apps",
  start_ai_app: "Start AI App", advance_ai_app: "Advance AI App",
};

function ToolPill({ name, args, isStreaming }: {
  name: string; args?: any; isStreaming?: boolean;
}) {
  const displayName = TOOL_NAMES[name] || name.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
  const parsedArgs = typeof args === "string" ? safeParse(args) : args;

  const preview = parsedArgs && typeof parsedArgs === "object"
    ? String(Object.values(parsedArgs)[0] || "").slice(0, 60) : "";

  return (
    <div className="da-tool-inline">
      <span className={`da-tool-dot ${isStreaming ? "streaming" : "idle"}`} />
      <span className="da-tool-name">{displayName}</span>
      {preview && <span className="da-tool-preview">{preview}</span>}
      {isStreaming && <Loader2 className="h-3 w-3 animate-spin shrink-0" style={{ color: "var(--da-accent)" }} />}
    </div>
  );
}

/** Tool result — renders output inline or as a collapsible code block */
function ToolResultBlock({ name, result }: { name: string; result?: string }) {
  const [expanded, setExpanded] = useState(false);
  const displayName = TOOL_NAMES[name] || name.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
  const parsed = result ? safeParse(result) : null;
  const isOk = parsed ? parsed?.ok !== false : true;

  // Extract meaningful output text
  const outputText = typeof parsed === "object"
    ? (parsed?.output || parsed?.stdout || parsed?.result || parsed?.message || "")
    : String(parsed || "");
  const lines = String(outputText).split("\n").filter(Boolean);
  const hasContent = lines.length > 0;
  const isMultiLine = lines.length > 3;

  return (
    <div className="da-result-block">
      <div className="da-result-header" onClick={() => isMultiLine && setExpanded(!expanded)} style={{ cursor: isMultiLine ? "pointer" : "default" }}>
        <span className={`da-tool-dot ${isOk ? "success" : "error"}`} />
        <span className="da-tool-name">{displayName}</span>
        <span className="da-result-status" style={{ color: isOk ? "#4ade80" : "#f87171" }}>
          {isOk ? "Done" : "Failed"}
        </span>
        {isMultiLine && (
          <ChevronDown className={`h-3 w-3 opacity-40 shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`} />
        )}
      </div>
      {hasContent && (expanded || !isMultiLine) && (
        <pre className="da-result-output">{lines.slice(0, expanded ? undefined : 3).join("\n")}</pre>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════
   ACTION BUTTONS
   ═══════════════════════════════════════════ */

function ActionBtn({ icon: Icon, label, onClick }: { icon: React.ElementType; label: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className="da-action-btn" aria-label={label}>
      <Icon className="h-4 w-4" />
    </button>
  );
}

function CopyBtn({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
      className="da-action-btn" aria-label="Copy"
    >
      {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
    </button>
  );
}

/* ═══════════════════════════════════════════
   CHAT MARKDOWN — react-markdown + remark-gfm
   ═══════════════════════════════════════════ */

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="da-codeblock">
      <div className="da-codeblock-header">
        <span className="da-codeblock-lang">{lang || "text"}</span>
        <button className="da-codeblock-copy" onClick={() => {
          navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 2000);
        }}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="da-codeblock-pre"><code>{code}</code></pre>
    </div>
  );
}

const mdComponents: Components = {
  code(props) {
    const { className, children, ...rest } = props;
    const match = /language-(\w+)/.exec(className || "");
    const content = String(children).replace(/\n$/, "");
    const isInline = !match && !content.includes("\n");
    if (isInline) {
      return <code className="da-icode" {...rest}>{children}</code>;
    }
    if (match) {
      return <CodeBlock code={content} lang={match[1]} />;
    }
    return (
      <pre className="da-codeblock-pre" style={{ margin: "6px 0" }}>
        <code>{content}</code>
      </pre>
    );
  },
  pre({ children }) { return <>{children}</>; },
  a({ href, children, ...props }) {
    return <a href={href} target="_blank" rel="noopener noreferrer" className="da-link" {...props}>{children}</a>;
  },
  table({ children, ...props }) {
    return <div className="da-table-wrap"><table className="da-table" {...props}>{children}</table></div>;
  },
  th({ children, ...props }) { return <th className="da-th" {...props}>{children}</th>; },
  td({ children, ...props }) { return <td className="da-td" {...props}>{children}</td>; },
  ul({ children, ...props }) { return <ul className="da-ul" {...props}>{children}</ul>; },
  ol({ children, ...props }) { return <ol className="da-ol-list" {...props}>{children}</ol>; },
  blockquote({ children, ...props }) { return <blockquote className="da-blockquote" {...props}>{children}</blockquote>; },
  h1({ children, ...props }) { return <h1 className="da-h da-h1" {...props}>{children}</h1>; },
  h2({ children, ...props }) { return <h2 className="da-h da-h2" {...props}>{children}</h2>; },
  h3({ children, ...props }) { return <h3 className="da-h da-h3" {...props}>{children}</h3>; },
  h4({ children, ...props }) { return <h4 className="da-h da-h4" {...props}>{children}</h4>; },
  p({ children, ...props }) { return <p className="da-p" {...props}>{children}</p>; },
  hr() { return <hr className="da-hr" />; },
};

const ChatMarkdown = memo(function ChatMarkdown({ text }: { text: string }) {
  return (
    <div className="da-md">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
        {text}
      </ReactMarkdown>
    </div>
  );
});

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
      msgs.push({ id: `tc_${tc.id || m.id}`, role: "tool_call", content: `Called ${tc.function?.name || "tool"}`,
        toolName: tc.function?.name, toolArgs: tc.function?.arguments ? safeParse(tc.function.arguments) : undefined });
    }
    if (m.content) msgs.push({ id: m.id, role: "assistant", content: m.content });
  } else if (m.role === "tool") {
    let results: any[] = [];
    try { results = JSON.parse(m.tool_results || "[]"); } catch {}
    for (const tr of results) {
      msgs.push({ id: `tr_${tr.id || m.id}`, role: "tool_result", content: tr.result || tr.output || "",
        toolName: tr.name, toolResult: tr.result || tr.output || "" });
    }
    if (results.length === 0 && m.content) msgs.push({ id: m.id, role: "tool_result", content: m.content, toolResult: m.content });
  }
  return msgs;
}

function safeParse(s: string | object): any {
  if (typeof s === "object") return s;
  try { return JSON.parse(s); } catch { return s; }
}
