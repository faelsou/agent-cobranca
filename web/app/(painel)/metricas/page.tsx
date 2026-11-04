"use client";

import { Card } from "@/components/ui";
import { api } from "@/lib/api";
import { money, pct } from "@/lib/format";
import { useQuery } from "@tanstack/react-query";

export default function MetricasPage() {
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: () => api.metrics() });
  const data = metrics.data;

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs uppercase tracking-[0.18em] text-gold-500">Fase 4</p>
        <h1 className="font-display text-3xl">Métricas</h1>
        <p className="mt-1 text-sm text-ink-700/70">
          Recuperação, DSO, promessas cumpridas e o percentual de baixa automática.
        </p>
      </header>

      {!data ? (
        <p className="text-sm text-ink-700/70">Calculando o período…</p>
      ) : (
        <>
          <p className="text-sm text-ink-700/70">
            Período {data.period_start} → {data.period_end}
          </p>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <Stat title="Taxa de recuperação" value={pct(data.recovery_rate)} hint={`${money(data.recovered_amount)} de ${money(data.overdue_amount)} vencidos`} />
            <Stat title="Dias médios de atraso" value={data.avg_days_late?.toFixed(1) ?? "—"} hint="DSO após o vencimento" />
            <Stat
              title="Promessas cumpridas"
              value={pct(data.promise_kept_rate)}
              hint={`${data.promises_kept} de ${data.promises_made}`}
            />
            <Stat
              title="Baixa automática"
              value={pct(data.auto_reconciliation_rate)}
              hint={`${data.auto_reconciled} de ${data.payments_reconciled} pagamentos`}
            />
            <Stat title="Exceções abertas" value={String(data.exceptions_open)} hint="Fila curta = matching bom" />
            <Stat
              title="Tempo médio de resolução"
              value={data.avg_exception_resolution_hours != null ? `${data.avg_exception_resolution_hours} h` : "—"}
              hint="Exceções fechadas no período"
            />
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ title, value, hint }: { title: string; value: string; hint: string }) {
  return (
    <Card className="p-5">
      <p className="text-xs uppercase tracking-wide text-ink-700/60">{title}</p>
      <p className="mt-2 font-display text-3xl">{value}</p>
      <p className="mt-2 text-sm text-ink-700/70">{hint}</p>
    </Card>
  );
}
