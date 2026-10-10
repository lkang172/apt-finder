import { EligibilityBadge } from "@/components/EligibilityNotice";
import { GoogleRatingLine, LowGoogleRatingBadge } from "@/components/GoogleRating";
import { Highlights } from "@/components/Highlights";
import { PriceStatusBadges } from "@/components/PriceStatusBadges";
import { PropertyImage } from "@/components/PropertyImage";
import { ReviewBriefText } from "@/components/ReviewBriefText";
import { Badge } from "@/components/ui/Badge";
import { ConfidenceBadge } from "@/components/ui/ConfidenceBadge";
import { IconPin } from "@/components/ui/icons";
import { ScoreValue } from "@/components/ui/ScoreValue";
import { Timestamp } from "@/components/ui/Timestamp";
import { formatSqftRange, pluralize } from "@/lib/format";
import { REGION_LABEL, sourcesLabel, UNIT_TYPE_LABEL, type SourceNames } from "@/lib/presentation";
import type { PropertyDetail } from "@/lib/types";

export function PropertyHeader({ detail, sourceNames }: { detail: PropertyDetail; sourceNames: SourceNames }) {
  const address = [detail.street_address, [detail.city, detail.zip].filter(Boolean).join(" ")].filter(Boolean).join(", ");
  const sqft = formatSqftRange(detail.sqft_min, detail.sqft_max);

  return (
    <header className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] lg:items-center">
      <PropertyImage
        src={detail.image_url}
        alt={`Photo of ${detail.name}`}
        sourceName={detail.image_source_name}
        className="aspect-[16/10] rounded-3xl"
      />

      <div className="space-y-4">
        <div className="flex flex-wrap gap-1.5">
          <Badge>{REGION_LABEL[detail.region]}</Badge>
          <EligibilityBadge notes={detail.eligibility_notes} />
          <PriceStatusBadges status={detail.price_status} hasPromotion={detail.has_promotion} />
          <LowGoogleRatingBadge google={detail.google} />
        </div>

        <div>
          <h1 className="text-3xl font-bold tracking-tight text-ink sm:text-4xl">{detail.name}</h1>
          <p className="mt-1.5 flex items-start gap-1.5 text-ink-muted">
            <IconPin className="mt-1 shrink-0" />
            {address || "Street address not published"}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {detail.unit_types.map((type) => (
            <Badge key={type}>{UNIT_TYPE_LABEL[type]}</Badge>
          ))}
          {sqft && <span className="text-sm text-ink-muted">{sqft}</span>}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <a
            href="#overall"
            className="rounded-2xl border border-line bg-surface p-3 shadow-sm transition hover:border-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            <span className="block text-xs font-semibold uppercase tracking-wider text-ink-faint">Overall score</span>
            <span className="mt-0.5 block">
              <ScoreValue score={detail.overall.score} size="md" compactNa />
            </span>
            <ConfidenceBadge confidence={detail.overall.confidence} className="mt-1" />
          </a>
          <a
            href="#google-reviews"
            className="min-w-0 rounded-2xl border border-line bg-surface p-3 shadow-sm transition hover:border-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            <span className="block text-xs font-semibold uppercase tracking-wider text-ink-faint">Reviews</span>
            <span className="mt-1 block">
              <GoogleRatingLine google={detail.google} size="compact" linked={false} />
            </span>
            <span className="mt-1.5 line-clamp-2 block text-xs text-ink-muted" title={sourcesLabel(detail.source_ids, sourceNames)}>
              {sourcesLabel(detail.source_ids, sourceNames)}: <ReviewBriefText review={detail.review} />
            </span>
          </a>
        </div>

        <Highlights positive={detail.strongest_positive} concern={detail.strongest_concern} variant="detail" />

        <p className="text-xs text-ink-faint">
          {detail.last_verified_at ? (
            <>
              Last verified: <Timestamp iso={detail.last_verified_at} className="font-medium text-ink-muted" />
            </>
          ) : (
            "Last verification time unknown"
          )}{" "}
          · {pluralize(detail.source_ids.length, "source")}
        </p>
      </div>
    </header>
  );
}
