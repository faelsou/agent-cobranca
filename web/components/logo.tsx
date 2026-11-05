import { clsx } from "@/lib/format";

export function LogoMark({
  className,
  stroke = "#c6f432",
  dot = "#ffffff",
}: {
  className?: string;
  stroke?: string;
  dot?: string;
}) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <path
        d="M23 7H12.5a5 5 0 0 0 0 10h7a5 5 0 0 1 0 10H8"
        fill="none"
        stroke={stroke}
        strokeWidth="4.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="27" cy="27" r="2.6" fill={dot} />
    </svg>
  );
}

export function Logo({ className, wordClassName }: { className?: string; wordClassName?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-2.5", className)}>
      <LogoMark className="h-8 w-8 shrink-0" />
      <span className={clsx("font-display text-2xl leading-none text-white", wordClassName)}>Settlr</span>
    </span>
  );
}
