import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from aptfinder.collectors.google_places import (
    DETAILS_FIELD_MASK,
    SEARCH_FIELD_MASK,
    TEXT_SEARCH_URL,
    GooglePlacesClient,
    GooglePlacesError,
    PropertyQuery,
    evaluate_candidate,
    name_overlap,
)

FIXTURES = Path(__file__).parent / "fixtures"
API_KEY = "test-key-should-never-leak"
QUERY = PropertyQuery("Example Gardens Apartments", "1200 Example Ave", "Sunnyvale", 37.37, -122.03)


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def places_client(seen: list[httpx.Request], search: dict, details: dict | None = None) -> GooglePlacesClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if str(request.url) == TEXT_SEARCH_URL:
            return httpx.Response(200, json=search)
        return httpx.Response(200, json=details or {})

    return GooglePlacesClient(API_KEY, transport=httpx.MockTransport(handler))


def place(name: str, address: str, lat: float, lon: float) -> dict:
    return {
        "id": "SYNTHETIC",
        "displayName": {"text": name},
        "formattedAddress": address,
        "location": {"latitude": lat, "longitude": lon},
    }


def test_collect_finds_the_nearby_matching_place_and_maps_reviews():
    seen: list[httpx.Request] = []
    with places_client(seen, fixture("places_text_search.json"), fixture("places_details.json")) as client:
        result = client.collect(QUERY)

    search, details = seen
    body = json.loads(search.content)
    assert search.method == "POST" and search.headers["x-goog-fieldmask"] == SEARCH_FIELD_MASK
    assert body["textQuery"] == "Example Gardens Apartments, 1200 Example Ave, Sunnyvale, CA"
    assert body["locationBias"]["circle"]["center"] == {"latitude": 37.37, "longitude": -122.03}
    assert details.method == "GET"
    assert details.url.path == "/v1/places/SYNTHETIC_MATCH"
    assert details.headers["x-goog-fieldmask"] == DETAILS_FIELD_MASK
    assert all(request.headers["x-goog-api-key"] == API_KEY for request in seen)
    assert all(API_KEY not in str(request.url) for request in seen)

    assert result is not None
    assert result.match.place_id == "SYNTHETIC_MATCH"
    assert result.match.match_confidence == "exact"
    assert result.match.distance_meters < 20
    assert result.source_url == "https://maps.google.com/?cid=0000000000000000001"
    assert result.rating.average == 3.9 and result.rating.count == 87 and result.rating.scale == 5.0
    assert result.rating.source_url == result.source_url
    assert "at most five" in result.rating.note

    first, second = result.reviews
    assert first.source_review_key == "places/SYNTHETIC_MATCH/reviews/SYNTHETIC_REVIEW_1"
    assert first.reviewer == "Synthetic Reviewer One"
    assert first.rating == 2.0
    assert first.review_date == datetime(2026, 8, 1, 17, 4, 5, 123456, tzinfo=UTC)
    assert first.text == "Synthetic review: packages went missing twice."
    assert first.review_url.startswith("https://www.google.com/maps/reviews/")
    assert first.extra["reviewer_url"] == "https://www.google.com/maps/contrib/000000000000000000001/reviews"


def test_review_without_a_returned_url_gets_none_and_keeps_original_text():
    seen: list[httpx.Request] = []
    with places_client(seen, fixture("places_text_search.json"), fixture("places_details.json")) as client:
        second = client.collect(QUERY).reviews[1]
    assert second.review_url is None
    assert "reviewer_url" not in second.extra
    assert second.text == "Reseña sintética: tranquilo y bien administrado."
    assert second.extra["translated_text"] == "Synthetic review: quiet and well managed."
    assert second.extra["language"] == "es"


def test_no_candidate_within_range_returns_none_without_fetching_details():
    seen: list[httpx.Request] = []
    far = {"places": [place("Example Gardens", "1200 Example Ave, Sunnyvale, CA", 37.3760, -122.03)]}
    with places_client(seen, far) as client:
        assert client.collect(QUERY) is None
    assert len(seen) == 1


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        (place("Example Gardens", "1200 Example Ave, Sunnyvale, CA", 37.3701, -122.0301), "exact"),
        (place("Example Gardens", "1250 Example Ave, Sunnyvale, CA", 37.3704, -122.03), "probable"),
        (place("Leasing Office", "1200 Example Ave, Sunnyvale, CA", 37.3711, -122.03), "weak"),
        (place("Sunnyvale Self Storage", "1210 Example Ave, Sunnyvale, CA", 37.3703, -122.0302), None),
        (place("Example Gardens", "1200 Example Ave, Sunnyvale, CA", 37.3760, -122.03), None),
    ],
)
def test_match_confidence_requires_proximity_and_address_or_name(candidate, expected):
    match = evaluate_candidate(QUERY, candidate)
    assert (match.match_confidence if match else None) == expected


def test_name_overlap_ignores_generic_words_and_city_names():
    assert name_overlap("The Arches Apartments", "Arches", "Sunnyvale") == 1.0
    assert name_overlap("Avalon Mountain View", "Mountain View Apartments", "Mountain View") == 0.0
    assert name_overlap("Eaves Mountain View at Middlefield", "eaves at Middlefield", "Mountain View") == 1.0


def test_details_without_rating_report_zero_count_not_a_score():
    seen: list[httpx.Request] = []
    with places_client(seen, fixture("places_text_search.json"), {}) as client:
        result = client.collect(QUERY)
    assert result.rating.average is None and result.rating.count == 0
    assert result.reviews == []
    assert result.source_url is None
    assert "Source URL unavailable" in result.notes[0]


def test_api_errors_raise_with_google_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"code": 403, "message": "Places API (New) has not been used"}})

    with GooglePlacesClient(API_KEY, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GooglePlacesError, match="HTTP 403: Places API"):
            client.collect(QUERY)


def test_same_street_address_accepted_beyond_150_m():
    from aptfinder.collectors.google_places import PropertyQuery, evaluate_candidate

    query = PropertyQuery("Eaves Creekside", "151 Calderon Avenue", "Mountain View", 37.391011, -122.071772)
    place = {"id": "p1", "displayName": {"text": "eaves Creekside"}, "formattedAddress": "151 Calderon Ave, Mountain View, CA 94041, USA",
             "location": {"latitude": 37.392711, "longitude": -122.071772}}
    match = evaluate_candidate(query, place)
    assert match is not None and match.match_confidence == "exact" and 150 < match.distance_meters < 500

    different_street = {**place, "formattedAddress": "300 Other St, Mountain View, CA 94041, USA"}
    assert evaluate_candidate(query, different_street) is None
    too_far = {**place, "location": {"latitude": 37.3990, "longitude": -122.071772}}
    assert evaluate_candidate(query, too_far) is None
