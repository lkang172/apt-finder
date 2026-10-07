import gzip
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from aptfinder.collectors.apartment_guide import (
    ApartmentGuideCollector,
    card_stub,
    listing_id_from_url,
    page_data,
    parse_listing_page,
    parse_search_page,
)
from aptfinder.collectors.types import DiscoveryStub
from aptfinder.config import SEARCH_CITIES
from aptfinder.http import FetchResult, PoliteClient, SourceBlocked, parse_robots, robots_allows

FIXTURES = Path(__file__).parent / "fixtures"
FETCH = FetchResult("u", "u", 200, "", datetime(2026, 10, 7, tzinfo=UTC), False, "sha", "path")
ROBOTS = (FIXTURES / "apartment_guide_robots.txt").read_text()
BASE = "https://www.apartmentguide.com"
NORTH_URL = BASE + "/a/720-North-Apartments-Sunnyvale-CA-5898597/"
CROSSINGS_URL = BASE + "/a/The-Crossings-Apartments-Sunnyvale-CA-6674486/"
MATHILDA_URL = BASE + "/rent/777-S-Mathilda-Ave-Sunnyvale-CA-LV3348039459/"
SEARCH_PATH = "/apartments/California/Sunnyvale/"
PAGE_2 = SEARCH_PATH + "page-2/"
PAGE_3 = SEARCH_PATH + "page-3/"
SUNNYVALE = next(c for c in SEARCH_CITIES if c.name == "Sunnyvale")
MOUNTAIN_VIEW = next(c for c in SEARCH_CITIES if c.name == "Mountain View")


def load(name: str) -> str:
    return gzip.decompress((FIXTURES / f"{name}.html.gz").read_bytes()).decode()


def stubs_by_id(name: str) -> dict[str, DiscoveryStub]:
    return {s.source_listing_id: s for s in parse_search_page(load(name))[0]}


def cards_by_id(name: str) -> dict[str, dict]:
    cards = page_data(load(name))["location"]["listingSearch"]["listings"]
    return {c["id"]: c for c in cards}


@pytest.fixture(scope="module")
def north():
    return parse_listing_page(load("apartment_guide_north"), NORTH_URL, FETCH)


@pytest.fixture(scope="module")
def crossings():
    return parse_listing_page(load("apartment_guide_crossings"), CROSSINGS_URL, FETCH)


@pytest.fixture(scope="module")
def mathilda():
    return parse_listing_page(load("apartment_guide_rent_single"), MATHILDA_URL, FETCH)


def test_listing_ids_come_from_property_and_rental_paths():
    assert listing_id_from_url(BASE + "/a/Hartwood-Sunnyvale-CA-5919369/") == "5919369"
    assert listing_id_from_url(MATHILDA_URL) == "LV3348039459"
    assert listing_id_from_url(BASE + SEARCH_PATH) is None
    assert listing_id_from_url("https://www.rent.com/apartment/720-north-apartments-sunnyvale-ca-lc5898597") is None


def test_search_page_stubs_and_total():
    stubs, total = parse_search_page(load("apartment_guide_search_p1"))
    assert len(stubs) == 50 and total == 223
    hartwood = next(s for s in stubs if s.source_listing_id == "5919369")
    assert hartwood.url == BASE + "/a/Hartwood-Sunnyvale-CA-5919369/" and hartwood.name == "Hartwood"
    assert hartwood.min_price_by_beds == {0: 3851, 1: 3870, 2: 5415}
    assert hartwood.lat == pytest.approx(37.369941) and hartwood.lon == pytest.approx(-121.99804)
    assert hartwood.city == "Sunnyvale"


def test_page_two_adds_new_listings_including_single_rentals_and_townhomes():
    stubs = stubs_by_id("apartment_guide_search_p2")
    assert len(stubs) == 50 and not set(stubs) & set(stubs_by_id("apartment_guide_search_p1"))
    north = stubs["5898597"]
    assert north.url == NORTH_URL and north.name == "720 North Apartments"
    assert north.min_price_by_beds == {0: 2185, 1: 2475}
    assert north.lat == pytest.approx(37.391947) and north.lon == pytest.approx(-122.01355)
    mathilda = stubs["LV3348039459"]
    assert mathilda.url == MATHILDA_URL and mathilda.min_price_by_beds == {0: 2125}
    townhomes = [c for c in cards_by_id("apartment_guide_search_p2").values() if c.get("propertyType") == "TOWNHOME"]
    assert len(townhomes) == 3 and all(t["id"] in stubs for t in townhomes)


def test_prefilter_keeps_only_listings_with_an_advertised_studio_or_one_bedroom_at_or_under_the_cap():
    stubs = stubs_by_id("apartment_guide_search_p1") | stubs_by_id("apartment_guide_search_p2")
    assert stubs["6674486"].min_price_by_beds == {1: 2968, 2: 4105}
    assert stubs["6674486"].may_have_qualifying_unit((0, 1), 3150)
    assert not stubs["5919369"].may_have_qualifying_unit((0, 1), 3150)
    # A bedroom count listed as "Contact for Price" has no advertised rent to qualify on, so it is ignored.
    assert stubs["5913900"].min_price_by_beds == {0: None, 1: 4142, 2: 5139}
    assert not stubs["5913900"].may_have_qualifying_unit((0, 1), 3150)
    wildwood = next(s for s in stubs.values() if s.name == "Wildwood Manor")
    assert wildwood.min_price_by_beds == {0: None} and not wildwood.may_have_qualifying_unit((0, 1), 3150)
    assert sum(s.may_have_qualifying_unit((0, 1), 3150) for s in stubs.values()) == 30
    # Every card's per-bedroom minimum equals the cheapest floor plan the card lists for that bedroom count.
    for card in (cards_by_id("apartment_guide_search_p1") | cards_by_id("apartment_guide_search_p2")).values():
        for entry in card["bedCountData"]:
            plans = [p["priceRange"]["min"] for p in card["floorPlans"] if p["bedCount"] == entry["beds"] and p["priceRange"].get("min")]
            if plans and entry["prices"]["low"] is not None:
                assert min(plans) == entry["prices"]["low"], card["name"]


def test_card_without_bedroom_prices_falls_back_to_the_card_price():
    card = cards_by_id("apartment_guide_search_p2")["5898597"]
    assert card_stub({**card, "bedCountData": []}, (0, 1)).min_price_by_beds == {0: 2185, 1: 2185}
    assert card_stub({**card, "bedCountData": None, "bedRange": None}, (0, 1)).min_price_by_beds == {0: 2185, 1: 2185}
    assert card_stub({**card, "bedCountData": [], "bedRange": None, "price": None}, (1,)).min_price_by_beds == {1: None}


def test_houses_condos_and_rooms_are_skipped_but_ambiguous_types_are_kept():
    card = cards_by_id("apartment_guide_search_p1")["5919369"]
    for skipped in ("HOUSE", "CONDO", "ROOM", "Condos", "SINGLE_FAMILY_HOUSE"):
        assert card_stub({**card, "propertyType": skipped}, (0, 1)) is None
    for kept in ("APARTMENTS", "TOWNHOME", None):
        assert card_stub({**card, "propertyType": kept}, (0, 1)) is not None
    assert card_stub({**card, "urlPathname": "/apartments/California/Sunnyvale/"}, (0, 1)) is None


def test_multi_word_city_uses_hyphens_in_the_path():
    html = load("apartment_guide_search_mountain_view")
    data = page_data(html)
    assert data["urlPathname"] == "/apartments/California/Mountain-View/"
    assert data["location"]["citySlug"] == "Mountain-View" and data["location"]["city"] == "Mountain View"
    stubs, total = parse_search_page(html)
    assert len(stubs) == 50 and total == 126 and {s.city for s in stubs} == {"Mountain View"}


def test_search_urls():
    collector = ApartmentGuideCollector(client=None, listing_ttl=timedelta(hours=12), max_pages=3, max_rent=3000)
    assert collector.search_url(SUNNYVALE) == BASE + SEARCH_PATH
    assert collector.search_url(SUNNYVALE, 2) == BASE + PAGE_2
    assert collector.search_url(MOUNTAIN_VIEW) == BASE + "/apartments/California/Mountain-View/"
    assert collector.search_url(MOUNTAIN_VIEW, 3) == BASE + "/apartments/California/Mountain-View/page-3/"


def test_listing_identity_and_location(north):
    assert north.source_id == "apartment_guide" and north.source_listing_id == "5898597"
    assert north.url == NORTH_URL and north.name == "720 North Apartments"
    assert (north.street_address, north.city, north.state, north.zip) == ("720 N Fair Oaks Ave", "Sunnyvale", "CA", "94085")
    assert north.lat == pytest.approx(37.391947) and north.lon == pytest.approx(-122.01355)
    assert north.source_updated_at == datetime(2026, 8, 24, tzinfo=UTC)
    assert north.image_url == "https://i.apartmentguide.com/t_3x2_fixed_webp_xl/f189a8203246e28a02da3fb7566edd24"
    assert north.official_website_url is None and north.promotions == [] and north.notes == []


def test_units_are_unit_level_base_rent(north):
    assert [u.label for u in north.units] == ["665-071", "639-02", "642-030", "639-28"]
    one_bed = next(u for u in north.units if u.label == "665-071")
    assert one_bed.kind == "unit" and one_bed.source_unit_key == "unit:665-071" and one_bed.floorplan_name == "1 Bed 1 Bath"
    assert (one_bed.beds, one_bed.baths, one_bed.sqft_min, one_bed.sqft_max) == (1, 1.0, 550, 800)
    assert one_bed.base_rent_min == one_bed.base_rent_max == 2475 and one_bed.total_monthly is None
    assert one_bed.available_on == "2026-09-11" and one_bed.availability == "Available now"
    assert one_bed.source_updated_at == datetime(2026, 8, 24, tzinfo=UTC)
    studio = next(u for u in north.units if u.label == "642-030")
    assert (studio.beds, studio.sqft_min, studio.sqft_max, studio.base_rent_min) == (0, 500, 500, 2185)
    assert studio.floorplan_name == "1st floor Studio" and studio.available_on == "2026-09-16"


def test_application_fee_and_contact_for_details(north):
    [fee] = north.fees
    assert (fee.fee_type, fee.description, fee.amount, fee.amount_text, fee.recurring, fee.mandatory) == ("one_time", "Application fee: $50", 50, "$50", False, True)
    html = load("apartment_guide_north").replace('"applicationFee":"$50"', '"applicationFee":"Contact for details"')
    [fee] = parse_listing_page(html, NORTH_URL, FETCH).fees
    assert fee.description == "Application fee: Contact for details" and fee.amount is None and fee.amount_text is None


def test_total_price_listings_do_not_report_base_rent(crossings):
    unit = next(u for u in crossings.units if u.label == "059")
    assert unit.base_rent_min is None and unit.base_rent_max is None and unit.total_monthly == 2968
    assert unit.floorplan_name == "One Bedroom, One Bath Income Restricted" and unit.availability == "Available now"
    assert all(u.base_rent_min is None for u in crossings.units)
    assert any("total monthly prices" in n for n in crossings.notes)
    disclosure = next(f for f in crossings.facts if f.key == "pricing_disclosure")
    assert disclosure.content.startswith("Total monthly leasing prices include base rent") and disclosure.data["prices_include_required_fees"] is True
    assert crossings.promotions == []


def test_future_move_in_dates_are_labeled_as_the_page_does(crossings):
    future = next(u for u in crossings.units if u.label == "043")
    assert future.available_on == "2026-10-27" and future.availability == "Available Oct 27" and future.total_monthly == 3316
    assert next(u for u in crossings.units if u.label == "071").availability == "Available Nov 2"


def test_unknown_price_basis_and_off_market_record_no_prices():
    unknown = parse_listing_page(load("apartment_guide_north").replace('"hasTotalCostWithFees":false', '"hasTotalCostWithFees":null'), NORTH_URL, FETCH)
    assert unknown.units == [] and any("did not state" in n for n in unknown.notes)
    off_market = parse_listing_page(load("apartment_guide_north").replace('"offMarket":false', '"offMarket":true'), NORTH_URL, FETCH)
    assert off_market.units == [] and any("off market" in n for n in off_market.notes)


def test_income_restrictions_become_an_eligibility_fact(crossings, north):
    fact = next(f for f in crossings.facts if f.key == "eligibility")
    assert fact.title == "Eligibility restrictions" and fact.data["restrictions"] == ["Income Restricted"]
    assert "1 occupant: $113,700; 2 occupants: $129,950" in fact.content
    assert fact.data["income_limits"][0] == {"max_occupants": 1, "max_annual_income": "$113,700"}
    assert any(e.startswith('floor plan "One Bedroom, One Bath Income Restricted"') for e in fact.data["evidence"])
    assert next(f for f in crossings.facts if f.key == "listing_tags").data["tags"] == ["Income Restricted"]
    assert not any(f.key == "eligibility" for f in north.facts)


def test_eligibility_words_in_names_and_floor_plans_are_mapped():
    senior = parse_listing_page(load("apartment_guide_north").replace('"name":"720 North Apartments"', '"name":"720 North Senior Apartments"'), NORTH_URL, FETCH)
    assert next(f for f in senior.facts if f.key == "eligibility").data["restrictions"] == ["Senior"]
    plan = parse_listing_page(load("apartment_guide_north").replace('"name":"1 Bed 1 Bath"', '"name":"1 Bed 1 Bath Income Restricted"'), NORTH_URL, FETCH)
    fact = next(f for f in plan.facts if f.key == "eligibility")
    assert fact.data["restrictions"] == ["Income Restricted"] and fact.data["income_limits"] == []


def test_pet_fees_parking_and_lease_terms(crossings):
    pet_rent = next(f for f in crossings.fees if f.description.startswith("Pet rent (Cats Allowed)"))
    assert (pet_rent.fee_type, pet_rent.amount, pet_rent.recurring, pet_rent.mandatory) == ("pet", 35, True, False)
    pet_deposit = next(f for f in crossings.fees if f.description.startswith("Pet deposit (Dogs Allowed)"))
    assert (pet_deposit.amount, pet_deposit.recurring, pet_deposit.mandatory) == (500, False, False)
    assert not any(f.description.startswith("Application fee") for f in crossings.fees)
    facts = {f.key: f for f in crossings.facts}
    assert facts["pet_policy"].content == "Cats Allowed (Cat; pet rent $35/month; deposit $500); Dogs Allowed (Dog; pet rent $35/month; deposit $500)"
    assert facts["parking_details"].content == "Other"
    assert facts["lease_terms"].content == "Available months 12, 13, 14, 15, 16, 17, 18"
    assert facts["management_company"].content == "Greystar"
    assert facts["units_available"].data == {"available": 1, "total_units": 148}


def test_single_rental_page(mathilda):
    assert mathilda.source_listing_id == "LV3348039459" and mathilda.name == "777 S Mathilda Ave unit 777-204"
    assert mathilda.zip == "94087" and mathilda.source_updated_at == datetime(2026, 10, 6, 11, 21, 37, tzinfo=UTC)
    [unit] = mathilda.units
    assert unit.kind == "unit" and unit.source_unit_key == "unit:LV3348039459" and unit.label == "777-204"
    assert (unit.beds, unit.baths, unit.sqft_min, unit.sqft_max) == (0, 1.0, 380, 380)
    assert unit.base_rent_min == unit.base_rent_max == 2125
    assert unit.available_on == "2026-09-10" and unit.availability == "1 Unit Available"
    deposit = next(f for f in mathilda.fees if f.fee_type == "deposit")
    assert (deposit.amount, deposit.amount_text, deposit.recurring, deposit.mandatory) == (1500, "$1,500", False, True)
    assert any("Single-unit rental listing" in n for n in mathilda.notes)


def test_feed_provenance_names_the_network(north, mathilda):
    zillow = next(f for f in north.facts if f.key == "feed_provenance")
    assert zillow.data["network"] == "Rent. (Redfin / Rocket Companies)" and zillow.data["independent_source"] is False
    assert zillow.data["tplsource"] == "ZILLOW" and zillow.data["shares_feed_with"] == ["redfin", "trulia"]
    assert "Zillow Group" in zillow.content
    lovely = next(f for f in mathilda.facts if f.key == "feed_provenance")
    assert lovely.data["tplsource"] == "LOVELY" and lovely.data["feed"] == "APPFOLIO_FREE" and lovely.data["independent_source"] is True


def test_rating_percent_is_recorded_as_a_fact_not_a_rating(north):
    assert north.rating is None and not any(f.key == "source_rating" for f in north.facts)
    html = load("apartment_guide_north").replace('"ratingCount":null,"ratingPercent":null', '"ratingCount":12,"ratingPercent":80')
    listing = parse_listing_page(html, NORTH_URL, FETCH)
    assert listing.rating is None and listing.reviews == []
    fact = next(f for f in listing.facts if f.key == "source_rating")
    assert fact.data == {"rating_percent": 80.0, "rating_count": 12} and "not converted" in fact.content


def test_website_and_room_for_rent():
    html = load("apartment_guide_north").replace('"website":null', '"website":"https://www.720north.com"')
    assert parse_listing_page(html, NORTH_URL, FETCH).official_website_url == "https://www.720north.com"
    assert parse_listing_page(load("apartment_guide_north").replace('"roomForRent":false', '"roomForRent":true'), NORTH_URL, FETCH) is None


def test_page_for_a_different_listing_is_rejected():
    assert parse_listing_page(load("apartment_guide_north"), CROSSINGS_URL, FETCH) is None
    assert parse_listing_page("<html></html>", NORTH_URL, FETCH) is None


def test_robots_rules():
    rules = parse_robots(ROBOTS, "Mozilla/5.0")
    for disallowed in ("/rentals/", "/rentals/sunnyvale-ca", SEARCH_PATH + "?order=price", SEARCH_PATH + "?max_price=3000",
                       SEARCH_PATH + "?min_price=2100&max_price=3000", SEARCH_PATH + "?limit=100", "/graphql/", "/filter/x", "/deals/x"):
        assert not robots_allows(rules, BASE + disallowed), disallowed
    for allowed in (SEARCH_PATH, PAGE_2, "/apartments/California/Mountain-View/page-3/", NORTH_URL, MATHILDA_URL):
        assert robots_allows(rules, BASE + allowed if allowed.startswith("/") else allowed), allowed


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
        tmp_path, "test-agent", min_intervals={"www.apartmentguide.com": 10.0},
        transport=httpx.MockTransport(handler), sleep=fake.sleep, clock=fake.clock,
    )
    return ApartmentGuideCollector(client, timedelta(hours=12), max_pages=max_pages, max_rent=3000), calls, fake


def two_pages() -> dict[str, str]:
    # The live city has 223 listings (5 pages); trimming the total to 100 makes page 2 the last page.
    return {
        SEARCH_PATH: load("apartment_guide_search_p1").replace('"total":223', '"total":100'),
        PAGE_2: load("apartment_guide_search_p2").replace('"total":223', '"total":100'),
    }


def test_discover_and_fetch_end_to_end(tmp_path):
    collector, calls, fake = make_collector(tmp_path, {**two_pages(), urlpath(NORTH_URL): load("apartment_guide_north")})
    stubs = list(collector.discover(SUNNYVALE))
    assert len(stubs) == 100 and len({s.source_listing_id for s in stubs}) == 100
    assert calls.count(SEARCH_PATH) == 1 and calls.count(PAGE_2) == 1 and PAGE_3 not in calls
    stub = next(s for s in stubs if s.source_listing_id == "5898597")
    listing = collector.fetch_listing(stub)
    assert listing.source_listing_id == stub.source_listing_id and listing.url == NORTH_URL
    assert next(u for u in listing.units if u.label == "665-071").base_rent_min == 2475
    assert listing.fetch.status == 200 and not listing.fetch.from_cache
    assert fake.now >= 20.0 and collector.client.network_requests == 4


def test_pagination_stops_when_a_page_adds_nothing_new(tmp_path):
    first = load("apartment_guide_search_p1")
    collector, calls, _fake = make_collector(tmp_path, {SEARCH_PATH: first, PAGE_2: first})
    assert len(list(collector.discover(SUNNYVALE))) == 50
    assert PAGE_2 in calls and PAGE_3 not in calls


def test_pagination_respects_max_pages(tmp_path):
    collector, calls, _fake = make_collector(tmp_path, two_pages(), max_pages=1)
    assert len(list(collector.discover(SUNNYVALE))) == 50
    assert PAGE_2 not in calls


def test_robots_disallowed_listing_is_never_requested(tmp_path):
    collector, calls, _fake = make_collector(tmp_path, {})
    stub = DiscoveryStub("apartment_guide", "x", BASE + "/rentals/x-1/", "x", None, None, None, {1: 2500})
    assert collector.fetch_listing(stub) is None
    assert "/rentals/x-1/" not in calls
    ordered = DiscoveryStub("apartment_guide", "y", BASE + SEARCH_PATH + "?order=price", "y", None, None, None, {1: 2500})
    assert collector.fetch_listing(ordered) is None
    assert calls == ["/robots.txt"]


def test_block_stops_discovery(tmp_path):
    collector, _calls, _fake = make_collector(tmp_path, {SEARCH_PATH: "Forbidden"}, status=403)
    with pytest.raises(SourceBlocked):
        list(collector.discover(SUNNYVALE))
    assert "www.apartmentguide.com" in collector.client.blocked_hosts


def urlpath(url: str) -> str:
    return httpx.URL(url).path
