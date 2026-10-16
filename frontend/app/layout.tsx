import "./globals.css";
import type { Metadata } from "next";
import AuthProvider from "@/components/AuthProvider";

export const metadata: Metadata = {
  title: "PANDA AI · Prompt-driven Analytics & Natural Data Access",
  description: "PANDA AI: ask your data in plain English, get governed answers and root-cause analysis.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body><AuthProvider>{children}</AuthProvider></body></html>;
}
