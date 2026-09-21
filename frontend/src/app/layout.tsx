import type { Metadata, Viewport } from "next";
import { SessionProvider } from "next-auth/react";
import { Inter, JetBrains_Mono } from "next/font/google";

import { AppShell } from "@/components/AppShell";
import { THEME_BOOT_SCRIPT } from "@/components/ThemeToggle";
import { WorkspaceProvider } from "@/components/WorkspaceProvider";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Equity Research Desk",
    template: "%s · Equity Research Desk",
  },
  description:
    "Agentic equity research desk. Licensed news, SEC filings, and sourced recommendations. Not investment advice.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f6fa" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a10" },
  ],
};

// The API token inside the session lasts an hour; refetch well before that so an open tab
// never presents an expired token.
const SESSION_REFETCH_SECONDS = 40 * 60;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body className={`${inter.variable} ${mono.variable}`}>
        <SessionProvider refetchInterval={SESSION_REFETCH_SECONDS} refetchOnWindowFocus>
          <WorkspaceProvider>
            <AppShell>{children}</AppShell>
          </WorkspaceProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
