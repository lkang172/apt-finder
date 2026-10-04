import { GoogleCommentsSummary, GoogleRatingLine, GoogleSummary } from "@/components/GoogleRating";
import { TONE_PANEL_CLASS } from "@/components/ui/Badge";
import { ExternalLink } from "@/components/ui/ExternalLink";
import { IconAlert } from "@/components/ui/icons";
import { Card } from "@/components/ui/Section";
import { Timestamp } from "@/components/ui/Timestamp";
import { pluralize } from "@/lib/format";
import { isUncertainGoogleMatch, UNCERTAIN_MATCH_TEXT } from "@/lib/presentation";
import type { GoogleReviewsBrief } from "@/lib/types";

export function GoogleReviewsPanel({ google }: { google: GoogleReviewsBrief }) {
  const ok = google.status === "ok";
  return (
    <section id="google-reviews" aria-labelledby="google-reviews-heading" className="scroll-mt-28">
      <Card className="grid grid-cols-1 gap-x-8 gap-y-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
        <div className="space-y-4">
          <div>
            <h2 id="google-reviews-heading" className="text-lg font-semibold tracking-tight text-ink">
              Google reviews
            </h2>
            {ok && google.observed_at && (
              <p className="text-xs text-ink-faint">
                Observed <Timestamp iso={google.observed_at} />
              </p>
            )}
          </div>
          <GoogleRatingLine google={google} size="large" linked={false} showMatchNote={false} />
          {isUncertainGoogleMatch(google) && (
            <p className={`flex items-start gap-2 rounded-xl border px-3 py-2 text-sm text-ink ${TONE_PANEL_CLASS.warning}`}>
              <IconAlert className="mt-0.5 shrink-0 text-amber-700 dark:text-amber-300" />
              {UNCERTAIN_MATCH_TEXT}
            </p>
          )}
          <ExternalLink href={google.maps_url} variant="button" unavailableText="Google Maps link unavailable">
            View on Google Maps
          </ExternalLink>
        </div>

        <div className="space-y-3">
          {ok && google.summary && (
            <div className="rounded-xl bg-surface-muted p-4">
              <GoogleSummary google={google} showReportLink />
            </div>
          )}
          {google.comments_summary && (
            <div className="rounded-xl bg-surface-muted p-4">
              <GoogleCommentsSummary google={google} />
            </div>
          )}
          {ok && !google.summary && !google.comments_summary && (
            <p className="text-sm text-ink-muted">No summary of the Google reviews is available for this place.</p>
          )}
          <p className="text-xs text-ink-muted">
            {ok
              ? `The star rating covers ${
                  google.count === null ? "all Google reviews" : `all ${pluralize(google.count, "Google review")}`
                }. Google returns at most 5 review texts, so “Reviews Analyzed” below includes up to 5 Google reviews plus any collected from other sources.`
              : "Missing Google data says nothing about this property's reviews — check Google Maps yourself before deciding."}
          </p>
        </div>
      </Card>
    </section>
  );
}
