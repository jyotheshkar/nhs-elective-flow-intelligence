import type { Metadata } from "next";

import AppShell from "@/components/AppShell";

import "./globals.css";

const SITE_DESCRIPTION =
  "Independent analytics prototype transforming publicly available NHS England " +
  "RTT waiting-list statistics into transparent operational rankings, " +
  "forecasts, peer benchmarking and scenario analysis. Not affiliated with " +
  "NHS England.";

export const metadata: Metadata = {
  title: {
    default: "NHS Elective Flow Intelligence | Operational Decision Intelligence",
    template: "%s · NHS Elective Flow Intelligence",
  },
  description: SITE_DESCRIPTION,
  applicationName: "NHS Elective Flow Intelligence",
  keywords: [
    "NHS England",
    "RTT waiting times",
    "elective care",
    "operational analytics",
    "waiting list",
    "data engineering portfolio",
  ],
  openGraph: {
    title: "NHS Elective Flow Intelligence",
    description: SITE_DESCRIPTION,
    type: "website",
    siteName: "NHS Elective Flow Intelligence",
    locale: "en_GB",
  },
  twitter: {
    card: "summary",
    title: "NHS Elective Flow Intelligence",
    description: SITE_DESCRIPTION,
  },
  robots: { index: true, follow: true },
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
