// Mirrors docs/api-contract.md. `null` always means unknown / not available — never zero, never "good".

export type Confidence = "high" | "medium" | "low" | "insufficient";
export type Category =
  | "commute"
  | "noise"
  | "management"
  | "pests"
  | "building_safety"
  | "neighborhood_safety"
  | "other_issues";
export type PriceStatus = "verified" | "conflict" | "stale";
export type ReviewStatus = "ok" | "no_reviews" | "insufficient" | "conflict";
export type UnitType = "studio" | "1br";
export type Region = "peninsula" | "south_bay" | "east_bay";

export interface ScoreBrief {
  score: number | null;
  confidence: Confidence;
}

export interface CommuteBrief {
  distance_miles: number | null;
  free_flow_minutes: number | null;
  am_rush_minutes: number | null;
  pm_rush_minutes: number | null;
  rush_status: string;
}

export interface ReviewBrief {
  average: number | null;
  count: number;
  status: ReviewStatus;
  explanation: string;
}

export interface Highlight {
  text: string;
  category: Category;
  claim_id: number;
}

export interface PropertySummary {
  id: number;
  name: string;
  city: string;
  region: Region;
  street_address: string | null;
  lat: number | null;
  lon: number | null;
  image_url: string | null;
  image_source_name: string | null;
  unit_types: UnitType[];
  rent_min: number | null;
  rent_max: number | null;
  est_monthly_total_min: number | null;
  has_unknown_required_costs: boolean;
  has_promotion: boolean;
  sqft_min: number | null;
  sqft_max: number | null;
  price_status: PriceStatus;
  last_verified_at: string | null;
  commute: CommuteBrief | null;
  review: ReviewBrief;
  overall: ScoreBrief;
  scores: Record<Category, ScoreBrief>;
  strongest_positive: Highlight | null;
  strongest_concern: Highlight | null;
  eligibility_notes: string[];
  source_ids: string[];
}

export interface PropertyListResponse {
  items: PropertySummary[];
  total: number;
  cities: string[];
  last_run: RunInfo | null;
}

export type EvidenceKind =
  | "review"
  | "listing_fact"
  | "price"
  | "fee"
  | "rating_summary"
  | "commute_fact"
  | "safety_fact"
  | "derived";

export interface EvidenceItem {
  id: string;
  kind: EvidenceKind;
  source_id: string;
  source_name: string;
  title: string;
  content: string;
  published_at: string | null;
  collected_at: string;
  source_url: string | null;
  source_page_url: string | null;
  is_derived: boolean;
  categories: string[];
  rating: number | null;
  reviewer: string | null;
  age_label: string | null;
  data: Record<string, unknown>;
}

export interface ClaimView {
  id: number;
  text: string;
  polarity: "positive" | "negative" | "neutral";
  theme: string | null;
  is_current: boolean;
  evidence: EvidenceItem[];
}

export interface AssessmentView {
  category: Category;
  label: string;
  score: number | null;
  confidence: Confidence;
  evidence_count: number;
  summary: string;
  details: Record<string, unknown>;
  claims: ClaimView[];
  audit_status: "passed" | "corrected";
}

export interface UnitView {
  id: number;
  source_id: string;
  source_name: string;
  label: string | null;
  floorplan_name: string | null;
  kind: "unit" | "floorplan";
  beds: number | null;
  baths: number | null;
  sqft_min: number | null;
  sqft_max: number | null;
  base_rent_min: number | null;
  base_rent_max: number | null;
  total_monthly: number | null;
  required_fees_monthly: number | null;
  lease_term_months: number | null;
  available_on: string | null;
  availability: string | null;
  is_promotional: boolean;
  promotion_text: string | null;
  effective_rent_estimate: number | null;
  effective_rent_method: string | null;
  collected_at: string;
  source_updated_at: string | null;
  fresh: boolean;
  qualifies: boolean;
  source_url: string | null;
}

export interface FeeView {
  fee_type: string;
  description: string;
  amount_monthly: number | null;
  amount_text: string | null;
  mandatory: boolean | null;
  recurring: boolean | null;
  source_id: string;
  source_name: string;
  source_url: string | null;
  evidence_id: string | null;
}

export interface MonthlyCost {
  base_rent_min: number | null;
  confirmed_required_fees: number | null;
  est_total_min: number | null;
  unknown_required: string[];
  unclear_recurring: string[];
}

export interface PriceConflictSide {
  source_id: string;
  source_name: string;
  price_min: number;
  price_max: number;
  label: string | null;
  url: string | null;
}

export interface PriceConflictView {
  beds: number;
  sqft: number | null;
  difference: number;
  sides: PriceConflictSide[];
}

export interface ListingLink {
  source_id: string;
  source_name: string;
  url: string | null;
  name: string | null;
  last_seen_at: string;
}

export interface CommuteView extends CommuteBrief {
  provider: string;
  methodology: string;
  confidence: Confidence;
  computed_at: string;
  source_url: string | null;
  view_url: string | null;
  live_traffic_url: string | null;
  evidence_id: string | null;
}

export interface OverallComponent {
  category: Category;
  label: string;
  score: number;
  confidence: Confidence;
  base_weight: number;
  effective_weight: number;
}

export interface OverallView {
  score: number | null;
  confidence: Confidence;
  components: OverallComponent[];
  excluded_categories: { category: Category; label: string; reason: string }[];
  confidence_reasons: string[];
}

export interface ThemeStat {
  theme: string;
  label: string;
  count: number;
  recent_count: number;
  evidence_ids: string[];
}

export interface ReviewIntelligence {
  praised: ThemeStat[];
  criticized: ThemeStat[];
  recent_trends: string[];
  outliers: { text: string; evidence_id: string }[];
  quality: { confidence: Confidence; summary: string; details: Record<string, unknown> };
  reviews: EvidenceItem[];
}

export interface OfficialWebsite {
  url: string;
  source_id: string;
  source_name: string;
  evidence_id: string | null;
}

export interface Promotion {
  text: string;
  source_id: string;
  source_name: string;
  url: string | null;
}

export interface RatingSummary {
  source_id: string;
  source_name: string;
  average: number | null;
  count: number;
  source_url: string | null;
  observed_at: string;
}

export interface AuditNote {
  category: Category | null;
  check_name: string;
  severity: "error" | "warning" | "info";
  action: string;
  detail: string;
}

export interface PropertyDetail extends PropertySummary {
  zip: string | null;
  listings: ListingLink[];
  official_website: OfficialWebsite | null;
  units: UnitView[];
  fees: FeeView[];
  monthly_cost: MonthlyCost;
  price_conflicts: PriceConflictView[];
  promotions: Promotion[];
  commute_detail: CommuteView | null;
  assessments: AssessmentView[];
  overall_detail: OverallView;
  review_intelligence: ReviewIntelligence;
  rating_summaries: RatingSummary[];
  rating_filter: { status: ReviewStatus | "excluded_low_rating"; explanation: string };
  facts: EvidenceItem[];
  audit: AuditNote[];
  limitations: string[];
}

export type RunStatus = "running" | "completed" | "completed_with_limitations" | "failed";

export interface RunInfo {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: RunStatus;
  stats: Record<string, number>;
  limitations: { source_id: string; message: string }[];
}

export interface ExcludedProperty {
  id: number;
  name: string;
  city: string | null;
  reasons: { filter: string; explanation: string }[];
}

export interface Meta {
  office: { label: string; address: string; lat: number; lon: number };
  search: { min_rent: number; max_rent: number; unit_types: string[] };
  sources: { id: string; name: string; kind: string; homepage_url: string | null }[];
}
