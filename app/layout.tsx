import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Adaptive RAG | Knowledge workspace",
  description: "Query a local knowledge base, trace retrieved passages, and inspect answer grounding.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
