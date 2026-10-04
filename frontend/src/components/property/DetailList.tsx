import { scalarDetails } from "@/lib/evidence";
import { formatDetailValue, humanize } from "@/lib/format";

export function DetailList({ details, exclude = [] }: { details: Record<string, unknown>; exclude?: string[] }) {
  const entries = scalarDetails(details, exclude);
  if (entries.length === 0) return null;
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div key={key} className="flex justify-between gap-3 border-b border-line/70 py-1">
          <dt className="text-ink-muted">{humanize(key)}</dt>
          <dd className="text-right font-medium text-ink">{formatDetailValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}
