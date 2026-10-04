import { ConfidenceBadge } from "@/components/ui/ConfidenceBadge";
import { ExternalLink } from "@/components/ui/ExternalLink";
import { Card } from "@/components/ui/Section";
import { Timestamp } from "@/components/ui/Timestamp";
import { formatMiles, formatMinutes } from "@/lib/format";
import type { CommuteView } from "@/lib/types";

interface CommutePanelProps {
  commute: CommuteView | null;
  officeLabel: string | null;
}

export function CommutePanel({ commute, officeLabel }: CommutePanelProps) {
  if (!commute) {
    return (
      <Card>
        <p className="text-sm text-ink-muted">
          Commute data is unavailable for this property — it hasn&apos;t been computed, or its location couldn&apos;t be
          verified. No estimate is shown rather than a guess.
        </p>
      </Card>
    );
  }

  return (
    <Card className="space-y-5">
      {officeLabel && (
        <p className="text-sm text-ink-muted">
          Driving to <span className="font-medium text-ink">{officeLabel}</span>
        </p>
      )}
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <CommuteStat label="Distance" value={commute.distance_miles === null ? null : formatMiles(commute.distance_miles)} />
        <CommuteStat
          label="Normal drive"
          caption="Free-flow, no traffic"
          value={commute.free_flow_minutes === null ? null : formatMinutes(commute.free_flow_minutes)}
        />
        <CommuteStat
          label="Weekday AM rush"
          value={commute.am_rush_minutes === null ? null : formatMinutes(commute.am_rush_minutes)}
          unavailableText={commute.rush_status}
        />
        <CommuteStat
          label="Weekday PM rush"
          value={commute.pm_rush_minutes === null ? null : formatMinutes(commute.pm_rush_minutes)}
          unavailableText={commute.rush_status}
        />
      </dl>

      <dl className="grid grid-cols-1 gap-x-6 gap-y-3 border-t border-line pt-4 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs font-medium text-ink-faint">Methodology</dt>
          <dd className="text-ink">{commute.methodology}</dd>
        </div>
        <div className="space-y-2">
          <div>
            <dt className="text-xs font-medium text-ink-faint">Provider</dt>
            <dd className="text-ink">{commute.provider}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-ink-faint">Computed</dt>
            <dd className="text-ink">
              <Timestamp iso={commute.computed_at} />
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-ink-faint">Confidence</dt>
            <dd>
              <ConfidenceBadge confidence={commute.confidence} />
            </dd>
          </div>
        </div>
      </dl>

      <div className="flex flex-wrap items-start gap-x-5 gap-y-3 border-t border-line pt-4 text-sm">
        <ExternalLink href={commute.source_url} variant="button">
          View Commute Source
        </ExternalLink>
        <ExternalLink href={commute.view_url} variant="button" unavailableText="Route map unavailable">
          View route map
        </ExternalLink>
        {commute.live_traffic_url && (
          <span className="flex flex-col gap-0.5">
            <ExternalLink href={commute.live_traffic_url} variant="button">
              Check live traffic on Google Maps
            </ExternalLink>
            <span className="text-xs text-ink-faint">Convenience link for checking traffic yourself — not evidence.</span>
          </span>
        )}
      </div>
    </Card>
  );
}

interface CommuteStatProps {
  label: string;
  value: string | null;
  caption?: string;
  unavailableText?: string;
}

function CommuteStat({ label, value, caption, unavailableText = "Unavailable" }: CommuteStatProps) {
  return (
    <div className="rounded-xl bg-surface-muted p-3">
      <dt className="text-xs font-medium text-ink-faint">{label}</dt>
      <dd>
        {value === null ? (
          <span className="mt-1 block text-sm font-medium text-ink-muted">{unavailableText}</span>
        ) : (
          <span className="block text-2xl font-bold tabular-nums text-ink">{value}</span>
        )}
        {caption && <span className="block text-xs text-ink-faint">{caption}</span>}
      </dd>
    </div>
  );
}
