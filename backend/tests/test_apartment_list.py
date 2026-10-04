import gzip
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aptfinder.collectors.apartment_list import parse_city_page, parse_listing_page
from aptfinder.collectors.page_data import iter_flight_rows
from aptfinder.http import FetchResult

FIXTURES = Path(__file__).parent / "fixtures"
FETCH = FetchResult("u", "u", 200, "", datetime(2026, 10, 3, tzinfo=UTC), False, "sha", "path")


def load(name: str) -> str:
    return gzip.decompress((FIXTURES / f"{name}.html.gz").read_bytes()).decode()


@pytest.fixture(scope="module")
def encasa():
    return parse_listing_page(load("al_enc"), "https://www.apartmentlist.com/ca/sunnyvale/encasa", FETCH)


@pytest.fixture(scope="module")
def arches():
    return parse_listing_page(load("al_arches"), "https://www.apartmentlist.com/ca/sunnyvale/the-arches", FETCH)


def test_city_page_discovers_all_listings_with_min_prices():
    stubs, total = parse_city_page(load("al_sunnyvale"))
    assert total == 44 and len(stubs) == 44
    cherry = next(s for s in stubs if s.name == "Cherry Blossom Apartments")
    assert cherry.min_price_by_beds[1] == 2450
    assert cherry.url == "https://www.apartmentlist.com/ca/sunnyvale/cherry-blossom-apartments"


def test_prefilter_never_drops_property_with_cheap_eligible_unit():
    stubs, _ = parse_city_page(load("al_sunnyvale"))
    for stub in stubs:
        eligible = [p for b, p in stub.min_price_by_beds.items() if b in (0, 1) and p]
        if eligible and min(eligible) <= 3000:
            assert stub.may_have_qualifying_unit((0, 1), 3000)


def test_text_rows_do_not_swallow_following_json_rows():
    kinds = [kind for kind, _ in iter_flight_rows(load("al_enc"))]
    assert "text" in kinds and kinds.count("json") > 100


def test_listing_identity_and_location(encasa):
    assert encasa.source_listing_id == "p1070038"
    assert encasa.street_address == "550 E Weddell Dr"
    assert encasa.city == "Sunnyvale" and encasa.zip == "94089"
    assert encasa.lat == pytest.approx(37.398975)


def test_unit_prices_separate_base_total_and_required_fees(encasa):
    unit = next(u for u in encasa.units if u.label == "0115")
    assert unit.beds == 1 and unit.kind == "unit"
    assert unit.base_rent_min == 3741
    assert unit.total_monthly == pytest.approx(3747)
    assert unit.required_fees_monthly == pytest.approx(5.33)
    assert unit.lease_term_months == 12
    assert unit.source_updated_at.tzinfo is not None


def test_fee_text_preserved_without_invented_amounts(encasa):
    trash = next(f for f in encasa.fees if f.fee_type == "trash")
    assert trash.amount == 25 and trash.recurring and trash.mandatory is None
    insurance = next(f for f in encasa.fees if f.fee_type == "insurance")
    assert insurance.amount is None and insurance.mandatory is True


def test_pricing_disclosure_and_fee_document_are_kept_as_facts(encasa):
    keys = {f.key: f for f in encasa.facts}
    assert "mandatory monthly fees" in keys["pricing_disclosure"].content
    assert keys["fee_document"].url.startswith("https://www.canva.com/")


def test_official_website_comes_from_listing(encasa, arches):
    assert encasa.official_website_url.startswith("https://www.encasaliving.com/")
    assert arches.official_website_url.startswith("https://www.equityapartments.com/")


def test_reviews_keep_date_author_text_and_subscores(arches):
    assert len(arches.reviews) == 1
    review = arches.reviews[0]
    assert review.reviewer == "Espinoza"
    assert review.review_date == datetime(2024, 8, 19, 11, 12, 27, tzinfo=UTC)
    assert review.subscores["noise"] == 5 and review.subscores["management"] == 4
    assert "kept nice and clean" in review.text
    assert arches.rating.count == 1 and arches.rating.average == 5.0


def test_no_reviews_is_explicit_not_positive(encasa):
    assert encasa.reviews == []
    assert encasa.rating.count == 0 and encasa.rating.average is None


def test_review_keys_are_stable():
    first = parse_listing_page(load("al_arches"), "https://x", FETCH).reviews[0].source_review_key
    second = parse_listing_page(load("al_arches"), "https://x", FETCH).reviews[0].source_review_key
    assert first == second
