import { ExternalLink } from "@/components/ui/ExternalLink";
import { Card } from "@/components/ui/Section";
import { Timestamp } from "@/components/ui/Timestamp";
import { evidenceSourceLink } from "@/lib/presentation";
import type { EvidenceItem } from "@/lib/types";

export function ListingFacts({ facts, officialUrl }: { facts: EvidenceItem[]; officialUrl: string | null }) {
  if (facts.length === 0) {
    return (
      <Card>
        <p className="text-sm text-ink-muted">No listing facts (amenities, parking, pets, lease terms, utilities) were collected.</p>
      </Card>
    );
  }

  const sorted = [...facts].sort((a, b) => a.title.localeCompare(b.title));
  return (
    <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {sorted.map((fact) => {
        const link = evidenceSourceLink(fact, officialUrl);
        return (
          <li key={fact.id} className="flex flex-col rounded-2xl border border-line bg-surface p-4 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-wider text-ink-faint">{fact.title}</p>
            <p className="mt-1 flex-1 text-sm text-ink">{fact.content}</p>
            <div className="mt-3 flex flex-wrap items-end justify-between gap-2 text-xs text-ink-faint">
              <span>
                <span className="block font-medium text-ink-muted">{fact.source_name}</span>
                Collected <Timestamp iso={fact.collected_at} />
                {fact.is_derived && <span className="block">Derived — computed, not quoted</span>}
              </span>
              <ExternalLink href={link.url} className="shrink-0">
                {link.label}
              </ExternalLink>
            </div>
            {link.note && <p className="mt-1 text-[11px] text-ink-faint sm:text-right">{link.note}</p>}
          </li>
        );
      })}
    </ul>
  );
}
