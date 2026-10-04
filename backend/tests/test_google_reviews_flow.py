import gzip
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from aptfinder.api import app as app_module
from aptfinder.collectors.apartment_list import parse_listing_page
from aptfinder.collectors.google_places import GooglePlaceReviews, GoogleReviewSummary, PlaceMatch
from aptfinder.collectors.types import CollectedRating, CollectedReview
from aptfinder.config import Settings, get_settings
from aptfinder.db.models import Evidence, GooglePlaceMatch, Property, utcnow
from aptfinder.db.session import session_scope, use_engine
from aptfinder.enrichment import collect_google_reviews
from aptfinder.evaluation import area_input, commute_input, persist_assessments, rating_inputs, review_inputs
from aptfinder.evaluators import evaluate_all
from aptfinder.http import FetchResult
from aptfinder.pipeline import apply_hard_filters
from aptfinder.store import upsert_listing

FIXTURES = Path(__file__).parent / "fixtures"
KEYED = Settings(_env_file=None, google_maps_api_key="test-key")
MAPS_URL = "https://maps.google.com/?cid=123"


def fake_factory(rating: float, count: int, texts: list[str], summary: str | None):
    class FakePlaces:
        calls = 0
        searches = 0

        def __init__(self, api_key):
            assert api_key == "test-key"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def find_place(self, query):
            FakePlaces.searches += 1
            return PlaceMatch("place-1", query.name, "1055 Manet Dr, Sunnyvale, CA", query.lat, query.lon, 12.0, True, 1.0, "exact")

        def fetch_reviews(self, match):
            FakePlaces.calls += 1
            now = utcnow()
            reviews = [
                CollectedReview(f"r{i}", f"Reviewer {i}", 1.0, now - timedelta(days=30 * (i + 1)), text, review_url=f"{MAPS_URL}&r={i}")
                for i, text in enumerate(texts)
            ]
            summary_obj = GoogleReviewSummary(summary, "Summarized with Gemini", "https://flag", MAPS_URL + "&reviews") if summary else None
            return GooglePlaceReviews(match, CollectedRating(rating, count, 5.0, MAPS_URL), reviews, MAPS_URL, now, [], summary_obj)

    return FakePlaces


@pytest.fixture
def central_park():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    use_engine(engine)
    html = gzip.decompress((FIXTURES / "al_cp.html.gz").read_bytes()).decode()
    listing = parse_listing_page(html, "https://www.apartmentlist.com/ca/sunnyvale/central-park-apartments",
                                 FetchResult("u", "u", 200, "", utcnow(), False, "sha", "p"))
    with session_scope() as session:
        prop, _ = upsert_listing(session, listing, None)
        apply_hard_filters(session, get_settings(), utcnow())
        return prop.id


COCKROACH_TEXTS = [
    "Cockroaches everywhere in the kitchen, management never fixed it.",
    "Roaches keep coming back every summer.",
    "Saw cockroaches in the bathroom the first week.",
    "Thin walls, I hear my neighbors all night.",
    "Maintenance takes weeks to respond.",
]


def test_low_google_rating_excludes_property(central_park):
    factory = fake_factory(1.6, 47, COCKROACH_TEXTS, "Residents frequently report cockroaches and slow maintenance.")
    with session_scope() as session:
        props = list(session.scalars(select(Property).where(Property.status == "included")))
        assert collect_google_reviews(session, KEYED, props, utcnow(), lambda s, m: None, client_factory=factory) == 1
        apply_hard_filters(session, KEYED, utcnow())
        prop = session.get(Property, central_park)
        assert prop.status == "excluded"
        assert prop.exclusion_reasons[0]["filter"] == "review_rating"
        assert "google_places: 1.6/5 (47 reviews)" in prop.exclusion_reasons[0]["explanation"]


def test_google_reviews_and_summary_feed_category_scores(central_park):
    factory = fake_factory(4.1, 33, COCKROACH_TEXTS, "Residents frequently report cockroaches and slow maintenance.")
    now = utcnow()
    with session_scope() as session:
        prop = session.get(Property, central_park)
        collect_google_reviews(session, KEYED, [prop], now, lambda s, m: None, client_factory=factory)
        apply_hard_filters(session, KEYED, now)
        assert prop.status == "included"
        reviews = review_inputs(session, prop)
        assert sum(r.is_summary for r in reviews) == 1 and len(reviews) == 6
        drafts = evaluate_all(reviews, rating_inputs(session, prop), commute_input(session, prop), area_input(session, prop), now)
        quality = drafts.pop("review_quality")
        audited = persist_assessments(session, prop, drafts, None, now, review_quality=quality)
        pests = audited["pests"]
        assert pests.score is not None and pests.score < 5
        summary_id = next(r.evidence_id for r in reviews if r.is_summary)
        assert any(summary_id in c.evidence_ids for c in pests.claims)
        assert quality.details["total_reviews"] == 5


def test_lookup_is_not_repeated_within_refresh_window(central_park):
    factory = fake_factory(4.1, 33, COCKROACH_TEXTS[:1], None)
    with session_scope() as session:
        prop = session.get(Property, central_park)
        collect_google_reviews(session, KEYED, [prop], utcnow(), lambda s, m: None, client_factory=factory)
        collect_google_reviews(session, KEYED, [prop], utcnow(), lambda s, m: None, client_factory=factory)
        assert factory.calls == 1
        collect_google_reviews(session, KEYED, [prop], utcnow() + timedelta(days=31), lambda s, m: None, client_factory=factory)
        assert factory.calls == 2
        assert factory.searches == 1


def test_api_exposes_google_brief(central_park, monkeypatch):
    factory = fake_factory(4.1, 33, COCKROACH_TEXTS[:2], "Residents mention cockroaches.")
    with session_scope() as session:
        prop = session.get(Property, central_park)
        collect_google_reviews(session, KEYED, [prop], utcnow(), lambda s, m: None, client_factory=factory)
    monkeypatch.setattr(app_module, "get_settings", lambda: KEYED)
    client = TestClient(app_module.app)
    google = client.get("/api/properties").json()["items"][0]["google"]
    assert google["status"] == "ok" and google["rating"] == 4.1 and google["count"] == 33
    assert google["summary"] == "Residents mention cockroaches." and google["summary_disclosure"] == "Summarized with Gemini"
    assert google["maps_url"] == MAPS_URL and google["match_confidence"] == "exact"
    detail = client.get(f"/api/properties/{central_park}").json()
    kinds = {r["kind"] for r in detail["review_intelligence"]["reviews"]}
    assert kinds == {"review", "review_summary"}
    assert detail["review"]["count"] == 0 and detail["review"]["explanation"] == "No reviews found on Apartment List"
    summary_item = next(r for r in detail["review_intelligence"]["reviews"] if r["kind"] == "review_summary")
    assert summary_item["data"]["summary_disclosure"] == "Summarized with Gemini"


def test_api_without_key_says_google_not_checked(central_park, monkeypatch):
    monkeypatch.setattr(app_module, "get_settings", lambda: Settings(_env_file=None))
    client = TestClient(app_module.app)
    item = client.get("/api/properties").json()["items"][0]
    assert item["google"]["status"] == "not_configured"
    assert "not configured" in item["google"]["explanation"]
    assert item["review"]["explanation"] == "No reviews found on Apartment List"
    detail = client.get(f"/api/properties/{central_park}").json()
    assert "Google reviews not checked" in detail["rating_filter"]["explanation"]


def test_no_match_is_recorded_not_treated_as_no_reviews(central_park):
    class NoMatch:
        def __init__(self, key): ...
        def __enter__(self): return self
        def __exit__(self, *exc): return None
        def find_place(self, query): return None
        def fetch_reviews(self, match): raise AssertionError("details must not be fetched without a match")

    with session_scope() as session:
        prop = session.get(Property, central_park)
        collect_google_reviews(session, KEYED, [prop], utcnow(), lambda s, m: None, client_factory=NoMatch)
        row = session.get(GooglePlaceMatch, prop.id)
        assert row.status == "no_match" and "150 m" in row.reason
        assert not session.scalars(select(Evidence).where(Evidence.source_id == "google_places")).all()


def test_budget_exhaustion_stops_before_any_extra_request(central_park):
    from aptfinder.api_budget import PLACE_DETAILS_ENTERPRISE_ATMOSPHERE, calls_this_period

    tight = Settings(_env_file=None, google_maps_api_key="test-key", google_details_monthly_budget=0)
    factory = fake_factory(4.1, 33, COCKROACH_TEXTS[:1], None)
    notes = []
    with session_scope() as session:
        prop = session.get(Property, central_park)
        assert collect_google_reviews(session, tight, [prop], utcnow(), lambda s, m: notes.append(m), client_factory=factory) == 0
        assert factory.calls == 0
        assert calls_this_period(session, PLACE_DETAILS_ENTERPRISE_ATMOSPHERE, utcnow()) == 0
    assert any("free usage" in n for n in notes)


def test_every_call_is_counted_before_it_is_made(central_park):
    from aptfinder.api_budget import PLACE_DETAILS_ENTERPRISE_ATMOSPHERE, TEXT_SEARCH_PRO, calls_this_period

    factory = fake_factory(4.1, 33, COCKROACH_TEXTS[:1], None)
    with session_scope() as session:
        prop = session.get(Property, central_park)
        collect_google_reviews(session, KEYED, [prop], utcnow(), lambda s, m: None, client_factory=factory)
        assert calls_this_period(session, TEXT_SEARCH_PRO, utcnow()) == 1
        assert calls_this_period(session, PLACE_DETAILS_ENTERPRISE_ATMOSPHERE, utcnow()) == 1


def test_configured_budget_can_never_exceed_free_cap():
    from aptfinder.api_budget import FREE_MONTHLY_CAPS, PLACE_DETAILS_ENTERPRISE_ATMOSPHERE, TEXT_SEARCH_PRO, effective_budget

    assert effective_budget(PLACE_DETAILS_ENTERPRISE_ATMOSPHERE, 10**9) == FREE_MONTHLY_CAPS[PLACE_DETAILS_ENTERPRISE_ATMOSPHERE] == 1000
    assert effective_budget(TEXT_SEARCH_PRO, 10**9) == 5000
    assert effective_budget(TEXT_SEARCH_PRO, -5) == 0


def test_billing_period_uses_pacific_time():
    from aptfinder.api_budget import billing_period

    assert billing_period(datetime(2026, 11, 1, 5, 0, tzinfo=UTC)) == "2026-10"
    assert billing_period(datetime(2026, 11, 1, 9, 0, tzinfo=UTC)) == "2026-11"


def test_routes_api_is_never_used_unless_explicitly_enabled(monkeypatch):
    from aptfinder.config import Office
    from aptfinder.routing import service

    used = []

    class FakeGoogleRoutes:
        def __init__(self, key):
            used.append(key)

    class FakeOsrm:
        def __init__(self, client):
            ...

        def route_many(self, origins, destination):
            from aptfinder.routing.base import RouteBatch

            return RouteBatch()

    class FakeClient:
        min_intervals = {}

    monkeypatch.setattr(service, "GoogleRoutesProvider", FakeGoogleRoutes)
    monkeypatch.setattr(service, "OsrmProvider", FakeOsrm)
    office = Office("o", "a", 37.4, -122.0, "x")
    service.route_many({1: (37.3, -122.0)}, office, KEYED, FakeClient())
    assert used == []


def test_google_brief_includes_keyword_comments_summary(central_park, monkeypatch):
    factory = fake_factory(1.6, 8, COCKROACH_TEXTS, None)
    with session_scope() as session:
        prop = session.get(Property, central_park)
        collect_google_reviews(session, KEYED, [prop], utcnow(), lambda s, m: None, client_factory=factory)
    monkeypatch.setattr(app_module, "get_settings", lambda: KEYED)
    detail = TestClient(app_module.app).get(f"/api/properties/{central_park}").json()
    google = detail["google"]
    assert google["summary"] is None
    assert google["comments_summary"].startswith("Complaints: ")
    assert "cockroach" in google["comments_summary"].lower()
    assert "not AI-generated" in google["comments_summary_method"]
