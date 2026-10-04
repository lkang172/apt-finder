import { Badge, TONE_PANEL_CLASS } from "@/components/ui/Badge";
import { ExternalLink } from "@/components/ui/ExternalLink";
import { IconAlert, IconTag } from "@/components/ui/icons";
import { Card } from "@/components/ui/Section";
import { Timestamp } from "@/components/ui/Timestamp";
import { bedsLabel, formatMoney, formatMoneyRange, formatSqftRange, humanize } from "@/lib/format";
import { listingLinkLabel, UNIT_TYPE_LABEL } from "@/lib/presentation";
import type { FeeView, ListingLink, MonthlyCost, OfficialWebsite, PriceConflictView, PropertyDetail } from "@/lib/types";

export function MonthlyCostCard({ cost, hasUnknownRequiredCosts }: { cost: MonthlyCost; hasUnknownRequiredCosts: boolean }) {
  const showUnknownFlag = hasUnknownRequiredCosts || cost.unknown_required.length > 0;
  return (
    <Card>
      <p className="text-xs font-semibold uppercase tracking-wider text-ink-faint">Estimated recurring monthly total</p>
      {cost.est_total_min === null ? (
        <p className="mt-1 text-xl font-semibold text-ink-muted">Unavailable</p>
      ) : (
        <p className="mt-1 text-4xl font-bold tracking-tight text-ink tabular-nums">
          <span className="text-base font-medium text-ink-muted">from </span>
          {formatMoney(cost.est_total_min)}
          <span className="text-base font-medium text-ink-muted">/mo</span>
        </p>
      )}
      {showUnknownFlag && (
        <p className="mt-1 text-sm font-semibold text-amber-800 dark:text-amber-300">+ unknown required costs</p>
      )}

      <dl className="mt-4 space-y-2 border-t border-line pt-4 text-sm">
        <div className="flex justify-between gap-3">
          <dt className="text-ink-muted">Lowest qualifying base rent</dt>
          <dd className="font-medium tabular-nums text-ink">
            {cost.base_rent_min === null ? "Not published" : formatMoney(cost.base_rent_min)}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-ink-muted">+ Confirmed required fees</dt>
          <dd className="font-medium tabular-nums text-ink">
            {cost.confirmed_required_fees === null ? "Unknown" : `${formatMoney(cost.confirmed_required_fees)}/mo`}
          </dd>
        </div>
        <div className="flex justify-between gap-3 border-t border-dashed border-line pt-2">
          <dt className="font-semibold text-ink">= Estimated monthly total</dt>
          <dd className="font-semibold tabular-nums text-ink">
            {cost.est_total_min === null ? "Unavailable" : formatMoney(cost.est_total_min)}
          </dd>
        </div>
      </dl>

      {cost.unknown_required.length > 0 && (
        <div className={`mt-4 rounded-xl border p-3 text-sm ${TONE_PANEL_CLASS.warning}`}>
          <p className="font-semibold text-ink">Required, but amount not published</p>
          <p className="text-xs text-ink-muted">Not included in the estimate — your real monthly cost will be higher.</p>
          <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-ink">
            {cost.unknown_required.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      {cost.unclear_recurring.length > 0 && (
        <div className="mt-3 rounded-xl border border-line bg-surface-muted p-3 text-sm">
          <p className="font-semibold text-ink">Recurring fees — unclear if required</p>
          <p className="text-xs text-ink-muted">Not included in the estimate. Ask the property whether these are mandatory.</p>
          <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-ink">
            {cost.unclear_recurring.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

export function ListingLinks({ listings, official }: { listings: ListingLink[]; official: OfficialWebsite | null }) {
  const officialUrl = official?.url ?? null;
  return (
    <section id="listings" aria-labelledby="listings-heading" className="scroll-mt-28">
      <Card>
        <h2 id="listings-heading" className="text-lg font-semibold tracking-tight text-ink">
          View Original Listings
        </h2>
        <p className="mt-0.5 text-sm text-ink-muted">Confirm current prices and availability directly with each source.</p>
        <ul className="mt-4 space-y-2.5">
          {official && (
            <li className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-accent/30 bg-accent-soft px-3 py-2.5">
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-ink">Official website</span>
                <span className="block truncate text-xs text-ink-muted">Linked from {official.source_name}</span>
              </span>
              <ExternalLink href={official.url} variant="primary">
                View Official Website
              </ExternalLink>
            </li>
          )}
          {listings.map((listing, index) => (
            <li
              key={`${listing.source_id}-${index}`}
              className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line px-3 py-2.5"
            >
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-ink">{listing.source_name}</span>
                {listing.name && <span className="block truncate text-xs text-ink-muted">{listing.name}</span>}
                <span className="block text-xs text-ink-faint">
                  Last seen <Timestamp iso={listing.last_seen_at} />
                </span>
              </span>
              <ExternalLink href={listing.url} variant="button">
                {listingLinkLabel(listing.url, officialUrl)}
              </ExternalLink>
            </li>
          ))}
          {!official && listings.length === 0 && (
            <li className="text-sm italic text-ink-faint">No listing sources recorded.</li>
          )}
        </ul>
        {!official && listings.length > 0 && (
          <p className="mt-3 text-xs text-ink-faint">No official property website was found.</p>
        )}
      </Card>
    </section>
  );
}

export function PriceAlerts({ detail }: { detail: PropertyDetail }) {
  const { price_conflicts: conflicts, price_status: status } = detail;
  if (conflicts.length === 0 && status === "verified") return null;
  return (
    <div className="space-y-3">
      {conflicts.map((conflict, index) => (
        <PriceConflictPanel key={index} conflict={conflict} />
      ))}
      {status === "conflict" && conflicts.length === 0 && (
        <div role="alert" className={`rounded-2xl border-2 p-4 ${TONE_PANEL_CLASS.danger}`}>
          <p className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-rose-800 dark:text-rose-300">
            <IconAlert /> Price conflict — verify directly
          </p>
          <p className="mt-1 text-sm text-ink">Sources disagree on current pricing. Compare the units and listings below.</p>
        </div>
      )}
      {status === "stale" && (
        <div role="alert" className={`rounded-2xl border-2 p-4 ${TONE_PANEL_CLASS.warning}`}>
          <p className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-amber-900 dark:text-amber-300">
            <IconAlert /> Stale pricing — verify directly
          </p>
          <p className="mt-1 text-sm text-ink">
            These prices haven&apos;t been re-verified recently
            {detail.last_verified_at ? (
              <>
                {" "}
                (last verified <Timestamp iso={detail.last_verified_at} className="font-medium" />)
              </>
            ) : null}
            . Confirm current rent with the property before relying on them.
          </p>
        </div>
      )}
    </div>
  );
}

function PriceConflictPanel({ conflict }: { conflict: PriceConflictView }) {
  return (
    <div role="alert" className={`rounded-2xl border-2 p-4 ${TONE_PANEL_CLASS.danger}`}>
      <p className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-rose-800 dark:text-rose-300">
        <IconAlert /> Price conflict — verify directly
      </p>
      <p className="mt-1 text-sm text-ink">
        {bedsLabel(conflict.beds)}
        {conflict.sqft !== null && ` · ${Math.round(conflict.sqft).toLocaleString("en-US")} sq ft`} — current sources differ by{" "}
        <span className="font-semibold">{formatMoney(conflict.difference)}</span>. We don&apos;t pick a winner.
      </p>
      <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {conflict.sides.map((side, index) => (
          <li key={`${side.source_id}-${index}`} className="rounded-xl border border-line bg-surface p-3">
            <p className="text-sm font-semibold text-ink">{side.source_name}</p>
            {side.label && <p className="text-xs text-ink-muted">{side.label}</p>}
            <p className="mt-1 text-2xl font-bold tabular-nums text-ink">{formatMoneyRange(side.price_min, side.price_max)}</p>
            <ExternalLink href={side.url} className="mt-1 inline-block text-sm">
              View Listing
            </ExternalLink>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function PricingDetails({ detail }: { detail: PropertyDetail }) {
  const officialUrl = detail.official_website?.url ?? null;
  const leaseTerms = [
    ...new Set(detail.units.filter((u) => u.qualifies && u.lease_term_months !== null).map((u) => u.lease_term_months as number)),
  ].sort((a, b) => a - b);

  return (
    <div className="space-y-5">
      <Card>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Stat label="Advertised base rent" value={formatMoneyRange(detail.rent_min, detail.rent_max) ?? "Not published"} />
          <Stat label="Square footage" value={formatSqftRange(detail.sqft_min, detail.sqft_max) ?? "Not published"} />
          <Stat
            label="Lease terms"
            value={leaseTerms.length > 0 ? leaseTerms.map((months) => `${months} mo`).join(", ") : "Not published"}
          />
          <Stat
            label="Qualifying unit types"
            value={detail.unit_types.length > 0 ? detail.unit_types.map((type) => UNIT_TYPE_LABEL[type]).join(", ") : "None"}
          />
        </dl>
      </Card>

      {detail.promotions.length > 0 && (
        <div className={`rounded-2xl border p-4 ${TONE_PANEL_CLASS.accent}`}>
          <p className="flex items-center gap-2 font-semibold text-ink">
            <IconTag className="text-accent" /> Promotions
          </p>
          <p className="mt-1 text-sm text-ink-muted">
            Promotional or “effective” rent is not equivalent to a normal lease at that price. Compare the base rent, lease term,
            and concession terms before deciding.
          </p>
          <ul className="mt-3 space-y-2">
            {detail.promotions.map((promotion, index) => (
              <li key={`${promotion.source_id}-${index}`} className="rounded-xl border border-line bg-surface p-3 text-sm">
                <p className="text-ink">{promotion.text}</p>
                <p className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-ink-faint">
                  <span>{promotion.source_name}</span>
                  <ExternalLink href={promotion.url}>{listingLinkLabel(promotion.url, officialUrl)}</ExternalLink>
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      <FeesTable fees={detail.fees} officialUrl={officialUrl} />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium text-ink-faint">{label}</dt>
      <dd className="mt-0.5 font-semibold tabular-nums text-ink">{value}</dd>
    </div>
  );
}

function YesNoUnclear({ value }: { value: boolean | null }) {
  if (value === null) return <Badge>Unclear</Badge>;
  return value ? <Badge tone="warning">Yes</Badge> : <Badge>No</Badge>;
}

function feeAmount(fee: FeeView): string {
  if (fee.amount_monthly !== null) return `${formatMoney(fee.amount_monthly)}/mo`;
  return fee.amount_text ?? "Amount not published";
}

function FeesTable({ fees, officialUrl }: { fees: FeeView[]; officialUrl: string | null }) {
  return (
    <Card flush>
      <div className="px-5 pt-5">
        <h3 className="font-semibold text-ink">Fees</h3>
        <p className="text-sm text-ink-muted">As published by each source. “Unclear” means the source doesn&apos;t say.</p>
      </div>
      {fees.length === 0 ? (
        <p className="px-5 py-4 text-sm text-ink-muted">No fees were published by the sources we checked — that doesn&apos;t mean there are none.</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[40rem] text-sm">
            <caption className="sr-only">Fees by source</caption>
            <thead>
              <tr className="border-y border-line bg-surface-muted/60 text-left text-xs font-semibold uppercase tracking-wider text-ink-faint">
                <th scope="col" className="px-5 py-2">Fee</th>
                <th scope="col" className="px-3 py-2">Amount</th>
                <th scope="col" className="px-3 py-2">Required</th>
                <th scope="col" className="px-3 py-2">Recurring</th>
                <th scope="col" className="px-5 py-2">Source</th>
              </tr>
            </thead>
            <tbody>
              {fees.map((fee, index) => (
                <tr key={`${fee.fee_type}-${index}`} className="border-b border-line/70 last:border-b-0">
                  <td className="px-5 py-3">
                    <span className="block font-medium text-ink">{humanize(fee.fee_type)}</span>
                    <span className="block text-xs text-ink-muted">{fee.description}</span>
                  </td>
                  <td className="px-3 py-3 font-medium tabular-nums text-ink">{feeAmount(fee)}</td>
                  <td className="px-3 py-3">
                    <YesNoUnclear value={fee.mandatory} />
                  </td>
                  <td className="px-3 py-3">
                    <YesNoUnclear value={fee.recurring} />
                  </td>
                  <td className="px-5 py-3 text-xs">
                    <span className="block text-ink-muted">{fee.source_name}</span>
                    <ExternalLink href={fee.source_url}>{listingLinkLabel(fee.source_url, officialUrl)}</ExternalLink>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
