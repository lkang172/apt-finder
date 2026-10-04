import { Badge } from "@/components/ui/Badge";
import { ConfidenceBadge } from "@/components/ui/ConfidenceBadge";
import { ScoreValue } from "@/components/ui/ScoreValue";
import { Card } from "@/components/ui/Section";
import { formatPercent, formatScore } from "@/lib/format";
import type { OverallView } from "@/lib/types";

export function OverallBreakdown({ overall }: { overall: OverallView }) {
  return (
    <Card className="space-y-6">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-faint">Overall score</p>
          <ScoreValue score={overall.score} size="lg" />
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-faint">Overall confidence</p>
          <ConfidenceBadge confidence={overall.confidence} className="mt-1 text-sm" />
        </div>
        <p className="basis-full text-sm text-ink-muted sm:basis-auto sm:flex-1">
          Calculated programmatically from the category scores below. Categories without enough evidence are excluded and the
          remaining weights are renormalized — they are never counted as neutral or positive.
        </p>
      </div>

      {overall.components.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] text-sm">
            <caption className="sr-only">Overall score components and weights</caption>
            <thead>
              <tr className="border-b border-line text-left text-xs font-semibold uppercase tracking-wider text-ink-faint">
                <th scope="col" className="py-2 pr-3">Category</th>
                <th scope="col" className="py-2 pr-3">Score</th>
                <th scope="col" className="py-2 pr-3">Confidence</th>
                <th scope="col" className="py-2 pr-3 text-right">Base weight</th>
                <th scope="col" className="py-2">Effective weight</th>
              </tr>
            </thead>
            <tbody>
              {overall.components.map((component) => (
                <tr key={component.category} className="border-b border-line/70">
                  <th scope="row" className="py-2.5 pr-3 text-left font-medium text-ink">
                    {component.label}
                  </th>
                  <td className="py-2.5 pr-3 font-semibold tabular-nums text-ink">{formatScore(component.score)}/10</td>
                  <td className="py-2.5 pr-3">
                    <ConfidenceBadge confidence={component.confidence} />
                  </td>
                  <td className="py-2.5 pr-3 text-right tabular-nums text-ink-muted">{formatPercent(component.base_weight)}</td>
                  <td className="py-2.5">
                    <span className="flex items-center gap-2">
                      <span className="w-10 text-right font-medium tabular-nums text-ink">
                        {formatPercent(component.effective_weight)}
                      </span>
                      <span className="h-1.5 w-full max-w-40 overflow-hidden rounded-full bg-surface-muted" aria-hidden="true">
                        <span
                          className="block h-full rounded-full bg-accent"
                          style={{ width: `${Math.min(1, component.effective_weight) * 100}%` }}
                        />
                      </span>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-ink-muted">No category had enough evidence to contribute to an overall score.</p>
      )}

      {overall.excluded_categories.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-ink">Excluded from the overall score</h3>
          <ul className="mt-2 space-y-1.5 text-sm">
            {overall.excluded_categories.map((excluded) => (
              <li key={excluded.category} className="flex flex-wrap items-start gap-2">
                <Badge>{excluded.label}</Badge>
                <span className="text-ink-muted">{excluded.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <h3 className="text-sm font-semibold text-ink">Why confidence was reduced</h3>
        {overall.confidence_reasons.length > 0 ? (
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-muted">
            {overall.confidence_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-sm text-ink-muted">No confidence reductions were recorded.</p>
        )}
      </div>
    </Card>
  );
}
