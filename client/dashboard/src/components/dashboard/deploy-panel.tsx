"use client";

import React, { useState, useEffect, useRef, useCallback, memo, useMemo } from "react";
import {
  Rocket, ArrowUp, Square, Loader2,
  MessageSquare, Plus, Trash2, ChevronDown,
  CheckCircle2, XCircle, AlertTriangle, Copy, Check,
  RotateCcw, Pencil, MoreHorizontal, X,
  Paperclip, FolderOpen, FileText, Package, GitBranch,
  ChevronRight, FolderClosed, Image, FileCode, Upload,
  Sparkles, Globe, Server, Wrench,
} from "lucide-react";
import { useDashboardStore } from "@/stores/dashboard-store";
import { FileTokenView, type FileEntry } from "./file-token-view";
import { ConnectorPicker } from "./connector-picker";
import {
  createDeployThread, listDeployThreads, getDeployThread,
  deleteDeployThread, streamDeployAgent,
  listWorkspaces, zarVersions,
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

interface Attachment {
  id: string;
  type: "workspace" | "zar" | "folder" | "file";
  label: string;
  path?: string;
  workspace?: string;
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
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [selectedWorkspace, setSelectedWorkspace] = useState<string | null>(null);
  const [workspaces, setWorkspaces] = useState<any[]>([]);
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

  // Load threads + workspaces
  useEffect(() => {
    setLoading(true);
    setActiveThreadId(null);
    setMessages([]);
    setSelectedWorkspace(null);
    Promise.all([
      listDeployThreads(projectId).catch(() => ({ threads: [] })),
      listWorkspaces(projectId).catch(() => ({ workspaces: [] })),
    ]).then(([threadRes, wsRes]) => {
      setThreads(threadRes.threads || []);
      setWorkspaces(wsRes.workspaces || []);
      if (threadRes.threads?.length > 0) setActiveThreadId(threadRes.threads[0].id);
    }).finally(() => setLoading(false));
  }, [projectId]);

  // Load messages when thread changes
  useEffect(() => {
    if (!activeThreadId) { setMessages([]); return; }
    getDeployThread(projectId, activeThreadId)
      .then((t) => setMessages((t.messages || []).flatMap(dbMsgToChat)))
      .catch(() => {});
  }, [activeThreadId, projectId]);

  // Auto-delete empty threads when switching away
  const cleanupEmptyThread = useCallback(async (threadId: string | null) => {
    if (!threadId) return;
    try {
      const data = await getDeployThread(projectId, threadId);
      if (!data.messages || data.messages.length === 0) {
        await deleteDeployThread(projectId, threadId);
        setThreads((prev) => prev.filter((t) => t.id !== threadId));
      }
    } catch {}
  }, [projectId]);

  const selectThread = useCallback(async (id: string) => {
    if (id === activeThreadId) return;
    // Cancel any active streaming before switching
    if (streaming) { abortRef.current?.abort(); abortRef.current = null; setStreaming(false); }
    // Cleanup previous empty thread
    await cleanupEmptyThread(activeThreadId);
    setActiveThreadId(id);
  }, [activeThreadId, cleanupEmptyThread, streaming]);

  const createThread = async () => {
    // Cancel any active streaming before creating new thread
    if (streaming) { abortRef.current?.abort(); abortRef.current = null; setStreaming(false); }
    // Cleanup current empty thread before creating new one
    await cleanupEmptyThread(activeThreadId);
    try {
      const t = await createDeployThread(projectId);
      setThreads((prev) => [t, ...prev]);
      setActiveThreadId(t.id);
      setMessages([]);
      setStreamText(""); setStreamReasoning(""); setActiveToolCall(null); setError("");
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

  const addAttachment = useCallback((att: Attachment) => {
    setAttachments((prev) => prev.some((a) => a.id === att.id) ? prev : [...prev, att]);
  }, []);
  const removeAttachment = useCallback((id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  }, []);

  const sendMessage = async (override?: string) => {
    let content = (override || input).trim();
    if (!content || streaming) return;
    // Prepend workspace context if selected
    if (selectedWorkspace) {
      content = `[workspace: ${selectedWorkspace}]\n${content}`;
    }
    // Prepend attachment context
    if (attachments.length > 0) {
      const ctx = attachments.map((a) => {
        if (a.type === "workspace") return `[workspace: ${a.label}]`;
        if (a.type === "zar") return `[zar: ${a.label}]`;
        if (a.type === "folder") return `[folder: ${a.workspace}/${a.path}]`;
        return `[file: ${a.workspace}/${a.path}]`;
      }).join(" ");
      content = `${ctx}\n${content}`;
      setAttachments([]);
    }
    if (!activeThreadId) {
      try {
        // Use first message (without attachment tags) as thread title
        const rawText = (override || input).trim();
        const title = rawText.length > 60 ? rawText.slice(0, 57) + "..." : rawText;
        const t = await createDeployThread(projectId, "", title);
        setThreads((prev) => [t, ...prev]);
        setActiveThreadId(t.id);
        await doStream(t.id, content);
      } catch (e: any) { setError(e.message || "Failed to create thread"); }
      return;
    }
    // Update thread title if it's still empty (created via + button)
    const currentThread = threads.find((t) => t.id === activeThreadId);
    if (currentThread && (!currentThread.title || currentThread.title === "New deploy")) {
      const rawText = (override || input).trim();
      const title = rawText.length > 60 ? rawText.slice(0, 57) + "..." : rawText;
      setThreads((prev) => prev.map((t) => t.id === activeThreadId ? { ...t, title } : t));
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
        onSelect={selectThread}
        onCreate={createThread}
        onDelete={deleteThread}
      />

      {/* Chat area */}
      <main className="da-main">
        {isEmpty ? (
          /* Welcome / empty state */
          <div className="da-welcome">
            <div className="da-welcome-inner">
              <h2 className="da-welcome-title">What can I help you deploy?</h2>

              <div className="da-welcome-suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s.text} className="da-suggestion" onClick={() => sendMessage(s.text)}>
                    <s.icon className="h-3.5 w-3.5 da-suggestion-icon" />
                    <span>{s.text}</span>
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
                  projectId={projectId}
                  attachments={attachments}
                  onAddAttachment={addAttachment}
                  onRemoveAttachment={removeAttachment}
                  workspaces={workspaces}
                  selectedWorkspace={selectedWorkspace}
                  onSelectWorkspace={setSelectedWorkspace}
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
                projectId={projectId}
                attachments={attachments}
                onAddAttachment={addAttachment}
                onRemoveAttachment={removeAttachment}
                workspaces={workspaces}
                selectedWorkspace={selectedWorkspace}
                onSelectWorkspace={setSelectedWorkspace}
              />
            </div>
          </>
        )}
      </main>
    </div>
  );
}

const SUGGESTIONS = [
  { text: "Deploy my app to production", icon: Rocket },
  { text: "Analyze my project structure", icon: Wrench },
  { text: "List my instances and status", icon: Server },
  { text: "Set up a custom domain", icon: Globe },
];

/* ═══════════════════════════════════════════
   CHAT INPUT BOX — with attachments + filesystem
   ═══════════════════════════════════════════ */

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileIcon(mime: string, name: string): React.ElementType {
  if (mime.startsWith("image/")) return Image;
  const ext = name.split(".").pop()?.toLowerCase() || "";
  if (["js", "ts", "tsx", "jsx", "py", "go", "rs", "java", "json", "yaml", "toml", "css", "html", "xml"].includes(ext)) return FileCode;
  return FileText;
}

function ChatInputBox({ input, streaming, textareaRef, onInputChange, onKeyDown, onSend, onStop, projectId, attachments, onAddAttachment, onRemoveAttachment, workspaces, selectedWorkspace, onSelectWorkspace }: {
  input: string;
  streaming: boolean;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  onInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  onSend: () => void;
  onStop: () => void;
  projectId: string;
  attachments: Attachment[];
  onAddAttachment: (a: Attachment) => void;
  onRemoveAttachment: (id: string) => void;
  workspaces: any[];
  selectedWorkspace: string | null;
  onSelectWorkspace: (ws: string | null) => void;
}) {
  const [showPicker, setShowPicker] = useState<"zar" | null>(null);
  const [pickerMenu, setPickerMenu] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<{ id: string; file: File; preview?: string }[]>([]);
  const pickerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const dragCounterRef = useRef(0);

  // Close picker on outside click
  useEffect(() => {
    if (!showPicker && !pickerMenu) return;
    const handler = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setShowPicker(null);
        setPickerMenu(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showPicker, pickerMenu]);

  // Process files (local or dropped)
  const processFiles = useCallback((fileList: FileList | File[]) => {
    const files = Array.from(fileList);
    for (const f of files) {
      if (f.size > MAX_FILE_SIZE) continue;
      const id = `file_${f.name}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
      onAddAttachment({ id, type: "file", label: `${f.name} (${formatFileSize(f.size)})`, path: f.name });
      // Generate preview for images
      if (f.type.startsWith("image/")) {
        const reader = new FileReader();
        reader.onload = (ev) => {
          setUploadedFiles((prev) => [...prev, { id, file: f, preview: ev.target?.result as string }]);
        };
        reader.readAsDataURL(f);
      } else {
        setUploadedFiles((prev) => [...prev, { id, file: f }]);
      }
    }
  }, [onAddAttachment]);

  const handleRemoveFile = useCallback((id: string) => {
    onRemoveAttachment(id);
    setUploadedFiles((prev) => prev.filter((f) => f.id !== id));
  }, [onRemoveAttachment]);

  // Drag and drop handlers
  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation();
    dragCounterRef.current++;
    if (e.dataTransfer.types.includes("Files")) setDragging(true);
  }, []);
  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation();
    dragCounterRef.current--;
    if (dragCounterRef.current === 0) setDragging(false);
  }, []);
  const handleDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); }, []);
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation();
    dragCounterRef.current = 0;
    setDragging(false);
    if (e.dataTransfer.files.length > 0) processFiles(e.dataTransfer.files);
  }, [processFiles]);

  const handleLocalFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) processFiles(e.target.files);
    e.target.value = "";
  };

  const handleLocalFolder = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const first = files[0];
    const folderName = first.webkitRelativePath?.split("/")[0] || "folder";
    onAddAttachment({
      id: `localdir_${folderName}_${Date.now()}`,
      type: "folder",
      label: `${folderName}/ (${files.length} files)`,
      path: folderName,
    });
    e.target.value = "";
  };

  const ATTACH_ICON: Record<string, React.ElementType> = {
    workspace: FolderOpen,
    zar: Package,
    folder: FolderClosed,
    file: FileText,
  };

  // Find uploaded file data for preview
  const getUploadPreview = (id: string) => uploadedFiles.find((f) => f.id === id);

  return (
    <div
      className="da-input-box"
      ref={pickerRef}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {/* Drag overlay */}
      {dragging && (
        <div className="da-drag-overlay">
          <Upload className="h-6 w-6" />
          <span>Drop files here</span>
        </div>
      )}

      <div className="da-input-inner">
        {/* File previews (images) */}
        {uploadedFiles.some((f) => f.preview) && (
          <div className="da-file-previews">
            {uploadedFiles.filter((f) => f.preview).map((f) => (
              <div key={f.id} className="da-file-preview">
                <img src={f.preview} alt={f.file.name} className="da-file-preview-img" />
                <button className="da-file-preview-x" onClick={() => handleRemoveFile(f.id)}>
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Attachment chips */}
        {attachments.length > 0 && (
          <div className="da-attach-chips">
            {attachments.map((a) => {
              const uploaded = getUploadPreview(a.id);
              const Icon = uploaded ? getFileIcon(uploaded.file.type, uploaded.file.name) : (ATTACH_ICON[a.type] || FileText);
              // Skip image previews (shown above)
              if (uploaded?.preview) return null;
              return (
                <span key={a.id} className="da-attach-chip">
                  <Icon className="h-3 w-3 shrink-0" />
                  <span className="da-attach-chip-label">{a.label}</span>
                  <button className="da-attach-chip-x" onClick={() => handleRemoveFile(a.id)}>
                    <X className="h-2.5 w-2.5" />
                  </button>
                </span>
              );
            })}
          </div>
        )}

        <div className="da-input-content">
          <div className="da-textarea-wrap">
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
          </div>
          <div className="da-toolbar">
            <div className="da-toolbar-left">
              <button
                className="da-attach-btn"
                onClick={() => setPickerMenu(!pickerMenu)}
                title="Attach"
                disabled={streaming}
              >
                <Plus className="h-4 w-4" />
              </button>
              <ConnectorPicker projectId={projectId} />
            </div>
            <div className="da-toolbar-right">
              {/* Workspace indicator (gradient text) */}
              <div className="da-model-indicator-wrap">
                <WorkspaceDropdown
                  workspaces={workspaces}
                  selected={selectedWorkspace}
                  onSelect={onSelectWorkspace}
                />
              </div>
              {/* Send / Stop */}
              {streaming ? (
                <button onClick={onStop} className="da-send-btn active" title="Stop">
                  <Square className="h-3.5 w-3.5" />
                </button>
              ) : (
                <button
                  onClick={onSend}
                  disabled={!input.trim() && attachments.length === 0}
                  className="da-send-btn active"
                  title="Send"
                >
                  <ArrowUp className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Hidden file inputs */}
      <input ref={fileInputRef} type="file" multiple hidden onChange={handleLocalFiles} />
      <input ref={folderInputRef} type="file" hidden onChange={handleLocalFolder}
        {...{ webkitdirectory: "", directory: "" } as any} />

      {/* Attach menu dropdown */}
      {pickerMenu && !showPicker && (
        <div className="da-attach-menu">
          <div className="da-attach-menu-header">
            <span className="da-attach-menu-title">Attach</span>
          </div>
          <button className="da-attach-menu-item" onClick={() => { setPickerMenu(false); setShowPicker("zar"); }}>
            <span className="da-attach-menu-icon"><Package className="h-4 w-4" /></span>
            Workspace
          </button>
          <button className="da-attach-menu-item" onClick={() => { setPickerMenu(false); folderInputRef.current?.click(); }}>
            <span className="da-attach-menu-icon"><FolderClosed className="h-4 w-4" /></span>
            Folder
          </button>
        </div>
      )}

      {/* .zar picker */}
      {showPicker === "zar" && (
        <ZarPicker
          projectId={projectId}
          onSelect={(ws, branch, ver) => {
            onAddAttachment({ id: `zar_${ws}_${branch}_${ver}`, type: "zar", label: `${ws}@${branch}/${ver}`, workspace: ws });
            setShowPicker(null);
          }}
          onClose={() => setShowPicker(null)}
        />
      )}

      <div className="da-disclaimer">AI can make mistakes. Double-check responses.</div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   ZAR PICKER
   ═══════════════════════════════════════════ */

function ZarPicker({ projectId, onSelect, onClose }: {
  projectId: string;
  onSelect: (ws: string, branch: string, version: string) => void;
  onClose: () => void;
}) {
  const [workspaces, setWorkspaces] = useState<any[]>([]);
  const [selectedWs, setSelectedWs] = useState<string | null>(null);
  const [versions, setVersions] = useState<{ versions: string[]; branches: Record<string, string> }>({ versions: [], branches: {} });
  const [loading, setLoading] = useState(true);
  const [loadingVer, setLoadingVer] = useState(false);

  useEffect(() => {
    listWorkspaces(projectId)
      .then((r) => setWorkspaces(r.workspaces || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId]);

  useEffect(() => {
    if (!selectedWs) return;
    setLoadingVer(true);
    zarVersions(projectId, selectedWs)
      .then((r) => setVersions({ versions: r.versions || [], branches: r.branches || {} }))
      .catch(() => setVersions({ versions: [], branches: {} }))
      .finally(() => setLoadingVer(false));
  }, [selectedWs, projectId]);

  return (
    <div className="da-picker">
      <div className="da-picker-header">
        <span className="da-picker-title">{selectedWs ? `${selectedWs} — versions` : "Select workspace"}</span>
        <button className="da-picker-close" onClick={selectedWs ? () => setSelectedWs(null) : onClose}>
          {selectedWs ? <ChevronRight className="h-3.5 w-3.5 rotate-180" /> : <X className="h-3.5 w-3.5" />}
        </button>
      </div>
      <div className="da-picker-body">
        {loading ? (
          <div className="da-picker-loading"><Loader2 className="h-4 w-4 animate-spin" /> Loading...</div>
        ) : !selectedWs ? (
          workspaces.length === 0 ? (
            <div className="da-picker-empty">No workspaces</div>
          ) : (
            workspaces.map((ws) => (
              <button key={ws.name} className="da-picker-item" onClick={() => setSelectedWs(ws.name)}>
                <Package className="h-3.5 w-3.5 shrink-0" />
                <span className="da-picker-item-name">{ws.name}</span>
                <ChevronRight className="h-3 w-3 opacity-30 ml-auto" />
              </button>
            ))
          )
        ) : loadingVer ? (
          <div className="da-picker-loading"><Loader2 className="h-4 w-4 animate-spin" /> Loading versions...</div>
        ) : versions.versions.length === 0 ? (
          <div className="da-picker-empty">No versions published</div>
        ) : (
          versions.versions.map((v) => (
            <button key={v} className="da-picker-item" onClick={() => onSelect(selectedWs, "main", v)}>
              <GitBranch className="h-3.5 w-3.5 shrink-0" />
              <span className="da-picker-item-name">{v}</span>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

/* (FileBrowser removed — local file/folder pickers used instead) */

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

/* ═══════════════════════════════════════════
   WORKSPACE DROPDOWN
   ═══════════════════════════════════════════ */

function WorkspaceDropdown({ workspaces, selected, onSelect }: {
  workspaces: any[];
  selected: string | null;
  onSelect: (ws: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div className="da-ws-selector" ref={ref}>
      <button className="da-ws-trigger" onClick={() => setOpen(!open)}>
        {selected ? (
          <span className="da-ws-trigger-label">{selected}</span>
        ) : (
          <span className="da-ws-trigger-label da-ws-trigger-placeholder">Workspaces</span>
        )}
        <ChevronDown className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)", flexShrink: 0 }} />
      </button>
      {open && (
        <div className="da-ws-dropdown">
          <div className="da-ws-dropdown-header">
            <span className="da-ws-dropdown-title">Workspaces</span>
          </div>
          <button
            className={`da-ws-option ${!selected ? "active" : ""}`}
            onClick={() => { onSelect(null); setOpen(false); }}
          >
            <span className="da-ws-option-icon"><Globe className="h-4 w-4" /></span>
            All workspaces
          </button>
          {workspaces.map((ws: any) => (
            <button
              key={ws.name}
              className={`da-ws-option ${selected === ws.name ? "active" : ""}`}
              onClick={() => { onSelect(ws.name); setOpen(false); }}
            >
              <span className="da-ws-option-icon"><Package className="h-4 w-4" /></span>
              {ws.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
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
  if (msg.role === "tool_call") return <ToolInline name={msg.toolName || ""} args={msg.toolArgs} />;
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
      {toolCall && <ToolInline name={toolCall.name} args={toolCall.args} isStreaming />}
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

/** Tool call in progress — inline with dot + name + args preview */
function ToolInline({ name, args, isStreaming }: {
  name: string; args?: any; isStreaming?: boolean;
}) {
  const displayName = TOOL_NAMES[name] || name.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
  const parsedArgs = typeof args === "string" ? safeParse(args) : args;

  // Build a meaningful preview from args
  const preview = useMemo(() => {
    if (!parsedArgs || typeof parsedArgs !== "object") return "";
    const parts: string[] = [];
    if (parsedArgs.workspace) parts.push(parsedArgs.workspace);
    if (parsedArgs.instance_id) parts.push(parsedArgs.instance_id);
    if (parsedArgs.file_path) parts.push(parsedArgs.file_path);
    if (parsedArgs.connector_id) parts.push(parsedArgs.connector_id);
    if (parsedArgs.key) parts.push(parsedArgs.key);
    if (parts.length === 0) {
      const first = Object.values(parsedArgs)[0];
      if (first && typeof first === "string") parts.push(first.slice(0, 60));
    }
    return parts.join(" · ");
  }, [parsedArgs]);

  return (
    <div className="da-tool-inline">
      <span className={`da-tool-dot ${isStreaming ? "streaming" : "idle"}`} />
      <span className="da-tool-name">{displayName}</span>
      {preview && <span className="da-tool-preview">{preview}</span>}
      {isStreaming && <Loader2 className="h-3 w-3 animate-spin shrink-0" style={{ color: "var(--da-accent)" }} />}
    </div>
  );
}

/** Deploy result card — shown for run_ship results */
function DeployResultCard({ data }: { data: any }) {
  const isOk = data?.ok;
  return (
    <div className="da-deploy-card">
      <div className="da-deploy-card-header">
        {isOk ? (
          <CheckCircle2 className="h-4 w-4" style={{ color: "#4ade80" }} />
        ) : (
          <XCircle className="h-4 w-4" style={{ color: "#f87171" }} />
        )}
        <span className="da-deploy-card-title">
          {isOk ? "Deployed successfully" : "Deploy failed"}
        </span>
      </div>
      {isOk && (
        <div className="da-deploy-card-body">
          {data.domain && (
            <div className="da-deploy-card-row">
              <Globe className="h-3.5 w-3.5" />
              <a
                href={`https://${data.domain}`}
                target="_blank"
                rel="noopener noreferrer"
                className="da-deploy-card-link"
              >
                {data.domain}
              </a>
            </div>
          )}
          {data.workspace && (
            <div className="da-deploy-card-row">
              <Package className="h-3.5 w-3.5" />
              <span>{data.workspace}</span>
              {data.version && <span className="da-deploy-card-meta">v{data.version}</span>}
              {data.branch && data.branch !== "main" && (
                <span className="da-deploy-card-meta">{data.branch}</span>
              )}
            </div>
          )}
          {data.instance_id && (
            <div className="da-deploy-card-row">
              <Server className="h-3.5 w-3.5" />
              <span className="da-deploy-card-meta">{data.instance_id}</span>
            </div>
          )}
        </div>
      )}
      {!isOk && data.error && (
        <div className="da-deploy-card-body">
          <p style={{ color: "#f87171", fontSize: 13, margin: 0 }}>{data.error}</p>
        </div>
      )}
    </div>
  );
}

/** Tool result — expandable block with status, uses FileTokenView for file reads */
function ToolResultBlock({ name, result }: { name: string; result?: string }) {
  const [expanded, setExpanded] = useState(false);
  const displayName = TOOL_NAMES[name] || name.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
  const parsed = result ? safeParse(result) : null;
  const isOk = parsed ? parsed?.ok !== false && !parsed?.error : true;

  // Deploy result → special card
  if (name === "run_ship" && parsed && typeof parsed === "object") {
    return <DeployResultCard data={parsed} />;
  }

  // File content → render with FileTokenView
  const fileData = useMemo((): FileEntry | null => {
    if (!parsed || typeof parsed !== "object") return null;
    if (name === "read_workspace_file" && parsed.content) {
      const filename = parsed.path || parsed.file || "file";
      const shortName = filename.split("/").pop() || filename;
      return { name: shortName, path: filename, content: parsed.content };
    }
    if (name === "write_workspace_file" && parsed.content) {
      const filename = parsed.path || parsed.file || "file";
      const shortName = filename.split("/").pop() || filename;
      return { name: shortName, path: filename, content: parsed.content };
    }
    return null;
  }, [parsed, name]);

  if (fileData) {
    return (
      <div className="my-2">
        <FileTokenView files={[fileData]} title={displayName} />
      </div>
    );
  }

  // Build summary lines for structured results
  const summaryLines = useMemo(() => {
    if (!parsed || typeof parsed !== "object") return [];
    const lines: string[] = [];

    // Workspace/instance lists
    if (parsed.workspaces && Array.isArray(parsed.workspaces)) {
      for (const ws of parsed.workspaces.slice(0, 10)) {
        lines.push(`${ws.name || ws}${ws.stack ? ` (${ws.stack})` : ""}${ws.path ? ` — ${ws.path}` : ""}`);
      }
    }
    if (parsed.instances && Array.isArray(parsed.instances)) {
      for (const inst of parsed.instances.slice(0, 10)) {
        lines.push(`${inst.label || inst.id} — ${inst.state || "unknown"}${inst.ip ? ` (${inst.ip})` : ""}`);
      }
    }
    if (parsed.secrets && typeof parsed.secrets === "object" && !Array.isArray(parsed.secrets)) {
      for (const [bucket, keys] of Object.entries(parsed.secrets)) {
        const keyList = Array.isArray(keys) ? keys : [];
        lines.push(`${bucket}: ${keyList.join(", ")}`);
      }
    }
    if (parsed.connectors && Array.isArray(parsed.connectors)) {
      for (const c of parsed.connectors) {
        lines.push(`${c.name || c.connector_id} — ${c.configured ? "configured" : "not configured"}`);
      }
    }

    // Generic output fields
    if (lines.length === 0) {
      const output = parsed.output || parsed.stdout || parsed.result || parsed.message || "";
      if (output) lines.push(...String(output).split("\n").filter(Boolean));
    }

    // Fallback: show key fields
    if (lines.length === 0) {
      for (const [k, v] of Object.entries(parsed)) {
        if (k === "ok" || k === "error") continue;
        if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
          lines.push(`${k}: ${v}`);
        }
      }
    }

    return lines;
  }, [parsed]);

  const hasContent = summaryLines.length > 0;
  const isMultiLine = summaryLines.length > 3;

  return (
    <div className="da-result-block">
      <div className="da-result-header" onClick={() => hasContent && setExpanded(!expanded)} style={{ cursor: hasContent ? "pointer" : "default" }}>
        <span className={`da-tool-dot ${isOk ? "success" : "error"}`} />
        <span className="da-tool-name">{displayName}</span>
        {parsed?.error && (
          <span className="da-result-error-hint">{String(parsed.error).slice(0, 80)}</span>
        )}
        <span className="da-result-status" style={{ color: isOk ? "#4ade80" : "#f87171" }}>
          {isOk ? "Done" : "Failed"}
        </span>
        {hasContent && isMultiLine && (
          <ChevronDown className={`h-3 w-3 opacity-40 shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`} />
        )}
      </div>
      {hasContent && (expanded || !isMultiLine) && (
        <pre className="da-result-output">{summaryLines.slice(0, expanded ? undefined : 5).join("\n")}</pre>
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
   TOKENIZER + RENDERER — multi-format message rendering
   Handles: markdown, HTML, code blocks, plain text
   ═══════════════════════════════════════════ */

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/** Token types for the message tokenizer */
type TokenType = "markdown" | "html";
interface ContentToken { type: TokenType; content: string }

/**
 * Tokenize a message into markdown and HTML segments.
 * ReactMarkdown handles code blocks, tables, lists, etc. natively.
 * This tokenizer ONLY extracts standalone HTML blocks for special rendering.
 */
function tokenizeContent(text: string): ContentToken[] {
  if (!text) return [];

  // Check if the entire content is an HTML document
  const trimmed = text.trim();
  if (/^<(!DOCTYPE|html)\b/i.test(trimmed)) {
    return [{ type: "html", content: text }];
  }

  // Look for standalone HTML block elements (not inside code fences)
  // First, protect code fences by replacing them with placeholders
  const codeFences: string[] = [];
  const protected_ = text.replace(/```[\s\S]*?```/g, (match) => {
    codeFences.push(match);
    return `\x00CODEFENCE${codeFences.length - 1}\x00`;
  });

  // Split on HTML block-level elements
  const htmlBlockRegex = /(<(?:div|section|article|form|nav|header|footer|details|figure|iframe|video|audio|canvas|svg)\b[^>]*>[\s\S]*?<\/(?:div|section|article|form|nav|header|footer|details|figure|iframe|video|audio|canvas|svg)>)/gi;

  if (!htmlBlockRegex.test(protected_)) {
    // No HTML blocks — everything is markdown
    return [{ type: "markdown", content: text }];
  }

  // Reset regex
  htmlBlockRegex.lastIndex = 0;
  const parts = protected_.split(htmlBlockRegex);
  const tokens: ContentToken[] = [];

  for (const part of parts) {
    if (!part.trim()) continue;
    // Restore code fences
    const restored = part.replace(/\x00CODEFENCE(\d+)\x00/g, (_, i) => codeFences[parseInt(i)]);
    if (/^<(?:div|section|article|form|nav|header|footer|details|figure|iframe|video|audio|canvas|svg)\b/i.test(part.trim())) {
      tokens.push({ type: "html", content: restored });
    } else {
      tokens.push({ type: "markdown", content: restored });
    }
  }

  return tokens.length ? tokens : [{ type: "markdown", content: text }];
}

/** Render an HTML token safely inside a sandboxed container */
function HtmlRenderer({ html }: { html: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    // Sanitize: strip script tags and event handlers
    const sanitized = html
      .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, "")
      .replace(/\bon\w+\s*=\s*"[^"]*"/gi, "")
      .replace(/\bon\w+\s*=\s*'[^']*'/gi, "");
    ref.current.innerHTML = sanitized;
  }, [html]);
  return <div ref={ref} className="da-html-render" />;
}

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

/** Main content renderer — tokenizes then renders each segment */
const ChatMarkdown = memo(function ChatMarkdown({ text }: { text: string }) {
  const tokens = useMemo(() => tokenizeContent(text), [text]);
  return (
    <div className="da-md">
      {tokens.map((token, i) =>
        token.type === "html" ? (
          <HtmlRenderer key={i} html={token.content} />
        ) : (
          <ReactMarkdown key={i} remarkPlugins={[remarkGfm]} components={mdComponents}>
            {token.content}
          </ReactMarkdown>
        )
      )}
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
