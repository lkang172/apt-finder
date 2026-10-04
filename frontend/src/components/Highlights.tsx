import { IconAlert, IconPlus } from "./ui/icons";
import { CATEGORY_LABEL } from "@/lib/presentation";
import type { Highlight } from "@/lib/types";

type Variant = "card" | "detail";

interface HighlightsProps {
  positive: Highlight | null;
  concern: Highlight | null;
  variant: Variant;
}

export function Highlights({ positive, concern, variant }: HighlightsProps) {
  if (!positive && !concern) {
    return <p className="text-sm text-ink-faint">Not enough evidence yet to identify a standout positive or concern.</p>;
  }
  return (
    <ul className={`text-sm ${variant === "card" ? "space-y-1.5" : "space-y-2"}`}>
      <HighlightLine kind="positive" highlight={positive} variant={variant} />
      <HighlightLine kind="concern" highlight={concern} variant={variant} />
    </ul>
  );
}

interface HighlightLineProps {
  kind: "positive" | "concern";
  highlight: Highlight | null;
  variant: Variant;
}

function HighlightLine({ kind, highlight, variant }: HighlightLineProps) {
  const isPositive = kind === "positive";
  const label = isPositive ? "Strongest positive: " : "Strongest concern: ";
  return (
    <li className="flex gap-2">
      <span
        className={`mt-0.5 grid size-5 shrink-0 place-items-center rounded-full text-xs ${
          isPositive
            ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-300"
            : "bg-amber-100 text-amber-900 dark:bg-amber-400/15 dark:text-amber-300"
        }`}
      >
        {isPositive ? <IconPlus /> : <IconAlert />}
      </span>
      <span className="min-w-0">
        <span className={variant === "card" ? "sr-only" : "font-medium text-ink-muted"}>{label}</span>
        {highlight ? (
          <span className={variant === "card" ? "line-clamp-2 text-ink" : "text-ink"}>
            {highlight.text}{" "}
            {variant === "card" ? (
              <span className="text-xs text-ink-faint">({CATEGORY_LABEL[highlight.category]})</span>
            ) : (
              <a href={`#claim-${highlight.claim_id}`} className="whitespace-nowrap text-xs font-medium text-accent hover:underline">
                {CATEGORY_LABEL[highlight.category]} evidence →
              </a>
            )}
          </span>
        ) : (
          <span className="text-ink-faint">
            {isPositive ? "No well-supported positive identified" : "Not enough evidence to identify a top concern"}
          </span>
        )}
      </span>
    </li>
  );
}
