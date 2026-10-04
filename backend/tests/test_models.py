from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError, StatementError

from aptfinder.db.models import (
    CategoryAssessment,
    Claim,
    ClaimEvidence,
    Evidence,
    ListingSource,
    Property,
    Review,
    Source,
)
from aptfinder.ids import stable_id


def _property(session) -> Property:
    prop = Property(name="Test Apartments", city="Sunnyvale", state="CA")
    session.add(prop)
    session.flush()
    return prop


def test_known_sources_seeded(session):
    assert session.get(Source, "apartment_list").kind == "listing"
    assert session.get(Source, "osrm").kind == "routing"


def test_datetimes_round_trip_as_utc(session):
    prop = _property(session)
    pacific = timezone(timedelta(hours=-7))
    ev = Evidence(
        id=stable_id("ev", "x"),
        property_id=prop.id,
        kind="review",
        source_id="apartment_list",
        title="t",
        content="c",
        published_at=datetime(2026, 1, 1, 8, 0, tzinfo=pacific),
    )
    session.add(ev)
    session.commit()
    session.expire_all()
    loaded = session.get(Evidence, ev.id)
    assert loaded.published_at == datetime(2026, 1, 1, 15, 0, tzinfo=UTC)
    assert loaded.published_at.tzinfo is not None


def test_naive_datetimes_rejected(session):
    prop = _property(session)
    session.add(
        Evidence(
            id="ev_naive", property_id=prop.id, kind="review", source_id="apartment_list",
            title="t", content="c", published_at=datetime(2026, 1, 1),
        )
    )
    with pytest.raises(StatementError):
        session.flush()


def test_claim_links_to_evidence_and_source(session):
    prop = _property(session)
    ev = Evidence(
        id=stable_id("ev", "review", 1), property_id=prop.id, kind="review", source_id="apartment_list",
        source_url="https://www.apartmentlist.com/ca/sunnyvale/test", title="Review", content="Thin walls.",
        categories=["noise"],
    )
    session.add(ev)
    session.add(Review(evidence_id=ev.id, property_id=prop.id, source_id="apartment_list", source_review_key="r1", text="Thin walls."))
    assessment = CategoryAssessment(property_id=prop.id, category="noise", confidence="low", summary="s")
    claim = Claim(property_id=prop.id, text="1 review mentions thin walls", polarity="negative")
    claim.evidence_links.append(ClaimEvidence(evidence_id=ev.id))
    assessment.claims.append(claim)
    session.add(assessment)
    session.commit()

    loaded = session.get(CategoryAssessment, assessment.id)
    linked = session.get(Evidence, loaded.claims[0].evidence_links[0].evidence_id)
    assert linked.source.name == "Apartment List"
    assert linked.source_url.startswith("https://www.apartmentlist.com/")


def test_listing_source_unique_per_source_listing(session):
    prop = _property(session)
    session.add(ListingSource(property_id=prop.id, source_id="apartment_list", source_listing_id="p1"))
    session.add(ListingSource(property_id=prop.id, source_id="redfin", source_listing_id="p1"))
    session.flush()
    session.add(ListingSource(property_id=prop.id, source_id="apartment_list", source_listing_id="p1"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_stable_id_is_deterministic():
    assert stable_id("ev", "a", 1) == stable_id("ev", "a", 1)
    assert stable_id("ev", "a", 1) != stable_id("ev", "a", 2)
