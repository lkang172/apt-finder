from datetime import UTC, date, datetime

from sqlalchemy import select

from aptfinder import enrichment
from aptfinder.config import Settings
from aptfinder.db.models import CommuteResult, Evidence, Property
from aptfinder.routing.base import RUSH_UNAVAILABLE, RouteResult
from aptfinder.safety.area import AreaSafetyData, AreaSafetyRecord, StatewideReference

NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)
SETTINGS = Settings(_env_file=None)


def make_property(session, name, city, lat=37.37, lon=-122.03) -> Property:
    prop = Property(name=name, city=city, lat=lat, lon=lon, status="included")
    session.add(prop)
    session.flush()
    return prop


def route(lat, lon) -> RouteResult:
    return RouteResult(
        provider="osrm", origin_lat=lat, origin_lon=lon, destination_lat=37.408, destination_lon=-122.018,
        distance_miles=4.3, free_flow_minutes=9.4, am_rush_minutes=None, pm_rush_minutes=None,
        rush_status=RUSH_UNAVAILABLE, computed_at=NOW, source_url="https://router.project-osrm.org/table/v1/driving/x",
        view_url="https://www.openstreetmap.org/directions?route=x", methodology="Free-flow", confidence="medium",
    )


def test_commute_results_become_evidence(session, monkeypatch):
    located = make_property(session, "A", "Sunnyvale")
    missing = make_property(session, "B", "Sunnyvale", lat=None, lon=None)
    monkeypatch.setattr(enrichment, "route_many", lambda origins, *a, **k: {pid: route(*pt) for pid, pt in origins.items()})
    notes = []
    count = enrichment.compute_commutes(session, None, SETTINGS, [located, missing], lambda s, m: notes.append(m))
    assert count == 1
    result = session.scalars(select(CommuteResult)).one()
    evidence = session.get(Evidence, result.evidence_id)
    assert evidence.kind == "commute_fact" and evidence.source_id == "osrm"
    assert "free-flow" in evidence.content and RUSH_UNAVAILABLE in evidence.content
    assert evidence.source_url.startswith("https://router.project-osrm.org/")
    assert any("no coordinates" in n for n in notes)


def test_recomputing_commute_replaces_result(session, monkeypatch):
    prop = make_property(session, "A", "Sunnyvale")
    monkeypatch.setattr(enrichment, "route_many", lambda origins, *a, **k: {pid: route(*pt) for pid, pt in origins.items()})
    enrichment.compute_commutes(session, None, SETTINGS, [prop], lambda s, m: None)
    enrichment.compute_commutes(session, None, SETTINGS, [prop], lambda s, m: None)
    assert len(session.scalars(select(CommuteResult)).all()) == 1


def safety_data() -> AreaSafetyData:
    reference = StatewideReference("California statewide", 2025, 170397, 705925, 39646907, 4.30, 17.81, 0)

    def record(city, status="ok", **kw) -> AreaSafetyRecord:
        base = dict(
            city=city, county="Santa Clara", status=status, year=2025, jurisdiction=city if status == "ok" else None,
            violent_count=293, property_count=2895, population=159955, violent_per_1000=1.83, property_per_1000=18.10,
            reference=reference, source_name="CA DOJ", source_url="https://data-openjustice.doj.ca.gov/x.csv",
            population_source="DOF E-1, January 1, 2025", population_source_url="https://dof.ca.gov/x.xlsx",
            population_as_of=date(2025, 1, 1), retrieved_at=NOW, methodology="m",
        )
        base.update(kw)
        return AreaSafetyRecord(**base)

    records = {
        "sunnyvale": record("Sunnyvale"),
        "san jose": record("San Jose", violent_per_1000=5.10, property_per_1000=24.0),
        "san carlos": record("San Carlos", status="no_city_agency", violent_count=None, property_count=None,
                             violent_per_1000=None, property_per_1000=None, reason="No city-level agency data"),
    }
    return AreaSafetyData(2025, reference, records, record("unlisted", status="unlisted", violent_per_1000=None, property_per_1000=None))


def test_area_safety_attaches_city_level_facts_with_caveat(session, monkeypatch):
    sunnyvale = make_property(session, "A", "Sunnyvale")
    alviso = make_property(session, "B", "Alviso")
    san_carlos = make_property(session, "C", "San Carlos")
    monkeypatch.setattr(enrichment, "load_area_safety", lambda settings, client: safety_data())
    notes = []
    enrichment.attach_area_safety(session, None, SETTINGS, [sunnyvale, alviso, san_carlos], lambda s, m: notes.append(m))
    facts = {e.property_id: e for e in session.scalars(select(Evidence).where(Evidence.kind == "safety_fact"))}
    assert "1.83 per 1,000" in facts[sunnyvale.id].content and "not specific to this neighborhood" in facts[sunnyvale.id].content
    assert facts[alviso.id].data["jurisdiction"] == "San Jose"
    assert facts[san_carlos.id].data["has_city_data"] is False
    assert any("No city-level agency data" in n for n in notes)


def test_google_reviews_skipped_without_key(session):
    prop = make_property(session, "A", "Sunnyvale")
    assert enrichment.collect_google_reviews(session, SETTINGS, [prop], NOW, lambda s, m: None) == 0
