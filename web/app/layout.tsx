import { QueryProvider } from "@/lib/query";
import { SentryClient } from "@/lib/sentry-client";
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cobrança + Conciliação",
  description: "Painel do operador — exceções, pagamentos, títulos e o agente de WhatsApp.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <head />
      <body>
        <SentryClient />
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
