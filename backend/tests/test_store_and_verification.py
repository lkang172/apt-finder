import gzip
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from aptfinder.collectors.apartment_list import parse_listing_page
from aptfinder.collectors.types import CollectedListing, CollectedRating, CollectedUnit
from aptfinder.config import Settings
from aptfinder.db.models import Evidence, ListingSource, PriceObservation, Property, RatingSummary, Review
from aptfinder.http import FetchResult
from aptfinder.store import upsert_listing
from aptfinder.verification import evaluate_property_status, verify_prices

FIXTURES = Path(__file__).parent / "fixtures"
FETCHED = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
SETTINGS = Settings(_env_file=None)


def fetch(sha: str, at: datetime = FETCHED) -> FetchResult:
    return FetchResult("https://x", "https://x", 200, "", at, False, sha, f"{sha}.gz")


def al_listing(name: str, slug: str, sha: str = "sha1", at: datetime = FETCHED) -> CollectedListing:
    html = gzip.decompress((FIXTURES / f"{name}.html.gz").read_bytes()).decode()
    return parse_listing_page(html, f"https://www.apartmentlist.com/ca/sunnyvale/{slug}", fetch(sha, at))


def synthetic_redfin(street: str, units: list[CollectedUnit], lat: float, lon: float, sha: str = "rf1", city: str = "Sunnyvale") -> CollectedListing:
    return CollectedListing(
        source_id="redfin", source_listing_id=f"rf-{street}", url=f"https://www.redfin.com/CA/{city}/x/apartment/1",
        name="Synthetic Redfin Listing", street_address=street, city=city, state="CA", zip="94087",
        lat=lat, lon=lon, fetch=fetch(sha), units=units,
    )


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


@pytest.fixture
def central_park(session):
    prop, _ = upsert_listing(session, al_listing("al_cp", "central-park-apartments"), run_id=None, now=FETCHED)
    return prop


def test_listing_creates_property_units_prices_and_evidence(session, central_park):
    assert central_park.name == "Central Park Apartments"
    assert central_park.region == "south_bay"
    observation = session.scalar(select(PriceObservation))
    assert observation.base_rent_min == 2715 and observation.lease_term_months == 12
    evidence = session.get(Evidence, observation.evidence_id)
    assert evidence.kind == "price" and evidence.source_url.startswith("https://www.apartmentlist.com/")
    assert "advertised base rent $2,715" in evidence.content
    website = session.scalars(select(Evidence).where(Evidence.title == "Official property website")).one()
    assert website.source_url == "https://www.centralparkaptliving.com/"


def test_reupsert_same_content_does_not_duplicate(session, central_park):
    before = (count(session, PriceObservation), count(session, Evidence))
    upsert_listing(session, al_listing("al_cp", "central-park-apartments"), run_id=None, now=FETCHED)
    assert (count(session, PriceObservation), count(session, Evidence)) == before
    assert count(session, Property) == 1


def test_refresh_adds_new_observation_but_not_duplicate_reviews(session):
    upsert_listing(session, al_listing("al_arches", "the-arches", "a1"), run_id=None, now=FETCHED)
    later = FETCHED + timedelta(days=1)
    upsert_listing(session, al_listing("al_arches", "the-arches", "a2", later), run_id=None, now=later)
    assert count(session, Review) == 1
    assert count(session, RatingSummary) == 2
    assert count(session, PriceObservation) == 2 * len(al_listing("al_arches", "the-arches").units)


def test_same_building_from_second_source_merges(session, central_park):
    redfin = synthetic_redfin(
        "1055 Manet Dr",
        [CollectedUnit("unit:r1", "unit", "58", "Fairwood", 1, 1.0, 720, 720, 2715, 2715)],
        37.35720, -122.02780,
    )
    prop, _ = upsert_listing(session, redfin, run_id=None, now=FETCHED)
    assert prop.id == central_park.id
    assert {ls.source_id for ls in session.scalars(select(ListingSource))} == {"apartment_list", "redfin"}
    assert prop.name == "Central Park Apartments"


def test_fresh_in_range_price_is_verified(session, central_park):
    result = verify_prices(session, central_park, SETTINGS, FETCHED + timedelta(hours=1))
    assert result.status == "verified"
    assert [s.observation.base_rent_min for s in result.qualifying] == [2715]
    assert evaluate_property_status(session, central_park, SETTINGS, FETCHED + timedelta(hours=1)).status == "included"


def test_stale_price_is_never_approved(session, central_park):
    status = evaluate_property_status(session, central_park, SETTINGS, FETCHED + timedelta(hours=100))
    assert status.status == "needs_reverification"
    assert status.reasons[0]["filter"] == "price_freshness"


def test_out_of_range_property_is_excluded(session):
    prop, _ = upsert_listing(session, al_listing("al_enc", "encasa"), run_id=None, now=FETCHED)
    status = evaluate_property_status(session, prop, SETTINGS, FETCHED + timedelta(hours=1))
    assert status.status == "excluded" and status.reasons[0]["filter"] == "price_and_unit_type"


def test_cross_source_price_conflict_detected(session, central_park):
    redfin = synthetic_redfin(
        "1055 Manet Dr",
        [CollectedUnit("unit:r1", "unit", "12", "Fairwood", 1, 1.0, 720, 720, 2995, 2995)],
        37.35720, -122.02780,
    )
    upsert_listing(session, redfin, run_id=None, now=FETCHED)
    result = verify_prices(session, central_park, SETTINGS, FETCHED + timedelta(hours=1))
    assert result.status == "conflict"
    conflict = result.conflicts[0]
    assert {conflict.a.source_id, conflict.b.source_id} == {"apartment_list", "redfin"}
    assert conflict.difference == 280


def test_unit_missing_from_latest_fetch_is_not_current(session):
    first = synthetic_redfin("10 Elm St", [CollectedUnit("unit:a", "unit", "A", None, 1, 1.0, 600, 600, 2800, 2800)], 37.37, -122.03, "s1")
    prop, _ = upsert_listing(session, first, run_id=None, now=FETCHED)
    later = FETCHED + timedelta(hours=2)
    second = replace(
        first,
        fetch=fetch("s2", later),
        units=[CollectedUnit("unit:b", "unit", "B", None, 2, 1.0, 900, 900, 3600, 3600)],
    )
    upsert_listing(session, second, run_id=None, now=later)
    status = evaluate_property_status(session, prop, SETTINGS, later + timedelta(hours=1))
    assert status.status == "excluded"


def test_low_rating_with_enough_reviews_excludes(session, central_park):
    listing = al_listing("al_cp", "central-park-apartments", "cp2")
    listing.rating = CollectedRating(2.4, 87, 5.0, "https://example-source")
    upsert_listing(session, listing, run_id=None, now=FETCHED)
    status = evaluate_property_status(session, central_park, SETTINGS, FETCHED + timedelta(hours=1))
    assert status.status == "excluded" and status.reasons[0]["filter"] == "review_rating"


def test_no_reviews_does_not_exclude(session, central_park):
    status = evaluate_property_status(session, central_park, SETTINGS, FETCHED + timedelta(hours=1))
    assert status.rating.status == "no_reviews" and status.status == "included"


def test_outside_region_is_excluded(session):
    sf = synthetic_redfin("1 Market St", [CollectedUnit("unit:x", "unit", "1", None, 1, 1.0, 600, 600, 2800, 2800)], 37.7936, -122.3958, city="San Francisco")
    prop, _ = upsert_listing(session, sf, run_id=None, now=FETCHED)
    status = evaluate_property_status(session, prop, SETTINGS, FETCHED + timedelta(hours=1))
    assert status.status == "excluded" and status.reasons[0]["filter"] == "geography"


def test_income_restricted_units_do_not_qualify(session):
    units = [CollectedUnit("unit:bmr", "unit", "5", "A5 Income Protected", 1, 1.0, 600, 600, 2400, 2400)]
    prop, _ = upsert_listing(session, synthetic_redfin("20 Oak St", units, 37.37, -122.03, "bmr1"), run_id=None, now=FETCHED)
    status = evaluate_property_status(session, prop, SETTINGS, FETCHED + timedelta(hours=1))
    assert status.status == "excluded"
    assert "income-restricted" in status.reasons[0]["explanation"]

    market = [*units, CollectedUnit("unit:mkt", "unit", "6", "A1", 1, 1.0, 600, 600, 2700, 2700)]
    prop2, _ = upsert_listing(session, synthetic_redfin("30 Oak St", market, 37.38, -122.04, "bmr2"), run_id=None, now=FETCHED)
    status2 = evaluate_property_status(session, prop2, SETTINGS, FETCHED + timedelta(hours=1))
    assert status2.status == "included"
    assert [s.unit.label for s in status2.price.qualifying] == ["6"]
