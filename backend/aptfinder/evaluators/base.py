from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

CATEGORIES = (
    "commute",
    "noise",
    "management",
    "pests",
    "building_safety",
    "neighborhood_safety",
    "other_issues",
)
CONFIDENCE_LEVELS = ("high", "medium", "low", "insufficient")


@dataclass(frozen=True)
class ReviewEvidence:
    evidence_id: str
    source_id: str
    source_url: str | None
    reviewer: str | None
    rating: float | None
    review_date: datetime | None
    text: str
    subscores: dict[str, float] = field(default_factory=dict)
    is_summary: bool = False


@dataclass(frozen=True)
class RatingEvidence:
    evidence_id: str
    source_id: str
    average: float | None
    count: int
    scale: float
    source_url: str | None


@dataclass(frozen=True)
class CommuteEvidence:
    evidence_id: str
    provider: str
    distance_miles: float | None
    free_flow_minutes: float | None
    am_rush_minutes: float | None
    pm_rush_minutes: float | None
    rush_status: str
    source_url: str | None


@dataclass(frozen=True)
class AreaSafetyEvidence:
    evidence_id: str
    jurisdiction: str
    year: int
    violent_per_1000: float | None
    property_per_1000: float | None
    reference_violent_per_1000: float | None
    reference_property_per_1000: float | None
    reference_label: str
    source_url: str | None


@dataclass
class ClaimDraft:
    text: str
    polarity: str
    theme: str | None
    evidence_ids: list[str]
    weight: float = 0.0
    is_current: bool = True


@dataclass
class AssessmentDraft:
    category: str
    score: float | None
    confidence: str
    evidence_count: int
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    positive_evidence_ids: list[str] = field(default_factory=list)
    negative_evidence_ids: list[str] = field(default_factory=list)
    claims: list[ClaimDraft] = field(default_factory=list)

    @classmethod
    def insufficient(cls, category: str, summary: str, evidence_count: int = 0, **details: Any) -> "AssessmentDraft":
        return cls(category, None, "insufficient", evidence_count, summary, dict(details))
