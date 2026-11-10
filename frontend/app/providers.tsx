"use client";
import { SessionProvider } from "next-auth/react";
import { ConfigProvider } from "@/lib/config";

export default function Providers({ children }: { children: React.ReactNode }) {
  return <SessionProvider><ConfigProvider>{children}</ConfigProvider></SessionProvider>;
}
