import { CONFIDENCE_RANK, googleRating } from "./presentation";
import type { Category, Confidence, PropertySummary, UnitType } from "./types";

export type SortDirection = "asc" | "desc";

export type ScoreFilterCategory = Exclude<Category, "commute" | "other_issues">;

export const SCORE_FILTER_CATEGORIES: ScoreFilterCategory[] = [
  "noise",
  "management",
  "pests",
  "building_safety",
  "neighborhood_safety",
];

export interface BrowseFilters {
  query: string;
  city: string;
  unitTypes: UnitType[];
  maxMonthlyTotal: number | null;
  maxCommuteMinutes: number | null;
  minOverall: number | null;
  minCategoryScore: Partial<Record<ScoreFilterCategory, number>>;
  minConfidence: Confidence | null;
  minReviewRating: number | null;
  hideEligibilityRestricted: boolean;
}

export const EMPTY_FILTERS: BrowseFilters = {
  query: "",
  city: "",
  unitTypes: [],
  maxMonthlyTotal: null,
  maxCommuteMinutes: null,
  minOverall: null,
  minCategoryScore: {},
  minConfidence: null,
  minReviewRating: null,
  hideEligibilityRestricted: false,
};

export type SortKey =
  | "overall"
  | "monthly_total"
  | "base_rent"
  | "commute"
  | ScoreFilterCategory
  | "review_rating"
  | "google_rating"
  | "confidence";

interface SortOption {
  key: SortKey;
  label: string;
  defaultDirection: SortDirection;
  value: (property: PropertySummary) => number | null;
}

// The rating shown most prominently on a card: Google's when available, otherwise the other sources' average.
export function primaryRating(property: PropertySummary): number | null {
  return googleRating(property.google) ?? property.review.average;
}

export const SORT_OPTIONS: SortOption[] = [
  { key: "overall", label: "Overall score", defaultDirection: "desc", value: (p) => p.overall.score },
  { key: "monthly_total", label: "Est. monthly total", defaultDirection: "asc", value: (p) => p.est_monthly_total_min },
  { key: "base_rent", label: "Base rent", defaultDirection: "asc", value: (p) => p.rent_min },
  { key: "commute", label: "Commute time", defaultDirection: "asc", value: (p) => p.commute?.free_flow_minutes ?? null },
  { key: "noise", label: "Noise score", defaultDirection: "desc", value: (p) => p.scores.noise.score },
  { key: "management", label: "Management score", defaultDirection: "desc", value: (p) => p.scores.management.score },
  { key: "pests", label: "Pests score", defaultDirection: "desc", value: (p) => p.scores.pests.score },
  { key: "building_safety", label: "Building safety", defaultDirection: "desc", value: (p) => p.scores.building_safety.score },
  {
    key: "neighborhood_safety",
    label: "Neighborhood safety",
    defaultDirection: "desc",
    value: (p) => p.scores.neighborhood_safety.score,
  },
  { key: "review_rating", label: "Rating (Google first)", defaultDirection: "desc", value: primaryRating },
  { key: "google_rating", label: "Google rating", defaultDirection: "desc", value: (p) => googleRating(p.google) },
  { key: "confidence", label: "Overall confidence", defaultDirection: "desc", value: (p) => CONFIDENCE_RANK[p.overall.confidence] },
];

export function sortOption(key: SortKey): SortOption {
  return SORT_OPTIONS.find((option) => option.key === key) ?? SORT_OPTIONS[0];
}

// Unknown values always sort last, whichever direction is chosen; null is never coerced to 0.
export function compareNullLast(a: number | null, b: number | null, direction: SortDirection): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return direction === "asc" ? a - b : b - a;
}

export function sortProperties(items: PropertySummary[], key: SortKey, direction: SortDirection): PropertySummary[] {
  const { value } = sortOption(key);
  return [...items].sort(
    (a, b) =>
      compareNullLast(value(a), value(b), direction) ||
      compareNullLast(a.overall.score, b.overall.score, "desc") ||
      a.name.localeCompare(b.name),
  );
}

function meetsMinimum(value: number | null, minimum: number | null | undefined): boolean {
  if (minimum === null || minimum === undefined) return true;
  return value !== null && value >= minimum;
}

function meetsMaximum(value: number | null, maximum: number | null): boolean {
  if (maximum === null) return true;
  return value !== null && value <= maximum;
}

function matchesQuery(property: PropertySummary, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [property.name, property.city, property.street_address ?? ""].some((field) =>
    field.toLowerCase().includes(needle),
  );
}

export function filterProperties(items: PropertySummary[], filters: BrowseFilters): PropertySummary[] {
  return items.filter(
    (p) =>
      matchesQuery(p, filters.query) &&
      (!filters.city || p.city === filters.city) &&
      (filters.unitTypes.length === 0 || filters.unitTypes.some((type) => p.unit_types.includes(type))) &&
      meetsMaximum(p.est_monthly_total_min, filters.maxMonthlyTotal) &&
      meetsMaximum(p.commute?.free_flow_minutes ?? null, filters.maxCommuteMinutes) &&
      meetsMinimum(p.overall.score, filters.minOverall) &&
      SCORE_FILTER_CATEGORIES.every((category) =>
        meetsMinimum(p.scores[category].score, filters.minCategoryScore[category]),
      ) &&
      (filters.minConfidence === null ||
        CONFIDENCE_RANK[p.overall.confidence] >= CONFIDENCE_RANK[filters.minConfidence]) &&
      meetsMinimum(primaryRating(p), filters.minReviewRating) &&
      (!filters.hideEligibilityRestricted || p.eligibility_notes.length === 0),
  );
}

export function countActiveFilters(filters: BrowseFilters): number {
  return (
    (filters.query.trim() ? 1 : 0) +
    (filters.city ? 1 : 0) +
    (filters.unitTypes.length > 0 ? 1 : 0) +
    (filters.hideEligibilityRestricted ? 1 : 0) +
    [filters.maxMonthlyTotal, filters.maxCommuteMinutes, filters.minOverall, filters.minConfidence, filters.minReviewRating].filter(
      (value) => value !== null,
    ).length +
    Object.values(filters.minCategoryScore).filter((value) => value !== undefined).length
  );
}
