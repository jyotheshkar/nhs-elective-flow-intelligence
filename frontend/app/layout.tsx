import type { Metadata } from "next";

import AppShell from "@/components/AppShell";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "NHS Elective Flow Intelligence",
    template: "%s · NHS Elective Flow Intelligence",
  },
  description:
    "Operational decision intelligence for NHS elective waiting list management, built on publicly available NHS England aggregate statistics.",
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en-GB">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
