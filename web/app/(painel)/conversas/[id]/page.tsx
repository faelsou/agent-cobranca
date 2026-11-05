import { redirect } from "next/navigation";

export default async function ConversaRedirect({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/conversas?id=${encodeURIComponent(id)}`);
}
