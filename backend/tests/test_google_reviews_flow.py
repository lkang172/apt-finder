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

        def __init__(self, api_key):
            assert api_key == "test-key"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def collect(self, query):
            FakePlaces.calls += 1
            now = utcnow()
            match = PlaceMatch("place-1", query.name, "1055 Manet Dr, Sunnyvale, CA", query.lat, query.lon, 12.0, True, 1.0, "exact")
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
        collect_google_reviews(session, KEYED, [prop], utcnow() + timedelta(days=8), lambda s, m: None, client_factory=factory)
        assert factory.calls == 2


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
        def collect(self, query): return None

    with session_scope() as session:
        prop = session.get(Property, central_park)
        collect_google_reviews(session, KEYED, [prop], utcnow(), lambda s, m: None, client_factory=NoMatch)
        row = session.get(GooglePlaceMatch, prop.id)
        assert row.status == "no_match" and "150 m" in row.reason
        assert not session.scalars(select(Evidence).where(Evidence.source_id == "google_places")).all()
