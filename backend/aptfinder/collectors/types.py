from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from aptfinder.http import FetchResult
from aptfinder.normalize import ParsedFee


@dataclass
class DiscoveryStub:
    source_id: str
    source_listing_id: str
    url: str
    name: str
    city: str | None
    lat: float | None
    lon: float | None
    min_price_by_beds: dict[int, int | None]

    def may_have_qualifying_unit(self, allowed_beds: tuple[int, ...], max_rent: int) -> bool:
        """Safe pre-filter: a property whose cheapest eligible unit exceeds the cap cannot qualify."""
        prices = [p for b, p in self.min_price_by_beds.items() if b in allowed_beds and p]
        return any(p <= max_rent for p in prices)


@dataclass
class CollectedUnit:
    source_unit_key: str
    kind: str
    label: str | None
    floorplan_name: str | None
    beds: int | None
    baths: float | None
    sqft_min: int | None
    sqft_max: int | None
    base_rent_min: int | None
    base_rent_max: int | None
    total_monthly: float | None = None
    required_fees_monthly: float | None = None
    lease_term_months: int | None = None
    available_on: str | None = None
    availability: str | None = None
    source_updated_at: datetime | None = None


@dataclass
class CollectedReview:
    source_review_key: str
    reviewer: str | None
    rating: float | None
    review_date: datetime | None
    text: str
    subscores: dict[str, Any] = field(default_factory=dict)
    review_url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CollectedRating:
    average: float | None
    count: int
    scale: float
    source_url: str | None
    note: str | None = None


@dataclass
class CollectedFact:
    key: str
    title: str
    content: str
    categories: list[str]
    data: dict[str, Any] = field(default_factory=dict)
    url: str | None = None


@dataclass
class CollectedListing:
    source_id: str
    source_listing_id: str
    url: str
    name: str
    street_address: str | None
    city: str | None
    state: str | None
    zip: str | None
    lat: float | None
    lon: float | None
    fetch: FetchResult
    image_url: str | None = None
    official_website_url: str | None = None
    source_updated_at: datetime | None = None
    units: list[CollectedUnit] = field(default_factory=list)
    fees: list[ParsedFee] = field(default_factory=list)
    promotions: list[str] = field(default_factory=list)
    reviews: list[CollectedReview] = field(default_factory=list)
    rating: CollectedRating | None = None
    facts: list[CollectedFact] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
