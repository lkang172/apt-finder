"use client";

import { useId, useState } from "react";
import type { RentRange } from "@/lib/browse";
import { formatMoney, formatMoneyRange } from "@/lib/format";

const STEP = 50;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

interface RentRangeFilterProps {
  bounds: RentRange;
  value: RentRange | null;
  onChange: (value: RentRange | null) => void;
}

export function RentRangeFilter({ bounds, value, onChange }: RentRangeFilterProps) {
  const range = value ?? bounds;
  const span = bounds.max - bounds.min;
  const percent = (rent: number) => (span === 0 ? 0 : ((rent - bounds.min) / span) * 100);

  function commit(next: RentRange) {
    const min = clamp(next.min, bounds.min, bounds.max);
    const max = clamp(next.max, bounds.min, bounds.max);
    const ordered = { min: Math.min(min, max), max: Math.max(min, max) };
    onChange(ordered.min === bounds.min && ordered.max === bounds.max ? null : ordered);
  }

  return (
    <div className="max-w-2xl space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm font-medium text-ink">Base rent of at least one qualifying unit</p>
        <p className="text-sm font-semibold tabular-nums text-ink">{formatMoneyRange(range.min, range.max)}</p>
      </div>

      {span > 0 && (
        <div className="relative h-8">
          <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-surface-muted ring-1 ring-inset ring-line" />
          <div
            className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-accent"
            style={{ left: `${percent(range.min)}%`, right: `${100 - percent(range.max)}%` }}
          />
          <input
            type="range"
            aria-label="Minimum base rent"
            aria-valuetext={formatMoney(range.min)}
            min={bounds.min}
            max={bounds.max}
            step={STEP}
            value={range.min}
            onChange={(event) => commit({ min: Math.min(Number(event.target.value), range.max), max: range.max })}
            className="range-thumb absolute inset-0 w-full"
            style={{ zIndex: range.min >= bounds.max - STEP ? 4 : 3 }}
          />
          <input
            type="range"
            aria-label="Maximum base rent"
            aria-valuetext={formatMoney(range.max)}
            min={bounds.min}
            max={bounds.max}
            step={STEP}
            value={range.max}
            onChange={(event) => commit({ min: range.min, max: Math.max(Number(event.target.value), range.min) })}
            className="range-thumb absolute inset-0 w-full"
          />
        </div>
      )}

      <div className="flex items-end gap-2">
        <MoneyInput
          label="Min"
          value={range.min}
          bounds={bounds}
          onCommit={(min) => commit({ min: Math.min(min, range.max), max: range.max })}
        />
        <span aria-hidden="true" className="pb-2.5 text-ink-faint">
          –
        </span>
        <MoneyInput
          label="Max"
          value={range.max}
          bounds={bounds}
          onCommit={(max) => commit({ min: range.min, max: Math.max(max, range.min) })}
        />
      </div>
      <p className="text-xs text-ink-faint">
        Allowed range {formatMoneyRange(bounds.min, bounds.max)} (the search&apos;s hard base-rent limits). A property matches
        only if one of its qualifying units is listed within your range.
      </p>
    </div>
  );
}

interface MoneyInputProps {
  label: string;
  value: number;
  bounds: RentRange;
  onCommit: (value: number) => void;
}

function MoneyInput({ label, value, bounds, onCommit }: MoneyInputProps) {
  const id = useId();
  const [draft, setDraft] = useState<string | null>(null);

  function commitDraft() {
    if (draft === null) return;
    const parsed = Number(draft.replace(/[^0-9.]/g, ""));
    if (draft.trim() !== "" && Number.isFinite(parsed)) onCommit(Math.round(parsed));
    setDraft(null);
  }

  return (
    <div className="flex flex-1 flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium text-ink-muted">
        {label} base rent
      </label>
      <div className="relative">
        <span aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-ink-faint">
          $
        </span>
        <input
          id={id}
          type="text"
          inputMode="numeric"
          value={draft ?? String(value)}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commitDraft}
          onKeyDown={(event) => {
            if (event.key === "Enter") commitDraft();
          }}
          aria-describedby={`${id}-hint`}
          className="h-10 w-full rounded-xl border border-line-strong bg-surface pl-6 pr-3 text-sm tabular-nums text-ink shadow-sm focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent"
        />
        <span id={`${id}-hint`} className="sr-only">
          Between {formatMoney(bounds.min)} and {formatMoney(bounds.max)}
        </span>
      </div>
    </div>
  );
}
