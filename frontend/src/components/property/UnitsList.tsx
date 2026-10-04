import { Badge } from "@/components/ui/Badge";
import { ExternalLink } from "@/components/ui/ExternalLink";
import { IconTag } from "@/components/ui/icons";
import { Timestamp } from "@/components/ui/Timestamp";
import { bedsLabel, formatCalendarDate, formatMoney, formatMoneyRange, formatSqftRange, pluralize } from "@/lib/format";
import { listingLinkLabel } from "@/lib/presentation";
import type { UnitView } from "@/lib/types";

interface UnitsListProps {
  units: UnitView[];
  officialUrl: string | null;
}

export function UnitsList({ units, officialUrl }: UnitsListProps) {
  const qualifying = units.filter((unit) => unit.qualifies);
  const others = units.filter((unit) => !unit.qualifies);

  if (units.length === 0) {
    return <p className="text-sm text-ink-muted">No unit-level listings were collected for this property.</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="mb-2 text-sm font-semibold text-ink">
          Qualifying units <span className="font-normal text-ink-muted">({qualifying.length})</span>
        </h3>
        {qualifying.length > 0 ? (
          <ul className="space-y-3">
            {qualifying.map((unit) => (
              <UnitRow key={unit.id} unit={unit} officialUrl={officialUrl} />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-ink-muted">No unit currently meets every search criterion with fresh pricing.</p>
        )}
      </div>
      {others.length > 0 && (
        <details className="group/units">
          <summary className="inline-flex rounded-lg px-2 py-1 text-sm font-medium text-accent hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-accent">
            <span className="group-open/units:hidden">
              Show {pluralize(others.length, "other unit")} seen (outside search criteria or stale)
            </span>
            <span className="hidden group-open/units:inline">Hide other units</span>
          </summary>
          <ul className="mt-3 space-y-3 opacity-90">
            {others.map((unit) => (
              <UnitRow key={unit.id} unit={unit} officialUrl={officialUrl} />
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function unitTitle(unit: UnitView): string {
  if (unit.label) return `Unit ${unit.label}`;
  if (unit.floorplan_name) return unit.floorplan_name;
  return unit.kind === "floorplan" ? "Floor plan (unnamed)" : "Unit (number not published)";
}

function availabilityText(unit: UnitView): string {
  if (unit.available_on) return formatCalendarDate(unit.available_on);
  return unit.availability ?? "Not stated";
}

function UnitRow({ unit, officialUrl }: { unit: UnitView; officialUrl: string | null }) {
  const specs = [
    bedsLabel(unit.beds),
    unit.baths === null ? null : `${unit.baths} ba`,
    formatSqftRange(unit.sqft_min, unit.sqft_max),
  ].filter(Boolean);

  return (
    <li
      className={`rounded-2xl border bg-surface p-4 shadow-sm ${unit.qualifies ? "border-line" : "border-dashed border-line-strong"}`}
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.2fr)]">
        <div>
          <p className="font-semibold text-ink">{unitTitle(unit)}</p>
          {unit.label && unit.floorplan_name && <p className="text-xs text-ink-muted">{unit.floorplan_name}</p>}
          <p className="mt-0.5 text-sm text-ink-muted">{specs.join(" · ")}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {unit.qualifies ? <Badge tone="positive">Qualifies</Badge> : <Badge>Doesn&apos;t qualify</Badge>}
            {unit.kind === "floorplan" && <Badge>Floor plan pricing</Badge>}
          </div>
        </div>

        <dl className="space-y-1 text-sm">
          <div>
            <dt className="text-xs text-ink-faint">Base rent</dt>
            <dd className="text-lg font-bold tabular-nums text-ink">
              {formatMoneyRange(unit.base_rent_min, unit.base_rent_max) ?? "Not published"}
            </dd>
          </div>
          <div className="flex justify-between gap-2 sm:block">
            <dt className="text-xs text-ink-faint">Published total</dt>
            <dd className="tabular-nums text-ink">{unit.total_monthly === null ? "Not published" : formatMoney(unit.total_monthly)}</dd>
          </div>
          <div className="flex justify-between gap-2 sm:block">
            <dt className="text-xs text-ink-faint">Required fees</dt>
            <dd className="tabular-nums text-ink">
              {unit.required_fees_monthly === null ? "Unknown" : `${formatMoney(unit.required_fees_monthly)}/mo`}
            </dd>
          </div>
        </dl>

        <dl className="space-y-1 text-sm">
          <div className="flex justify-between gap-2 sm:block">
            <dt className="text-xs text-ink-faint">Lease term</dt>
            <dd className="text-ink">{unit.lease_term_months === null ? "Not stated" : `${unit.lease_term_months} months`}</dd>
          </div>
          <div className="flex justify-between gap-2 sm:block">
            <dt className="text-xs text-ink-faint">Available</dt>
            <dd className="text-ink">{availabilityText(unit)}</dd>
          </div>
        </dl>

        <div className="space-y-1.5 text-sm">
          <p className="flex flex-wrap items-center gap-1.5">
            {unit.fresh ? <Badge tone="positive">Fresh</Badge> : <Badge tone="warning">Stale</Badge>}
            <span className="text-xs text-ink-faint">
              Collected <Timestamp iso={unit.collected_at} />
            </span>
          </p>
          {unit.source_updated_at && (
            <p className="text-xs text-ink-faint">
              Source updated <Timestamp iso={unit.source_updated_at} />
            </p>
          )}
          <p className="text-xs">
            <span className="block text-ink-muted">{unit.source_name}</span>
            <ExternalLink href={unit.source_url}>{listingLinkLabel(unit.source_url, officialUrl)}</ExternalLink>
          </p>
        </div>
      </div>

      {unit.is_promotional && (
        <div className="mt-3 rounded-xl border border-accent/30 bg-accent-soft p-3 text-sm">
          <p className="flex items-center gap-1.5 font-semibold text-ink">
            <IconTag className="text-accent" /> Promotional pricing
          </p>
          {unit.promotion_text && <p className="mt-0.5 text-ink">{unit.promotion_text}</p>}
          {unit.effective_rent_estimate !== null && (
            <p className="mt-1.5 text-ink-muted">
              Effective rent estimate:{" "}
              <span className="font-semibold tabular-nums text-ink">{formatMoney(unit.effective_rent_estimate)}/mo</span>{" "}
              <Badge tone="warning">Derived — not a quoted price</Badge>
              {unit.effective_rent_method && <span className="mt-1 block text-xs">Method: {unit.effective_rent_method}</span>}
            </p>
          )}
          <p className="mt-1.5 text-xs text-ink-muted">Promotional/effective rent is not equivalent to a normal lease at that price.</p>
        </div>
      )}
    </li>
  );
}
