import { humanize } from "./format";
import type { EvidenceItem, PropertyDetail } from "./types";

export type EvidenceIndex = Record<string, EvidenceItem>;

export function buildEvidenceIndex(detail: PropertyDetail): EvidenceIndex {
  const index: EvidenceIndex = {};
  const add = (item: EvidenceItem) => {
    index[item.id] = item;
  };
  detail.review_intelligence.reviews.forEach(add);
  detail.facts.forEach(add);
  detail.assessments.forEach((assessment) => assessment.claims.forEach((claim) => claim.evidence.forEach(add)));
  return index;
}

export type ThemeLabels = Record<string, string>;

export function buildThemeLabels(detail: PropertyDetail): ThemeLabels {
  const labels: ThemeLabels = {};
  const { praised, criticized } = detail.review_intelligence;
  [...praised, ...criticized].forEach((stat) => {
    labels[stat.theme] = stat.label;
  });
  return labels;
}

export function themeLabel(theme: string, labels: ThemeLabels): string {
  return labels[theme] ?? humanize(theme);
}

export function themeCounts(details: Record<string, unknown>): [string, number][] {
  const raw = details.theme_counts;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return [];
  return Object.entries(raw as Record<string, unknown>)
    .filter((entry): entry is [string, number] => typeof entry[1] === "number" && entry[1] > 0)
    .sort((a, b) => b[1] - a[1]);
}

export function scalarDetails(details: Record<string, unknown>, exclude: string[] = []): [string, string | number | boolean][] {
  return Object.entries(details).filter(
    (entry): entry is [string, string | number | boolean] =>
      !exclude.includes(entry[0]) && ["string", "number", "boolean"].includes(typeof entry[1]),
  );
}
