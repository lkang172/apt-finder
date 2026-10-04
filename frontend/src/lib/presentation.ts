import type { Category, Confidence, EvidenceItem, Region, ReviewBrief, RunStatus, UnitType } from "./types";

export const NA_TEXT = "N/A — insufficient evidence";
export const URL_UNAVAILABLE_TEXT = "Source URL unavailable";

export const SCORECARD_ORDER: Category[] = [
  "noise",
  "management",
  "pests",
  "building_safety",
  "neighborhood_safety",
  "commute",
  "other_issues",
];

export const CATEGORY_LABEL: Record<Category, string> = {
  commute: "Commute",
  noise: "Noise",
  management: "Management",
  pests: "Pests",
  building_safety: "Building safety",
  neighborhood_safety: "Neighborhood safety",
  other_issues: "Other issues",
};

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
  insufficient: "Insufficient evidence",
};

export const CONFIDENCE_RANK: Record<Confidence, number> = {
  insufficient: 0,
  low: 1,
  medium: 2,
  high: 3,
};

export const UNIT_TYPE_LABEL: Record<UnitType, string> = {
  studio: "Studio",
  "1br": "1BR",
};

export const REGION_LABEL: Record<Region, string> = {
  peninsula: "Peninsula",
  south_bay: "South Bay",
  east_bay: "East Bay",
};

export const RUN_STATUS_LABEL: Record<RunStatus, string> = {
  running: "Refreshing data…",
  completed: "Completed",
  completed_with_limitations: "Completed with limitations",
  failed: "Failed",
};

export type Tone = "neutral" | "positive" | "info" | "warning" | "danger" | "accent";

export const CONFIDENCE_TONE: Record<Confidence, Tone> = {
  high: "positive",
  medium: "info",
  low: "warning",
  insufficient: "neutral",
};

export function scoreTone(score: number | null): Tone {
  if (score === null) return "neutral";
  if (score >= 7.5) return "positive";
  if (score >= 5.5) return "warning";
  return "danger";
}

const EVIDENCE_KIND_LABEL: Record<EvidenceItem["kind"], string> = {
  review: "Review",
  listing_fact: "Listing fact",
  price: "Price",
  fee: "Fee",
  rating_summary: "Rating summary",
  commute_fact: "Commute fact",
  safety_fact: "Safety fact",
  derived: "Derived",
};

export function evidenceKindLabel(kind: EvidenceItem["kind"]): string {
  return EVIDENCE_KIND_LABEL[kind];
}

export interface SourceLinkTarget {
  url: string | null;
  label: string;
  note: string | null;
}

export function listingLinkLabel(url: string | null, officialUrl: string | null): string {
  return officialUrl !== null && url === officialUrl ? "View Official Website" : "View Listing";
}

function evidenceActionLabel(item: EvidenceItem, officialUrl: string | null): string {
  switch (item.kind) {
    case "listing_fact":
    case "price":
    case "fee":
      return listingLinkLabel(item.source_url, officialUrl);
    case "safety_fact":
      return "View Safety Source";
    case "commute_fact":
      return "View Commute Source";
    default:
      return "View Source";
  }
}

export function evidenceSourceLink(item: EvidenceItem, officialUrl: string | null): SourceLinkTarget {
  const label = evidenceActionLabel(item, officialUrl);
  if (item.source_url) return { url: item.source_url, label, note: null };
  if (item.source_page_url) {
    return {
      url: item.source_page_url,
      label: "View Source Page",
      note: item.kind === "review" ? "Individual review link unavailable — opens the closest source page" : "Direct link unavailable — opens the closest source page",
    };
  }
  return { url: null, label, note: null };
}

export function hasNoReviews(review: ReviewBrief): boolean {
  return review.status === "no_reviews" || review.count === 0;
}
