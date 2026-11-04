import { clsx } from "@/lib/format";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={clsx("rounded-2xl border border-paper-200 bg-white shadow-card", className)}>{children}</section>;
}

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" | "outline" }) {
  const styles = {
    primary: "bg-moss-600 text-white hover:bg-moss-500 disabled:bg-ink-700/30",
    ghost: "bg-transparent text-ink-800 hover:bg-paper-100",
    danger: "bg-red-700 text-white hover:bg-red-600",
    outline: "border border-paper-200 bg-white text-ink-800 hover:border-moss-500",
  }[variant];
  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed",
        styles,
        className,
      )}
      {...props}
    />
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={clsx(
        "w-full rounded-xl border border-paper-200 bg-paper-50 px-3 py-2 text-sm text-ink-900 outline-none ring-moss-500/30 focus:border-moss-500 focus:ring-2",
        props.className,
      )}
    />
  );
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={clsx(
        "w-full rounded-xl border border-paper-200 bg-paper-50 px-3 py-2 text-sm text-ink-900 outline-none ring-moss-500/30 focus:border-moss-500 focus:ring-2",
        props.className,
      )}
    />
  );
}

export function Label({ children }: { children: ReactNode }) {
  return <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-ink-700/70">{children}</label>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <Label>{label}</Label>
      {children}
    </div>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="px-6 py-16 text-center">
      <p className="font-display text-xl text-ink-900">{title}</p>
      {hint ? <p className="mt-2 text-sm text-ink-700/70">{hint}</p> : null}
    </div>
  );
}

export function Banner({ children, tone = "error" }: { children: ReactNode; tone?: "error" | "ok" }) {
  return (
    <p
      className={clsx(
        "rounded-xl px-3 py-2 text-sm",
        tone === "error" ? "bg-red-50 text-red-800" : "bg-moss-100 text-moss-600",
      )}
    >
      {children}
    </p>
  );
}
