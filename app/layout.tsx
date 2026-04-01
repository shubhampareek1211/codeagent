import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sports Analytics Workbench",
  description:
    "Standalone natural-language sports analytics demo with a Next.js frontend and FastAPI + LangGraph backend.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
