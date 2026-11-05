import { Suspense } from "react";
import { ConversasInbox } from "./inbox-page";

export default function ConversasPage() {
  return (
    <Suspense fallback={<p className="text-sm text-ink-700/70">Carregando conversas…</p>}>
      <ConversasInbox />
    </Suspense>
  );
}
