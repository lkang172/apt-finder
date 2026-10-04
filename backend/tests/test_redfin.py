import gzip
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aptfinder.collectors.redfin import parse_building_page, parse_search_page
from aptfinder.http import FetchResult

FIXTURES = Path(__file__).parent / "fixtures"
FETCH = FetchResult("u", "u", 200, "", datetime(2026, 10, 3, tzinfo=UTC), False, "sha", "path")
BUILDING_URL = "https://www.redfin.com/CA/Sunnyvale/720-N-Fair-Oaks-Ave-94085/apartment/1210629"


def load(name: str) -> str:
    return gzip.decompress((FIXTURES / f"{name}.html.gz").read_bytes()).decode()


@pytest.fixture(scope="module")
def building():
    return parse_building_page(load("rf_bldg"), BUILDING_URL, FETCH)


def test_search_page_stubs_use_min_price_as_lower_bound():
    stubs = {s.source_listing_id: s for s in parse_search_page(load("rf_sunnyvale"))}
    north = stubs["1210629"]
    assert north.name == "720 North Apartments"
    assert north.min_price_by_beds == {0: 2185, 1: 2185}
    assert north.lat == pytest.approx(37.39195)
    assert all(s.url.startswith("https://www.redfin.com/") for s in stubs.values())


def test_two_bedroom_only_listing_fails_prefilter():
    stubs = {s.source_listing_id: s for s in parse_search_page(load("rf_sunnyvale"))}
    assert not stubs["1487048"].may_have_qualifying_unit((0, 1), 3000)


def test_building_units_are_unit_level_base_rent(building):
    assert building.street_address == "720 N Fair Oaks Ave" and building.zip == "94085"
    studio = next(u for u in building.units if u.label == "639-28")
    assert studio.beds == 0 and studio.sqft_min == 500
    assert studio.base_rent_min == studio.base_rent_max == 2185
    assert studio.total_monthly is None
    assert studio.source_updated_at == datetime(2026, 10, 3, 13, 0, 32, 482199, tzinfo=UTC)


def test_building_never_constructs_image_urls(building):
    assert building.image_url is None


def test_building_fees_and_provenance(building):
    assert any(f.amount == 50 and f.recurring is False for f in building.fees)
    feed = next(f for f in building.facts if f.key == "feed_source")
    assert "RentPath" in feed.content


def test_total_price_listings_do_not_report_base_rent():
    html = load("rf_bldg").replace('\\"isTotalPrice\\": false', '\\"isTotalPrice\\": true')
    listing = parse_building_page(html, BUILDING_URL, FETCH)
    assert listing.units and all(u.base_rent_min is None and u.total_monthly for u in listing.units)
