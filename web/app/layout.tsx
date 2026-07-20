import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CAVDESIGN",
  description: "design anything. prompt. generate. done.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-black font-mono text-white antialiased">
        {children}
      </body>
    </html>
  );
}
