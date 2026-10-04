import { Badge } from "@/components/ui/Badge";
import { IconAlert, IconMinus, IconPlus } from "@/components/ui/icons";
import { themeLabel, type EvidenceIndex, type ThemeLabels } from "@/lib/evidence";
import { pluralize } from "@/lib/format";
import type { ClaimView, EvidenceItem } from "@/lib/types";
import { EvidenceCard } from "./EvidenceCard";
import { MissingEvidence } from "./MissingEvidence";

interface EvidenceListProps {
  items: EvidenceItem[];
  officialUrl: string | null;
  initialCount?: number;
  moreLabel?: (remaining: number) => string;
}

export function EvidenceList({
  items,
  officialUrl,
  initialCount = 1,
  moreLabel = (remaining) => `Show ${pluralize(remaining, "more evidence item")}`,
}: EvidenceListProps) {
  const shown = items.slice(0, initialCount);
  const rest = items.slice(initialCount);
  return (
    <div className="space-y-2">
      {shown.map((item) => (
        <EvidenceCard key={item.id} item={item} officialUrl={officialUrl} />
      ))}
      {rest.length > 0 && (
        <details className="group/more">
          <summary className="inline-flex rounded-lg px-2 py-1 text-sm font-medium text-accent hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-accent">
            <span className="group-open/more:hidden">{moreLabel(rest.length)}</span>
            <span className="hidden group-open/more:inline">Show fewer</span>
          </summary>
          <div className="mt-2 space-y-2">
            {rest.map((item) => (
              <EvidenceCard key={item.id} item={item} officialUrl={officialUrl} />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

interface EvidenceRefsProps {
  ids: string[];
  index: EvidenceIndex;
  officialUrl: string | null;
  initialCount?: number;
}

export function EvidenceRefs({ ids, index, officialUrl, initialCount }: EvidenceRefsProps) {
  const resolved = ids.flatMap((id) => (index[id] ? [index[id]] : []));
  const missing = ids.filter((id) => !index[id]);
  return (
    <div className="space-y-2">
      <EvidenceList items={resolved} officialUrl={officialUrl} initialCount={initialCount} />
      {missing.map((id) => (
        <MissingEvidence key={id} id={id} officialUrl={officialUrl} />
      ))}
    </div>
  );
}

const POLARITY_STYLE = {
  positive: {
    icon: IconPlus,
    label: "Positive",
    className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-300",
  },
  negative: {
    icon: IconAlert,
    label: "Negative",
    className: "bg-rose-100 text-rose-800 dark:bg-rose-400/15 dark:text-rose-300",
  },
  neutral: {
    icon: IconMinus,
    label: "Neutral",
    className: "bg-surface-muted text-ink-muted",
  },
} as const;

interface ClaimItemProps {
  claim: ClaimView;
  officialUrl: string | null;
  themeLabels: ThemeLabels;
}

export function ClaimItem({ claim, officialUrl, themeLabels }: ClaimItemProps) {
  const polarity = POLARITY_STYLE[claim.polarity];
  const PolarityIcon = polarity.icon;
  return (
    <li id={`claim-${claim.id}`} className="scroll-mt-28 rounded-2xl border border-line bg-surface-muted/50 p-3.5">
      <div className="flex items-start gap-2.5">
        <span className={`mt-0.5 grid size-6 shrink-0 place-items-center rounded-full text-sm ${polarity.className}`}>
          <PolarityIcon />
          <span className="sr-only">{polarity.label} claim:</span>
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-ink">{claim.text}</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {claim.theme && <Badge>{themeLabel(claim.theme, themeLabels)}</Badge>}
            {!claim.is_current && <Badge tone="warning">Older evidence — may not reflect current conditions</Badge>}
            <span className="text-xs text-ink-faint">{pluralize(claim.evidence.length, "evidence item")}</span>
          </div>
        </div>
      </div>
      <div className="mt-3">
        {claim.evidence.length > 0 ? (
          <EvidenceList items={claim.evidence} officialUrl={officialUrl} />
        ) : (
          <Badge tone="danger">No linked evidence — treat this claim as unverified</Badge>
        )}
      </div>
    </li>
  );
}
