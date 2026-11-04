"use client";

import { Badge } from "@/components/status";
import { Banner, Button, Card, Empty, Textarea } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { when } from "@/lib/format";
import type { Approval, Invoice } from "@/lib/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

export default function AprovacoesPage() {
  const client = useQueryClient();
  const list = useQuery({
    queryKey: ["approvals"],
    queryFn: () => api.approvals(),
    refetchInterval: 5000,
    refetchOnWindowFocus: true,
  });
  const invoices = useQuery({
    queryKey: ["invoices", "labels"],
    queryFn: () => api.invoices({}),
    staleTime: 15_000,
  });
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const decide = useMutation({
    mutationFn: ({ id, approved, message }: { id: string; approved: boolean; message: string }) =>
      api.decideApproval(id, approved, message),
    onSuccess: () => client.invalidateQueries({ queryKey: ["approvals"] }),
    onError: (err) => setError(errorText(err)),
  });

  const approvals = list.data ?? [];

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs uppercase tracking-[0.18em] text-gold-500">Fase 3</p>
        <h1 className="font-display text-3xl">Aprovações</h1>
        <p className="mt-1 text-sm text-ink-700/70">
          Pedidos que o agente pausou com interrupt — fora da política, sem inventar condição.
        </p>
      </header>
      {error ? <Banner>{error}</Banner> : null}
      {list.isError ? <Banner>{errorText(list.error)}</Banner> : null}
      {list.isPending ? (
        <Card>
          <Empty title="Carregando aprovações…" />
        </Card>
      ) : approvals.length === 0 ? (
        <Card>
          <Empty title="Nada aguardando humano" hint="Quando o pedido não cabe na política, ele para aqui." />
        </Card>
      ) : (
        <div className="grid gap-4">
          {approvals.map((item) => (
            <ApprovalCard
              key={item.id}
              item={item}
              invoices={invoices.data?.items ?? []}
              message={drafts[item.id] ?? ""}
              onMessage={(value) => setDrafts((prev) => ({ ...prev, [item.id]: value }))}
              onDecide={(approved) =>
                decide.mutate({
                  id: item.id,
                  approved,
                  message: drafts[item.id] || (approved ? "Aprovado pela equipe." : "Não foi possível aprovar."),
                })
              }
              busy={decide.isPending}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ApprovalCard({
  item,
  invoices,
  message,
  onMessage,
  onDecide,
  busy,
}: {
  item: Approval;
  invoices: Invoice[];
  message: string;
  onMessage: (value: string) => void;
  onDecide: (approved: boolean) => void;
  busy: boolean;
}) {
  return (
    <Card className="p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-semibold">{item.debtor.name}</p>
          <p className="mt-1 text-sm text-ink-700/70">{item.reason}</p>
          <Link href={`/conversas/${item.conversation_id}`} className="mt-2 inline-block text-sm text-moss-700 underline">
            Abrir conversa
          </Link>
        </div>
        <Badge value={item.status} />
      </div>
      <dl className="mt-4 space-y-1 rounded-xl bg-paper-50 p-3 text-sm">
        {Object.entries(item.payload).map(([key, value]) => (
          <div key={key} className="flex gap-2">
            <dt className="text-ink-700/60">{key === "invoice_id" ? "título" : key}</dt>
            <dd>{payloadText(key, value, invoices)}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-xs text-ink-700/60">{when(item.created_at)}</p>
      <Textarea
        className="mt-4"
        rows={3}
        value={message}
        onChange={(e) => onMessage(e.target.value)}
        placeholder="Mensagem que o agente envia ao retomar o grafo"
      />
      <div className="mt-3 flex gap-2">
        <Button onClick={() => onDecide(true)} disabled={busy}>
          Aprovar
        </Button>
        <Button variant="outline" onClick={() => onDecide(false)} disabled={busy}>
          Recusar
        </Button>
      </div>
    </Card>
  );
}

function payloadText(key: string, value: unknown, invoices: Invoice[]): string {
  if (key === "invoice_id" && typeof value === "string") {
    const invoice = invoices.find((item) => item.id === value);
    if (invoice) return `${invoice.debtor.name} · ${invoice.description ?? invoice.external_id}`;
  }
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value);
}
