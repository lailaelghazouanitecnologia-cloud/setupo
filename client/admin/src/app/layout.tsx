import type { Metadata } from "next";
import { Providers } from "@/contexts/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sonfazt — Admin Panel",
  description: "NSO admin panel — sonfazt.nso.dev",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: `
          (function() {
            var t = localStorage.getItem('sonfazt_theme') || 'dark';
            if (t === 'auto') {
              t = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
            }
            if (t === 'dark') document.documentElement.classList.add('dark');
          })();
        `}} />
      </head>
      <body><Providers>{children}</Providers></body>
    </html>
  );
}
