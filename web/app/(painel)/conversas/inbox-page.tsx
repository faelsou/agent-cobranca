"use client";

import { Inbox } from "@/components/inbox";
import { useSearchParams } from "next/navigation";

export function ConversasInbox() {
  const params = useSearchParams();
  const id = params.get("id") ?? undefined;
  return <Inbox activeId={id} />;
}
