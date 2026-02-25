import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Setupo — Infrastructure Dashboard",
  description: "VPS management dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
