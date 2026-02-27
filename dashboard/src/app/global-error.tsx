"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en" className="dark">
      <body style={{ background: "#0d1117", color: "#c9d1d9", fontFamily: "monospace", padding: 40 }}>
        <h2 style={{ color: "#f85149" }}>Something went wrong</h2>
        <pre style={{ background: "#161b22", padding: 16, borderRadius: 8, overflow: "auto", fontSize: 13 }}>
          {error.message}
          {"\n\n"}
          {error.stack}
        </pre>
        <button
          onClick={reset}
          style={{ marginTop: 16, padding: "8px 16px", background: "#238636", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer" }}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
