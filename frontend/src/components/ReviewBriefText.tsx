import { formatRating, pluralize } from "@/lib/format";
import { hasNoReviews } from "@/lib/presentation";
import type { ReviewBrief } from "@/lib/types";

export function ReviewBriefText({ review }: { review: ReviewBrief }) {
  if (hasNoReviews(review)) return <span className="text-ink-muted">No reviews found</span>;
  return (
    <>
      {review.average !== null ? (
        <span className="font-semibold tabular-nums text-ink">{formatRating(review.average)}/5</span>
      ) : (
        <span className="text-ink-muted">No reliable average</span>
      )}
      <span className="text-ink-muted"> · {pluralize(review.count, "review")}</span>
      {review.status === "conflict" && (
        <span className="block text-xs font-medium text-amber-800 dark:text-amber-300">Sources disagree</span>
      )}
      {review.status === "insufficient" && <span className="block text-xs text-ink-faint">Insufficient evidence</span>}
    </>
  );
}
