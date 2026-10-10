"use client";

import { useId } from "react";
import { IconStar } from "@/components/ui/icons";
import { GOOGLE_STARS_OPTIONS, googleStarsLabel } from "@/lib/browse";

interface GoogleStarsFilterProps {
  value: number | null;
  includeUnrated: boolean;
  onChange: (value: number | null) => void;
  onIncludeUnratedChange: (value: boolean) => void;
}

const OPTIONS: (number | null)[] = [null, ...GOOGLE_STARS_OPTIONS];

export function GoogleStarsFilter({ value, includeUnrated, onChange, onIncludeUnratedChange }: GoogleStarsFilterProps) {
  const name = useId();
  const labelId = useId();

  return (
    <div className="max-w-2xl space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p id={labelId} className="text-sm font-medium text-ink">
          Minimum Google Maps rating
        </p>
        <p className="text-sm font-semibold tabular-nums text-ink">
          {value === null ? "Any rating" : `${googleStarsLabel(value)} stars`}
        </p>
      </div>

      <div role="radiogroup" aria-labelledby={labelId} className="flex flex-wrap gap-1.5">
        {OPTIONS.map((option) => {
          const checked = option === value;
          return (
            <label
              key={option ?? "any"}
              className={`inline-flex h-10 cursor-pointer items-center gap-1 rounded-xl border px-3.5 text-sm font-medium tabular-nums shadow-sm transition has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-1 has-[:focus-visible]:outline-accent ${
                checked ? "border-accent bg-accent text-accent-ink" : "border-line-strong bg-surface text-ink hover:border-accent"
              }`}
            >
              <input
                type="radio"
                name={name}
                value={option ?? ""}
                checked={checked}
                onChange={() => onChange(option)}
                className="sr-only"
              />
              {option !== null && <IconStar className={checked ? "" : "text-amber-500"} />}
              {googleStarsLabel(option)}
            </label>
          );
        })}
      </div>

      <label className="flex items-center gap-2 text-sm text-ink">
        <input
          type="checkbox"
          checked={includeUnrated}
          onChange={(event) => onIncludeUnratedChange(event.target.checked)}
          className="size-4 accent-[var(--accent)]"
        />
        Include unrated
      </label>

      <p className="text-xs text-ink-faint">
        Uses the Google Maps rating only. With a minimum set, properties without a Google rating (no confident match, not
        checked, or no Google reviews yet) stay visible only while “Include unrated” is checked. Ratings below 3.0 are
        flagged on cards — never excluded.
      </p>
    </div>
  );
}
