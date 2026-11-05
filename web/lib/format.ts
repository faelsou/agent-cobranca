const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const DATE = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short" });
const DATETIME = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

export function money(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return BRL.format(Number(value));
}

export function day(value: string | null | undefined): string {
  if (!value) return "—";
  return DATE.format(new Date(value.includes("T") ? value : `${value}T12:00:00`));
}

export function when(value: string | null | undefined): string {
  if (!value) return "—";
  return DATETIME.format(new Date(value));
}

export function pct(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export function documentBr(value: string | null | undefined): string {
  if (!value) return "—";
  const d = value.replace(/\D/g, "");
  if (d.length === 11) return d.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
  if (d.length === 14) return d.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, "$1.$2.$3/$4-$5");
  return value;
}

export function phoneBr(value: string | null | undefined): string {
  if (!value) return "—";
  let d = value.replace(/\D/g, "");
  if (d.startsWith("55") && (d.length === 12 || d.length === 13)) d = d.slice(2);
  if (d.length === 11) return d.replace(/(\d{2})(\d{5})(\d{4})/, "($1) $2-$3");
  if (d.length === 10) return d.replace(/(\d{2})(\d{4})(\d{4})/, "($1) $2-$3");
  return value;
}

export function phonesBr(phones: string[] | null | undefined, fallback?: string | null): string {
  const list = (phones ?? []).filter((phone) => phone.trim());
  if (!list.length) return phoneBr(fallback);
  return list.map((phone) => phoneBr(phone)).join(" · ");
}

export function clsx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
