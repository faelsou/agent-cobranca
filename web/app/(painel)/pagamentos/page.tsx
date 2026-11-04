"use client";

import { Badge } from "@/components/status";
import { Banner, Button, Card, Empty, Field } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { documentBr, money, when } from "@/lib/format";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

export default function PagamentosPage() {
  const [status, setStatus] = useState("");
  const [origin, setOrigin] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ["payments", status, origin],
    queryFn: () => api.payments({ status: status || undefined, origin: origin || undefined }),
    refetchInterval: 5000,
    refetchOnWindowFocus: true,
  });
  const invoices = useQuery({
    queryKey: ["invoices", "labels"],
    queryFn: () => api.invoices({}),
    staleTime: 15_000,
  });

  async function onImport(file: File | undefined) {
    if (!file) return;
    setError(null);
    try {
      const result = await api.importStatement(file);
      setNotice(`Extrato importado: ${result.created} novos, ${result.duplicates} já existentes.`);
      list.refetch();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function openReceipt(id: string) {
    try {
      setReceipt(await api.receiptUrl(id));
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-gold-500">Fase 1</p>
          <h1 className="font-display text-3xl">Pagamentos</h1>
          <p className="mt-1 text-sm text-ink-700/70">
            Comprovante sozinho nunca baixa. Só vira definitivo com extrato ou webhook.
          </p>
        </div>
        <Field label="Importar OFX/CSV">
          <input type="file" accept=".ofx,.csv,.txt" onChange={(e) => onImport(e.target.files?.[0])} />
        </Field>
      </header>

      <div className="flex gap-3">
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-full border border-paper-200 bg-white px-3 py-2 text-sm">
          <option value="">Todos os status</option>
          <option value="aguardando_banco">Aguardando banco</option>
          <option value="confirmado">Confirmado</option>
          <option value="conciliado">Conciliado</option>
          <option value="em_excecao">Em exceção</option>
        </select>
        <select value={origin} onChange={(e) => setOrigin(e.target.value)} className="rounded-full border border-paper-200 bg-white px-3 py-2 text-sm">
          <option value="">Todas as origens</option>
          <option value="comprovante">Comprovante</option>
          <option value="extrato">Extrato</option>
          <option value="webhook">Webhook</option>
        </select>
      </div>

      {notice ? <Banner tone="ok">{notice}</Banner> : null}
      {error ? <Banner>{error}</Banner> : null}

      <Card>
        {list.isError ? (
          <Banner>{errorText(list.error)}</Banner>
        ) : list.isPending ? (
          <Empty title="Carregando pagamentos…" />
        ) : !list.data.items.length ? (
          <Empty title="Nenhum pagamento" hint="Importe um extrato ou aguarde o webhook do banco." />
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-ink-700/60">
              <tr>
                <th className="px-5 py-3">Valor</th>
                <th>Pagador</th>
                <th>Origem</th>
                <th>Status</th>
                <th>Banco</th>
                <th>Quando</th>
                <th>Títulos</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {list.data.items.map((p) => (
                <tr key={p.id} className="border-t border-paper-100">
                  <td className="px-5 py-3 font-semibold">{money(p.amount)}</td>
                  <td>
                    <div>{p.payer_name ?? "—"}</div>
                    <div className="text-xs text-ink-700/60">{documentBr(p.payer_doc)}</div>
                  </td>
                  <td>
                    <Badge value={p.origin} />
                  </td>
                  <td>
                    <Badge value={p.status} />
                  </td>
                  <td>{p.bank_confirmed ? "Confirmado" : "Só comprovante"}</td>
                  <td>{when(p.paid_at)}</td>
                  <td>
                    {p.matches.length
                      ? p.matches
                          .map((m) => invoices.data?.items.find((inv) => inv.id === m.invoice_id)?.external_id ?? "título")
                          .join(", ")
                      : "—"}
                  </td>
                  <td>
                    {p.has_receipt ? (
                      <Button variant="ghost" onClick={() => openReceipt(p.id)}>
                        ver comprovante
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {receipt ? (
        <div className="fixed inset-0 z-20 grid place-items-center bg-ink-950/60 p-6" onClick={() => setReceipt(null)}>
          <img src={receipt} alt="Comprovante" className="max-h-full max-w-3xl rounded-2xl bg-white p-2" />
        </div>
      ) : null}
    </div>
  );
}
