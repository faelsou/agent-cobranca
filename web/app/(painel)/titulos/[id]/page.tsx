"use client";

import { Badge, labelOf } from "@/components/status";
import { Banner, Card, Empty } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { day, documentBr, money, phoneBr, when } from "@/lib/format";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";

export default function TituloDetalhePage() {
  const { id } = useParams<{ id: string }>();
  const invoice = useQuery({ queryKey: ["invoice", id], queryFn: () => api.invoice(id) });
  const data = invoice.data;

  if (invoice.isError) return <Banner>{errorText(invoice.error)}</Banner>;
  if (!data) return <Empty title="Carregando título…" />;

  return (
    <div className="space-y-6">
      <Link href="/titulos" className="text-sm text-moss-600 hover:underline">
        ← Títulos
      </Link>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-gold-500">{data.external_id}</p>
          <h1 className="font-display text-3xl">{data.debtor.name}</h1>
          <p className="mt-1 text-sm text-ink-700/70">
            {documentBr(data.debtor.document)} · {phoneBr(data.debtor.phone)}
            {data.debtor.opt_out ? " · opt-out" : ""}
          </p>
        </div>
        <div className="text-right">
          <p className="font-display text-3xl">{money(data.amount)}</p>
          <Badge value={data.status} />
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-6">
          <h2 className="font-display text-xl">Régua</h2>
          {!data.dunning_events.length ? (
            <p className="mt-3 text-sm text-ink-700/70">Nenhum disparo ainda.</p>
          ) : (
            <ol className="mt-4 space-y-3 text-sm">
              {data.dunning_events.map((ev) => (
                <li key={`${ev.step}-${ev.channel}`} className="flex justify-between border-b border-paper-100 pb-2">
                  <span>
                    {ev.step} · {ev.channel}
                  </span>
                  <span>
                    {when(ev.sent_at)} · {ev.delivery_status}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </Card>
        <Card className="p-6">
          <h2 className="font-display text-xl">Promessas e matches</h2>
          <ul className="mt-4 space-y-2 text-sm">
            {data.promises.map((p) => (
              <li key={p.promised_date}>
                Promessa para {day(p.promised_date)} · {p.fulfilled === null ? "em aberto" : p.fulfilled ? "cumprida" : "quebrada"}
              </li>
            ))}
            {data.matches.map((m) => (
              <li key={`${m.payment_id}-${m.invoice_id}`}>
                {money(m.amount_applied)} via {labelOf(m.method)}
                {m.provisional ? " (provisório)" : ""} · {m.confirmed_by}
              </li>
            ))}
            {!data.promises.length && !data.matches.length ? (
              <li className="text-ink-700/70">Sem promessa e sem baixa ainda.</li>
            ) : null}
          </ul>
        </Card>
      </div>

      {data.installments.length > 0 ? (
        <Card className="p-6">
          <h2 className="font-display text-xl">Parcelas do acordo</h2>
          <ul className="mt-4 space-y-2 text-sm">
            {data.installments.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-3 border-b border-paper-100 pb-2">
                <Link href={`/titulos/${item.id}`} className="font-semibold hover:underline">
                  {item.description ?? item.external_id}
                </Link>
                <span>{money(item.amount)}</span>
                <span>{day(item.due_date)}</span>
                <Badge value={item.status} />
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <Card className="p-6">
        <h2 className="font-display text-xl">Conversa do devedor</h2>
        {!data.messages.length ? (
          <p className="mt-3 text-sm text-ink-700/70">Nenhuma mensagem nesta conversa.</p>
        ) : (
          <ul className="mt-4 space-y-3 text-sm">
            {data.messages.map((m) => (
              <li key={m.id} className="rounded-xl bg-paper-50 px-3 py-2">
                <p className="text-xs text-ink-700/60">
                  {m.direction === "in" ? "Devedor" : m.author} · {when(m.created_at)}
                </p>
                <p>{m.body}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
