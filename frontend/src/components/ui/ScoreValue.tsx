import { formatScore } from "@/lib/format";
import { NA_TEXT, scoreTone, type Tone } from "@/lib/presentation";

const SCORE_TEXT_CLASS: Record<Tone, string> = {
  positive: "text-emerald-700 dark:text-emerald-300",
  warning: "text-amber-700 dark:text-amber-300",
  danger: "text-rose-700 dark:text-rose-300",
  neutral: "text-ink-faint",
  info: "text-sky-700 dark:text-sky-300",
  accent: "text-accent",
};

const SIZE_CLASS = {
  sm: "text-base",
  md: "text-2xl",
  lg: "text-4xl",
};

interface ScoreValueProps {
  score: number | null;
  size?: keyof typeof SIZE_CLASS;
  compactNa?: boolean;
}

export function ScoreValue({ score, size = "md", compactNa = false }: ScoreValueProps) {
  if (score === null) {
    return (
      <span className="font-semibold text-ink-faint" title={NA_TEXT}>
        {compactNa ? (
          <>
            <span className={SIZE_CLASS[size]}>N/A</span>
            <span className="sr-only"> — insufficient evidence</span>
          </>
        ) : (
          <span className="text-sm">{NA_TEXT}</span>
        )}
      </span>
    );
  }
  return (
    <span className={`font-semibold tabular-nums ${SCORE_TEXT_CLASS[scoreTone(score)]}`}>
      <span className={SIZE_CLASS[size]}>{formatScore(score)}</span>
      <span className="text-sm font-medium text-ink-faint">/10</span>
    </span>
  );
}
