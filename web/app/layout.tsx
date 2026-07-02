import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AvatarForge",
  description: "Self-hosted AI avatar video studio",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
