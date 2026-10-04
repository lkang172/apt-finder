import { Badge, TONE_PANEL_CLASS } from "./ui/Badge";
import { IconAlert } from "./ui/icons";

const RESTRICTION_HINT = "Age or income requirements may apply";

export function EligibilityBadge({ notes, overImage = false }: { notes: string[]; overImage?: boolean }) {
  if (notes.length === 0) return null;
  return (
    <Badge tone="warning" title={`Eligibility restrictions — ${RESTRICTION_HINT.toLowerCase()}`} className={overImage ? "shadow-sm" : ""}>
      <IconAlert />
      <span className="sr-only">Eligibility restrictions: </span>
      {notes.join(" · ")}
    </Badge>
  );
}

export function EligibilityCallout({ notes }: { notes: string[] }) {
  if (notes.length === 0) return null;
  return (
    <div role="note" className={`flex gap-3 rounded-2xl border-2 p-4 ${TONE_PANEL_CLASS.warning}`}>
      <IconAlert className="mt-0.5 shrink-0 text-xl text-amber-700 dark:text-amber-300" />
      <div>
        <p className="font-semibold text-ink">Eligibility restrictions: {notes.join(" · ")}</p>
        <p className="mt-0.5 text-sm text-ink-muted">
          {RESTRICTION_HINT}. Confirm with the property that you qualify before applying.
        </p>
      </div>
    </div>
  );
}
