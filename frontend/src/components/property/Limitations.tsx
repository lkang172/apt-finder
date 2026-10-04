import { Badge } from "@/components/ui/Badge";
import { IconChevronDown } from "@/components/ui/icons";
import { humanize, pluralize } from "@/lib/format";
import { CATEGORY_LABEL, type Tone } from "@/lib/presentation";
import type { AuditNote } from "@/lib/types";

const SEVERITY_TONE: Record<AuditNote["severity"], Tone> = {
  error: "danger",
  warning: "warning",
  info: "neutral",
};

export function Limitations({ limitations, audit }: { limitations: string[]; audit: AuditNote[] }) {
  return (
    <div className="space-y-4 rounded-2xl border border-dashed border-line-strong bg-surface-muted/50 p-5 text-sm">
      {limitations.length > 0 ? (
        <ul className="list-disc space-y-1 pl-5 text-ink-muted">
          {limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      ) : (
        <p className="text-ink-muted">No data limitations were recorded for this property.</p>
      )}

      {audit.length > 0 && (
        <details className="group/audit border-t border-line pt-3">
          <summary className="inline-flex items-center gap-1 rounded font-medium text-ink hover:text-accent focus-visible:outline-2 focus-visible:outline-accent">
            Evidence audit log ({pluralize(audit.length, "note")})
            <IconChevronDown className="transition group-open/audit:rotate-180" />
          </summary>
          <ul className="mt-3 space-y-2.5">
            {audit.map((note, index) => (
              <li key={`${note.check_name}-${index}`} className="rounded-xl border border-line bg-surface p-3">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge tone={SEVERITY_TONE[note.severity]}>{humanize(note.severity)}</Badge>
                  <Badge>{note.category ? CATEGORY_LABEL[note.category] : "General"}</Badge>
                  <span className="font-medium text-ink">{humanize(note.check_name)}</span>
                </div>
                <p className="mt-1.5 text-ink-muted">{note.detail}</p>
                <p className="mt-1 text-xs text-ink-faint">Action taken: {note.action}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
