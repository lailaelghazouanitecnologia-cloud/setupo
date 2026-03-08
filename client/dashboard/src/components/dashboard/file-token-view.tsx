"use client";

import React, { useState, useMemo, memo } from "react";
import { FileText, ChevronDown, ChevronRight, Hash } from "lucide-react";

/* ═══════════════════════════════════════════
   FILE TOKEN VIEW — Tokenized file renderer
   Orange (keywords/funcs) + Blue (strings/types)
   ═══════════════════════════════════════════ */

/* ── Token types ── */
type TokenKind =
  | "keyword"    // orange
  | "builtin"    // orange-light
  | "function"   // orange
  | "string"     // blue
  | "type"       // blue
  | "number"     // blue-light
  | "comment"    // muted
  | "decorator"  // orange-soft
  | "operator"   // muted
  | "punctuation"// dim
  | "plain";     // default

interface Token {
  kind: TokenKind;
  text: string;
}

interface TokenizedLine {
  tokens: Token[];
  lineNumber: number;
}

/* ── Python tokenizer ── */

const PY_KEYWORDS = new Set([
  "def", "class", "import", "from", "return", "if", "elif", "else",
  "for", "while", "try", "except", "finally", "with", "as", "yield",
  "raise", "pass", "break", "continue", "and", "or", "not", "in",
  "is", "lambda", "async", "await", "None", "True", "False", "global",
  "nonlocal", "del", "assert",
]);

const PY_BUILTINS = new Set([
  "print", "len", "range", "int", "str", "list", "dict", "set",
  "tuple", "bool", "float", "type", "isinstance", "hasattr", "getattr",
  "setattr", "super", "property", "staticmethod", "classmethod",
  "enumerate", "zip", "map", "filter", "sorted", "reversed", "any",
  "all", "open", "Exception", "ValueError", "TypeError", "KeyError",
  "RuntimeError", "AttributeError", "ImportError", "StopIteration",
]);

const TS_KEYWORDS = new Set([
  "const", "let", "var", "function", "return", "if", "else", "for",
  "while", "do", "switch", "case", "break", "continue", "try", "catch",
  "finally", "throw", "new", "delete", "typeof", "instanceof", "in",
  "of", "class", "extends", "implements", "interface", "type", "enum",
  "import", "export", "default", "from", "as", "async", "await",
  "yield", "void", "null", "undefined", "true", "false", "this",
  "super", "static", "readonly", "abstract", "public", "private",
  "protected", "declare", "module", "namespace",
]);

const TS_TYPES = new Set([
  "string", "number", "boolean", "any", "void", "never", "unknown",
  "object", "symbol", "bigint", "null", "undefined", "Array", "Promise",
  "Record", "Partial", "Required", "Pick", "Omit", "Exclude", "Extract",
  "React", "ReactNode", "JSX", "HTMLElement", "Event", "MouseEvent",
]);

function detectLang(filename: string): "python" | "typescript" | "toml" | "text" {
  if (filename.endsWith(".py")) return "python";
  if (filename.endsWith(".ts") || filename.endsWith(".tsx") || filename.endsWith(".js") || filename.endsWith(".jsx") || filename.endsWith(".mjs") || filename.endsWith(".cjs")) return "typescript";
  if (filename.endsWith(".toml") || filename.endsWith(".yaml") || filename.endsWith(".yml") || filename.endsWith(".ini") || filename.endsWith(".cfg") || filename.endsWith(".env")) return "toml";
  if (filename.endsWith(".json") || filename.endsWith(".css") || filename.endsWith(".html") || filename.endsWith(".md") || filename.endsWith(".sh") || filename.endsWith(".bash")) return "typescript";
  return "text";
}

function tokenizeLine(line: string, lang: "python" | "typescript" | "toml" | "text"): Token[] {
  if (lang === "text") return [{ kind: "plain", text: line }];

  const tokens: Token[] = [];
  let i = 0;

  while (i < line.length) {
    // Whitespace
    if (/\s/.test(line[i])) {
      let start = i;
      while (i < line.length && /\s/.test(line[i])) i++;
      tokens.push({ kind: "plain", text: line.slice(start, i) });
      continue;
    }

    // Comments
    if (lang === "python" && line[i] === "#") {
      tokens.push({ kind: "comment", text: line.slice(i) });
      break;
    }
    if (lang === "typescript" && line[i] === "/" && line[i + 1] === "/") {
      tokens.push({ kind: "comment", text: line.slice(i) });
      break;
    }
    if (lang === "toml" && line[i] === "#") {
      tokens.push({ kind: "comment", text: line.slice(i) });
      break;
    }

    // TOML section headers [section]
    if (lang === "toml" && line[i] === "[") {
      let end = line.indexOf("]", i);
      if (end !== -1) {
        tokens.push({ kind: "keyword", text: line.slice(i, end + 1) });
        i = end + 1;
        continue;
      }
    }

    // Strings (single, double, triple)
    if (line[i] === '"' || line[i] === "'") {
      const q = line[i];
      // Triple quote
      if (line[i + 1] === q && line[i + 2] === q) {
        let end = line.indexOf(q + q + q, i + 3);
        if (end === -1) {
          tokens.push({ kind: "string", text: line.slice(i) });
          break;
        }
        tokens.push({ kind: "string", text: line.slice(i, end + 3) });
        i = end + 3;
        continue;
      }
      // Single-line string
      let j = i + 1;
      while (j < line.length && line[j] !== q) {
        if (line[j] === "\\") j++;
        j++;
      }
      tokens.push({ kind: "string", text: line.slice(i, j + 1) });
      i = j + 1;
      continue;
    }

    // f-strings prefix
    if (lang === "python" && (line[i] === "f" || line[i] === "b" || line[i] === "r") &&
        (line[i + 1] === '"' || line[i + 1] === "'")) {
      const prefix = line[i];
      const q = line[i + 1];
      let j = i + 2;
      while (j < line.length && line[j] !== q) {
        if (line[j] === "\\") j++;
        j++;
      }
      tokens.push({ kind: "string", text: line.slice(i, j + 1) });
      i = j + 1;
      continue;
    }

    // Decorators
    if (lang === "python" && line[i] === "@") {
      let j = i + 1;
      while (j < line.length && /[\w.]/.test(line[j])) j++;
      tokens.push({ kind: "decorator", text: line.slice(i, j) });
      i = j;
      continue;
    }

    // Numbers
    if (/\d/.test(line[i])) {
      let j = i;
      while (j < line.length && /[\d._xXoObBeE]/.test(line[j])) j++;
      tokens.push({ kind: "number", text: line.slice(i, j) });
      i = j;
      continue;
    }

    // Words (identifiers, keywords)
    if (/[\w]/.test(line[i])) {
      let j = i;
      while (j < line.length && /[\w]/.test(line[j])) j++;
      const word = line.slice(i, j);

      // Check if followed by (  → function call
      let afterWord = j;
      while (afterWord < line.length && line[afterWord] === " ") afterWord++;
      const isCall = line[afterWord] === "(";

      if (lang === "python") {
        if (PY_KEYWORDS.has(word)) tokens.push({ kind: "keyword", text: word });
        else if (PY_BUILTINS.has(word)) tokens.push({ kind: "builtin", text: word });
        else if (isCall) tokens.push({ kind: "function", text: word });
        else if (word[0] === word[0].toUpperCase() && /^[A-Z]/.test(word)) tokens.push({ kind: "type", text: word });
        else tokens.push({ kind: "plain", text: word });
      } else if (lang === "typescript") {
        if (TS_KEYWORDS.has(word)) tokens.push({ kind: "keyword", text: word });
        else if (TS_TYPES.has(word)) tokens.push({ kind: "type", text: word });
        else if (isCall) tokens.push({ kind: "function", text: word });
        else if (word[0] === word[0].toUpperCase() && /^[A-Z]/.test(word)) tokens.push({ kind: "type", text: word });
        else tokens.push({ kind: "plain", text: word });
      } else if (lang === "toml") {
        // TOML keys before =
        const rest = line.slice(j).trimStart();
        if (rest.startsWith("=")) tokens.push({ kind: "keyword", text: word });
        else tokens.push({ kind: "plain", text: word });
      } else {
        tokens.push({ kind: "plain", text: word });
      }
      i = j;
      continue;
    }

    // Operators
    if ("=+-*/<>!&|^~%".includes(line[i])) {
      tokens.push({ kind: "operator", text: line[i] });
      i++;
      continue;
    }

    // Punctuation
    if ("()[]{}:;,.".includes(line[i])) {
      tokens.push({ kind: "punctuation", text: line[i] });
      i++;
      continue;
    }

    // Fallback
    tokens.push({ kind: "plain", text: line[i] });
    i++;
  }

  return tokens;
}

export function tokenizeFile(content: string, filename: string): TokenizedLine[] {
  const lang = detectLang(filename);
  return content.split("\n").map((line, idx) => ({
    tokens: tokenizeLine(line, lang),
    lineNumber: idx + 1,
  }));
}

/* ── Approximate token count (cl100k_base-like) ── */
export function estimateTokens(text: string): number {
  // Rough: ~4 chars per token for code
  return Math.ceil(text.length / 3.7);
}

/* ── File data ── */
export interface FileEntry {
  name: string;
  path: string;
  content: string;
  tokens?: number;  // pre-computed token count
}

/* ═══════════════════════════════════════════
   MAIN COMPONENT
   ═══════════════════════════════════════════ */

export const FileTokenView = memo(function FileTokenView({
  files,
  title,
}: {
  files: FileEntry[];
  title?: string;
}) {
  const [expandedFile, setExpandedFile] = useState<string | null>(
    files.length === 1 ? files[0].path : null
  );

  const totalTokens = useMemo(
    () => files.reduce((sum, f) => sum + (f.tokens ?? estimateTokens(f.content)), 0),
    [files]
  );

  const totalLines = useMemo(
    () => files.reduce((sum, f) => sum + f.content.split("\n").length, 0),
    [files]
  );

  return (
    <div className="ftv-container">
      {/* Header with gradient */}
      <div className="ftv-header">
        <div className="ftv-header-content">
          <span className="ftv-header-title">{title || "Files"}</span>
          <div className="ftv-header-stats">
            <span className="ftv-stat">
              <FileText className="h-3 w-3" />
              {files.length} {files.length === 1 ? "file" : "files"}
            </span>
            <span className="ftv-stat">
              <Hash className="h-3 w-3" />
              {totalTokens.toLocaleString()} tokens
            </span>
            <span className="ftv-stat-lines">{totalLines.toLocaleString()} lines</span>
          </div>
        </div>
      </div>

      {/* File list */}
      <div className="ftv-files">
        {files.map((file) => (
          <FileBlock
            key={file.path}
            file={file}
            expanded={expandedFile === file.path}
            onToggle={() => setExpandedFile(expandedFile === file.path ? null : file.path)}
          />
        ))}
      </div>
    </div>
  );
});

/* ── Single file block ── */
const FileBlock = memo(function FileBlock({
  file,
  expanded,
  onToggle,
}: {
  file: FileEntry;
  expanded: boolean;
  onToggle: () => void;
}) {
  const tokenCount = file.tokens ?? estimateTokens(file.content);
  const lineCount = file.content.split("\n").length;

  const tokenized = useMemo(
    () => (expanded ? tokenizeFile(file.content, file.name) : []),
    [expanded, file.content, file.name]
  );

  return (
    <div className={`ftv-file ${expanded ? "expanded" : ""}`}>
      {/* File title bar with gradient */}
      <button className="ftv-file-title" onClick={onToggle}>
        <span className="ftv-file-title-left">
          {expanded
            ? <ChevronDown className="h-3.5 w-3.5 shrink-0 ftv-chevron" />
            : <ChevronRight className="h-3.5 w-3.5 shrink-0 ftv-chevron" />
          }
          <span className="ftv-filename">{file.name}</span>
        </span>
        <span className="ftv-file-meta">
          <span className="ftv-token-badge">{tokenCount.toLocaleString()} tk</span>
          <span className="ftv-line-count">{lineCount} ln</span>
        </span>
      </button>

      {/* Tokenized content */}
      {expanded && (
        <div className="ftv-code-wrap">
          <pre className="ftv-code">
            {tokenized.map((line) => (
              <div key={line.lineNumber} className="ftv-line">
                <span className="ftv-line-num">{line.lineNumber}</span>
                <span className="ftv-line-content">
                  {line.tokens.map((tok, ti) => (
                    <span key={ti} className={`ftv-tok ftv-tok-${tok.kind}`}>
                      {tok.text}
                    </span>
                  ))}
                </span>
              </div>
            ))}
          </pre>
        </div>
      )}
    </div>
  );
});
