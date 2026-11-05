import { QueryProvider } from "@/lib/query";
import { SentryClient } from "@/lib/sentry-client";
import type { Metadata } from "next";
import { Manrope, Sora } from "next/font/google";
import "./globals.css";

const display = Sora({
  subsets: ["latin"],
  weight: ["600", "700"],
  variable: "--font-display",
});

const sans = Manrope({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "Settlr",
  description: "Painel do operador — exceções, pagamentos, títulos e o agente de WhatsApp.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className={`${display.variable} ${sans.variable}`}>
      <head />
      <body>
        <SentryClient />
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
