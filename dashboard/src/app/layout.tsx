import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NSO — Dashboard",
  description: "NSO infrastructure dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: `
          (function() {
            var t = localStorage.getItem('nso_theme') || 'dark';
            if (t === 'auto') {
              t = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
            }
            if (t === 'dark') document.documentElement.classList.add('dark');
          })();
        `}} />
      </head>
      <body>{children}</body>
    </html>
  );
}
