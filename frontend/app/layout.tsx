import "./globals.css";
import type { Metadata } from "next";
import Providers from "./providers";

export const metadata: Metadata = { title: "VM Algo", description: "Strategy builder, backtesting, scanner and automated trading for Indian markets and crypto" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // suppressHydrationWarning: browser extensions (dark mode, translators, Grammarly...) edit <html>/<body> before React hydrates; that must not break the app.
  return <html lang="en" suppressHydrationWarning><body suppressHydrationWarning><Providers>{children}</Providers></body></html>;
}
