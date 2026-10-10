# API Contract (backend ⇄ frontend)

FastAPI serves JSON on `http://localhost:8000`. The Next.js app proxies `/api/*` to it. On Vercel the two run as
services in one project and `vercel.json` routes public `/api/*` to the backend; the paths below are unchanged.
All timestamps are ISO-8601 UTC strings. Money is USD per month unless noted. `null` always means
"unknown / not available" — never zero, never "good".

```ts
type Confidence = "high" | "medium" | "low" | "insufficient";
type Category =
  | "commute" | "noise" | "management" | "pests"
  | "building_safety" | "neighborhood_safety" | "other_issues";
type PriceStatus = "verified" | "conflict" | "stale";
type ReviewStatus = "ok" | "no_reviews" | "insufficient" | "conflict";

interface ScoreBrief { score: number | null; confidence: Confidence }   // score null => "N/A — insufficient evidence"

interface CommuteBrief {
  distance_miles: number | null;
  free_flow_minutes: number | null;       // OSRM free-flow, NO traffic
  am_rush_minutes: number | null;         // null unless a traffic-aware API is configured
  pm_rush_minutes: number | null;
  rush_status: string;                    // e.g. "Unavailable — traffic-aware routing API required"
}

interface ReviewBrief {
  average: number | null;                 // normalized to /5
  count: number;
  status: ReviewStatus;
  explanation: string;                    // e.g. "No reviews found"
}

interface Highlight { text: string; category: Category; claim_id: number }

interface GoogleReviewsBrief {
  status: "ok" | "not_configured" | "not_checked" | "no_match" | "error";
  rating: number | null;                  // Google stars out of 5 (all Google reviewers)
  count: number | null;                   // total Google ratings — may be far more than the review texts we hold
  maps_url: string | null;                // Google Maps place page from the API; never constructed
  summary: string | null;                 // Google's AI-generated summary of the reviews, verbatim
  summary_disclosure: string | null;      // e.g. "Summarized with Gemini" — always show next to the summary
  summary_flag_url: string | null;        // Google's "report this summary" link, show when present
  comments_summary: string | null;        // Apt Finder's keyword-based summary of the Google review texts returned
  comments_summary_method: string | null; // how it was made (not AI) — show in small print next to it
  match_confidence: "exact" | "probable" | "weak" | null;
  observed_at: string | null;
  explanation: string;                    // human-readable status, e.g. why there is no Google data
}

interface PropertySummary {
  id: number;
  name: string;
  city: string;
  region: "peninsula" | "south_bay" | "east_bay";
  street_address: string | null;
  lat: number | null;
  lon: number | null;
  image_url: string | null;
  image_source_name: string | null;
  unit_types: ("studio" | "1br")[];       // qualifying, fresh units only
  rent_min: number | null;                // advertised BASE rent of qualifying units
  rent_max: number | null;
  qualifying_rents: number[];             // distinct base rents of qualifying units, ascending — use for custom price-range filtering
  est_monthly_total_min: number | null;   // base + confirmed mandatory recurring fees
  has_unknown_required_costs: boolean;    // e.g. "renter's insurance required" with no amount
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
  eligibility_notes: string[];            // e.g. ["Senior Housing"], ["Affordable Housing"]; show prominently
  google: GoogleReviewsBrief;             // show stars + count on every card; summary on card (truncated) and detail
  source_ids: string[];
}

interface PropertyListResponse {
  items: PropertySummary[];               // primary results only (hard filters passed)
  total: number;
  cities: string[];
  last_run: RunInfo | null;
}

interface EvidenceItem {
  id: string;
  kind: "review" | "review_summary" | "listing_fact" | "price" | "fee" | "rating_summary" | "commute_fact" | "safety_fact" | "derived";
  source_id: string;
  source_name: string;
  title: string;
  content: string;                        // excerpt or fact text
  published_at: string | null;            // original publication (reviews)
  collected_at: string;
  source_url: string | null;              // null => show "Source URL unavailable"
  source_page_url: string | null;
  is_derived: boolean;
  categories: string[];
  rating: number | null;
  reviewer: string | null;
  age_label: string | null;               // e.g. "2 years ago" — old evidence must show its age
  data: Record<string, unknown>;
}

interface ClaimView {
  id: number;
  text: string;
  polarity: "positive" | "negative" | "neutral";
  theme: string | null;
  is_current: boolean;                    // false => based on old evidence, show qualifier
  evidence: EvidenceItem[];
}

interface AssessmentView {
  category: Category;
  label: string;                          // "Noise", "Building safety", ...
  score: number | null;
  confidence: Confidence;
  evidence_count: number;
  summary: string;
  details: Record<string, unknown>;       // e.g. { theme_counts: { thin_walls: 3, quiet: 1 } }
  claims: ClaimView[];
  audit_status: "passed" | "corrected";
}

interface UnitView {
  id: number;
  source_id: string;
  source_name: string;
  label: string | null;                   // unit number when known
  floorplan_name: string | null;
  kind: "unit" | "floorplan";
  beds: number | null;
  baths: number | null;
  sqft_min: number | null;
  sqft_max: number | null;
  base_rent_min: number | null;
  base_rent_max: number | null;
  total_monthly: number | null;           // as published by the source
  required_fees_monthly: number | null;
  lease_term_months: number | null;
  available_on: string | null;            // YYYY-MM-DD
  availability: string | null;
  is_promotional: boolean;
  promotion_text: string | null;
  effective_rent_estimate: number | null; // derived, never a quoted price
  effective_rent_method: string | null;
  collected_at: string;
  source_updated_at: string | null;
  fresh: boolean;
  qualifies: boolean;                     // studio/1BR, base rent within range, fresh
  source_url: string | null;
}

interface FeeView {
  fee_type: string;                       // trash, parking, utilities, internet, amenity, pet, insurance, deposit, one_time, other
  description: string;
  amount_monthly: number | null;
  amount_text: string | null;
  mandatory: boolean | null;              // null => unclear
  recurring: boolean | null;
  source_id: string;
  source_name: string;
  source_url: string | null;
  evidence_id: string | null;
}

interface MonthlyCost {
  base_rent_min: number | null;
  confirmed_required_fees: number | null; // monthly, from source-declared mandatory fees
  est_total_min: number | null;
  unknown_required: string[];             // required but amount not published
  unclear_recurring: string[];            // listed recurring fees whose mandatory status is unclear
}

interface PriceConflictView {
  beds: number;
  sqft: number | null;
  difference: number;
  sides: { source_id: string; source_name: string; price_min: number; price_max: number; label: string | null; url: string | null }[];
}

interface ListingLink { source_id: string; source_name: string; url: string | null; name: string | null; last_seen_at: string }

interface CommuteView extends CommuteBrief {
  provider: string;
  methodology: string;
  confidence: Confidence;
  computed_at: string;
  source_url: string | null;              // the routing request that produced the numbers
  view_url: string | null;                // human-viewable route map
  live_traffic_url: string | null;        // convenience link to check live traffic yourself (not evidence)
  evidence_id: string | null;
}

interface OverallView {
  score: number | null;
  confidence: Confidence;
  components: { category: Category; label: string; score: number; confidence: Confidence; base_weight: number; effective_weight: number }[];
  excluded_categories: { category: Category; label: string; reason: string }[];
  confidence_reasons: string[];
}

interface ThemeStat { theme: string; label: string; count: number; recent_count: number; evidence_ids: string[] }

interface ReviewIntelligence {
  praised: ThemeStat[];
  criticized: ThemeStat[];
  recent_trends: string[];
  outliers: { text: string; evidence_id: string }[];
  quality: { confidence: Confidence; summary: string; details: Record<string, unknown> };
  reviews: EvidenceItem[];                // kind === "review", newest first
}

interface PropertyDetail extends PropertySummary {
  zip: string | null;
  listings: ListingLink[];                // "View Original Listings"
  official_website: { url: string; source_id: string; source_name: string; evidence_id: string | null } | null;
  units: UnitView[];
  fees: FeeView[];
  monthly_cost: MonthlyCost;
  price_conflicts: PriceConflictView[];
  promotions: { text: string; source_id: string; source_name: string; url: string | null }[];
  commute_detail: CommuteView | null;
  assessments: AssessmentView[];          // one per Category, always present (may be insufficient)
  overall_detail: OverallView;
  review_intelligence: ReviewIntelligence;
  rating_summaries: { source_id: string; source_name: string; average: number | null; count: number; source_url: string | null; observed_at: string }[];
  rating_filter: { status: ReviewStatus | "low_rating"; explanation: string };
  facts: EvidenceItem[];
  audit: { category: Category | null; check_name: string; severity: "error" | "warning" | "info"; action: string; detail: string }[];
  limitations: string[];
}

interface RunInfo {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: "running" | "completed" | "completed_with_limitations" | "failed";
  stats: Record<string, number>;
  limitations: { source_id: string; message: string }[];
}

interface ExcludedProperty { id: number; name: string; city: string | null; reasons: { filter: string; explanation: string }[] }

interface Meta {
  office: { label: string; address: string; lat: number; lon: number };
  search: { min_rent: number; max_rent: number; unit_types: string[] };
  sources: { id: string; name: string; kind: string; homepage_url: string | null }[];
}
```

## Endpoints

| Method | Path | Response |
| ------ | ---- | -------- |
| GET | `/api/properties` | `PropertyListResponse` (filter/sort happen client-side; the set is small) |
| GET | `/api/properties/{id}` | `PropertyDetail` |
| GET | `/api/evidence/{id}` | `EvidenceItem` |
| GET | `/api/excluded` | `ExcludedProperty[]` |
| GET | `/api/runs/latest` | `RunInfo \| null` |
| POST | `/api/runs` | `{ run_id: number }` (202; starts a refresh in the background) |
| GET | `/api/meta` | `Meta` |
