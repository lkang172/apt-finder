import gzip
import json
import logging
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from aptfinder.collectors.official import avalon, jonah, knock, sightmap
from aptfinder.collectors.official.common import money
from aptfinder.collectors.official_sites import (
    OfficialSiteCollector,
    OfficialSiteTarget,
    clean_website_url,
    detect_platform,
    floorplans_link,
    known_blocked_reason,
)
from aptfinder.db.models import PriceObservation
from aptfinder.filters import is_restricted_unit
from aptfinder.http import PoliteClient, SourceBlocked
from aptfinder.store import upsert_listing

FIXTURES = Path(__file__).parent / "fixtures"
AVALON_URL = "https://www.avaloncommunities.com/california/san-jose-apartments/eaves-san-jose/"
LINQ_FLOORPLANS = "https://liveatlinq.com/floorplans/"
ALDERWOOD = "https://www.alderwoodparkapts.com/"
SOFI = "https://www.sofifremont.com/"
SOFI_FLOORPLANS = "https://www.sofifremont.com/apartments/ca/fremont/floor-plans"
SOFI_EMBED = "https://sightmap.com/embed/y8px0z93p19"
SOFI_DATA = "https://sightmap.com/app/api/v1/x1p89nrrwd6/sightmaps/25292"
KNOCK_COMMUNITY = "https://doorway-api.knockrentals.com/v1/property/community/6411e9358cea588d"
KNOCK_UNITS = "https://doorway-api.knockrentals.com/v1/property/2005773/units"


def fixture(name: str) -> str:
    return gzip.decompress((FIXTURES / f"official_{name}.gz").read_bytes()).decode("utf-8")


def fixture_json(name: str) -> dict:
    return json.loads(fixture(name))


def unit(site, label):
    return next(u for u in site.units if u.label == label)


def no_dns(host):
    raise AssertionError(f"unexpected DNS lookup for {host}")


def unresolvable(host):
    raise socket.gaierror(f"no DNS in tests for {host}")


class FakeTime:
    def __init__(self):
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def make_collector(tmp_path, routes, resolve=unresolvable):
    calls: list[str] = []

    def handler(request):
        url = str(request.url)
        calls.append(url)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if url not in routes:
            return httpx.Response(404, text="not found")
        status, body, headers = routes[url]
        return httpx.Response(status, text=body, headers=headers)

    fake = FakeTime()
    client = PoliteClient(tmp_path, "test-agent", transport=httpx.MockTransport(handler), sleep=fake.sleep, clock=fake.clock)
    return OfficialSiteCollector(client, timedelta(hours=6), resolve=resolve), calls


def page(body: str) -> tuple[int, str, dict]:
    return 200, body, {}


def redirect(location: str) -> tuple[int, str, dict]:
    return 301, "", {"location": location}


def target(url: str, name: str = "Test Property") -> OfficialSiteTarget:
    return OfficialSiteTarget(name=name, website_url=url, city="San Jose")


@pytest.fixture(scope="module")
def eaves():
    return avalon.parse_community_page(fixture("avalon_eaves_san_jose.html"))


@pytest.fixture(scope="module")
def linq():
    return jonah.parse_floorplans_page(fixture("jonah_linq_floorplans.html"), LINQ_FLOORPLANS)


@pytest.fixture(scope="module")
def sofi():
    return sightmap.parse_sightmap(fixture_json("sightmap_sofi_data.json"), fixture("sightmap_sofi_embed.html"))


@pytest.fixture(scope="module")
def linq_sightmap():
    return sightmap.parse_sightmap(fixture_json("sightmap_linq_data.json"), fixture("sightmap_linq_embed.html"))


@pytest.mark.parametrize(
    ("name", "url", "expected"),
    [
        ("avalon_eaves_san_jose.html", AVALON_URL, "avalon"),
        ("jonah_linq_home.html", "https://liveatlinq.com/", "jonah"),
        ("jonah_linq_floorplans.html", LINQ_FLOORPLANS, "jonah"),
        ("knock_alderwood_home.html", ALDERWOOD, "knock"),
        ("knock_colonnade_home.html", "https://www.colonnadeapt.com/", "knock"),
        ("sightmap_sofi_floorplans.html", SOFI_FLOORPLANS, "sightmap"),
        ("sightmap_sofi_home.html", SOFI, None),
    ],
)
def test_detect_platform(name, url, expected):
    assert detect_platform(url, fixture(name)) == expected


def test_platform_discovery_helpers():
    assert knock.find_community_id(fixture("knock_alderwood_home.html")) == "6411e9358cea588d"
    assert knock.find_community_id(fixture("knock_colonnade_home.html")) == "9bd4280c69711ee5"
    assert floorplans_link(SOFI, fixture("sightmap_sofi_home.html")) == SOFI_FLOORPLANS
    assert floorplans_link("https://liveatlinq.com/", fixture("jonah_linq_home.html")) == LINQ_FLOORPLANS
    assert sightmap.find_embed_url(fixture("sightmap_sofi_floorplans.html")) == SOFI_EMBED
    assert sightmap.data_urls(fixture("sightmap_sofi_embed.html")) == [SOFI_DATA]
    assert sightmap.find_embed_url('<script>{"enableSiteMap": "engrain", "sightmapID": "8epm5kgew6d"}</script>') == (
        "https://sightmap.com/embed/8epm5kgew6d"
    )
    assert sightmap.find_embed_url('<script src="https://sightmap.com/embed/api.js"></script>') is None


def test_avalon_unit_separates_base_total_and_required_fees(eaves):
    studio = unit(eaves, "2")
    assert (studio.beds, studio.baths, studio.sqft_min, studio.floorplan_name) == (0, 1.0, 330, "330")
    assert studio.base_rent_min == studio.base_rent_max == 2670
    assert studio.total_monthly == 2745
    assert studio.required_fees_monthly == 75
    assert studio.lease_term_months == 17
    assert studio.available_on == "2026-10-04"


def test_avalon_identity_and_repeated_unit_numbers(eaves):
    assert eaves.platform_property_id == "AVB-CA010" and eaves.name == "eaves San Jose"
    assert (eaves.address.street_address, eaves.address.city, eaves.address.zip) == ("1895 N. Capitol Ave", "San Jose", "95132")
    same_number = [u for u in eaves.units if u.label == "1810"]
    assert len(same_number) == 2 and len({u.source_unit_key for u in same_number}) == 2
    assert len(eaves.units) == 37


def test_avalon_fees_promotions_and_policies(eaves):
    [fee] = eaves.fees
    assert fee.amount == 75 and fee.recurring and fee.mandatory
    assert "Connect+ Smart Tech, Connect+ Internet" in fee.description
    assert any(p.startswith("Apply by 10/7 for 1 month off! Get 1 month off on select homes") for p in eaves.promotions)
    facts = {f.key: f for f in eaves.facts}
    assert "includes base rent and all required monthly fees" in facts["pricing_disclosure"].content
    assert "Water: paid by resident" in facts["utilities"].content
    assert "net_effective_prices" not in facts


def test_avalon_net_effective_price_never_replaces_base_rent():
    html = fixture("avalon_eaves_san_jose.html").replace(
        '"price":2670,"totalPrice":2745,"netEffectivePrice":2670', '"price":2670,"totalPrice":2745,"netEffectivePrice":2450', 1
    )
    site = avalon.parse_community_page(html)
    assert unit(site, "2").base_rent_min == 2670
    facts = {f.key: f for f in site.facts}
    assert "Unit 2: net effective $2,450/month vs. base rent $2,670" in facts["net_effective_prices"].content
    assert any("not base rent" in p and "$2,450" in p for p in site.promotions)


def test_jonah_keeps_income_restricted_plan_names_verbatim(linq):
    restricted = unit(linq, "318")
    assert restricted.floorplan_name == "A6-A Income Protected"
    assert is_restricted_unit(restricted.floorplan_name, restricted.label)
    assert not is_restricted_unit(unit(linq, "458").floorplan_name)


def test_jonah_base_rent_total_and_required_fees(linq):
    apartment = unit(linq, "318")
    assert (apartment.beds, apartment.baths, apartment.sqft_min) == (1, 1.0, 902)
    assert apartment.base_rent_min == apartment.base_rent_max == 2892
    assert apartment.total_monthly == pytest.approx(2933.06)
    assert apartment.required_fees_monthly == pytest.approx(41.06)
    assert apartment.lease_term_months == 15
    assert apartment.available_on == "2026-11-02" and apartment.availability == "Available Nov 02"
    assert unit(linq, "356").beds == 0


def test_jonah_identity_facts_and_one_time_fees(linq):
    assert linq.platform_property_id == "liveatlinq.com" and linq.name == "Linq"
    assert linq.address.street_address == "1700 Newbury Park Drive" and linq.address.zip == "95133"
    facts = {f.key: f for f in linq.facts}
    assert facts["pricing_disclosure"].content.startswith("* Total Monthly Leasing Price includes base rent")
    assert "Unit 318: 6 Months ($2,892 Base Rent)" in facts["lease_term_prices"].content
    assert facts["lease_term_prices"].data["by_unit"]["318"]["12"] == 2892
    assert "Unit 318: $2,933.06–$2,953.06" in facts["total_price_ranges"].content
    application = next(f for f in linq.fees if f.description.startswith("Est. Application Costs"))
    assert application.amount == 535 and application.recurring is False


def test_knock_units_fees_and_policies():
    community = knock.parse_community(fixture_json("knock_alderwood_community.json"))
    assert community.property_id == 2005773 and not community.pricing_hidden
    site = knock.add_units(community, fixture_json("knock_alderwood_units.json"))
    assert site.name == "Alderwood Park" and site.address.zip == "94560"
    one_bedroom = unit(site, "02211")
    assert (one_bedroom.beds, one_bedroom.sqft_min, one_bedroom.floorplan_name) == (1, 685, "1BD, 1BTH")
    assert one_bedroom.base_rent_min == 2222
    assert one_bedroom.total_monthly is None and one_bedroom.required_fees_monthly is None
    assert one_bedroom.available_on == "2026-11-06" and one_bedroom.availability == "On notice"
    assert one_bedroom.source_updated_at == datetime(2026, 10, 4, 4, 22, 42, 87000, tzinfo=UTC)
    fees = {f.description: f for f in site.fees}
    pet_rent = fees["Pet rent: $50/month (only if you have a pet)"]
    assert pet_rent.amount == 50 and pet_rent.mandatory is False
    assert fees["Application fee: $53.33"].amount == 53
    assert fees["Security deposit: $500 for one bedrooms & $700 for two bedrooms"].amount is None
    assert "Max weight 25 lb" in next(f.content for f in site.facts if f.key == "pet_policy")


def test_knock_escaped_init_site_and_studio_prices():
    community = knock.parse_community(fixture_json("knock_colonnade_community.json"))
    site = knock.add_units(community, fixture_json("knock_colonnade_units.json"))
    studio = unit(site, "520A")
    assert (studio.beds, studio.floorplan_name, studio.base_rent_min) == (0, "Medium Studio", 2091)
    assert any("availability panel is turned off" in n for n in site.notes)


def test_knock_hidden_pricing_records_no_prices():
    doc = fixture_json("knock_alderwood_community.json")
    doc["property"]["data"]["doorway"]["hidePricing"] = True
    community = knock.parse_community(doc)
    assert community.pricing_hidden
    assert knock.add_units(community, fixture_json("knock_alderwood_units.json")).units == []


def test_sightmap_base_rent_only_site(sofi):
    assert sofi.name == "Sofi Fremont" and sofi.address.street_address == "889 Mowry Avenue"
    apartment = unit(sofi, "014")
    assert (apartment.beds, apartment.floorplan_name, apartment.sqft_min) == (1, "1 Bedroom, 1 Bath (B)", 710)
    assert apartment.base_rent_min == 2775
    assert apartment.total_monthly is None and apartment.required_fees_monthly is None
    assert apartment.lease_term_months == 12 and apartment.available_on == "2026-10-11"
    assert sofi.fees == []


def test_sightmap_total_price_and_itemized_fees(linq_sightmap):
    apartment = unit(linq_sightmap, "318")
    assert apartment.base_rent_min == 2892
    assert apartment.total_monthly == pytest.approx(2933.06)
    assert apartment.required_fees_monthly == pytest.approx(41.06)
    assert apartment.lease_term_months == 15
    assert apartment.floorplan_name == "liqA6Aaf"
    assert unit(linq_sightmap, "356").floorplan_name == "S2-A/B Income Protected"
    fees = {f.description.split(":")[0]: f for f in linq_sightmap.fees}
    admin = fees["Utility - Billing Administrative Fee"]
    assert (admin.amount_text, admin.recurring, admin.mandatory) == ("$6.06", True, True)
    assert fees["Pet Rent"].mandatory is False and fees["Pet Rent"].amount is None
    assert fees["Parking - Garage"].mandatory is False
    composition = next(f for f in linq_sightmap.facts if f.key == "total_price_composition").content
    assert "Utility - Billing Administrative Fee ($6.06)" in composition
    assert "Pet Rent ($35.00 - $55.00; applies only to residents with pets)" in composition


def test_call_for_details_is_absent_not_zero():
    assert money("Call for details") is None and money("$0") is None and money(0) is None and money("") is None
    assert money("$2,775.00") == 2775.0 and money("2892") == 2892.0

    doc = fixture_json("sightmap_sofi_data.json")
    raw = next(u for u in doc["data"]["units"] if u["unit_number"] == "014")
    raw.update(price=None, display_price="Call for details", total_price=[None, None])
    site = sightmap.parse_sightmap(doc, fixture("sightmap_sofi_embed.html"))
    assert "014" not in {u.label for u in site.units}
    assert all(u.base_rent_min for u in site.units)
    assert "1 listed unit(s) show no published price and were not recorded" in site.notes

    units = fixture_json("knock_alderwood_units.json")
    for raw in units["units_data"]["units"]:
        raw.update(price="", displayPrice="")
    site = knock.add_units(knock.parse_community(fixture_json("knock_alderwood_community.json")), units)
    assert site.units == [] and any("no published price" in n for n in site.notes)


def test_sightmap_affordable_flag_marks_unit_restricted():
    doc = fixture_json("sightmap_sofi_data.json")
    raw = next(u for u in doc["data"]["units"] if u["unit_number"] == "014")
    raw["affordable_housing_info"]["is_affordable_housing_unit"] = True
    apartment = unit(sightmap.parse_sightmap(doc, fixture("sightmap_sofi_embed.html")), "014")
    assert apartment.floorplan_name == "1 Bedroom, 1 Bath (B) (affordable housing unit)"
    assert is_restricted_unit(apartment.floorplan_name)


def test_clean_website_url_drops_only_tracking_parameters():
    assert clean_website_url("https://www.alderwoodparkapts.com/?utm_knock=al") == "https://www.alderwoodparkapts.com/"
    assert clean_website_url("http://www.maxwellatbascom.com?funnelleasing=aptlist") == "http://www.maxwellatbascom.com/"
    assert clean_website_url("https://example.com/community?id=5&utm_medium=listing") == "https://example.com/community?id=5"
    assert clean_website_url("www.example.com") == "https://www.example.com/"


def test_known_blocked_domain_needs_no_dns():
    reason = known_blocked_reason("https://www.equityapartments.com/san-francisco-bay/san-jose/verde-apartments", no_dns)
    assert "Equity Residential" in reason
    assert "RentCafe" in known_blocked_reason("https://parkkiely.securecafe.com/", no_dns)


def test_known_blocked_by_cname_and_ip():
    def rentcafe(host):
        return "www.rentcafecloudflaremvccn.com.cdn.cloudflare.net", [host, "www-aviarasanjose-com.rentcafecn.com"], ["172.66.1.254"]

    def entrata(host):
        return host, [], ["198.190.14.13"]

    def ordinary(host):
        return "d3back1mwb2ylq.cloudfront.net", [host, "sofifremont.g5dns.com"], ["108.138.64.54"]

    assert "RentCafe/Yardi" in known_blocked_reason("https://www.aviarasanjose.com/", rentcafe)
    assert "Entrata" in known_blocked_reason("https://www.palmcourtsanjose.com/", entrata)
    assert known_blocked_reason(SOFI, ordinary) is None
    assert known_blocked_reason(SOFI, unresolvable) is None


def test_collect_skips_known_blocked_site_without_requests(tmp_path):
    collector, calls = make_collector(tmp_path, {}, resolve=no_dns)
    assert collector.collect(target("https://www.equityapartments.com/san-francisco-bay/fremont/alborada")) is None
    assert calls == []


def test_collect_avalon_end_to_end(tmp_path):
    routes = {AVALON_URL.rstrip("/"): redirect(AVALON_URL), AVALON_URL: page(fixture("avalon_eaves_san_jose.html"))}
    collector, _ = make_collector(tmp_path, routes)
    listing = collector.collect(target(AVALON_URL.rstrip("/"), "eaves San Jose"))
    assert listing.source_id == "official_site" and listing.source_listing_id == "avalon:AVB-CA010"
    assert listing.url == AVALON_URL and listing.official_website_url == AVALON_URL.rstrip("/")
    assert listing.street_address == "1895 N. Capitol Ave" and listing.zip == "95132"
    assert unit(listing, "2").total_monthly == 2745
    facts = {f.key: f for f in listing.facts}
    assert facts["platform"].data["platform"] == "avalon"
    assert facts["data_endpoint"].url == AVALON_URL


def test_collect_jonah_follows_same_site_redirect_and_floorplans_link(tmp_path):
    routes = {
        "https://www.liveatlinq.com/": redirect("https://liveatlinq.com/"),
        "https://liveatlinq.com/": page(fixture("jonah_linq_home.html")),
        LINQ_FLOORPLANS: page(fixture("jonah_linq_floorplans.html")),
    }
    collector, calls = make_collector(tmp_path, routes)
    listing = collector.collect(target("https://www.liveatlinq.com/", "LINQ"))
    assert listing.url == LINQ_FLOORPLANS and listing.fetch.url == LINQ_FLOORPLANS
    assert listing.source_listing_id == "jonah:liveatlinq.com"
    assert unit(listing, "318").floorplan_name == "A6-A Income Protected"
    assert "https://liveatlinq.com/" in calls


def test_collect_knock_reads_only_the_two_widget_endpoints(tmp_path):
    routes = {
        ALDERWOOD: page(fixture("knock_alderwood_home.html")),
        KNOCK_COMMUNITY: page(fixture("knock_alderwood_community.json")),
        KNOCK_UNITS: page(fixture("knock_alderwood_units.json")),
    }
    collector, calls = make_collector(tmp_path, routes)
    listing = collector.collect(target(ALDERWOOD + "?utm_knock=al", "Alderwood Park"))
    assert listing.url == ALDERWOOD and listing.source_listing_id == "knock:2005773"
    assert listing.fetch.url == KNOCK_UNITS
    assert {c for c in calls if "knockrentals" in c and not c.endswith("robots.txt")} == {KNOCK_COMMUNITY, KNOCK_UNITS}
    endpoint = next(f for f in listing.facts if f.key == "data_endpoint")
    assert endpoint.url == KNOCK_UNITS and endpoint.data["endpoints"] == [KNOCK_COMMUNITY, KNOCK_UNITS]
    assert unit(listing, "02211").base_rent_min == 2222


def test_collect_sightmap_via_floorplans_page(tmp_path):
    routes = {
        SOFI: page(fixture("sightmap_sofi_home.html")),
        SOFI_FLOORPLANS: page(fixture("sightmap_sofi_floorplans.html")),
        SOFI_EMBED: page(fixture("sightmap_sofi_embed.html")),
        SOFI_DATA: page(fixture("sightmap_sofi_data.json")),
    }
    collector, _ = make_collector(tmp_path, routes)
    listing = collector.collect(target(SOFI, "Sofi Fremont"))
    assert listing.url == SOFI_FLOORPLANS and listing.source_listing_id == "sightmap:25292"
    assert listing.fetch.url == SOFI_DATA
    assert unit(listing, "014").base_rent_min == 2775
    endpoint = next(f for f in listing.facts if f.key == "data_endpoint")
    assert endpoint.url == SOFI_DATA and SOFI_EMBED in endpoint.content


def test_collect_falls_back_to_next_platform_when_first_has_no_data(tmp_path):
    home = (
        '<html><head><meta name="generator" content="Jonah Systems, LLC - www.jonahdigital.com"/></head><body>'
        "<script>knockDoorway.init('KEY', 'community', '6411e9358cea588d')</script></body></html>"
    )
    routes = {
        ALDERWOOD: page(home),
        ALDERWOOD + "floorplans/": page("<html>Floor plans coming soon</html>"),
        KNOCK_COMMUNITY: page(fixture("knock_alderwood_community.json")),
        KNOCK_UNITS: page(fixture("knock_alderwood_units.json")),
    }
    collector, calls = make_collector(tmp_path, routes)
    listing = collector.collect(target(ALDERWOOD))
    assert listing.source_listing_id == "knock:2005773"
    assert ALDERWOOD + "floorplans/" in calls


def test_collected_listing_round_trips_through_store(tmp_path, session):
    routes = {
        "https://liveatlinq.com/": page(fixture("jonah_linq_home.html")),
        LINQ_FLOORPLANS: page(fixture("jonah_linq_floorplans.html")),
    }
    collector, _ = make_collector(tmp_path, routes)
    upsert_listing(session, collector.collect(target("https://liveatlinq.com/", "LINQ")), run_id=None)
    observation = next(o for o in session.query(PriceObservation) if o.base_rent_min == 2892 and o.lease_term_months == 15)
    assert observation.total_monthly == pytest.approx(2933.06)
    assert observation.source_url == LINQ_FLOORPLANS


def test_collect_returns_none_without_supported_platform(tmp_path, caplog):
    url = "https://www.example-apartments.com/"
    routes = {
        url: page('<html><a href="/floor-plans">Floor plans</a></html>'),
        url + "floor-plans": page('<html><a href="/floor-plans">Floor plans</a></html>'),
    }
    collector, calls = make_collector(tmp_path, routes)
    with caplog.at_level(logging.INFO):
        assert collector.collect(target(url)) is None
    assert "No supported pricing platform" in caplog.text
    assert calls.count(url + "floor-plans") == 1


def test_collect_returns_none_on_parse_failure(tmp_path, caplog):
    routes = {AVALON_URL: page("<script>Fusion.globalContent={not json;</script>")}
    collector, _ = make_collector(tmp_path, routes)
    with caplog.at_level(logging.WARNING):
        assert collector.collect(target(AVALON_URL)) is None
    assert "Could not read prices" in caplog.text


def test_collect_does_not_follow_cross_site_redirect(tmp_path):
    routes = {"https://www.example-apartments.com/": redirect("https://unrelated-host.com/")}
    collector, calls = make_collector(tmp_path, routes)
    assert collector.collect(target("https://www.example-apartments.com/")) is None
    assert not any("unrelated-host.com" in c for c in calls)


def test_collect_lets_source_blocked_propagate(tmp_path):
    collector, _ = make_collector(tmp_path, {AVALON_URL: (429, "", {"retry-after": "60"})})
    with pytest.raises(SourceBlocked):
        collector.collect(target(AVALON_URL))
