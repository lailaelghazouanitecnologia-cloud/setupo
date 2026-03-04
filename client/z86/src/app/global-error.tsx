"use client";

export default function GlobalError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <html>
      <body style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", fontFamily: "system-ui", background: "#0a0a0a", color: "#fafafa" }}>
        <div style={{ textAlign: "center" }}>
          <h2 style={{ fontSize: 18, fontWeight: 500, marginBottom: 8 }}>Something went wrong</h2>
          <p style={{ fontSize: 13, color: "#888", marginBottom: 16 }}>{error.message}</p>
          <button onClick={reset} style={{ padding: "8px 16px", background: "#6366f1", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 13 }}>Try again</button>
        </div>
      </body>
    </html>
  );
}
