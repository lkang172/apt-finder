import { Badge } from "@/components/ui/Badge";
import { ExternalLink } from "@/components/ui/ExternalLink";
import { IconStar } from "@/components/ui/icons";
import { Timestamp } from "@/components/ui/Timestamp";
import { formatRating } from "@/lib/format";
import { evidenceKindLabel, evidenceSourceLink } from "@/lib/presentation";
import type { EvidenceItem } from "@/lib/types";

interface EvidenceCardProps {
  item: EvidenceItem;
  officialUrl: string | null;
}

export function EvidenceCard({ item, officialUrl }: EvidenceCardProps) {
  const link = evidenceSourceLink(item, officialUrl);
  const showTitle = item.title.trim() !== "" && item.title !== item.content;
  const isReview = item.kind === "review";

  return (
    <article className="rounded-xl border border-line bg-surface p-3.5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-faint">
        <Badge>{evidenceKindLabel(item.kind)}</Badge>
        <span className="font-semibold text-ink-muted">{item.source_name}</span>
        {item.rating !== null && (
          <span className="inline-flex items-center gap-0.5 font-medium text-amber-700 dark:text-amber-300">
            <IconStar />
            <span className="sr-only">Rating: </span>
            {formatRating(item.rating)}
          </span>
        )}
        {item.reviewer && <span>by {item.reviewer}</span>}
        {item.is_derived && <Badge tone="warning">Derived — computed, not quoted from a source</Badge>}
      </div>
      {showTitle && <p className="mt-2 text-sm font-semibold text-ink">{item.title}</p>}
      {isReview ? (
        <blockquote className="mt-2 border-l-2 border-line-strong pl-3 text-sm leading-relaxed text-ink">{item.content}</blockquote>
      ) : (
        <p className="mt-1.5 text-sm leading-relaxed text-ink">{item.content}</p>
      )}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 text-xs text-ink-faint">
        <p className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
          {item.published_at ? (
            <span>
              {isReview ? "Reviewed" : "Published"} <Timestamp iso={item.published_at} dateOnly className="font-medium text-ink-muted" />
            </span>
          ) : (
            isReview && <span>Review date unknown</span>
          )}
          {item.age_label && <Badge>{item.age_label}</Badge>}
          <span>
            · Collected <Timestamp iso={item.collected_at} />
          </span>
        </p>
        <ExternalLink href={link.url} className="shrink-0">
          {link.label}
        </ExternalLink>
      </div>
      {link.note && <p className="mt-1 text-[11px] text-ink-faint sm:text-right">{link.note}</p>}
    </article>
  );
}
