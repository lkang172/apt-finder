"use client";

import { useId, useState, type ReactNode } from "react";
import { IconChevronDown, IconGrid, IconMap, IconSearch, IconSliders, IconSort, IconStar } from "@/components/ui/icons";
import {
  googleStarsLabel,
  monthlyTotalOptions,
  SCORE_FILTER_CATEGORIES,
  SORT_OPTIONS,
  type BrowseFilters,
  type RentRange,
  type SortDirection,
  type SortKey,
} from "@/lib/browse";
import { formatMoney, formatMoneyRange } from "@/lib/format";
import { CATEGORY_LABEL, CONFIDENCE_LABEL, UNIT_TYPE_LABEL } from "@/lib/presentation";
import type { Confidence, UnitType } from "@/lib/types";
import { GoogleStarsFilter } from "./GoogleStarsFilter";
import { RentRangeFilter } from "./RentRangeFilter";

export type ViewMode = "grid" | "map";

const MAX_COMMUTE_OPTIONS = [10, 15, 20, 25, 30, 40];
const MIN_SCORE_OPTIONS = [5, 6, 7, 8, 9];
const CONFIDENCE_OPTIONS: Confidence[] = ["low", "medium", "high"];
const UNIT_TYPES: UnitType[] = ["studio", "1br"];

const CONTROL_CLASS =
  "h-10 rounded-xl border border-line-strong bg-surface px-3 text-sm text-ink shadow-sm focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent";

interface FilterBarProps {
  filters: BrowseFilters;
  onFiltersChange: (filters: BrowseFilters) => void;
  cities: string[];
  rentBounds: RentRange | null;
  sortKey: SortKey;
  sortDirection: SortDirection;
  onSortChange: (key: SortKey, direction: SortDirection) => void;
  moreOpen: boolean;
  onMoreOpenChange: (open: boolean) => void;
  activeFilterCount: number;
  onClear: () => void;
}

export function FilterBar({
  filters,
  onFiltersChange,
  cities,
  rentBounds,
  sortKey,
  sortDirection,
  onSortChange,
  moreOpen,
  onMoreOpenChange,
  activeFilterCount,
  onClear,
}: FilterBarProps) {
  const searchId = useId();
  const cityId = useId();
  const sortId = useId();
  const panelId = useId();
  const rentPanelId = useId();
  const starsPanelId = useId();
  const [rentOpen, setRentOpen] = useState(false);
  const [starsOpen, setStarsOpen] = useState(false);
  const starsActive = filters.minGoogleStars !== null;
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

        {rentBounds && (
          <button
            type="button"
            aria-expanded={rentOpen}
            aria-controls={rentPanelId}
            onClick={() => setRentOpen(!rentOpen)}
            className={`${CONTROL_CLASS} inline-flex min-w-56 items-center justify-between gap-1.5 font-medium tabular-nums ${
              filters.baseRent ? "border-accent bg-accent-soft text-accent" : rentOpen ? "border-accent text-accent" : ""
            }`}
          >
            {filters.baseRent ? `Base rent ${formatMoneyRange(filters.baseRent.min, filters.baseRent.max)}` : "Base rent: Any"}
            <IconChevronDown className={`transition ${rentOpen ? "rotate-180" : ""}`} />
          </button>
        )}

        <button
          type="button"
          aria-expanded={starsOpen}
          aria-controls={starsPanelId}
          onClick={() => setStarsOpen(!starsOpen)}
          className={`${CONTROL_CLASS} inline-flex min-w-44 items-center justify-between gap-1.5 font-medium tabular-nums ${
            starsActive ? "border-accent bg-accent-soft text-accent" : starsOpen ? "border-accent text-accent" : ""
          }`}
        >
          <span className="inline-flex items-center gap-1.5">
            <IconStar className="text-amber-500" />
            {starsActive ? `Google rating ${googleStarsLabel(filters.minGoogleStars)}` : "Google rating: Any"}
          </span>
          <IconChevronDown className={`transition ${starsOpen ? "rotate-180" : ""}`} />
        </button>

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

      </div>

      {rentBounds && (
        <div id={rentPanelId} hidden={!rentOpen} className="rounded-2xl border border-line bg-surface p-4 shadow-sm">
          <RentRangeFilter bounds={rentBounds} value={filters.baseRent} onChange={(baseRent) => update({ baseRent })} />
          <div className="mt-3 flex justify-end border-t border-line pt-3">
            <button
              type="button"
              onClick={() => update({ baseRent: null })}
              disabled={!filters.baseRent}
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-accent hover:bg-accent-soft disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-accent"
            >
              Reset base rent
            </button>
          </div>
        </div>
      )}

      <div id={starsPanelId} hidden={!starsOpen} className="rounded-2xl border border-line bg-surface p-4 shadow-sm">
        <GoogleStarsFilter
          value={filters.minGoogleStars}
          includeUnrated={filters.includeUnrated}
          onChange={(minGoogleStars) => update({ minGoogleStars })}
          onIncludeUnratedChange={(includeUnrated) => update({ includeUnrated })}
        />
        <div className="mt-3 flex justify-end border-t border-line pt-3">
          <button
            type="button"
            onClick={() => update({ minGoogleStars: null, includeUnrated: true })}
            disabled={!starsActive && filters.includeUnrated}
            className="rounded-lg px-3 py-1.5 text-sm font-medium text-accent hover:bg-accent-soft disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-accent"
          >
            Reset Google rating
          </button>
        </div>
      </div>

      <div id={panelId} hidden={!moreOpen} className="rounded-2xl border border-line bg-surface p-4 shadow-sm">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <NumberSelect
            label="Max est. monthly total"
            value={filters.maxMonthlyTotal}
            options={monthlyTotalOptions(rentBounds)}
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

export function ViewToggle({ view, onViewChange }: { view: ViewMode; onViewChange: (view: ViewMode) => void }) {
  return (
    <div role="group" aria-label="View" className="flex rounded-xl border border-line-strong bg-surface p-0.5 shadow-sm">
      <ViewButton active={view === "grid"} onClick={() => onViewChange("grid")} icon={<IconGrid />} label="Grid" />
      <ViewButton active={view === "map"} onClick={() => onViewChange("map")} icon={<IconMap />} label="Map" />
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
