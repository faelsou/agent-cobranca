"use client";

import { Badge } from "@/components/status";
import { Banner, Button, Card, Empty, Textarea } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { clsx, when } from "@/lib/format";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

export default function ConversaDetalhePage() {
  const { id } = useParams<{ id: string }>();
  const client = useQueryClient();
  const [text, setText] = useState("");
  const conversations = useQuery({
    queryKey: ["conversations"],
    queryFn: () => api.conversations(),
    refetchInterval: 3000,
    refetchOnWindowFocus: true,
  });
  const conversation = conversations.data?.items.find((c) => c.id === id);
  const messages = useQuery({
    queryKey: ["messages", id],
    queryFn: () => api.messages(id),
    refetchInterval: 3000,
    refetchOnWindowFocus: true,
  });

  const takeover = useMutation({
    mutationFn: () => api.takeover(id),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["conversations"] });
      client.invalidateQueries({ queryKey: ["messages", id] });
    },
  });
  const release = useMutation({
    mutationFn: () => api.release(id),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["conversations"] });
      client.invalidateQueries({ queryKey: ["messages", id] });
    },
  });
  const send = useMutation({
    mutationFn: () => api.sendMessage(id, text),
    onSuccess: () => {
      setText("");
      client.invalidateQueries({ queryKey: ["messages", id] });
    },
  });

  if (!conversation) return <Empty title="Conversa não encontrada" />;

  return (
    <div className="space-y-6">
      <Link href="/conversas" className="text-sm text-moss-600 hover:underline">
        ← Conversas
      </Link>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-gold-500">{conversation.intent ?? "sem intenção"}</p>
          <h1 className="font-display text-3xl">{conversation.debtor.name}</h1>
          <p className="mt-1 text-sm text-ink-700/70">{conversation.summary}</p>
        </div>
        <div className="flex items-center gap-3">
          <Badge value={conversation.state} />
          {conversation.state !== "humano" ? (
            <Button onClick={() => takeover.mutate()} disabled={takeover.isPending}>
              Assumir
            </Button>
          ) : (
            <Button variant="outline" onClick={() => release.mutate()} disabled={release.isPending}>
              Devolver ao agente
            </Button>
          )}
        </div>
      </header>

      {takeover.isError || release.isError || send.isError ? (
        <Banner>{errorText(takeover.error ?? release.error ?? send.error)}</Banner>
      ) : null}

      <Card className="p-6">
        <div className="space-y-3">
          {messages.data?.map((m) => (
            <div
              key={m.id}
              className={clsx(
                "max-w-xl rounded-2xl px-4 py-3 text-sm",
                m.direction === "in" ? "bg-paper-100" : "ml-auto bg-moss-600 text-white",
              )}
            >
              <p className="text-xs opacity-70">
                {m.author} · {when(m.created_at)}
              </p>
              <p className="mt-1 whitespace-pre-wrap">{m.body}</p>
            </div>
          ))}
        </div>
        <div className="mt-6 flex gap-3">
          <Textarea
            rows={2}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={conversation.state === "humano" ? "Escreva para o devedor" : "Assuma a conversa para responder"}
            disabled={conversation.state !== "humano"}
          />
          <Button onClick={() => send.mutate()} disabled={conversation.state !== "humano" || !text || send.isPending}>
            Enviar
          </Button>
        </div>
      </Card>
    </div>
  );
}
