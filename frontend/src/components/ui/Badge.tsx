import type { ReactNode } from "react";
import type { Tone } from "@/lib/presentation";

export const TONE_BADGE_CLASS: Record<Tone, string> = {
  neutral: "bg-surface-muted text-ink-muted ring-line-strong",
  positive:
    "bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-400/10 dark:text-emerald-300 dark:ring-emerald-400/25",
  info: "bg-sky-50 text-sky-800 ring-sky-200 dark:bg-sky-400/10 dark:text-sky-300 dark:ring-sky-400/25",
  warning: "bg-amber-50 text-amber-900 ring-amber-300 dark:bg-amber-400/10 dark:text-amber-300 dark:ring-amber-400/25",
  danger: "bg-rose-50 text-rose-800 ring-rose-200 dark:bg-rose-400/10 dark:text-rose-300 dark:ring-rose-400/25",
  accent: "bg-accent-soft text-accent ring-accent/25",
};

export const TONE_PANEL_CLASS: Record<Tone, string> = {
  neutral: "border-line bg-surface-muted",
  positive: "border-emerald-200 bg-emerald-50/70 dark:border-emerald-400/25 dark:bg-emerald-400/5",
  info: "border-sky-200 bg-sky-50/70 dark:border-sky-400/25 dark:bg-sky-400/5",
  warning: "border-amber-300 bg-amber-50/80 dark:border-amber-400/30 dark:bg-amber-400/5",
  danger: "border-rose-300 bg-rose-50/80 dark:border-rose-400/30 dark:bg-rose-400/5",
  accent: "border-accent/30 bg-accent-soft",
};

interface BadgeProps {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  title?: string;
}

export function Badge({ tone = "neutral", children, className = "", title }: BadgeProps) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${TONE_BADGE_CLASS[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
