import json
from pathlib import Path

import httpx
import pytest

from aptfinder.geocoding import GeocodingError, census_geocode_url, geocode_address
from aptfinder.http import PoliteClient

FIXTURES = Path(__file__).parent / "fixtures"
OFFICE_ADDRESS = "242 Humboldt Ct, Sunnyvale, CA 94089"


def census_client(tmp_path, payload, seen: list[httpx.Request] | None = None) -> PoliteClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, json=payload)

    return PoliteClient(tmp_path, "test-agent", transport=httpx.MockTransport(handler), sleep=lambda _s: None)


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_census_url_encodes_the_one_line_address():
    assert census_geocode_url(OFFICE_ADDRESS) == (
        "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
        "?address=242%20Humboldt%20Ct%2C%20Sunnyvale%2C%20CA%2094089&benchmark=Public_AR_Current&format=json"
    )


def test_match_returns_coordinates_and_provenance(tmp_path):
    seen: list[httpx.Request] = []
    result = geocode_address(OFFICE_ADDRESS, census_client(tmp_path, fixture("geo_match.json"), seen))
    assert result is not None
    assert (result.lat, result.lon) == (37.408084124783, -122.018319487984)
    assert result.matched_address == "242 HUMBOLDT CT, SUNNYVALE, CA, 94089"
    assert result.source_url == census_geocode_url(OFFICE_ADDRESS) == str(seen[0].url)
    assert result.fetched_at.tzinfo is not None
    assert "interpolated" in result.methodology
    assert result.candidate_count == 1


def test_no_match_returns_none(tmp_path):
    client = census_client(tmp_path, fixture("geo_nomatch.json"))
    assert geocode_address("99999 Nowhere Blvd, Faketown, CA", client) is None


def test_different_house_number_is_rejected(tmp_path):
    payload = fixture("geo_match.json")
    payload["result"]["addressMatches"][0]["matchedAddress"] = "240 HUMBOLDT CT, SUNNYVALE, CA, 94089"
    assert geocode_address(OFFICE_ADDRESS, census_client(tmp_path, payload)) is None


def test_far_apart_candidates_are_ambiguous(tmp_path):
    payload = fixture("geo_match.json")
    other = json.loads(json.dumps(payload["result"]["addressMatches"][0]))
    other["coordinates"] = {"x": -121.9, "y": 37.3}
    payload["result"]["addressMatches"].append(other)
    assert geocode_address(OFFICE_ADDRESS, census_client(tmp_path, payload)) is None


def test_repeat_lookups_use_the_cache(tmp_path):
    seen: list[httpx.Request] = []
    client = census_client(tmp_path, fixture("geo_match.json"), seen)
    geocode_address(OFFICE_ADDRESS, client)
    geocode_address(OFFICE_ADDRESS, client)
    assert len(seen) == 1


def test_error_payload_raises(tmp_path):
    with pytest.raises(GeocodingError):
        geocode_address(OFFICE_ADDRESS, census_client(tmp_path, {"errors": ["Address cannot be empty"]}))
