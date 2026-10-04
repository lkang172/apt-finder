import gzip
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from aptfinder.api import app as app_module
from aptfinder.collectors.apartment_list import parse_listing_page
from aptfinder.config import get_settings
from aptfinder.db.models import utcnow
from aptfinder.db.session import session_scope, use_engine
from aptfinder.http import FetchResult
from aptfinder.pipeline import apply_hard_filters
from aptfinder.store import upsert_listing

FIXTURES = Path(__file__).parent / "fixtures"


def listing(name: str, slug: str):
    html = gzip.decompress((FIXTURES / f"{name}.html.gz").read_bytes()).decode()
    fetch = FetchResult("u", "u", 200, "", utcnow(), False, f"sha-{name}", "p")
    return parse_listing_page(html, f"https://www.apartmentlist.com/ca/sunnyvale/{slug}", fetch)


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    use_engine(engine)
    with session_scope() as session:
        upsert_listing(session, listing("al_cp", "central-park-apartments"), None)
        upsert_listing(session, listing("al_enc", "encasa"), None)
        apply_hard_filters(session, get_settings(), utcnow())
    return TestClient(app_module.app)


def test_list_only_returns_hard_filter_passing_properties(client):
    body = client.get("/api/properties").json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["name"] == "Central Park Apartments"
    assert item["unit_types"] == ["1br"]
    assert item["rent_min"] == 2715 and item["est_monthly_total_min"] == 2715
    assert item["has_unknown_required_costs"] is True
    assert item["review"]["status"] == "no_reviews"
    assert item["overall"] == {"score": None, "confidence": "insufficient"}
    assert all(v["score"] is None for v in item["scores"].values())


def test_detail_exposes_sources_costs_and_insufficient_states(client):
    pid = client.get("/api/properties").json()["items"][0]["id"]
    detail = client.get(f"/api/properties/{pid}").json()
    assert detail["listings"][0]["url"] == "https://www.apartmentlist.com/ca/sunnyvale/central-park-apartments"
    assert detail["official_website"]["url"] == "https://www.centralparkaptliving.com/"
    assert "Renter's insurance required" in detail["monthly_cost"]["unknown_required"]
    assert len(detail["assessments"]) == 7
    assert all(a["score"] is None and a["confidence"] == "insufficient" for a in detail["assessments"])
    assert detail["review_intelligence"]["quality"]["summary"] == "Review data: No reviews found"
    qualifying = [u for u in detail["units"] if u["qualifies"]]
    assert qualifying and qualifying[0]["source_url"].startswith("https://www.apartmentlist.com/")


def test_excluded_endpoint_lists_reasons(client):
    excluded = client.get("/api/excluded").json()
    encasa = next(e for e in excluded if e["name"] == "Encasa")
    assert encasa["reasons"][0]["filter"] == "price_and_unit_type"


def test_unknown_property_and_evidence_404(client):
    assert client.get("/api/properties/999999").status_code == 404
    assert client.get("/api/evidence/ev_missing").status_code == 404


def test_evidence_endpoint_returns_source_links(client):
    pid = client.get("/api/properties").json()["items"][0]["id"]
    fact = client.get(f"/api/properties/{pid}").json()["facts"][0]
    evidence = client.get(f"/api/evidence/{fact['id']}").json()
    assert evidence["source_name"] == "Apartment List"


def test_trigger_run_starts_background_run_and_rejects_concurrent(client, monkeypatch):
    import threading
    release = threading.Event()
    calls = []

    def fake_execute(run_id, settings):
        calls.append(run_id)
        release.wait(5)

    monkeypatch.setattr(app_module, "execute_run", fake_execute)
    first = client.post("/api/runs")
    assert first.status_code == 202
    assert client.post("/api/runs").status_code == 409
    release.set()


def test_meta_reports_office_and_search(client):
    meta = client.get("/api/meta").json()
    assert meta["office"]["address"] == "242 Humboldt Ct, Sunnyvale, CA 94089"
    assert meta["search"] == {"min_rent": 2500, "max_rent": 3000, "unit_types": ["studio", "1br"]}


def test_undisclosed_required_fees_are_unknown_not_zero(client):
    from aptfinder.collectors.types import CollectedListing, CollectedUnit

    synthetic = CollectedListing(
        source_id="redfin", source_listing_id="rf-test", url="https://www.redfin.com/CA/Sunnyvale/x/apartment/9",
        name="Synthetic Fee Test", street_address="10 Elm St", city="Sunnyvale", state="CA", zip="94086",
        lat=37.37, lon=-122.03, fetch=FetchResult("u", "u", 200, "", utcnow(), False, "sha-fee", "p"),
        units=[CollectedUnit("unit:a", "unit", "A", None, 1, 1.0, 600, 600, 2800, 2800)],
    )
    with session_scope() as session:
        prop, _ = upsert_listing(session, synthetic, None)
        apply_hard_filters(session, get_settings(), utcnow())
        pid = prop.id
    cost = client.get(f"/api/properties/{pid}").json()["monthly_cost"]
    assert cost["confirmed_required_fees"] is None
    assert cost["est_total_min"] == 2800
    assert "Required monthly fees are not published by the listing source" in cost["unknown_required"]

    declared = client.get("/api/properties").json()["items"]
    central = next(i for i in declared if i["name"] == "Central Park Apartments")
    detail = client.get(f"/api/properties/{central['id']}").json()
    assert detail["monthly_cost"]["confirmed_required_fees"] == 0
