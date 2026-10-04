import { Badge, TONE_PANEL_CLASS } from "@/components/ui/Badge";
import { ConfidenceBadge } from "@/components/ui/ConfidenceBadge";
import { IconChevronDown } from "@/components/ui/icons";
import { ScoreValue } from "@/components/ui/ScoreValue";
import { scalarDetails, themeCounts, themeLabel, type ThemeLabels } from "@/lib/evidence";
import { pluralize } from "@/lib/format";
import { SCORECARD_ORDER, scoreTone } from "@/lib/presentation";
import type { AssessmentView, ClaimView } from "@/lib/types";
import { DetailList } from "./DetailList";
import { ClaimItem } from "./Evidence";

const BAR_CLASS = {
  positive: "bg-emerald-500",
  warning: "bg-amber-500",
  danger: "bg-rose-500",
  neutral: "bg-line-strong",
  info: "bg-sky-500",
  accent: "bg-accent",
};

const POLARITY_ORDER: Record<ClaimView["polarity"], number> = { negative: 0, positive: 1, neutral: 2 };

interface ScorecardProps {
  assessments: AssessmentView[];
  officialUrl: string | null;
  themeLabels: ThemeLabels;
  noReviews: boolean;
}

export function Scorecard({ assessments, officialUrl, themeLabels, noReviews }: ScorecardProps) {
  const rank = (assessment: AssessmentView) => {
    const position = SCORECARD_ORDER.indexOf(assessment.category);
    return position === -1 ? SCORECARD_ORDER.length : position;
  };
  const ordered = [...assessments].sort((a, b) => rank(a) - rank(b));

  return (
    <div className="space-y-3">
      {noReviews && (
        <p className="rounded-xl border border-line bg-surface-muted px-4 py-3 text-sm text-ink-muted">
          No reviews were found, so review-based categories (noise, management, pests, and most building issues) can&apos;t
          be scored. Missing reviews are never treated as a positive signal.
        </p>
      )}
      {ordered.map((assessment) => (
        <AssessmentRow
          key={assessment.category}
          assessment={assessment}
          officialUrl={officialUrl}
          themeLabels={themeLabels}
        />
      ))}
    </div>
  );
}

function AssessmentRow({
  assessment: a,
  officialUrl,
  themeLabels,
}: {
  assessment: AssessmentView;
  officialUrl: string | null;
  themeLabels: ThemeLabels;
}) {
  const counts = themeCounts(a.details);
  const claims = [...a.claims].sort(
    (x, y) => Number(y.is_current) - Number(x.is_current) || POLARITY_ORDER[x.polarity] - POLARITY_ORDER[y.polarity],
  );

  const hasDrillDown =
    claims.length > 0 || counts.length > 0 || scalarDetails(a.details, ["theme_counts"]).length > 0 || a.audit_status === "corrected";
  const overview = (
    <>
      <span className="flex flex-col items-start gap-1">
        <span className="font-semibold text-ink">{a.label}</span>
        <ConfidenceBadge confidence={a.confidence} />
      </span>
      <span className="flex flex-col items-end gap-1.5 sm:items-start">
        <ScoreValue score={a.score} size="md" />
        {a.score !== null && (
          <span className="block h-1.5 w-24 overflow-hidden rounded-full bg-surface-muted" aria-hidden="true">
            <span
              className={`block h-full rounded-full ${BAR_CLASS[scoreTone(a.score)]}`}
              style={{ width: `${Math.max(0, Math.min(10, a.score)) * 10}%` }}
            />
          </span>
        )}
      </span>
      <span className="col-span-2 text-sm text-ink-muted sm:col-span-1">{a.summary}</span>
    </>
  );
  const rowClass = "grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 rounded-2xl p-4 sm:grid-cols-[11rem_9rem_minmax(0,1fr)_auto]";

  if (!hasDrillDown) {
    return (
      <div id={`score-${a.category}`} className={`scroll-mt-28 border border-line bg-surface ${rowClass}`}>
        {overview}
        <span className="col-span-2 text-xs font-medium text-ink-faint sm:col-span-1 sm:text-right">
          {a.evidence_count === 0 ? "No evidence collected" : pluralize(a.evidence_count, "evidence item")}
        </span>
      </div>
    );
  }

  return (
    <details id={`score-${a.category}`} className="group/score scroll-mt-28 rounded-2xl border border-line bg-surface shadow-sm open:shadow-md">
      <summary
        className={`${rowClass} hover:bg-surface-muted/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent`}
      >
        {overview}
        <span className="col-span-2 flex items-center justify-between gap-2 text-xs font-medium text-ink-faint sm:col-span-1 sm:flex-col sm:items-end">
          <span>{pluralize(a.evidence_count, "evidence item")}</span>
          <span className="inline-flex items-center gap-1 text-accent">
            <span className="group-open/score:hidden">View evidence</span>
            <span className="hidden group-open/score:inline">Hide evidence</span>
            <IconChevronDown className="transition group-open/score:rotate-180" />
          </span>
        </span>
      </summary>

      <div className="space-y-4 border-t border-line p-4">
        {a.audit_status === "corrected" && (
          <p className={`rounded-xl border px-3 py-2 text-sm text-ink ${TONE_PANEL_CLASS.warning}`}>
            The evidence auditor corrected this assessment before display. Details are in “What we couldn&apos;t verify” below.
          </p>
        )}

        {counts.length > 0 && (
          <div>
            <p className="text-sm font-semibold text-ink">
              {pluralize(a.evidence_count, `${a.label.toLowerCase()}-related evidence item`)} analyzed
            </p>
            <ul className="mt-2 space-y-1.5">
              {counts.map(([theme, count]) => (
                <li key={theme} className="flex items-center gap-3 text-sm">
                  <span className="w-48 shrink-0 text-ink sm:w-64">
                    <span className="font-semibold tabular-nums">{count}</span> {count === 1 ? "mentions" : "mention"}{" "}
                    {lowerFirst(themeLabel(theme, themeLabels))}
                  </span>
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-muted" aria-hidden="true">
                    <span
                      className="block h-full rounded-full bg-accent/70"
                      style={{ width: `${(count / counts[0][1]) * 100}%` }}
                    />
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <DetailList details={a.details} exclude={["theme_counts"]} />

        {claims.length > 0 ? (
          <div>
            <p className="mb-2 text-sm font-semibold text-ink">Claims and supporting evidence</p>
            <ul className="space-y-3">
              {claims.map((claim) => (
                <ClaimItem key={claim.id} claim={claim} officialUrl={officialUrl} themeLabels={themeLabels} />
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-sm text-ink-muted">
            {a.score === null
              ? `No claims could be supported for ${a.label.toLowerCase()} — the evidence collected so far is insufficient.`
              : "No individual claims were recorded for this assessment."}
          </p>
        )}

        {a.score === null && <Badge>Not scored — missing evidence is never treated as a positive signal</Badge>}
      </div>
    </details>
  );
}

function lowerFirst(label: string): string {
  const [first = "", ...rest] = label.split(" ");
  const isAcronym = first.length > 1 && first === first.toUpperCase();
  return [isAcronym ? first : first.toLowerCase(), ...rest].join(" ");
}
