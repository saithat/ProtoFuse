import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ProtoFuse / Evaluation Readout",
  description: "A workload-specific summary of current ProtoFuse cohorts, paired execution evidence, and independent audit outcomes.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
