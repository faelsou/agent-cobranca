"use client";

import { api } from "@/lib/api";
import { clearToken, supabase, supabaseEnabled } from "@/lib/auth";
import { clsx } from "@/lib/format";
import { useQuery } from "@tanstack/react-query";
import {
  CheckSquare,
  CircleDollarSign,
  FileWarning,
  Gauge,
  LogOut,
  MessageSquare,
  Receipt,
  Settings2,
  SlidersHorizontal,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

const NAV = [
  { href: "/excecoes", label: "Exceções", hint: "Fase 1", icon: FileWarning },
  { href: "/pagamentos", label: "Pagamentos", hint: "Fase 1", icon: CircleDollarSign },
  { href: "/titulos", label: "Títulos", hint: "Fase 2", icon: Receipt },
  { href: "/conversas", label: "Conversas", hint: "Fase 3", icon: MessageSquare },
  { href: "/aprovacoes", label: "Aprovações", hint: "Fase 3", icon: CheckSquare },
  { href: "/configuracoes", label: "Configurações", hint: "Fase 4", icon: SlidersHorizontal },
  { href: "/metricas", label: "Métricas", hint: "Fase 4", icon: Gauge },
];

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, retry: false });

  useEffect(() => {
    if (me.isError) router.replace("/login");
  }, [me.isError, router]);

  async function logout() {
    clearToken();
    if (supabaseEnabled()) await supabase().auth.signOut();
    router.replace("/login");
  }

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-72 shrink-0 flex-col bg-ink-950 text-paper-50">
        <div className="border-b border-white/10 px-6 py-6">
          <p className="text-[11px] uppercase tracking-[0.22em] text-gold-500">Agente</p>
          <h1 className="font-display text-2xl leading-tight">Cobrança + Conciliação</h1>
          <p className="mt-2 text-sm text-paper-200/80">{me.data?.tenant_name ?? "Carregando…"}</p>
        </div>
        <nav className="flex-1 space-y-1 px-3 py-4">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={clsx(
                  "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition",
                  active ? "bg-white/10 text-white" : "text-paper-200/80 hover:bg-white/5 hover:text-white",
                )}
              >
                <Icon size={18} />
                <span className="flex-1 font-medium">{item.label}</span>
                <span className="text-[10px] uppercase tracking-wide text-gold-500/80">{item.hint}</span>
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-white/10 px-5 py-4 text-sm">
          <p className="truncate text-paper-50">{me.data?.email}</p>
          <p className="text-xs capitalize text-paper-200/70">{me.data?.role}</p>
          <button
            onClick={logout}
            className="mt-3 inline-flex items-center gap-2 text-paper-200/80 hover:text-white"
          >
            <LogOut size={16} /> Sair
          </button>
        </div>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="flex items-center justify-between border-b border-paper-200 bg-white/70 px-8 py-4 backdrop-blur">
          <Settings2 className="text-moss-600" size={18} />
          <p className="text-sm text-ink-700/70">
            O painel só fala com a API. Nenhuma baixa ou acordo é gravado daqui direto no banco.
          </p>
        </header>
        <main className="px-8 py-8">{children}</main>
      </div>
    </div>
  );
}
