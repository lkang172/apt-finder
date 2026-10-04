import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from aptfinder.collectors.page_data import as_float, as_int, parse_timestamp
from aptfinder.collectors.types import CollectedRating, CollectedReview
from aptfinder.geo import haversine_meters
from aptfinder.ids import stable_id
from aptfinder.normalize import normalize_street_address

log = logging.getLogger(__name__)

SOURCE_ID = "google_places"
SOURCE_NAME = "Google Maps (Places API)"
TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
SEARCH_FIELD_MASK = "places.id,places.displayName,places.formattedAddress,places.location"
DETAILS_FIELD_MASK = "rating,userRatingCount,reviews,googleMapsUri,reviewSummary"
MAX_MATCH_METERS = 150.0
PROBABLE_MAX_METERS = 75.0
# Large complexes are often pinned at a leasing office a few hundred meters from a listing's coordinates;
# an identical street address is strong enough evidence to accept those farther pins.
ADDRESS_MATCH_MAX_METERS = 500.0
SEARCH_BIAS_RADIUS_METERS = 500.0
STRONG_NAME_OVERLAP = 0.6
RATING_NOTE = (
    "Average and count cover all Google reviews of the place; the Places API returns at most five "
    "individual reviews, chosen by Google's relevance ranking."
)
GENERIC_NAME_TOKENS = frozenset(
    "the at of and on a apartment apartments apts apt homes residences residence community communities "
    "living rentals ca california".split()
)
TOKEN = re.compile(r"[a-z0-9]+")
STREET_NUMBER = re.compile(r"^\s*(\d+)")


class GooglePlacesError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code

    @property
    def is_fatal(self) -> bool:
        return self.status_code in (400, 401, 403, 429)


@dataclass(frozen=True)
class GoogleReviewSummary:
    text: str
    disclosure: str | None
    flag_url: str | None
    reviews_url: str | None


@dataclass(frozen=True)
class PropertyQuery:
    name: str
    street_address: str | None
    city: str | None
    lat: float
    lon: float

    @property
    def text(self) -> str:
        return ", ".join(p for p in (self.name, self.street_address, self.city, "CA") if p)


@dataclass(frozen=True)
class PlaceMatch:
    place_id: str
    display_name: str
    formatted_address: str | None
    lat: float
    lon: float
    distance_meters: float
    street_number_matches: bool
    name_overlap: float
    match_confidence: str


@dataclass
class GooglePlaceReviews:
    match: PlaceMatch
    rating: CollectedRating
    reviews: list[CollectedReview]
    source_url: str | None
    fetched_at: datetime
    notes: list[str] = field(default_factory=list)
    summary: GoogleReviewSummary | None = None


def evaluate_candidate(query: PropertyQuery, place: dict[str, Any]) -> PlaceMatch | None:
    location = place.get("location") or {}
    lat, lon = as_float(location.get("latitude")), as_float(location.get("longitude"))
    place_id = place.get("id")
    if lat is None or lon is None or not place_id:
        return None
    distance = haversine_meters(query.lat, query.lon, lat, lon)
    display_name = (place.get("displayName") or {}).get("text") or ""
    formatted_address = place.get("formattedAddress")
    our_number = _street_number(query.street_address)
    number_matches = our_number is not None and our_number == _street_number(formatted_address)
    overlap = name_overlap(query.name, display_name, query.city)
    strong_name = overlap >= STRONG_NAME_OVERLAP
    our_street = normalize_street_address(query.street_address)
    street_matches = our_street is not None and our_street == normalize_street_address((formatted_address or "").split(",")[0])
    if distance > MAX_MATCH_METERS:
        if not street_matches or distance > ADDRESS_MATCH_MAX_METERS:
            return None
        confidence = "exact" if strong_name else "probable"
        return PlaceMatch(place_id, display_name, formatted_address, lat, lon, round(distance, 1), True, overlap, confidence)
    if not (number_matches or strong_name):
        return None
    if number_matches and strong_name:
        confidence = "exact"
    elif distance <= PROBABLE_MAX_METERS:
        confidence = "probable"
    else:
        confidence = "weak"
    return PlaceMatch(
        place_id, display_name, formatted_address, lat, lon, round(distance, 1), number_matches, overlap, confidence
    )


def name_overlap(property_name: str, place_name: str, city: str | None) -> float:
    ignored = GENERIC_NAME_TOKENS | set(_tokens(city or ""))
    ours = set(_tokens(property_name)) - ignored
    theirs = set(_tokens(place_name)) - ignored
    shared = {t for t in ours & theirs if not t.isdigit()}
    if not shared:
        return 0.0
    return round(len(shared) / min(len(ours), len(theirs)), 2)


def parse_details(payload: dict[str, Any], place_id: str) -> tuple[CollectedRating, list[CollectedReview], str | None]:
    maps_uri = payload.get("googleMapsUri")
    rating = CollectedRating(
        average=as_float(payload.get("rating")),
        count=as_int(payload.get("userRatingCount")) or 0,
        scale=5.0,
        source_url=maps_uri,
        note=RATING_NOTE,
    )
    reviews = [_review(item, place_id) for item in payload.get("reviews") or []]
    return rating, reviews, maps_uri


def parse_review_summary(payload: dict[str, Any]) -> GoogleReviewSummary | None:
    summary = payload.get("reviewSummary") or {}
    text = ((summary.get("text") or {}).get("text") or "").strip()
    if not text:
        return None
    return GoogleReviewSummary(
        text=text,
        disclosure=((summary.get("disclosureText") or {}).get("text") or None),
        flag_url=summary.get("flagContentUri"),
        reviews_url=summary.get("reviewsUri"),
    )


class GooglePlacesClient:
    def __init__(self, api_key: str, transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise ValueError("Google Places requires an API key")
        self._http = httpx.Client(
            timeout=httpx.Timeout(30.0),
            transport=transport,
            headers={"X-Goog-Api-Key": api_key},
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "GooglePlacesClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def find_place(self, query: PropertyQuery) -> PlaceMatch | None:
        body = {
            "textQuery": query.text,
            "languageCode": "en",
            "locationBias": {
                "circle": {
                    "center": {"latitude": query.lat, "longitude": query.lon},
                    "radius": SEARCH_BIAS_RADIUS_METERS,
                }
            },
        }
        payload = self._request("POST", TEXT_SEARCH_URL, SEARCH_FIELD_MASK, json=body)
        matches = [m for m in (evaluate_candidate(query, p) for p in payload.get("places") or []) if m]
        rank = {"exact": 0, "probable": 1, "weak": 2}
        return min(matches, key=lambda m: (rank[m.match_confidence], m.distance_meters), default=None)

    def fetch_reviews(self, match: PlaceMatch) -> GooglePlaceReviews:
        url = PLACE_DETAILS_URL.format(place_id=match.place_id)
        payload = self._request("GET", url, DETAILS_FIELD_MASK, params={"languageCode": "en"})
        rating, reviews, maps_uri = parse_details(payload, match.place_id)
        notes = [] if maps_uri else ["Google did not return a Maps URL for this place; Source URL unavailable."]
        return GooglePlaceReviews(match, rating, reviews, maps_uri, datetime.now(UTC), notes, parse_review_summary(payload))

    def collect(self, query: PropertyQuery) -> GooglePlaceReviews | None:
        match = self.find_place(query)
        if match is None:
            log.info("No Google place within %.0f m matched %r", MAX_MATCH_METERS, query.text)
            return None
        return self.fetch_reviews(match)

    def _request(self, method: str, url: str, field_mask: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._http.request(method, url, headers={"X-Goog-FieldMask": field_mask}, **kwargs)
        except httpx.HTTPError as exc:
            raise GooglePlacesError(f"{method} {url} failed: {exc.__class__.__name__}") from exc
        if response.status_code != 200:
            raise GooglePlacesError(f"{method} {url} returned HTTP {response.status_code}: {_error_message(response)}", response.status_code)
        return response.json()


def _review(item: dict[str, Any], place_id: str) -> CollectedReview:
    author = item.get("authorAttribution") or {}
    original = item.get("originalText") or {}
    translated = item.get("text") or {}
    text = original.get("text") or translated.get("text") or ""
    publish_time = item.get("publishTime")
    extra: dict[str, Any] = {
        "reviewer_url": author.get("uri"),
        "publish_time": publish_time,
        "relative_publish_time": item.get("relativePublishTimeDescription"),
        "language": original.get("languageCode") or translated.get("languageCode"),
    }
    if original.get("text") and translated.get("text") and translated["text"] != original["text"]:
        extra["translated_text"] = translated["text"]
    return CollectedReview(
        source_review_key=item.get("name") or stable_id("gpr", place_id, author.get("displayName"), publish_time, text),
        reviewer=author.get("displayName"),
        rating=as_float(item.get("rating")),
        review_date=parse_timestamp(publish_time),
        text=text,
        review_url=item.get("googleMapsUri"),
        extra={k: v for k, v in extra.items() if v is not None},
    )


def _tokens(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


def _street_number(address: str | None) -> str | None:
    match = STREET_NUMBER.match(address or "")
    return match.group(1) if match else None


def _error_message(response: httpx.Response) -> str:
    try:
        return str(response.json()["error"]["message"])
    except (ValueError, KeyError, TypeError):
        return response.reason_phrase or "unknown error"
