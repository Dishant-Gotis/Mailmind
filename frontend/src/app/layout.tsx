import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MailMind — AI Email Coordination Assistant",
  description:
    "Automate meeting scheduling with intelligent AI agents that read emails, resolve conflicts, and book calendar events — so your team never wastes time on coordination again.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="h-full">{children}</body>
    </html>
  );
}
