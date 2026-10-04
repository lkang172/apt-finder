import { formatScore } from "@/lib/format";
import { NA_TEXT, scoreTone } from "@/lib/presentation";
import { TONE_TEXT_CLASS } from "./Badge";

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
    <span className={`font-semibold tabular-nums ${TONE_TEXT_CLASS[scoreTone(score)]}`}>
      <span className={SIZE_CLASS[size]}>{formatScore(score)}</span>
      <span className="text-sm font-medium text-ink-faint">/10</span>
    </span>
  );
}
