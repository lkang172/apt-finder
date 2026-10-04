from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from aptfinder.config import Settings
from aptfinder.db.models import Evidence, ListingSource, PriceObservation, Property, RatingSummary, Unit
from aptfinder.filters import (
    PriceConflict,
    PricePoint,
    RatingDecision,
    RatingInput,
    detect_price_conflicts,
    evaluate_rating_filter,
    excluded_eligibility,
    extended_stay_hotel,
    is_restricted_unit,
    is_allowed_unit_type,
    is_price_fresh,
    rent_in_range,
)
from aptfinder.geo import evaluate_location


@dataclass
class UnitPriceState:
    unit: Unit
    observation: PriceObservation
    source_id: str
    current: bool
    fresh: bool
    in_range: bool
    restricted: bool = False

    @property
    def qualifies(self) -> bool:
        return self.current and self.fresh and self.in_range and not self.restricted


@dataclass
class PriceVerification:
    status: str
    units: list[UnitPriceState]
    conflicts: list[PriceConflict]
    reason: str

    @property
    def qualifying(self) -> list[UnitPriceState]:
        return [u for u in self.units if u.qualifies]


@dataclass
class PropertyStatus:
    status: str
    reasons: list[dict] = field(default_factory=list)
    price: PriceVerification | None = None
    rating: RatingDecision | None = None


def latest_unit_states(session: Session, prop: Property, settings: Settings, now: datetime) -> list[UnitPriceState]:
    rows = session.execute(
        select(PriceObservation, Unit, ListingSource.source_id)
        .join(Unit, PriceObservation.unit_id == Unit.id)
        .join(ListingSource, PriceObservation.listing_source_id == ListingSource.id)
        .where(PriceObservation.property_id == prop.id)
        .order_by(PriceObservation.collected_at.desc(), PriceObservation.id.desc())
    ).all()
    latest_fetch_by_listing: dict[int, datetime] = {}
    seen_units: set[int] = set()
    states = []
    freshness = timedelta(hours=settings.price_freshness_hours)
    source_max_age = timedelta(days=settings.source_update_max_age_days)
    for observation, unit, source_id in rows:
        latest_fetch_by_listing.setdefault(observation.listing_source_id, observation.collected_at)
        if unit.id in seen_units:
            continue
        seen_units.add(unit.id)
        current = observation.collected_at >= latest_fetch_by_listing[observation.listing_source_id]
        states.append(
            UnitPriceState(
                unit=unit,
                observation=observation,
                source_id=source_id,
                current=current,
                fresh=is_price_fresh(observation.collected_at, observation.source_updated_at, now, freshness, source_max_age),
                in_range=is_allowed_unit_type(unit.beds, settings.allowed_bedrooms)
                and rent_in_range(observation.base_rent_min, observation.base_rent_max, settings.min_rent, settings.max_rent),
                restricted=is_restricted_unit(unit.floorplan_name, unit.label),
            )
        )
    return states


def _price_points(states: list[UnitPriceState], allowed_beds: tuple[int, ...]) -> list[PricePoint]:
    grouped: dict[tuple[str, int, int | None], list[UnitPriceState]] = {}
    for state in states:
        obs = state.observation
        if not (state.current and state.fresh) or state.restricted or state.unit.beds not in allowed_beds or obs.base_rent_min is None:
            continue
        grouped.setdefault((state.source_id, state.unit.beds, state.unit.sqft_min), []).append(state)
    points = []
    for (source_id, beds, sqft), group in grouped.items():
        labels = sorted({s.unit.label or s.unit.floorplan_name or "" for s in group} - {""})
        points.append(
            PricePoint(
                source_id=source_id,
                beds=beds,
                sqft=sqft,
                base_min=min(s.observation.base_rent_min for s in group),
                base_max=max(s.observation.base_rent_max or s.observation.base_rent_min for s in group),
                source_url=group[0].observation.source_url,
                label=", ".join(labels[:4]) or None,
            )
        )
    return points


def verify_prices(session: Session, prop: Property, settings: Settings, now: datetime) -> PriceVerification:
    states = latest_unit_states(session, prop, settings, now)
    conflicts = detect_price_conflicts(_price_points(states, settings.allowed_bedrooms))
    qualifying = [s for s in states if s.qualifies]
    if qualifying:
        if conflicts:
            return PriceVerification("conflict", states, conflicts, "Qualifying price found, but sources disagree on comparable units")
        return PriceVerification("verified", states, conflicts, "Fresh studio/1BR price within range")
    if any(s.in_range and s.current and not s.restricted for s in states):
        return PriceVerification("stale", states, conflicts, "Only stale pricing falls within range; re-verification required")
    reason = f"No studio/1BR unit with advertised base rent within ${settings.min_rent:,}–${settings.max_rent:,}"
    if any(s.in_range and s.current and s.restricted for s in states):
        reason += " (in-range units are income-restricted and excluded)"
    return PriceVerification("none", states, conflicts, reason)


def latest_ratings(session: Session, prop: Property) -> list[RatingSummary]:
    rows = session.scalars(
        select(RatingSummary)
        .where(RatingSummary.property_id == prop.id)
        .order_by(RatingSummary.observed_at.desc(), RatingSummary.id.desc())
    ).all()
    latest: dict[str, RatingSummary] = {}
    for row in rows:
        latest.setdefault(row.source_id, row)
    return list(latest.values())


def evaluate_property_status(session: Session, prop: Property, settings: Settings, now: datetime) -> PropertyStatus:
    geo = evaluate_location(prop.city, prop.lat, prop.lon)
    if not geo.allowed:
        return PropertyStatus("excluded", [{"filter": "geography", "explanation": geo.reason}])

    restrictions = [
        r for e in session.scalars(
            select(Evidence).where(Evidence.property_id == prop.id, Evidence.kind == "listing_fact", Evidence.title == "Eligibility restrictions")
        )
        for r in (e.data or {}).get("restrictions", [])
    ]
    website = session.scalars(
        select(Evidence).where(Evidence.property_id == prop.id, Evidence.title == "Official property website")
    ).first()
    hotel = extended_stay_hotel(prop.name, website.source_url if website else None)
    if hotel:
        return PropertyStatus("excluded", [{"filter": "property_type", "explanation": f"Not an apartment — {hotel}"}])
    listing_names = [ls.name for ls in prop.listing_sources if ls.name]
    eligibility = excluded_eligibility(restrictions, " / ".join(dict.fromkeys([prop.name, *listing_names])))
    if eligibility:
        return PropertyStatus("excluded", [{"filter": "eligibility", "explanation": f"Senior or income-restricted housing excluded: {eligibility}"}])

    price = verify_prices(session, prop, settings, now)
    if price.status == "none":
        return PropertyStatus("excluded", [{"filter": "price_and_unit_type", "explanation": price.reason}], price)
    if price.status == "stale":
        return PropertyStatus("needs_reverification", [{"filter": "price_freshness", "explanation": price.reason}], price)

    ratings = latest_ratings(session, prop)
    decision = evaluate_rating_filter(
        [RatingInput(r.source_id, r.average, r.count, r.scale, r.match_confidence) for r in ratings]
    )
    if decision.exclude:
        return PropertyStatus("excluded", [{"filter": "review_rating", "explanation": decision.explanation}], price, decision)
    return PropertyStatus("included", [], price, decision)
