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
      <body style={{ background: "#0d1117", color: "#c9d1d9", fontFamily: "system-ui, sans-serif", padding: 40, textAlign: "center" }}>
        <div style={{ maxWidth: 420, margin: "80px auto" }}>
          <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.5 }}>&#9888;</div>
          <h2 style={{ fontSize: 20, fontWeight: 600, marginBottom: 8 }}>Something went wrong</h2>
          <p style={{ color: "#8b949e", fontSize: 14, marginBottom: 24 }}>
            An unexpected error occurred. Please try again or reload the page.
          </p>
          <button
            onClick={reset}
            style={{ padding: "10px 24px", background: "#238636", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 14, fontWeight: 500 }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
