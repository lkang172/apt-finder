import type { ReactNode } from "react";
import { Badge, TONE_PANEL_CLASS } from "@/components/ui/Badge";
import { ConfidenceBadge } from "@/components/ui/ConfidenceBadge";
import { ExternalLink } from "@/components/ui/ExternalLink";
import { IconChevronDown } from "@/components/ui/icons";
import { Card } from "@/components/ui/Section";
import { Timestamp } from "@/components/ui/Timestamp";
import type { EvidenceIndex } from "@/lib/evidence";
import { formatRating, pluralize } from "@/lib/format";
import { CONFIDENCE_LABEL, hasNoReviews, type Tone } from "@/lib/presentation";
import type { PropertyDetail, RatingFilterStatus, RatingSummary, ReviewBrief, ThemeStat } from "@/lib/types";
import { DetailList } from "./DetailList";
import { EvidenceList, EvidenceRefs } from "./Evidence";

interface ReviewIntelligenceProps {
  detail: PropertyDetail;
  evidenceIndex: EvidenceIndex;
  officialUrl: string | null;
  sourceLabel: string;
}

export function ReviewIntelligence({ detail, evidenceIndex, officialUrl, sourceLabel }: ReviewIntelligenceProps) {
  const { review, review_intelligence: intel } = detail;
  const noReviewTexts = intel.reviews.length === 0;

  return (
    <div className="space-y-5">
      <ReviewDataLine review={review} sourceLabel={sourceLabel} confidence={CONFIDENCE_LABEL[intel.quality.confidence]} />

      {noReviewTexts ? (
        <Card>
          <p className="text-sm text-ink-muted">
            No review texts were collected for this property, so noise, management, and pest conditions can&apos;t be
            assessed from reviews. That absence is not a positive signal — check the Google rating above and look for
            resident feedback yourself.
          </p>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            <ThemePanel
              title="Most Commonly Praised"
              stats={intel.praised}
              emptyText="No recurring praise themes were identified in the collected reviews."
              tone="positive"
              evidenceIndex={evidenceIndex}
              officialUrl={officialUrl}
            />
            <ThemePanel
              title="Most Commonly Criticized"
              stats={intel.criticized}
              emptyText="No recurring criticism themes were identified in the collected reviews. That isn't evidence that problems don't exist."
              tone="danger"
              evidenceIndex={evidenceIndex}
              officialUrl={officialUrl}
            />
          </div>

          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            <Card>
              <h3 className="font-semibold text-ink">Recent Trends</h3>
              {intel.recent_trends.length > 0 ? (
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink">
                  {intel.recent_trends.map((trend) => (
                    <li key={trend}>{trend}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-ink-muted">Not enough recent reviews to identify a trend.</p>
              )}
            </Card>
            <Card>
              <h3 className="font-semibold text-ink">Important Outliers</h3>
              {intel.outliers.length > 0 ? (
                <ul className="mt-2 space-y-3">
                  {intel.outliers.map((outlier) => (
                    <li key={outlier.evidence_id} className="text-sm">
                      <p className="text-ink">{outlier.text}</p>
                      <Disclosure label="View evidence">
                        <EvidenceRefs ids={[outlier.evidence_id]} index={evidenceIndex} officialUrl={officialUrl} />
                      </Disclosure>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-ink-muted">No outliers were flagged.</p>
              )}
            </Card>
          </div>
        </>
      )}

      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-semibold text-ink">Evidence Quality</h3>
          <ConfidenceBadge confidence={intel.quality.confidence} />
        </div>
        <p className="mt-2 text-sm text-ink">{intel.quality.summary}</p>
        <div className="mt-3">
          <DetailList details={intel.quality.details} />
        </div>
      </Card>

      <Card>
        <h3 className="font-semibold text-ink">
          Reviews Analyzed <span className="font-normal text-ink-muted">({intel.reviews.length})</span>
        </h3>
        {intel.reviews.length > 0 ? (
          <div className="mt-3">
            <EvidenceList
              items={intel.reviews}
              officialUrl={officialUrl}
              initialCount={5}
              moreLabel={(remaining) => `Show ${pluralize(remaining, "more review")}`}
            />
          </div>
        ) : (
          <p className="mt-2 text-sm text-ink-muted">No individual review texts were collected.</p>
        )}
      </Card>
    </div>
  );
}

function ReviewDataLine({ review, sourceLabel, confidence }: { review: ReviewBrief; sourceLabel: string; confidence: string }) {
  const reviewData =
    hasNoReviews(review)
      ? "No reviews found"
      : review.average !== null
        ? `${formatRating(review.average)}/5 across ${pluralize(review.count, "review")}`
        : review.explanation;
  return (
    <div className="rounded-2xl border border-line bg-surface px-4 py-3 text-sm shadow-sm">
      <p className="text-ink">
        <span className="text-ink-muted">Review data ({sourceLabel}):</span> <span className="font-semibold">{reviewData}</span>
        <span aria-hidden="true" className="px-2 text-ink-faint">
          ·
        </span>
        <span className="text-ink-muted">Review confidence:</span> <span className="font-semibold">{confidence}</span>
      </p>
      {!hasNoReviews(review) && review.explanation && review.explanation !== reviewData && (
        <p className="mt-1 text-xs text-ink-muted">{review.explanation}</p>
      )}
    </div>
  );
}

interface ThemePanelProps {
  title: string;
  stats: ThemeStat[];
  emptyText: string;
  tone: "positive" | "danger";
  evidenceIndex: EvidenceIndex;
  officialUrl: string | null;
}

function ThemePanel({ title, stats, emptyText, tone, evidenceIndex, officialUrl }: ThemePanelProps) {
  return (
    <Card>
      <h3 className="font-semibold text-ink">{title}</h3>
      {stats.length > 0 ? (
        <ul className="mt-3 space-y-2">
          {stats.map((stat) => (
            <li key={stat.theme}>
              <details className="group/theme rounded-xl border border-line">
                <summary className="flex items-center justify-between gap-3 rounded-xl px-3 py-2 hover:bg-surface-muted/60 focus-visible:outline-2 focus-visible:outline-accent">
                  <span className="flex min-w-0 items-center gap-2">
                    <Badge tone={tone}>{stat.count}</Badge>
                    <span className="truncate text-sm font-medium text-ink">{stat.label}</span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2 text-xs text-ink-faint">
                    {stat.recent_count} recent
                    <IconChevronDown className="transition group-open/theme:rotate-180" />
                  </span>
                </summary>
                <div className="border-t border-line p-3">
                  <EvidenceRefs ids={stat.evidence_ids} index={evidenceIndex} officialUrl={officialUrl} initialCount={3} />
                </div>
              </details>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-ink-muted">{emptyText}</p>
      )}
    </Card>
  );
}

function Disclosure({ label, children }: { label: string; children: ReactNode }) {
  return (
    <details className="group/disclosure mt-1">
      <summary className="inline-flex items-center gap-1 rounded text-xs font-medium text-accent hover:underline focus-visible:outline-2 focus-visible:outline-accent">
        {label} <IconChevronDown className="transition group-open/disclosure:rotate-180" />
      </summary>
      <div className="mt-2">{children}</div>
    </details>
  );
}

const RATING_FILTER_TONE: Record<RatingFilterStatus, Tone> = {
  ok: "positive",
  no_reviews: "neutral",
  insufficient: "neutral",
  conflict: "warning",
  low_rating: "warning",
};

// A low rating is flagged, never used to exclude a property — the browse page filters by Google stars instead.
const RATING_FILTER_TITLE: Record<RatingFilterStatus, string> = {
  ok: "Rating filter: passed",
  no_reviews: "Rating filter not applied — no reviews found",
  insufficient: "Rating filter not applied — not enough reliable ratings",
  conflict: "Conflicting ratings across sources — not resolved automatically",
  low_rating: "Flagged: well-established rating below 3.0/5",
};

interface RatingSummariesProps {
  summaries: RatingSummary[];
  filter: PropertyDetail["rating_filter"];
}

export function RatingSummaries({ summaries, filter }: RatingSummariesProps) {
  const tone = RATING_FILTER_TONE[filter.status];
  return (
    <Card className="space-y-4">
      <h3 className="font-semibold text-ink">Ratings by source</h3>
      <div className={`rounded-xl border p-3 text-sm ${TONE_PANEL_CLASS[tone]}`}>
        <p className="font-semibold text-ink">{RATING_FILTER_TITLE[filter.status]}</p>
        <p className="mt-0.5 text-ink-muted">{filter.explanation}</p>
        {filter.status === "low_rating" && (
          <p className="mt-1 text-xs text-ink-muted">
            Flagged for your attention — a low rating never removes a property from the results. Use the Google rating
            filter on the browse page to hide low-rated properties.
          </p>
        )}
      </div>
      {summaries.length > 0 ? (
        <ul className="divide-y divide-line">
          {summaries.map((summary, index) => (
            <li key={`${summary.source_id}-${index}`} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
              <span>
                <span className="block text-sm font-semibold text-ink">{summary.source_name}</span>
                <span className="block text-xs text-ink-faint">
                  Observed <Timestamp iso={summary.observed_at} />
                </span>
              </span>
              <span className="flex items-center gap-4">
                <span className="text-right text-sm">
                  <span className="block font-semibold tabular-nums text-ink">
                    {summary.average === null ? "No average published" : `${formatRating(summary.average)}/5`}
                  </span>
                  <span className="block text-xs text-ink-muted">{pluralize(summary.count, "review")}</span>
                </span>
                <ExternalLink href={summary.source_url} className="text-sm">
                  View Source
                </ExternalLink>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-ink-muted">No source published a rating summary for this property.</p>
      )}
    </Card>
  );
}
