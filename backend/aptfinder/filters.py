import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

LOW_RATING_THRESHOLD = 3.0
MIN_REVIEWS_FOR_EXCLUSION = 3
RATING_CONFLICT_GAP = 1.0


EXCLUDED_ELIGIBILITY = re.compile(
    r"\b(senior|age[- ]restricted|\d{2}\s*\+|affordable|income[- ](?:restricted|qualified|capped|protected|limits?)|"
    r"below[- ]market[- ]rate|bmr|low[- ]income)(?![a-z])",
    re.I,
)
EXCLUDED_NAME_PATTERN = re.compile(
    r"\b(senior|age\s*55|55\s*\+|62\s*\+|affordable housing|income[- ](?:restricted|protected)|below[- ]market[- ]rate|bmr|low[- ]income)(?![a-z])",
    re.I,
)


RESTRICTED_UNIT_PATTERN = re.compile(
    r"\b(income|bmr|below[- ]market|affordable|senior|\d{2}\s*%\s*ami|ami)(?![a-z])",
    re.I,
)
EXTENDED_STAY_DOMAINS = (
    "extendedstayamerica.com", "extendedstay.com", "intownsuites.com", "woodspring.com", "sonesta.com",
    "staybridge.com", "candlewoodsuites.com", "homewoodsuites.com", "home2suites.com", "residenceinn.com",
    "towneplacesuites.com", "hyatthouse.com",
)


def is_restricted_unit(*names: str | None) -> bool:
    """Floor plans or units named as income-restricted (e.g. "A5 Income Protected") never qualify."""
    return any(name and RESTRICTED_UNIT_PATTERN.search(name) for name in names)


def extended_stay_hotel(name: str | None, website_url: str | None) -> str | None:
    host = (website_url or "").lower().split("//")[-1].split("/")[0]
    if any(host == d or host.endswith("." + d) for d in EXTENDED_STAY_DOMAINS):
        return f"Official website is an extended-stay hotel ({host})"
    if name and re.search(r"\bextended[- ]stay\b", name, re.I):
        return f"Name indicates an extended-stay hotel: {name}"
    return None


def excluded_eligibility(restrictions: list[str], name: str | None) -> str | None:
    """Senior and income-capped housing is excluded by the owner's request; other restrictions are only shown."""
    for restriction in restrictions:
        if EXCLUDED_ELIGIBILITY.search(restriction):
            return f"Listed as {restriction}"
    if name and EXCLUDED_NAME_PATTERN.search(name):
        return f"Name indicates restricted eligibility: {name}"
    return None


def is_allowed_unit_type(beds: int | None, allowed: tuple[int, ...] = (0, 1)) -> bool:
    return beds is not None and beds in allowed


def rent_in_range(base_min: int | None, base_max: int | None, min_rent: int, max_rent: int) -> bool:
    """A floor-plan range qualifies only if one of its endpoints (each a real advertised price) is in range;
    a range that merely straddles the window does not prove any unit is priced inside it."""
    prices = [p for p in (base_min, base_max) if p is not None and p > 0]
    return any(min_rent <= p <= max_rent for p in prices)


def is_price_fresh(
    collected_at: datetime,
    source_updated_at: datetime | None,
    now: datetime,
    freshness: timedelta,
    source_max_age: timedelta,
) -> bool:
    if now - collected_at > freshness:
        return False
    return source_updated_at is None or now - source_updated_at <= source_max_age


@dataclass(frozen=True)
class RatingInput:
    source_id: str
    average: float | None
    count: int
    scale: float = 5.0
    match_confidence: str = "exact"

    @property
    def normalized(self) -> float | None:
        return None if self.average is None else self.average * 5.0 / self.scale


@dataclass(frozen=True)
class RatingDecision:
    exclude: bool
    status: str
    explanation: str
    sources_considered: list[str] = field(default_factory=list)


def evaluate_rating_filter(ratings: list[RatingInput]) -> RatingDecision:
    usable = [r for r in ratings if r.count > 0 and r.normalized is not None]
    if not usable:
        return RatingDecision(False, "no_reviews", "No reviews found")

    credible = [r for r in usable if r.match_confidence in ("exact", "probable")]
    established = [r for r in credible if r.count >= MIN_REVIEWS_FOR_EXCLUSION]
    names = [r.source_id for r in established]
    if not established:
        total = sum(r.count for r in credible)
        return RatingDecision(
            False, "insufficient",
            f"Only {total} credible review(s); at least {MIN_REVIEWS_FOR_EXCLUSION} needed before a rating can exclude a property",
        )

    low = [r for r in established if r.normalized < LOW_RATING_THRESHOLD]
    ok = [r for r in established if r.normalized >= LOW_RATING_THRESHOLD]
    describe = "; ".join(f"{r.source_id}: {r.normalized:.1f}/5 ({r.count} reviews)" for r in established)

    if not low:
        return RatingDecision(False, "ok", f"Ratings at or above {LOW_RATING_THRESHOLD}: {describe}", names)
    if not ok:
        return RatingDecision(True, "excluded_low_rating", f"Confirmed rating below {LOW_RATING_THRESHOLD}: {describe}", names)

    gap = max(r.normalized for r in ok) - min(r.normalized for r in low)
    if gap >= RATING_CONFLICT_GAP:
        return RatingDecision(
            False, "conflict",
            f"Review sources disagree by {gap:.1f} stars ({describe}); not excluded — verify directly",
            names,
        )
    pooled = sum(r.normalized * r.count for r in established) / sum(r.count for r in established)
    if pooled < LOW_RATING_THRESHOLD:
        return RatingDecision(True, "excluded_low_rating", f"Pooled rating {pooled:.2f}/5 below threshold: {describe}", names)
    return RatingDecision(False, "ok", f"Pooled rating {pooled:.2f}/5: {describe}", names)


@dataclass(frozen=True)
class PricePoint:
    source_id: str
    beds: int
    sqft: int | None
    base_min: int
    base_max: int
    source_url: str | None
    label: str | None = None
    unit_keys: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PriceConflict:
    beds: int
    sqft: int | None
    a: PricePoint
    b: PricePoint
    difference: int


def detect_price_conflicts(points: list[PricePoint], sqft_tolerance: float = 0.02) -> list[PriceConflict]:
    """Compares the same floor plan (same beds, sqft within tolerance) across different sources.

    When both sources name specific units, they are compared only if they share a unit: different units
    of one floor plan are routinely priced differently by floor or view."""
    conflicts = []
    for i, a in enumerate(points):
        for b in points[i + 1:]:
            if a.source_id == b.source_id or a.beds != b.beds or not a.sqft or not b.sqft:
                continue
            if abs(a.sqft - b.sqft) > max(a.sqft, b.sqft) * sqft_tolerance:
                continue
            if a.unit_keys and b.unit_keys and not a.unit_keys & b.unit_keys:
                continue
            if a.base_max < b.base_min:
                gap = b.base_min - a.base_max
            elif b.base_max < a.base_min:
                gap = a.base_min - b.base_max
            else:
                continue
            if gap > max(50, 0.02 * min(a.base_min, b.base_min)):
                conflicts.append(PriceConflict(a.beds, a.sqft, a, b, gap))
    return conflicts
