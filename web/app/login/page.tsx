"use client";

import { Banner, Button, Field, Input } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { setToken, supabase, supabaseEnabled } from "@/lib/auth";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("operador@demo.local");
  const [password, setPassword] = useState("");
  const [slug, setSlug] = useState("demo");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const hasSupabase = supabaseEnabled();

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (hasSupabase) {
        const { data, error: authError } = await supabase().auth.signInWithPassword({ email, password });
        if (authError || !data.session) throw new Error(authError?.message ?? "Falha no login");
        setToken(data.session.access_token);
      } else {
        const result = await api.devLogin(email, slug);
        setToken(result.access_token);
      }
      router.replace("/excecoes");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-[radial-gradient(circle_at_top,_#d8f3dc,_#fbf8f1_55%)] px-4">
      <div className="w-full max-w-md rounded-3xl border border-paper-200 bg-white p-8 shadow-card">
        <p className="text-[11px] uppercase tracking-[0.22em] text-gold-500">Painel do operador</p>
        <h1 className="mt-2 font-display text-3xl text-ink-900">Entrar na conciliação</h1>
        <p className="mt-2 text-sm text-ink-700/70">
          {hasSupabase
            ? "Use a conta do tenant no Supabase Auth. O JWT carrega o tenant_id."
            : "Ambiente local: o token é emitido pela API após o seed-demo."}
        </p>
        <form onSubmit={onSubmit} className="mt-8 space-y-4">
          <Field label="E-mail">
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </Field>
          {hasSupabase ? (
            <Field label="Senha">
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </Field>
          ) : (
            <Field label="Tenant">
              <Input value={slug} onChange={(e) => setSlug(e.target.value)} required />
            </Field>
          )}
          {error ? <Banner>{error}</Banner> : null}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Entrando…" : "Entrar"}
          </Button>
        </form>
      </div>
    </main>
  );
}
