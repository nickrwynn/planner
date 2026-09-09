import "./globals.css";
import { AppShell } from "../components/app-shell";
import { ThemeBoot } from "../components/theme-boot";
import type { Metadata, Viewport } from "next";

export const metadata: Metadata = {
  title: "StudyFlows",
  description: "StudyFlows — courses, resources, and study tools",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "StudyFlows"
  }
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#111827"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeBoot />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
