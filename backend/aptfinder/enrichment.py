import logging
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from aptfinder.collectors.google_places import GooglePlacesClient, GooglePlacesError, PropertyQuery
from aptfinder.config import Settings
from aptfinder.db.models import CommuteResult, Evidence, Property
from aptfinder.http import FetchError, PoliteClient
from aptfinder.ids import stable_id
from aptfinder.routing.base import RouteResult
from aptfinder.routing.service import route_many
from aptfinder.safety.area import AreaSafetyData, AreaSafetyRecord, load_area_safety
from aptfinder.store import save_rating, save_reviews

log = logging.getLogger(__name__)

# Neighborhoods that DOF does not list as cities; their crime is reported by the parent city's agency.
SAFETY_CITY_ALIASES = {"alviso": "San Jose"}
OPENJUSTICE_PAGE = "https://openjustice.doj.ca.gov/data"

Note = Callable[[str, str], None]


def _commute_content(route: RouteResult) -> str:
    if route.distance_miles is None or route.free_flow_minutes is None:
        return f"No drivable route found. {route.rush_status}"
    text = f"{route.distance_miles:.1f} miles; {route.free_flow_minutes:.0f} min free-flow driving time (no traffic)"
    if route.am_rush_minutes is not None and route.pm_rush_minutes is not None:
        text += f"; weekday rush hour: {route.am_rush_minutes:.0f} min AM, {route.pm_rush_minutes:.0f} min PM (predicted)"
    else:
        text += f". Rush hour: {route.rush_status}"
    return text


def compute_commutes(session: Session, client: PoliteClient, settings: Settings, props: list[Property], note: Note) -> int:
    located = {p.id: (p.lat, p.lon) for p in props if p.lat is not None and p.lon is not None}
    for prop in props:
        if prop.id not in located:
            note("osrm", f"{prop.name}: no coordinates, so commute could not be computed")
    if not located:
        return 0
    results = route_many(located, settings.office, settings, client)
    by_id = {p.id: p for p in props}
    for property_id, route in results.items():
        prop = by_id[property_id]
        evidence_id = stable_id("ev", "commute", property_id, route.provider, route.origin_lat, route.origin_lon, route.computed_at.isoformat())
        evidence = session.get(Evidence, evidence_id)
        if evidence is None:
            session.add(
                Evidence(
                    id=evidence_id, property_id=property_id, kind="commute_fact", source_id=route.provider,
                    source_url=route.source_url, source_page_url=route.view_url,
                    title=f"Drive to {settings.office_label}", content=_commute_content(route), categories=["commute"],
                    data={
                        "distance_miles": route.distance_miles, "free_flow_minutes": route.free_flow_minutes,
                        "am_rush_minutes": route.am_rush_minutes, "pm_rush_minutes": route.pm_rush_minutes,
                        "rush_status": route.rush_status, "methodology": route.methodology, "confidence": route.confidence,
                        "origin": [route.origin_lat, route.origin_lon], "destination": [route.destination_lat, route.destination_lon],
                    },
                    first_collected_at=route.computed_at, collected_at=route.computed_at,
                )
            )
        session.execute(delete(CommuteResult).where(CommuteResult.property_id == property_id))
        session.add(
            CommuteResult(
                property_id=property_id, provider=route.provider, distance_miles=route.distance_miles,
                free_flow_minutes=route.free_flow_minutes, am_rush_minutes=route.am_rush_minutes,
                pm_rush_minutes=route.pm_rush_minutes, rush_status=route.rush_status, computed_at=route.computed_at,
                source_url=route.source_url, view_url=route.view_url, methodology=route.methodology,
                confidence=route.confidence, evidence_id=evidence_id,
            )
        )
        if route.confidence == "insufficient":
            note(route.provider, f"{prop.name}: {route.rush_status}")
    for property_id in set(located) - set(results):
        note("osrm", f"{by_id[property_id].name}: routing failed; commute unavailable")
    session.commit()
    return len(results)


def _safety_content(record: AreaSafetyRecord) -> str:
    if record.status != "ok":
        return record.reason or "No city-level crime data available."
    ref = record.reference
    return (
        f"{record.jurisdiction}, {record.year}: {record.violent_count:,} violent crimes "
        f"({record.violent_per_1000:.2f} per 1,000 residents) and {record.property_count:,} property crimes "
        f"({record.property_per_1000:.2f} per 1,000), compared with {ref.violent_per_1000:.2f} and "
        f"{ref.property_per_1000:.2f} per 1,000 statewide. Population: {record.population_source}. "
        "City-wide reported crime; not specific to this neighborhood or building."
    )


def attach_area_safety(session: Session, client: PoliteClient, settings: Settings, props: list[Property], note: Note) -> int:
    try:
        data: AreaSafetyData = load_area_safety(settings, client)
    except (FetchError, ValueError, KeyError) as exc:
        note("ca_doj", f"Area safety data could not be loaded: {exc}")
        return 0
    for prop in props:
        city = prop.city or ""
        record = data.lookup(SAFETY_CITY_ALIASES.get(city.lower(), city))
        evidence_id = stable_id("ev", "safety", prop.id, record.jurisdiction or record.city, record.year, record.source_url)
        fields = {
            "property_id": prop.id, "kind": "safety_fact", "source_id": "ca_doj", "source_url": record.source_url,
            "source_page_url": OPENJUSTICE_PAGE, "title": f"Reported crime in {record.jurisdiction or city} ({record.year})",
            "content": _safety_content(record), "categories": ["neighborhood_safety"], "collected_at": record.retrieved_at,
            "data": {
                "has_city_data": record.status == "ok", "status": record.status, "reason": record.reason,
                "jurisdiction": record.jurisdiction or record.city, "year": record.year,
                "violent_count": record.violent_count, "property_count": record.property_count, "population": record.population,
                "violent_per_1000": record.violent_per_1000, "property_per_1000": record.property_per_1000,
                "reference_violent_per_1000": record.reference.violent_per_1000,
                "reference_property_per_1000": record.reference.property_per_1000,
                "reference_label": record.reference.label, "population_source": record.population_source,
                "population_source_url": record.population_source_url, "population_as_of": record.population_as_of.isoformat(),
                "methodology": record.methodology,
            },
        }
        existing = session.get(Evidence, evidence_id)
        if existing is None:
            session.add(Evidence(id=evidence_id, first_collected_at=record.retrieved_at, **fields))
        else:
            for key, value in fields.items():
                setattr(existing, key, value)
        if record.status != "ok":
            note("ca_doj", f"{prop.name}: {record.reason}")
    session.commit()
    return len(props)


def collect_google_reviews(session: Session, settings: Settings, props: list[Property], now: datetime, note: Note) -> int:
    if not settings.google_maps_api_key:
        return 0
    collected = 0
    with GooglePlacesClient(settings.google_maps_api_key) as places:
        for prop in props:
            if prop.lat is None or prop.lon is None:
                continue
            try:
                result = places.collect(PropertyQuery(prop.name, prop.street_address, prop.city, prop.lat, prop.lon))
            except GooglePlacesError as exc:
                note("google_places", f"Stopped Google Places collection: {exc}")
                break
            if result is None:
                note("google_places", f"{prop.name}: no confidently matching Google Maps place")
                continue
            save_reviews(session, prop, "google_places", result.reviews, result.source_url, result.fetched_at)
            save_rating(
                session, prop, "google_places", result.rating, result.source_url, result.fetched_at,
                stable_id("ev", "rating", "google_places", result.match.place_id, result.fetched_at.date().isoformat()),
                match_confidence=result.match.match_confidence,
            )
            session.commit()
            collected += 1
    return collected
