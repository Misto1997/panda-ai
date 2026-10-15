import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = { title: "PANDA · Prompt-driven Analytics & Natural Data Access", description: "Ask your data in plain English." };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
