"use client";

import { Badge } from "@/components/status";
import { Banner, Card, Empty, Input } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { day, documentBr, money } from "@/lib/format";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

export default function TitulosPage() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ["invoices", status, q],
    queryFn: () => api.invoices({ status: status || undefined, q: q || undefined }),
    refetchInterval: 5000,
    refetchOnWindowFocus: true,
  });

  async function onImport(file: File | undefined) {
    if (!file) return;
    setError(null);
    try {
      const result = await api.importInvoices(file);
      setNotice(`Importação: ${result.created} criados, ${result.updated} atualizados.`);
      list.refetch();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-gold-500">Fase 2</p>
          <h1 className="font-display text-3xl">Títulos</h1>
          <p className="mt-1 text-sm text-ink-700/70">
            Centro do modelo: régua, conversas e pagamentos apontam para o título.
          </p>
        </div>
        <label className="text-sm">
          Importar CSV
          <input className="ml-2" type="file" accept=".csv" onChange={(e) => onImport(e.target.files?.[0])} />
        </label>
      </header>

      <div className="flex flex-wrap gap-3">
        <Input
          placeholder="Buscar por nome, documento ou referência"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="max-w-md"
        />
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-full border border-paper-200 bg-white px-3 py-2 text-sm">
          <option value="">Todos</option>
          <option value="aberto">Aberto</option>
          <option value="em_cobranca">Em cobrança</option>
          <option value="promessa">Promessa</option>
          <option value="em_negociacao">Em negociação</option>
          <option value="parcialmente_pago">Parcial</option>
          <option value="pago">Pago</option>
          <option value="fila_humana">Fila humana</option>
          <option value="contestado">Contestado</option>
        </select>
      </div>

      {notice ? <Banner tone="ok">{notice}</Banner> : null}
      {error ? <Banner>{error}</Banner> : null}

      <Card>
        {list.isError ? (
          <Banner>{errorText(list.error)}</Banner>
        ) : list.isPending ? (
          <Empty title="Carregando títulos…" />
        ) : !list.data.items.length ? (
          <Empty title="Nenhum título" hint="Importe a planilha do emissor ou cadastre via webhook." />
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-ink-700/60">
              <tr>
                <th className="px-5 py-3">Devedor</th>
                <th>Referência</th>
                <th>Valor</th>
                <th>Vencimento</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {list.data.items.map((inv) => (
                <tr key={inv.id} className="border-t border-paper-100 hover:bg-paper-50">
                  <td className="px-5 py-3">
                    <Link href={`/titulos/${inv.id}`} className="font-semibold hover:underline">
                      {inv.debtor.name}
                    </Link>
                    <div className="text-xs text-ink-700/60">{documentBr(inv.debtor.document)}</div>
                  </td>
                  <td>{inv.external_id}</td>
                  <td>{money(inv.amount)}</td>
                  <td>{day(inv.due_date)}</td>
                  <td>
                    <Badge value={inv.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
