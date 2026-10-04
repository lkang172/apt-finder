import gzip
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.robotparser import RobotFileParser

import httpx
import pytest

from aptfinder.collectors.trulia import (
    TruliaCollector,
    parse_building_page,
    parse_search_page,
)
from aptfinder.collectors.types import DiscoveryStub
from aptfinder.config import SEARCH_CITIES
from aptfinder.http import FetchResult, PoliteClient, SourceBlocked, parse_robots, robots_allows

FIXTURES = Path(__file__).parent / "fixtures"
FETCH = FetchResult("u", "u", 200, "", datetime(2026, 10, 4, tzinfo=UTC), False, "sha", "path")
ROBOTS = (FIXTURES / "trulia_robots.txt").read_text()
WINDEMERE_URL = "https://www.trulia.com/building/windemere-apartments-395-ano-nuevo-ave-sunnyvale-ca-94085-1001482995"
MARIPOSA_URL = "https://www.trulia.com/building/mariposa-631-mariposa-ave-mountain-view-ca-94041-2082716176"
CROSSINGS_URL = "https://www.trulia.com/building/the-crossings-apartments-1180-lochinvar-ave-sunnyvale-ca-94087-1001483222"
BLAIR_URL = "https://www.trulia.com/home/8-blair-ave-sunnyvale-ca-94087-2087793870"
SEARCH_PATH = "/for_rent/Sunnyvale,CA/0-1_beds/0-3150_price/"
SUNNYVALE = next(c for c in SEARCH_CITIES if c.name == "Sunnyvale")


def load(name: str) -> str:
    return gzip.decompress((FIXTURES / f"{name}.html.gz").read_bytes()).decode()


def stubs_by_id(name: str) -> dict[str, DiscoveryStub]:
    return {s.source_listing_id: s for s in parse_search_page(load(name))[0]}


@pytest.fixture(scope="module")
def windemere():
    return parse_building_page(load("trulia_windemere"), WINDEMERE_URL, FETCH)


@pytest.fixture(scope="module")
def crossings():
    return parse_building_page(load("trulia_crossings"), CROSSINGS_URL, FETCH)


@pytest.fixture(scope="module")
def blair():
    return parse_building_page(load("trulia_home_blair"), BLAIR_URL, FETCH)


def test_search_page_stubs_and_page_count():
    stubs, pages = parse_search_page(load("trulia_search_p1"))
    assert len(stubs) == 40 and pages == 2
    windemere = next(s for s in stubs if s.source_listing_id == "building:1001482995")
    assert windemere.url == WINDEMERE_URL
    assert windemere.min_price_by_beds == {1: 2850}
    assert windemere.lat == pytest.approx(37.390606) and windemere.lon == pytest.approx(-122.04524)
    assert windemere.city == "Sunnyvale"
    north = next(s for s in stubs if s.source_listing_id == "building:1001487502")
    assert north.name == "720 North Apartments" and north.min_price_by_beds == {0: 2185, 1: 2185}
    blair = next(s for s in stubs if s.source_listing_id == "home:2087793870")
    assert blair.url == BLAIR_URL and blair.min_price_by_beds == {1: 2600}


def test_page_two_skips_rooms_for_rent_and_maps_studios():
    stubs, pages = parse_search_page(load("trulia_search_p2"))
    ids = {s.source_listing_id for s in stubs}
    assert len(stubs) == 23 and pages == 2
    assert "home:2070765866" not in ids
    studio = next(s for s in stubs if s.source_listing_id == "home:2091411307")
    assert studio.min_price_by_beds == {0: 2050}
    assert not ids & set(stubs_by_id("trulia_search_p1"))


def test_card_prices_are_filtered_per_unit_so_no_lower_bound_is_needed():
    narrow = stubs_by_id("trulia_search_2100_3000")["building:1001478579"]
    wide = stubs_by_id("trulia_search_p1")["building:1001478579"]
    assert narrow.min_price_by_beds == {0: 2224}
    assert wide.min_price_by_beds == {0: 1612}


def test_prefilter_is_a_safe_lower_bound():
    stubs = stubs_by_id("trulia_search_p1") | stubs_by_id("trulia_search_p2")
    assert not stubs["building:1001478832"].may_have_qualifying_unit((0, 1), 3000)
    assert stubs["building:1001478832"].may_have_qualifying_unit((0, 1), 3150)
    assert stubs["building:1001487729"].may_have_qualifying_unit((0, 1), 3000)
    assert stubs["home:458775208"].min_price_by_beds == {0: 1200}
    for stub in stubs.values():
        assert stub.may_have_qualifying_unit((0, 1), 3150), stub.source_listing_id


def test_card_without_bedrooms_falls_back_to_searched_range():
    studio = '"bedrooms":{"formattedValue":"Studio","__typename":"HOME_StudioBedroom"}'
    html = load("trulia_search_p1")
    assert studio in html
    stubs = {s.source_listing_id: s for s in parse_search_page(html.replace(studio, '"bedrooms":null'))[0]}
    assert stubs["home:458775208"].min_price_by_beds == {0: 1200, 1: 1200}


def test_building_identity_and_location(windemere):
    assert windemere.source_id == "trulia" and windemere.source_listing_id == "building:1001482995"
    assert windemere.url == WINDEMERE_URL and windemere.name == "Windemere Apartments"
    assert (windemere.street_address, windemere.city, windemere.state, windemere.zip) == ("395 Ano Nuevo Ave", "Sunnyvale", "CA", "94085")
    assert windemere.lat == pytest.approx(37.390606379063)
    assert windemere.source_updated_at == datetime(2026, 8, 11, tzinfo=UTC)


def test_building_units_are_unit_level_base_rent(windemere):
    one_bed = next(u for u in windemere.units if u.label == "218")
    assert one_bed.kind == "unit" and one_bed.source_unit_key == "unit:465520846"
    assert one_bed.floorplan_name == "Upstairs 1 Bedroom"
    assert (one_bed.beds, one_bed.baths, one_bed.sqft_min, one_bed.sqft_max) == (1, 1.0, 710, 710)
    assert one_bed.base_rent_min == one_bed.base_rent_max == 2850 and one_bed.total_monthly is None
    assert one_bed.available_on == "2026-12-02" and one_bed.availability == "Available Dec 2"
    assert one_bed.source_updated_at == datetime(2026, 8, 11, tzinfo=UTC)
    two_bed = next(u for u in windemere.units if u.label == "502")
    assert two_bed.beds == 2 and two_bed.base_rent_min == 3550


def test_image_comes_only_from_structured_data(windemere):
    assert windemere.image_url == "https://www.trulia.com/pictures/thumbs_5/zillowstatic/fp/1c9e84246d6acf8859593a1f3b8fde03-f_b.jpg"
    html = load("trulia_windemere").replace('"@type":"Product"', '"@type":"NotAProduct"')
    assert parse_building_page(html, WINDEMERE_URL, FETCH).image_url is None


def test_contact_for_details_fees_never_get_amounts(windemere):
    application = next(f for f in windemere.fees if f.description.startswith("Application fee"))
    assert application.amount is None and application.amount_text is None
    assert application.recurring is False and application.mandatory is True
    assert "Contact for details" in application.description
    mariposa = parse_building_page(load("trulia_mariposa"), MARIPOSA_URL, FETCH)
    assert [f.description for f in mariposa.fees] == ["Security deposit (required one-time fee): Contact for details"]


def test_rent_rows_in_fee_breakdown_are_not_fees(windemere, crossings):
    for listing in (windemere, crossings):
        assert not any(f.description.lower().startswith(("rent ", "monthly base rent")) for f in listing.fees)


def test_required_and_optional_fee_sections(crossings):
    fees = {f.description.split(" (")[0]: f for f in crossings.fees}
    pest = fees["Pest Control Services"]
    assert pest.recurring is True and pest.mandatory is True and pest.amount is None
    deposit = next(f for f in crossings.fees if f.description.startswith("Security Deposit"))
    assert deposit.amount is None and deposit.amount_text == "$600–$800" and deposit.recurring is False
    pet_rent = fees["Pet Rent"]
    assert pet_rent.fee_type == "pet" and pet_rent.mandatory is False and pet_rent.recurring is True


def test_stated_required_monthly_fee_is_mandatory_and_recurring():
    html = load("trulia_crossings").replace(
        '"displayValue":"Trash Services - CA","amount":{"displayText":"Varies"',
        '"displayValue":"Trash Services - CA","amount":{"displayText":"$25"',
    )
    trash = next(f for f in parse_building_page(html, CROSSINGS_URL, FETCH).fees if f.fee_type == "trash")
    assert (trash.amount, trash.amount_text, trash.recurring, trash.mandatory) == (25, "$25", True, True)


def test_total_price_listings_do_not_report_base_rent(crossings):
    unit = next(u for u in crossings.units if u.label == "059")
    assert unit.base_rent_min is None and unit.base_rent_max is None
    assert unit.total_monthly == 2968
    assert unit.floorplan_name == "One Bedroom, One Bath Income Restricted"
    assert all(u.base_rent_min is None for u in crossings.units)
    assert any("total monthly prices" in n for n in crossings.notes)
    disclosure = next(f for f in crossings.facts if f.key == "pricing_disclosure")
    assert "base rent ($2,958–$4,095)" in disclosure.content


def test_unknown_price_basis_records_no_prices():
    html = load("trulia_windemere").replace('"isTotalMonthlyFeeIncluded":false', '"isTotalMonthlyFeeIncluded":null')
    listing = parse_building_page(html, WINDEMERE_URL, FETCH)
    assert listing.units == [] and any("did not state" in n for n in listing.notes)


def test_special_offer_disclosures_are_not_promotions(crossings):
    assert crossings.promotions == []
    disclosure = next(f for f in crossings.facts if f.key == "pricing_disclosure")
    assert "Total monthly leasing prices include base rent" in disclosure.content


def test_specials_are_kept_verbatim():
    html = load("trulia_windemere").replace(
        '"specialOffers":null',
        '"specialOffers":[{"description":"Up to 6 weeks free on select units","subText":"Restrictions apply.","__typename":"HOME_SpecialOffers"}]',
    )
    listing = parse_building_page(html, WINDEMERE_URL, FETCH)
    assert listing.promotions == ["Up to 6 weeks free on select units — Restrictions apply."]


def test_income_restricted_tag_becomes_eligibility_fact(crossings, windemere):
    fact = next(f for f in crossings.facts if f.key == "eligibility")
    assert fact.title == "Eligibility restrictions" and fact.data["restrictions"] == ["Income Restricted"]
    assert not any(f.key == "eligibility" for f in windemere.facts)


def test_pet_units_and_freshness_facts(windemere):
    facts = {f.key: f for f in windemere.facts}
    assert facts["pet_policy"].content.startswith("Cats allowed")
    assert facts["units_available"].data == {"available": 2, "total_units": 260}
    assert facts["source_last_modified"].data["last_modified"] == "2026-08-11T00:00:00+00:00"


def test_feed_provenance_is_recorded(windemere, blair):
    building = next(f for f in windemere.facts if f.key == "feed_provenance")
    assert building.data["network"] == "Zillow Group" and building.data["independent_source"] is False
    home = next(f for f in blair.facts if f.key == "feed_provenance")
    assert "Zillow Rentals" in home.data["price_history_sources"] and "N/A" not in home.data["price_history_sources"]
    assert home.data["zpid"] == "2087793870"


def test_single_unit_home_page(blair):
    assert blair.source_listing_id == "home:2087793870" and blair.street_address == "8 Blair Ave"
    assert blair.name == "8 Blair Ave" and blair.zip == "94087"
    [unit] = blair.units
    assert unit.kind == "unit" and unit.label is None
    assert (unit.beds, unit.baths, unit.sqft_min) == (1, 1.0, 750)
    assert unit.base_rent_min == unit.base_rent_max == 2600 and unit.availability == "Available now"
    deposit = next(f for f in blair.fees if f.fee_type == "deposit")
    assert deposit.amount == 2000 and deposit.recurring is False and deposit.mandatory is True
    assert any("Single-unit listing" in n for n in blair.notes)


def test_off_market_home_records_no_price():
    html = load("trulia_home_blair").replace('"isActiveForRent":true', '"isActiveForRent":false')
    listing = parse_building_page(html, BLAIR_URL, FETCH)
    assert listing.units == [] and any("no longer for rent" in n for n in listing.notes)


def test_page_for_a_different_listing_is_rejected():
    assert parse_building_page(load("trulia_windemere"), CROSSINGS_URL, FETCH) is None
    assert parse_building_page("<html></html>", WINDEMERE_URL, FETCH) is None


def test_robots_rules_follow_rfc_9309_where_urllib_does_not():
    stdlib = RobotFileParser()
    stdlib.parse(ROBOTS.splitlines())
    assert stdlib.can_fetch("Mozilla/5.0", "https://www.trulia.com/api/x")
    rules = parse_robots(ROBOTS, "Mozilla/5.0")
    assert not robots_allows(rules, "https://www.trulia.com/api/x")
    assert not robots_allows(rules, "https://www.trulia.com/building/some-building_li")
    assert not robots_allows(rules, "https://www.trulia.com/for_rent/Sunnyvale,CA/37.3,-122.0_xy/")
    assert not robots_allows(rules, "https://www.trulia.com/pictures/x.jpg")
    assert robots_allows(rules, "https://www.trulia.com/pictures/thumbs_5/zillowstatic/fp/x.jpg")
    assert robots_allows(rules, "https://www.trulia.com" + SEARCH_PATH + "2_p/")
    assert robots_allows(rules, WINDEMERE_URL) and robots_allows(rules, BLAIR_URL)


def test_search_urls():
    collector = TruliaCollector(client=None, listing_ttl=timedelta(hours=12), max_pages=3, max_rent=3000)
    assert collector.search_url(SUNNYVALE) == "https://www.trulia.com" + SEARCH_PATH
    assert collector.search_url(SUNNYVALE, 2) == "https://www.trulia.com" + SEARCH_PATH + "2_p/"
    mountain_view = next(c for c in SEARCH_CITIES if c.name == "Mountain View")
    assert collector.search_url(mountain_view).startswith("https://www.trulia.com/for_rent/Mountain_View,CA/")


class FakeTime:
    def __init__(self):
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def make_collector(tmp_path, pages: dict[str, str], max_pages: int = 3, status: int = 200):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        if request.url.path in pages:
            return httpx.Response(status, text=pages[request.url.path])
        return httpx.Response(404, text="not found")

    fake = FakeTime()
    client = PoliteClient(
        tmp_path, "test-agent", min_intervals={"www.trulia.com": 15.0},
        transport=httpx.MockTransport(handler), sleep=fake.sleep, clock=fake.clock,
    )
    return TruliaCollector(client, timedelta(hours=12), max_pages=max_pages, max_rent=3000), calls


def test_discover_and_fetch_end_to_end(tmp_path):
    collector, calls = make_collector(tmp_path, {
        SEARCH_PATH: load("trulia_search_p1"),
        SEARCH_PATH + "2_p/": load("trulia_search_p2"),
        urlpath(WINDEMERE_URL): load("trulia_windemere"),
    })
    stubs = list(collector.discover(SUNNYVALE))
    assert len(stubs) == 63 and len({s.source_listing_id for s in stubs}) == 63
    assert calls.count(SEARCH_PATH) == 1 and calls.count(SEARCH_PATH + "2_p/") == 1
    assert SEARCH_PATH + "3_p/" not in calls
    stub = next(s for s in stubs if s.source_listing_id == "building:1001482995")
    listing = collector.fetch_listing(stub)
    assert listing.source_listing_id == stub.source_listing_id and listing.url == WINDEMERE_URL
    assert next(u for u in listing.units if u.label == "218").base_rent_min == 2850
    assert listing.fetch.status == 200 and not listing.fetch.from_cache


def test_pagination_stops_when_a_page_adds_nothing_new(tmp_path):
    first = load("trulia_search_p1").replace('"totalHomes":64', '"totalHomes":400')
    collector, calls = make_collector(tmp_path, {SEARCH_PATH: first, SEARCH_PATH + "2_p/": first})
    assert len(list(collector.discover(SUNNYVALE))) == 40
    assert SEARCH_PATH + "2_p/" in calls and SEARCH_PATH + "3_p/" not in calls


def test_pagination_respects_max_pages(tmp_path):
    first = load("trulia_search_p1").replace('"totalHomes":64', '"totalHomes":400')
    collector, calls = make_collector(tmp_path, {SEARCH_PATH: first, SEARCH_PATH + "2_p/": load("trulia_search_p2")}, max_pages=1)
    assert len(list(collector.discover(SUNNYVALE))) == 40
    assert SEARCH_PATH + "2_p/" not in calls


def test_robots_disallowed_listing_is_never_requested(tmp_path):
    collector, calls = make_collector(tmp_path, {})
    stub = DiscoveryStub("trulia", "building:1", "https://www.trulia.com/building/x-1_li", "x", None, None, None, {1: 2500})
    assert collector.fetch_listing(stub) is None
    assert "/building/x-1_li" not in calls


def test_block_stops_discovery(tmp_path):
    collector, _calls = make_collector(tmp_path, {SEARCH_PATH: "Forbidden"}, status=403)
    with pytest.raises(SourceBlocked):
        list(collector.discover(SUNNYVALE))


def urlpath(url: str) -> str:
    return httpx.URL(url).path
