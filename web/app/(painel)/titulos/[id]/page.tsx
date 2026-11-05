"use client";

import { Badge, labelOf } from "@/components/status";
import { Banner, Button, Card, Empty, Field, Input } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { day, documentBr, money, phonesBr, when } from "@/lib/format";
import type { Debtor } from "@/lib/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

const MAX_WHATSAPP = 5;

function nationalPhone(value: string): string {
  const digits = value.replace(/\D/g, "");
  if (digits.startsWith("55") && (digits.length === 12 || digits.length === 13)) return digits.slice(2);
  return digits || value;
}

function fieldsFrom(debtor: Debtor): string[] {
  const stored = (debtor.phones?.length ? debtor.phones : debtor.phone ? [debtor.phone] : []).map(nationalPhone);
  return stored.length ? stored : [""];
}

function WhatsAppNumbers({ debtor }: { debtor: Debtor }) {
  const client = useQueryClient();
  const savedKey = [debtor.id, ...(debtor.phones ?? []), debtor.phone ?? ""].join("|");
  const [numbers, setNumbers] = useState<string[]>(() => fieldsFrom(debtor));
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    setNumbers(fieldsFrom(debtor));
  }, [savedKey, debtor]);

  const save = useMutation({
    mutationFn: () =>
      api.saveWhatsappNumbers(
        debtor.id,
        numbers.map((item) => item.trim()).filter(Boolean),
      ),
    onSuccess: (saved) => {
      const next = (saved.phones?.length ? saved.phones : saved.phone ? [saved.phone] : []).map(nationalPhone);
      setNumbers(next.length ? next : [""]);
      setNotice("Números gravados. A régua dispara para cada um deles.");
      client.invalidateQueries({ queryKey: ["invoice"] });
    },
  });

  return (
    <Card className="space-y-4 p-6">
      <div>
        <h2 className="font-display text-xl">WhatsApp</h2>
        <p className="mt-1 text-sm text-ink-700/70">
          Até {MAX_WHATSAPP} celulares de quem paga. A mesma cobrança sai para todos. Vale para os títulos deste devedor.
        </p>
      </div>
      {notice ? <Banner tone="ok">{notice}</Banner> : null}
      {save.isError ? <Banner>{errorText(save.error)}</Banner> : null}
      <div className="grid gap-3 md:grid-cols-2">
        {numbers.map((value, index) => (
          <Field key={index} label={`WhatsApp ${index + 1}`}>
            <div className="flex gap-2">
              <Input
                inputMode="tel"
                placeholder="11988887777"
                value={value}
                onChange={(event) => {
                  const next = [...numbers];
                  next[index] = event.target.value;
                  setNumbers(next);
                  setNotice(null);
                }}
              />
              {numbers.length > 1 ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setNumbers(numbers.filter((_, item) => item !== index))}
                >
                  Tirar
                </Button>
              ) : null}
            </div>
          </Field>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        {numbers.length < MAX_WHATSAPP ? (
          <Button type="button" variant="outline" onClick={() => setNumbers([...numbers, ""])}>
            Adicionar número
          </Button>
        ) : null}
        <Button type="button" onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending ? "Salvando…" : "Salvar WhatsApp"}
        </Button>
      </div>
    </Card>
  );
}

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
            {documentBr(data.debtor.document)} · {phonesBr(data.debtor.phones, data.debtor.phone)}
            {data.debtor.opt_out ? " · opt-out" : ""}
          </p>
        </div>
        <div className="text-right">
          <p className="font-display text-3xl">{money(data.amount)}</p>
          <Badge value={data.status} />
        </div>
      </header>

      <WhatsAppNumbers debtor={data.debtor} />

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
