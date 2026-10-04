import type { ReactNode } from "react";
import { URL_UNAVAILABLE_TEXT } from "@/lib/presentation";

type Variant = "inline" | "button" | "primary";

const VARIANT_CLASS: Record<Variant, string> = {
  inline:
    "font-medium text-accent underline-offset-2 hover:text-accent-hover hover:underline focus-visible:rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
  button:
    "inline-flex items-center gap-1 rounded-full border border-line-strong bg-surface px-3 py-1.5 text-sm font-medium text-ink shadow-sm transition hover:border-accent hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
  primary:
    "inline-flex items-center gap-1.5 rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-sm transition hover:bg-accent-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
};

function isHttpUrl(value: string): boolean {
  try {
    const { protocol } = new URL(value);
    return protocol === "http:" || protocol === "https:";
  } catch {
    return false;
  }
}

interface ExternalLinkProps {
  href: string | null;
  children: ReactNode;
  variant?: Variant;
  unavailableText?: string;
  className?: string;
}

export function ExternalLink({
  href,
  children,
  variant = "inline",
  unavailableText = URL_UNAVAILABLE_TEXT,
  className = "",
}: ExternalLinkProps) {
  if (!href || !isHttpUrl(href)) {
    return <span className={`text-sm italic text-ink-faint ${className}`}>{unavailableText}</span>;
  }
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={`relative ${VARIANT_CLASS[variant]} ${className}`}>
      {children}
      <span aria-hidden="true"> ↗</span>
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}
