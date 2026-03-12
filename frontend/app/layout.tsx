import type { Metadata } from "next";
import { IBM_Plex_Mono, Space_Grotesk } from "next/font/google";

import "@/app/globals.css";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";

const sans = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-ibm-plex-mono",
});

const themeInitScript = `
  (() => {
    const stored = localStorage.getItem('agentcart.theme');
    const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.dataset.theme = stored || (systemDark ? 'dark' : 'light');
  })();
`;

export const metadata: Metadata = {
  title: "AgentCart",
  description: "Session-first agentic shopping assistant for trust-heavy product decisions.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="min-h-screen bg-[color:var(--background)] font-sans text-[color:var(--text-strong)] antialiased">
        <div className="relative min-h-screen overflow-hidden bg-[radial-gradient(circle_at_top,rgba(255,122,26,0.10),transparent_32%),linear-gradient(180deg,var(--background),var(--background-elevated))]">
          <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,transparent_0%,rgba(255,255,255,0.06)_49%,transparent_100%)] opacity-40 dark:opacity-10" />
          <Header />
          <main className="relative z-10">{children}</main>
          <Footer />
        </div>
      </body>
    </html>
  );
}
