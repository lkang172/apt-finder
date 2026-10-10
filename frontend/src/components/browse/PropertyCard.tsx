import Link from "next/link";
import { EligibilityBadge } from "@/components/EligibilityNotice";
import { GoogleCommentsSummary, GoogleRatingLine, GoogleSummary, LowGoogleRatingBadge } from "@/components/GoogleRating";
import { Highlights } from "@/components/Highlights";
import { PriceStatusBadges } from "@/components/PriceStatusBadges";
import { PropertyImage } from "@/components/PropertyImage";
import { ReviewBriefText } from "@/components/ReviewBriefText";
import { Badge } from "@/components/ui/Badge";
import { ConfidenceBadge } from "@/components/ui/ConfidenceBadge";
import { IconCar, IconPin, IconStar } from "@/components/ui/icons";
import { ScoreValue } from "@/components/ui/ScoreValue";
import { Timestamp } from "@/components/ui/Timestamp";
import { rentsInRange, SCORE_FILTER_CATEGORIES, type RentRange, type SortKey } from "@/lib/browse";
import {
  formatMiles,
  formatMinutes,
  formatMoney,
  formatMoneyRange,
  formatScore,
  formatSqftRange,
  pluralize,
} from "@/lib/format";
import {
  CATEGORY_LABEL,
  NA_TEXT,
  REGION_LABEL,
  sourcesLabel,
  UNIT_TYPE_LABEL,
  type SourceNames,
} from "@/lib/presentation";
import type { CommuteBrief, PropertySummary, ReviewBrief } from "@/lib/types";

interface PropertyCardProps {
  property: PropertySummary;
  highlighted: boolean;
  sortKey: SortKey;
  sourceNames: SourceNames;
  baseRent: RentRange | null;
  onHoverChange: (id: number | null) => void;
}

export function PropertyCard({ property: p, highlighted, sortKey, sourceNames, baseRent, onHoverChange }: PropertyCardProps) {
  const sortedCategory = SCORE_FILTER_CATEGORIES.find((category) => category === sortKey);
  const titleId = `property-${p.id}-title`;

  return (
    <article
      id={`property-card-${p.id}`}
      aria-labelledby={titleId}
      onMouseEnter={() => onHoverChange(p.id)}
      onMouseLeave={() => onHoverChange(null)}
      className={`relative flex w-full flex-col overflow-hidden rounded-2xl border bg-surface shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg has-[a:focus-visible]:ring-2 has-[a:focus-visible]:ring-accent ${
        highlighted ? "border-accent ring-2 ring-accent" : "border-line"
      }`}
    >
      <div className="relative">
        <PropertyImage src={p.image_url} alt={`Photo of ${p.name}`} sourceName={p.image_source_name} className="aspect-[16/10]" />
        <div className="absolute left-3 top-3 flex flex-wrap gap-1.5">
          <EligibilityBadge notes={p.eligibility_notes} overImage />
          <PriceStatusBadges status={p.price_status} hasPromotion={p.has_promotion} overImage />
          <LowGoogleRatingBadge google={p.google} overImage />
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-4 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 id={titleId} className="text-base font-semibold leading-snug tracking-tight text-ink">
              <Link href={`/properties/${p.id}`} className="outline-none after:absolute after:inset-0 after:content-['']">
                {p.name}
              </Link>
            </h3>
            <p className="mt-0.5 flex items-center gap-1 text-sm text-ink-muted">
              <IconPin className="shrink-0" />
              <span className="truncate">
                {p.city} · {REGION_LABEL[p.region]}
              </span>
            </p>
          </div>
          <div className="shrink-0 text-right">
            <span className="sr-only">Overall score: </span>
            <ScoreValue score={p.overall.score} size="md" compactNa />
            <div className="mt-1">
              <ConfidenceBadge confidence={p.overall.confidence} />
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {p.unit_types.map((type) => (
            <Badge key={type}>{UNIT_TYPE_LABEL[type]}</Badge>
          ))}
          <span className="text-sm text-ink-muted">{formatSqftRange(p.sqft_min, p.sqft_max) ?? "Sq ft not published"}</span>
        </div>

        <PriceBlock property={p} baseRent={baseRent} />

        <div className="space-y-2 rounded-xl border border-line px-3 py-2.5">
          <GoogleRatingLine google={p.google} linkClassName="relative z-10" />
          <GoogleSummary google={p.google} clamp />
          <GoogleCommentsSummary google={p.google} clamp />
        </div>

        <dl className="grid grid-cols-2 gap-3 text-sm">
          <CommuteSummary commute={p.commute} />
          <ReviewSummary review={p.review} sourceLabel={sourcesLabel(p.source_ids, sourceNames)} />
        </dl>

        <Highlights positive={p.strongest_positive} concern={p.strongest_concern} variant="card" />

        <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3 text-xs text-ink-faint">
          {sortedCategory ? (
            <span className="font-medium text-ink-muted">
              {CATEGORY_LABEL[sortedCategory]}: {scoreText(p.scores[sortedCategory].score)}
            </span>
          ) : (
            <span>{pluralize(p.source_ids.length, "source")}</span>
          )}
          <span>
            {p.last_verified_at ? (
              <>
                Verified <Timestamp iso={p.last_verified_at} />
              </>
            ) : (
              "Verification time unknown"
            )}
          </span>
        </div>
      </div>
    </article>
  );
}

function scoreText(score: number | null): string {
  return score === null ? NA_TEXT : `${formatScore(score)}/10`;
}

function PriceBlock({ property: p, baseRent: range }: { property: PropertySummary; baseRent: RentRange | null }) {
  const baseRent = formatMoneyRange(p.rent_min, p.rent_max);
  const matching = range ? rentsInRange(p, range) : [];
  return (
    <div className="rounded-xl bg-surface-muted px-3 py-2.5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">Est. monthly total</p>
      {p.est_monthly_total_min === null ? (
        <p className="text-base font-semibold text-ink-muted">Unavailable</p>
      ) : (
        <p className="text-2xl font-bold tracking-tight text-ink tabular-nums">
          <span className="text-sm font-medium text-ink-muted">from </span>
          {formatMoney(p.est_monthly_total_min)}
          <span className="text-sm font-medium text-ink-muted">/mo</span>
        </p>
      )}
      {p.has_unknown_required_costs && (
        <p className="text-xs font-semibold text-amber-800 dark:text-amber-300">+ unknown required costs</p>
      )}
      <p className="mt-0.5 text-sm text-ink-muted">
        Base rent <span className="font-medium text-ink tabular-nums">{baseRent ?? "not published"}</span>
      </p>
      {matching.length > 0 && (
        <p className="text-xs font-medium text-accent">
          In your range: {matching.slice(0, 3).map(formatMoney).join(", ")}
          {matching.length > 3 && ` +${matching.length - 3} more`}
        </p>
      )}
    </div>
  );
}

function rushText(commute: CommuteBrief): string {
  const { am_rush_minutes: am, pm_rush_minutes: pm } = commute;
  if (am === null && pm === null) return "Rush hour unavailable";
  return `Rush: AM ${am === null ? "unavailable" : formatMinutes(am)} · PM ${pm === null ? "unavailable" : formatMinutes(pm)}`;
}

function CommuteSummary({ commute }: { commute: CommuteBrief | null }) {
  return (
    <div>
      <dt className="flex items-center gap-1 text-xs font-medium text-ink-faint">
        <IconCar /> Commute
      </dt>
      {commute === null ? (
        <dd className="text-ink-muted">Unavailable</dd>
      ) : (
        <dd>
          <span className="font-semibold text-ink tabular-nums">
            {commute.free_flow_minutes === null ? "Time unavailable" : formatMinutes(commute.free_flow_minutes)}
          </span>
          {commute.distance_miles !== null && (
            <span className="text-ink-muted tabular-nums"> · {formatMiles(commute.distance_miles)}</span>
          )}
          <span className="block text-xs text-ink-faint">No traffic</span>
          <span className="block text-xs text-ink-faint" title={commute.rush_status}>
            {rushText(commute)}
          </span>
        </dd>
      )}
    </div>
  );
}

function ReviewSummary({ review, sourceLabel }: { review: ReviewBrief; sourceLabel: string }) {
  return (
    <div className="min-w-0">
      <dt className="flex items-center gap-1 text-xs font-medium text-ink-faint">
        <IconStar className="shrink-0" />{" "}
        <span className="truncate" title={sourceLabel}>
          {sourceLabel}
        </span>
      </dt>
      <dd>
        <ReviewBriefText review={review} />
      </dd>
    </div>
  );
}
