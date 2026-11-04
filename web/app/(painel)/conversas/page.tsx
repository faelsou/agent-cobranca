"use client";

import { Badge } from "@/components/status";
import { Card, Empty } from "@/components/ui";
import { api } from "@/lib/api";
import { phoneBr, when } from "@/lib/format";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

export default function ConversasPage() {
  const [state, setState] = useState("");
  const list = useQuery({
    queryKey: ["conversations", state],
    queryFn: () => api.conversations(state || undefined),
    refetchInterval: 3000,
    refetchOnWindowFocus: true,
  });

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-gold-500">Fase 3</p>
          <h1 className="font-display text-3xl">Conversas</h1>
          <p className="mt-1 text-sm text-ink-700/70">
            Histórico do WhatsApp. Assuma a conversa para falar no lugar do agente e devolva quando terminar.
          </p>
        </div>
        <select value={state} onChange={(e) => setState(e.target.value)} className="rounded-full border border-paper-200 bg-white px-3 py-2 text-sm">
          <option value="">Todas</option>
          <option value="agente">Com o agente</option>
          <option value="humano">Com humano</option>
          <option value="aguardando_aprovacao">Aguardando aprovação</option>
        </select>
      </header>

      <Card>
        {!list.data?.items.length ? (
          <Empty title="Nenhuma conversa" hint="O agente só aparece aqui depois que o devedor responde." />
        ) : (
          <ul className="divide-y divide-paper-100">
            {list.data.items.map((c) => (
              <li key={c.id}>
                <Link href={`/conversas/${c.id}`} className="flex items-center justify-between px-5 py-4 hover:bg-paper-50">
                  <div>
                    <p className="font-semibold">{c.debtor.name}</p>
                    <p className="text-sm text-ink-700/70">
                      {phoneBr(c.debtor.phone)} · {c.summary ?? "sem resumo"}
                    </p>
                  </div>
                  <div className="text-right">
                    <Badge value={c.state} />
                    <p className="mt-1 text-xs text-ink-700/60">{when(c.updated_at)}</p>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
