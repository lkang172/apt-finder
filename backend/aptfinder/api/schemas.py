from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

Confidence = Literal["high", "medium", "low", "insufficient"]
Category = Literal["commute", "noise", "management", "pests", "building_safety", "neighborhood_safety", "other_issues"]
PriceStatus = Literal["verified", "conflict", "stale"]
ReviewStatus = Literal["ok", "no_reviews", "insufficient", "conflict"]


class ScoreBrief(BaseModel):
    score: float | None
    confidence: Confidence


class CommuteBrief(BaseModel):
    distance_miles: float | None
    free_flow_minutes: float | None
    am_rush_minutes: float | None
    pm_rush_minutes: float | None
    rush_status: str


class ReviewBrief(BaseModel):
    average: float | None
    count: int
    status: ReviewStatus
    explanation: str


class Highlight(BaseModel):
    text: str
    category: Category
    claim_id: int


class PropertySummary(BaseModel):
    id: int
    name: str
    city: str
    region: Literal["peninsula", "south_bay", "east_bay"]
    street_address: str | None
    lat: float | None
    lon: float | None
    image_url: str | None
    image_source_name: str | None
    unit_types: list[Literal["studio", "1br"]]
    rent_min: int | None
    rent_max: int | None
    est_monthly_total_min: float | None
    has_unknown_required_costs: bool
    has_promotion: bool
    sqft_min: int | None
    sqft_max: int | None
    price_status: PriceStatus
    last_verified_at: datetime | None
    commute: CommuteBrief | None
    review: ReviewBrief
    overall: ScoreBrief
    scores: dict[Category, ScoreBrief]
    strongest_positive: Highlight | None
    strongest_concern: Highlight | None
    eligibility_notes: list[str]
    source_ids: list[str]


class RunInfo(BaseModel):
    id: int
    started_at: datetime
    finished_at: datetime | None
    status: Literal["running", "completed", "completed_with_limitations", "failed"]
    stats: dict[str, int]
    limitations: list[dict[str, str]]


class PropertyListResponse(BaseModel):
    items: list[PropertySummary]
    total: int
    cities: list[str]
    last_run: RunInfo | None


class EvidenceItem(BaseModel):
    id: str
    kind: Literal["review", "listing_fact", "price", "fee", "rating_summary", "commute_fact", "safety_fact", "derived"]
    source_id: str
    source_name: str
    title: str
    content: str
    published_at: datetime | None
    collected_at: datetime
    source_url: str | None
    source_page_url: str | None
    is_derived: bool
    categories: list[str]
    rating: float | None
    reviewer: str | None
    age_label: str | None
    data: dict[str, Any]


class ClaimView(BaseModel):
    id: int
    text: str
    polarity: Literal["positive", "negative", "neutral"]
    theme: str | None
    is_current: bool
    evidence: list[EvidenceItem]


class AssessmentView(BaseModel):
    category: Category
    label: str
    score: float | None
    confidence: Confidence
    evidence_count: int
    summary: str
    details: dict[str, Any]
    claims: list[ClaimView]
    audit_status: Literal["passed", "corrected"]


class UnitView(BaseModel):
    id: int
    source_id: str
    source_name: str
    label: str | None
    floorplan_name: str | None
    kind: Literal["unit", "floorplan"]
    beds: int | None
    baths: float | None
    sqft_min: int | None
    sqft_max: int | None
    base_rent_min: int | None
    base_rent_max: int | None
    total_monthly: float | None
    required_fees_monthly: float | None
    lease_term_months: int | None
    available_on: str | None
    availability: str | None
    is_promotional: bool
    promotion_text: str | None
    effective_rent_estimate: int | None
    effective_rent_method: str | None
    collected_at: datetime
    source_updated_at: datetime | None
    fresh: bool
    qualifies: bool
    source_url: str | None


class FeeView(BaseModel):
    fee_type: str
    description: str
    amount_monthly: float | None
    amount_text: str | None
    mandatory: bool | None
    recurring: bool | None
    source_id: str
    source_name: str
    source_url: str | None
    evidence_id: str | None


class MonthlyCost(BaseModel):
    base_rent_min: int | None
    confirmed_required_fees: float | None
    est_total_min: float | None
    unknown_required: list[str]
    unclear_recurring: list[str]


class PriceConflictSide(BaseModel):
    source_id: str
    source_name: str
    price_min: int
    price_max: int
    label: str | None
    url: str | None


class PriceConflictView(BaseModel):
    beds: int
    sqft: int | None
    difference: int
    sides: list[PriceConflictSide]


class ListingLink(BaseModel):
    source_id: str
    source_name: str
    url: str | None
    name: str | None
    last_seen_at: datetime


class OfficialWebsite(BaseModel):
    url: str
    source_id: str
    source_name: str
    evidence_id: str | None


class Promotion(BaseModel):
    text: str
    source_id: str
    source_name: str
    url: str | None


class CommuteView(CommuteBrief):
    provider: str
    methodology: str
    confidence: Confidence
    computed_at: datetime
    source_url: str | None
    view_url: str | None
    live_traffic_url: str | None
    evidence_id: str | None


class OverallComponent(BaseModel):
    category: Category
    label: str
    score: float
    confidence: Confidence
    base_weight: float
    effective_weight: float


class ExcludedCategory(BaseModel):
    category: Category
    label: str
    reason: str


class OverallView(BaseModel):
    score: float | None
    confidence: Confidence
    components: list[OverallComponent]
    excluded_categories: list[ExcludedCategory]
    confidence_reasons: list[str]


class ThemeStat(BaseModel):
    theme: str
    label: str
    count: int
    recent_count: int
    evidence_ids: list[str]


class Outlier(BaseModel):
    text: str
    evidence_id: str


class ReviewQuality(BaseModel):
    confidence: Confidence
    summary: str
    details: dict[str, Any]


class ReviewIntelligence(BaseModel):
    praised: list[ThemeStat]
    criticized: list[ThemeStat]
    recent_trends: list[str]
    outliers: list[Outlier]
    quality: ReviewQuality
    reviews: list[EvidenceItem]


class RatingSummaryView(BaseModel):
    source_id: str
    source_name: str
    average: float | None
    count: int
    source_url: str | None
    observed_at: datetime


class RatingFilterView(BaseModel):
    status: Literal["ok", "no_reviews", "insufficient", "conflict", "excluded_low_rating"]
    explanation: str


class AuditView(BaseModel):
    category: Category | None
    check_name: str
    severity: Literal["error", "warning", "info"]
    action: str
    detail: str


class PropertyDetail(PropertySummary):
    zip: str | None
    listings: list[ListingLink]
    official_website: OfficialWebsite | None
    units: list[UnitView]
    fees: list[FeeView]
    monthly_cost: MonthlyCost
    price_conflicts: list[PriceConflictView]
    promotions: list[Promotion]
    commute_detail: CommuteView | None
    assessments: list[AssessmentView]
    overall_detail: OverallView
    review_intelligence: ReviewIntelligence
    rating_summaries: list[RatingSummaryView]
    rating_filter: RatingFilterView
    facts: list[EvidenceItem]
    audit: list[AuditView]
    limitations: list[str]


class ExclusionReason(BaseModel):
    filter: str
    explanation: str


class ExcludedProperty(BaseModel):
    id: int
    name: str
    city: str | None
    reasons: list[ExclusionReason]


class OfficeInfo(BaseModel):
    label: str
    address: str
    lat: float
    lon: float


class SearchInfo(BaseModel):
    min_rent: int
    max_rent: int
    unit_types: list[str]


class SourceInfo(BaseModel):
    id: str
    name: str
    kind: str
    homepage_url: str | None


class Meta(BaseModel):
    office: OfficeInfo
    search: SearchInfo
    sources: list[SourceInfo]


class RunStarted(BaseModel):
    run_id: int
