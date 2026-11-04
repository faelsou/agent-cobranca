"use client";

import { Banner, Button, Card, Field, Input, Textarea } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import type { TenantSettings } from "@/lib/types";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

const WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];

export default function ConfiguracoesPage() {
  const query = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [form, setForm] = useState<TenantSettings | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (query.data) setForm(query.data);
  }, [query.data]);

  const save = useMutation({
    mutationFn: () => api.saveSettings(form!),
    onSuccess: (data) => {
      setForm(data);
      setNotice("Configurações gravadas. A régua e o agente passam a usar estes limites.");
    },
  });

  if (!form) return <p className="text-sm text-ink-700/70">Carregando configurações…</p>;

  const policy = form.negotiation_policy;
  const hours = form.allowed_hours;
  const recon = form.reconciliation_rules;

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs uppercase tracking-[0.18em] text-gold-500">Fase 4</p>
        <h1 className="font-display text-3xl">Configurações</h1>
        <p className="mt-1 text-sm text-ink-700/70">
          Política, régua e horário. O agente só oferece o que cabe aqui — nunca inventa valor.
        </p>
      </header>

      {notice ? <Banner tone="ok">{notice}</Banner> : null}
      {save.isError ? <Banner>{errorText(save.error)}</Banner> : null}

      <Card className="grid gap-4 p-6 md:grid-cols-2">
        <h2 className="font-display text-xl md:col-span-2">Política de negociação</h2>
        <Field label="Desconto máx. à vista (%)">
          <Input
            value={policy.max_discount_pct_cash}
            onChange={(e) =>
              setForm({ ...form, negotiation_policy: { ...policy, max_discount_pct_cash: e.target.value } })
            }
          />
        </Field>
        <Field label="Entrada mínima (%)">
          <Input
            value={policy.min_down_payment_pct}
            onChange={(e) =>
              setForm({ ...form, negotiation_policy: { ...policy, min_down_payment_pct: e.target.value } })
            }
          />
        </Field>
        <Field label="Máx. de parcelas">
          <Input
            type="number"
            value={policy.max_installments}
            onChange={(e) =>
              setForm({ ...form, negotiation_policy: { ...policy, max_installments: Number(e.target.value) } })
            }
          />
        </Field>
        <Field label="Parcela mínima (R$)">
          <Input
            value={policy.min_installment_amount}
            onChange={(e) =>
              setForm({ ...form, negotiation_policy: { ...policy, min_installment_amount: e.target.value } })
            }
          />
        </Field>
        <Field label="Juros ao mês (%)">
          <Input
            value={policy.monthly_interest_pct}
            onChange={(e) =>
              setForm({ ...form, negotiation_policy: { ...policy, monthly_interest_pct: e.target.value } })
            }
          />
        </Field>
        <Field label="Promessa máxima (dias)">
          <Input
            type="number"
            value={policy.max_promise_days}
            onChange={(e) =>
              setForm({ ...form, negotiation_policy: { ...policy, max_promise_days: Number(e.target.value) } })
            }
          />
        </Field>
      </Card>

      <Card className="grid gap-4 p-6 md:grid-cols-2">
        <h2 className="font-display text-xl md:col-span-2">Horário permitido (CDC)</h2>
        <Field label="Início">
          <Input
            type="time"
            value={hours.start.slice(0, 5)}
            onChange={(e) => setForm({ ...form, allowed_hours: { ...hours, start: e.target.value } })}
          />
        </Field>
        <Field label="Fim">
          <Input
            type="time"
            value={hours.end.slice(0, 5)}
            onChange={(e) => setForm({ ...form, allowed_hours: { ...hours, end: e.target.value } })}
          />
        </Field>
        <div className="md:col-span-2 flex flex-wrap gap-2">
          {WEEKDAYS.map((label, idx) => {
            const on = hours.weekdays.includes(idx);
            return (
              <button
                key={label}
                type="button"
                onClick={() => {
                  const next = on ? hours.weekdays.filter((d) => d !== idx) : [...hours.weekdays, idx].sort();
                  setForm({ ...form, allowed_hours: { ...hours, weekdays: next } });
                }}
                className={`rounded-full px-3 py-1 text-sm ${on ? "bg-moss-600 text-white" : "bg-paper-100 text-ink-800"}`}
              >
                {label}
              </button>
            );
          })}
        </div>
        <Field label="Fuso">
          <Input value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} />
        </Field>
      </Card>

      <Card className="grid gap-4 p-6 md:grid-cols-2">
        <h2 className="font-display text-xl md:col-span-2">Conciliação</h2>
        <Field label="Dias antes do vencimento">
          <Input
            type="number"
            value={recon.days_before_due}
            onChange={(e) =>
              setForm({ ...form, reconciliation_rules: { ...recon, days_before_due: Number(e.target.value) } })
            }
          />
        </Field>
        <Field label="Dias depois do vencimento">
          <Input
            type="number"
            value={recon.days_after_due}
            onChange={(e) =>
              setForm({ ...form, reconciliation_rules: { ...recon, days_after_due: Number(e.target.value) } })
            }
          />
        </Field>
        <Field label="Sobrepagamento máx. (%)">
          <Input
            value={recon.max_overpay_pct}
            onChange={(e) => setForm({ ...form, reconciliation_rules: { ...recon, max_overpay_pct: e.target.value } })}
          />
        </Field>
        <label className="flex items-center gap-2 text-sm md:col-span-2">
          <input
            type="checkbox"
            checked={recon.allow_partial}
            onChange={(e) => setForm({ ...form, reconciliation_rules: { ...recon, allow_partial: e.target.checked } })}
          />
          Permitir baixa parcial
        </label>
      </Card>

      <Card className="space-y-4 p-6">
        <h2 className="font-display text-xl">Templates da régua</h2>
        {Object.entries(form.dunning_rules.templates).map(([key, value]) => (
          <Field key={key} label={key}>
            <Textarea
              rows={3}
              value={value}
              onChange={(e) =>
                setForm({
                  ...form,
                  dunning_rules: {
                    ...form.dunning_rules,
                    templates: { ...form.dunning_rules.templates, [key]: e.target.value },
                  },
                })
              }
            />
          </Field>
        ))}
      </Card>

      <Button onClick={() => save.mutate()} disabled={save.isPending}>
        {save.isPending ? "Salvando…" : "Salvar configurações"}
      </Button>
    </div>
  );
}
