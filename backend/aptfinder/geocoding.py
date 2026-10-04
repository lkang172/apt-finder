import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import combinations
from urllib.parse import quote, urlencode

from aptfinder.geo import haversine_meters
from aptfinder.http import PoliteClient

log = logging.getLogger(__name__)

SOURCE_ID = "census_geocoder"
SOURCE_NAME = "U.S. Census Bureau Geocoder (Public_AR_Current)"
CENSUS_ONELINE_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
BENCHMARK = "Public_AR_Current"
GEOCODE_CACHE_TTL = timedelta(days=90)
AMBIGUOUS_SPREAD_METERS = 250.0
METHODOLOGY = (
    "U.S. Census Bureau geocoder, Public_AR_Current benchmark. Coordinates are interpolated along the "
    "TIGER/Line address range for the matched street segment, so they are approximate (typically within "
    "tens of meters) rather than a surveyed building location."
)

HOUSE_NUMBER = re.compile(r"^\s*(\d+)")


class GeocodingError(Exception):
    pass


@dataclass(frozen=True)
class GeocodeResult:
    lat: float
    lon: float
    matched_address: str
    candidate_count: int
    source: str
    source_url: str
    fetched_at: datetime
    methodology: str


def census_geocode_url(address: str) -> str:
    query = urlencode({"address": address, "benchmark": BENCHMARK, "format": "json"}, quote_via=quote)
    return f"{CENSUS_ONELINE_URL}?{query}"


def geocode_address(address: str, client: PoliteClient) -> GeocodeResult | None:
    url = census_geocode_url(address)
    fetch = client.get(url, ttl=GEOCODE_CACHE_TTL, accept="application/json")
    try:
        payload = json.loads(fetch.text)
    except json.JSONDecodeError as exc:
        raise GeocodingError(f"Census geocoder returned invalid JSON for {url}") from exc
    if "result" not in payload:
        raise GeocodingError(f"Census geocoder error for {url}: {payload.get('errors') or payload}")

    matches = payload["result"].get("addressMatches") or []
    if not matches:
        return None
    points = [(m["coordinates"]["y"], m["coordinates"]["x"]) for m in matches]
    if any(haversine_meters(*a, *b) > AMBIGUOUS_SPREAD_METERS for a, b in combinations(points, 2)):
        log.info("Census geocoder returned %d far-apart candidates for %r; ambiguous", len(matches), address)
        return None

    best = matches[0]
    matched = best["matchedAddress"]
    if _house_number(address) != _house_number(matched):
        log.info("Census geocoder matched %r to %r with a different house number; rejecting", address, matched)
        return None
    return GeocodeResult(
        lat=points[0][0],
        lon=points[0][1],
        matched_address=matched,
        candidate_count=len(matches),
        source=SOURCE_NAME,
        source_url=url,
        fetched_at=fetch.fetched_at,
        methodology=METHODOLOGY,
    )


def _house_number(address: str) -> str | None:
    match = HOUSE_NUMBER.match(address)
    return match.group(1) if match else None
