"use client";

import { useId, type ReactNode } from "react";
import { IconGrid, IconMap, IconSearch, IconSliders, IconSort } from "@/components/ui/icons";
import {
  SCORE_FILTER_CATEGORIES,
  SORT_OPTIONS,
  type BrowseFilters,
  type SortDirection,
  type SortKey,
} from "@/lib/browse";
import { formatMoney } from "@/lib/format";
import { CATEGORY_LABEL, CONFIDENCE_LABEL, UNIT_TYPE_LABEL } from "@/lib/presentation";
import type { Confidence, UnitType } from "@/lib/types";

export type ViewMode = "grid" | "map";

const MAX_TOTAL_OPTIONS = [2600, 2700, 2800, 2900, 3000, 3100, 3200, 3400, 3600];
const MAX_COMMUTE_OPTIONS = [10, 15, 20, 25, 30, 40];
const MIN_SCORE_OPTIONS = [5, 6, 7, 8, 9];
const MIN_RATING_OPTIONS = [3, 3.5, 4, 4.5];
const CONFIDENCE_OPTIONS: Confidence[] = ["low", "medium", "high"];
const UNIT_TYPES: UnitType[] = ["studio", "1br"];

const CONTROL_CLASS =
  "h-10 rounded-xl border border-line-strong bg-surface px-3 text-sm text-ink shadow-sm focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent";

interface FilterBarProps {
  filters: BrowseFilters;
  onFiltersChange: (filters: BrowseFilters) => void;
  cities: string[];
  sortKey: SortKey;
  sortDirection: SortDirection;
  onSortChange: (key: SortKey, direction: SortDirection) => void;
  view: ViewMode;
  onViewChange: (view: ViewMode) => void;
  moreOpen: boolean;
  onMoreOpenChange: (open: boolean) => void;
  activeFilterCount: number;
  onClear: () => void;
}

export function FilterBar({
  filters,
  onFiltersChange,
  cities,
  sortKey,
  sortDirection,
  onSortChange,
  view,
  onViewChange,
  moreOpen,
  onMoreOpenChange,
  activeFilterCount,
  onClear,
}: FilterBarProps) {
  const searchId = useId();
  const cityId = useId();
  const sortId = useId();
  const panelId = useId();
  const update = (patch: Partial<BrowseFilters>) => onFiltersChange({ ...filters, ...patch });

  function toggleUnitType(type: UnitType) {
    const unitTypes = filters.unitTypes.includes(type)
      ? filters.unitTypes.filter((existing) => existing !== type)
      : [...filters.unitTypes, type];
    update({ unitTypes });
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[12rem] flex-1">
          <label htmlFor={searchId} className="sr-only">
            Search by name, city, or address
          </label>
          <IconSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" />
          <input
            id={searchId}
            type="search"
            value={filters.query}
            onChange={(event) => update({ query: event.target.value })}
            placeholder="Search name, city, or address"
            className={`${CONTROL_CLASS} w-full pl-9`}
          />
        </div>

        <label htmlFor={cityId} className="sr-only">
          City
        </label>
        <select id={cityId} value={filters.city} onChange={(event) => update({ city: event.target.value })} className={CONTROL_CLASS}>
          <option value="">All cities</option>
          {cities.map((city) => (
            <option key={city} value={city}>
              {city}
            </option>
          ))}
        </select>

        <div role="group" aria-label="Unit type" className="flex gap-1">
          {UNIT_TYPES.map((type) => {
            const pressed = filters.unitTypes.includes(type);
            return (
              <button
                key={type}
                type="button"
                aria-pressed={pressed}
                onClick={() => toggleUnitType(type)}
                className={`h-10 rounded-xl border px-3.5 text-sm font-medium shadow-sm transition focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent ${
                  pressed ? "border-accent bg-accent text-accent-ink" : "border-line-strong bg-surface text-ink hover:border-accent"
                }`}
              >
                {UNIT_TYPE_LABEL[type]}
              </button>
            );
          })}
        </div>

        <button
          type="button"
          aria-expanded={moreOpen}
          aria-controls={panelId}
          onClick={() => onMoreOpenChange(!moreOpen)}
          className={`${CONTROL_CLASS} inline-flex items-center gap-2 font-medium ${moreOpen ? "border-accent text-accent" : ""}`}
        >
          <IconSliders />
          Filters
          {activeFilterCount > 0 && (
            <span className="grid min-w-5 place-items-center rounded-full bg-accent px-1.5 text-xs font-semibold text-accent-ink">
              {activeFilterCount}
            </span>
          )}
        </button>

        <div className="flex items-center gap-1">
          <label htmlFor={sortId} className="sr-only">
            Sort by
          </label>
          <select
            id={sortId}
            value={sortKey}
            onChange={(event) => {
              const option = SORT_OPTIONS.find((candidate) => candidate.key === event.target.value);
              if (option) onSortChange(option.key, option.defaultDirection);
            }}
            className={CONTROL_CLASS}
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.key} value={option.key}>
                Sort: {option.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => onSortChange(sortKey, sortDirection === "asc" ? "desc" : "asc")}
            aria-label={`Sort direction: ${sortDirection === "asc" ? "ascending" : "descending"}. Click to reverse.`}
            title="Reverse sort direction (N/A values always stay last)"
            className={`${CONTROL_CLASS} inline-flex items-center gap-1 font-medium`}
          >
            <IconSort />
            <span aria-hidden="true">{sortDirection === "asc" ? "Low → High" : "High → Low"}</span>
          </button>
        </div>

        <div role="group" aria-label="View" className="flex rounded-xl border border-line-strong bg-surface p-0.5 shadow-sm">
          <ViewButton active={view === "grid"} onClick={() => onViewChange("grid")} icon={<IconGrid />} label="Grid" />
          <ViewButton active={view === "map"} onClick={() => onViewChange("map")} icon={<IconMap />} label="Map" />
        </div>
      </div>

      <div id={panelId} hidden={!moreOpen} className="rounded-2xl border border-line bg-surface p-4 shadow-sm">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <NumberSelect
            label="Max est. monthly total"
            value={filters.maxMonthlyTotal}
            options={MAX_TOTAL_OPTIONS}
            format={formatMoney}
            onChange={(maxMonthlyTotal) => update({ maxMonthlyTotal })}
          />
          <NumberSelect
            label="Max commute (no traffic)"
            value={filters.maxCommuteMinutes}
            options={MAX_COMMUTE_OPTIONS}
            format={(minutes) => `${minutes} min`}
            onChange={(maxCommuteMinutes) => update({ maxCommuteMinutes })}
          />
          <NumberSelect
            label="Min overall score"
            value={filters.minOverall}
            options={MIN_SCORE_OPTIONS}
            format={(score) => `${score}+`}
            onChange={(minOverall) => update({ minOverall })}
          />
          <NumberSelect
            label="Min rating (Google when available)"
            value={filters.minReviewRating}
            options={MIN_RATING_OPTIONS}
            format={(rating) => `${rating.toFixed(1)}+ / 5`}
            onChange={(minReviewRating) => update({ minReviewRating })}
          />
          {SCORE_FILTER_CATEGORIES.map((category) => (
            <NumberSelect
              key={category}
              label={`Min ${CATEGORY_LABEL[category].toLowerCase()} score`}
              value={filters.minCategoryScore[category] ?? null}
              options={MIN_SCORE_OPTIONS}
              format={(score) => `${score}+`}
              onChange={(score) =>
                update({ minCategoryScore: { ...filters.minCategoryScore, [category]: score ?? undefined } })
              }
            />
          ))}
          <ConfidenceSelect value={filters.minConfidence} onChange={(minConfidence) => update({ minConfidence })} />
          <label className="flex items-center gap-2 self-end pb-2.5 text-sm text-ink">
            <input
              type="checkbox"
              checked={filters.hideEligibilityRestricted}
              onChange={(event) => update({ hideEligibilityRestricted: event.target.checked })}
              className="size-4 accent-[var(--accent)]"
            />
            Hide age- or income-restricted housing
          </label>
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3">
          <p className="text-xs text-ink-faint">
            Minimum-score, rating, price, and commute filters hide properties where that value is N/A or unknown — missing
            evidence never counts as a pass.
          </p>
          <button
            type="button"
            onClick={onClear}
            disabled={activeFilterCount === 0}
            className="rounded-lg px-3 py-1.5 text-sm font-medium text-accent hover:bg-accent-soft disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-accent"
          >
            Clear all filters
          </button>
        </div>
      </div>
    </div>
  );
}

function ViewButton({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: ReactNode; label: string }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`inline-flex h-9 items-center gap-1.5 rounded-[10px] px-3 text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-accent ${
        active ? "bg-ink text-bg" : "text-ink-muted hover:text-ink"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

interface NumberSelectProps {
  label: string;
  value: number | null;
  options: number[];
  format: (value: number) => string;
  onChange: (value: number | null) => void;
}

function NumberSelect({ label, value, options, format, onChange }: NumberSelectProps) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium text-ink-muted">
        {label}
      </label>
      <select
        id={id}
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value === "" ? null : Number(event.target.value))}
        className={CONTROL_CLASS}
      >
        <option value="">Any</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {format(option)}
          </option>
        ))}
      </select>
    </div>
  );
}

function ConfidenceSelect({ value, onChange }: { value: Confidence | null; onChange: (value: Confidence | null) => void }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium text-ink-muted">
        Min overall confidence
      </label>
      <select
        id={id}
        value={value ?? ""}
        onChange={(event) => onChange(CONFIDENCE_OPTIONS.find((option) => option === event.target.value) ?? null)}
        className={CONTROL_CLASS}
      >
        <option value="">Any</option>
        {CONFIDENCE_OPTIONS.map((option) => (
          <option key={option} value={option}>
            {CONFIDENCE_LABEL[option]}
            {option !== "high" && " or better"}
          </option>
        ))}
      </select>
    </div>
  );
}
