import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from aptfinder.config import Settings
from aptfinder.http import PoliteClient
from aptfinder.routing import service
from aptfinder.routing.base import RUSH_UNAVAILABLE, google_maps_directions_url
from aptfinder.routing.google_routes import (
    COMPUTE_ROUTES_URL,
    GoogleRoutesProvider,
    next_commute_departures,
    parse_duration,
)
from aptfinder.routing.osrm import MAX_ORIGINS_PER_REQUEST, OsrmProvider
from aptfinder.routing.service import route_many

FIXTURES = Path(__file__).parent / "fixtures"
OFFICE = (37.408084124783, -122.018319487984)
ORIGINS = {
    "sunnyvale": (37.357268, -122.027901),
    "bay_water": (37.5, -122.1),
    "fremont": (37.5485, -121.988),
}
API_KEY = "test-key-should-never-leak"


def make_client(tmp_path, handler) -> PoliteClient:
    return PoliteClient(tmp_path, "test-agent", transport=httpx.MockTransport(handler), sleep=lambda _s: None)


def osrm_handler(table_response, seen: list[httpx.Request] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(400, json={"code": "InvalidUrl"})
        if seen is not None:
            seen.append(request)
        body = table_response(request) if callable(table_response) else table_response
        return httpx.Response(200, json=body)

    return handler


def fixture_table() -> dict:
    return json.loads((FIXTURES / "routing_osrm_table.json").read_text())


def settings(tmp_path, key: str = "") -> Settings:
    return Settings(data_dir=tmp_path, google_maps_api_key=key)


def test_osrm_table_request_batches_origins_to_the_office(tmp_path):
    seen: list[httpx.Request] = []
    client = make_client(tmp_path, osrm_handler(fixture_table(), seen))
    batch = OsrmProvider(client).route_many(ORIGINS, OFFICE)

    assert len(seen) == 1
    url = str(seen[0].url)
    coordinates = "-122.027901,37.357268;-122.100000,37.500000;-121.988000,37.548500;-122.018319,37.408084"
    assert urlsplit(url).path == f"/table/v1/driving/{coordinates}"
    query = parse_qs(urlsplit(url).query)
    assert query == {"sources": ["0;1;2"], "destinations": ["3"], "annotations": ["duration,distance"]}
    assert seen[0].headers["accept"] == "application/json"
    assert batch.failures == {}

    sunnyvale = batch.results["sunnyvale"]
    assert sunnyvale.distance_miles == round(7859.5 / 1609.344, 1) == 4.9
    assert sunnyvale.free_flow_minutes == round(676.9 / 60, 1) == 11.3
    assert sunnyvale.am_rush_minutes is None and sunnyvale.pm_rush_minutes is None
    assert sunnyvale.rush_status == RUSH_UNAVAILABLE
    assert sunnyvale.confidence == "medium"
    assert sunnyvale.provider == "osrm"
    assert sunnyvale.source_url == url
    assert sunnyvale.computed_at.tzinfo is not None
    assert sunnyvale.view_url == (
        "https://www.openstreetmap.org/directions?engine=fossgis_osrm_car"
        "&route=37.357268,-122.027901;37.408084,-122.018319"
    )
    for phrase in ("OSRM", "OpenStreetMap", "typical road speeds", "does not account for traffic", "differ slightly"):
        assert phrase in sunnyvale.methodology
    assert batch.results["fremont"].distance_miles == 17.1


def test_osrm_flags_origins_far_from_any_road(tmp_path):
    client = make_client(tmp_path, osrm_handler(fixture_table()))
    water = OsrmProvider(client).route_many(ORIGINS, OFFICE).results["bay_water"]
    assert water.confidence == "low"
    assert "nearest routable road" in water.methodology


def test_osrm_unroutable_cell_yields_no_numbers(tmp_path):
    table = {
        "code": "Ok",
        "durations": [[None], [600.0]],
        "distances": [[None], [8000.0]],
        "sources": [{"distance": 3.0}, {"distance": 2.0}],
    }
    client = make_client(tmp_path, osrm_handler(table))
    batch = OsrmProvider(client).route_many({"island": (37.0, -122.0), "ok": (37.3, -122.0)}, OFFICE)
    island = batch.results["island"]
    assert island.distance_miles is None and island.free_flow_minutes is None
    assert island.rush_status.startswith(RUSH_UNAVAILABLE)
    assert "no drivable route" in island.rush_status
    assert island.confidence == "insufficient"
    assert batch.results["ok"].free_flow_minutes == 10.0


def test_osrm_error_code_records_failure_instead_of_numbers(tmp_path):
    client = make_client(tmp_path, osrm_handler({"code": "InvalidQuery", "message": "bad coordinates"}))
    batch = OsrmProvider(client).route_many({"a": (37.3, -122.0)}, OFFICE)
    assert batch.results == {}
    assert "InvalidQuery" in batch.failures["a"]


def test_osrm_splits_large_batches_and_dedupes_identical_coordinates(tmp_path):
    seen: list[httpx.Request] = []

    def table(request: httpx.Request) -> dict:
        count = len(parse_qs(request.url.query.decode())["sources"][0].split(";"))
        return {
            "code": "Ok",
            "durations": [[60.0 * (i + 1)] for i in range(count)],
            "distances": [[1609.344 * (i + 1)] for i in range(count)],
            "sources": [{"distance": 1.0}] * count,
        }

    client = make_client(tmp_path, osrm_handler(table, seen))
    origins = {f"p{i}": (37.3 + i * 0.001, -122.0) for i in range(MAX_ORIGINS_PER_REQUEST + 10)}
    origins["twin"] = origins["p0"]
    batch = OsrmProvider(client).route_many(origins, OFFICE)

    assert len(seen) == 2
    assert [len(parse_qs(r.url.query.decode())["sources"][0].split(";")) for r in seen] == [MAX_ORIGINS_PER_REQUEST, 10]
    assert all(len(str(r.url)) < 2000 for r in seen)
    assert set(batch.results) == set(origins)
    assert batch.results["twin"] == batch.results["p0"]


def test_osrm_results_are_cached_between_runs(tmp_path):
    seen: list[httpx.Request] = []
    client = make_client(tmp_path, osrm_handler(fixture_table(), seen))
    first = OsrmProvider(client).route_many(ORIGINS, OFFICE)
    second = OsrmProvider(client).route_many(ORIGINS, OFFICE)
    assert len(seen) == 1
    assert second.results["sunnyvale"].computed_at == first.results["sunnyvale"].computed_at


@pytest.mark.parametrize(
    ("now_utc", "expected_am_local"),
    [
        (datetime(2026, 10, 2, 22, 0, tzinfo=UTC), "2026-10-05T08:30:00-07:00"),  # Friday 3 PM PDT
        (datetime(2026, 10, 3, 18, 0, tzinfo=UTC), "2026-10-05T08:30:00-07:00"),  # Saturday
        (datetime(2026, 10, 5, 14, 0, tzinfo=UTC), "2026-10-05T08:30:00-07:00"),  # Monday 7 AM PDT
        (datetime(2026, 10, 5, 16, 0, tzinfo=UTC), "2026-10-06T08:30:00-07:00"),  # Monday 9 AM PDT
        (datetime(2026, 10, 30, 23, 0, tzinfo=UTC), "2026-11-02T08:30:00-08:00"),  # across the DST change
    ],
)
def test_next_commute_departures_uses_next_weekday_in_pacific_time(now_utc, expected_am_local):
    departures = next_commute_departures(now_utc)
    assert departures.am.isoformat() == expected_am_local
    assert departures.pm.date() == departures.am.date()
    assert (departures.pm.hour, departures.pm.minute) == (17, 30)


def google_handler(responses: list[httpx.Response], seen: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responses[min(len(seen), len(responses)) - 1]

    return handler


def route_json(distance_m: int, duration: str, static: str) -> httpx.Response:
    return httpx.Response(
        200, json={"routes": [{"distanceMeters": distance_m, "duration": duration, "staticDuration": static}]}
    )


def test_google_routes_requests_traffic_aware_am_and_pm_legs(tmp_path):
    seen: list[httpx.Request] = []
    responses = [route_json(7860, "1500s", "690s"), route_json(7900, "1320.5s", "700s")]
    provider = GoogleRoutesProvider(
        API_KEY,
        transport=httpx.MockTransport(google_handler(responses, seen)),
        now=lambda: datetime(2026, 10, 2, 22, 0, tzinfo=UTC),
    )
    batch = provider.route_many({"home": ORIGINS["sunnyvale"]}, OFFICE)

    am_body, pm_body = (json.loads(r.content) for r in seen)
    assert all(str(r.url) == COMPUTE_ROUTES_URL and r.method == "POST" for r in seen)
    assert seen[0].headers["x-goog-api-key"] == API_KEY
    assert seen[0].headers["x-goog-fieldmask"] == "routes.duration,routes.distanceMeters,routes.staticDuration"
    assert am_body["routingPreference"] == "TRAFFIC_AWARE_OPTIMAL" and am_body["travelMode"] == "DRIVE"
    assert am_body["departureTime"] == "2026-10-05T15:30:00Z"
    assert pm_body["departureTime"] == "2026-10-06T00:30:00Z"
    assert am_body["origin"]["location"]["latLng"] == {"latitude": 37.357268, "longitude": -122.027901}
    assert pm_body["origin"] == am_body["destination"] and pm_body["destination"] == am_body["origin"]

    route = batch.results["home"]
    assert route.provider == "google_routes"
    assert route.distance_miles == 4.9
    assert route.free_flow_minutes == 11.5
    assert route.am_rush_minutes == 25.0
    assert route.pm_rush_minutes == 22.0
    assert route.confidence == "high"
    assert "predict" in route.methodology and "BEST_GUESS" in route.methodology
    assert "not observed travel" in route.methodology
    assert "Monday, October 5, 2026" in route.methodology
    assert route.view_url == google_maps_directions_url(ORIGINS["sunnyvale"], OFFICE)
    assert API_KEY not in (route.source_url or "") and API_KEY not in (route.view_url or "")


def test_google_failure_falls_back_to_osrm_and_says_so(tmp_path):
    seen: list[httpx.Request] = []
    failure = httpx.Response(500, json={"error": {"code": 500, "message": "Internal error"}})
    google = GoogleRoutesProvider(API_KEY, transport=httpx.MockTransport(google_handler([failure], seen)))
    client = make_client(tmp_path, osrm_handler(fixture_table()))

    results = route_many(ORIGINS, settings(tmp_path).office, settings(tmp_path), client, traffic_provider=google)

    assert set(results) == set(ORIGINS)
    fallback = results["sunnyvale"]
    assert fallback.provider == "osrm"
    assert fallback.am_rush_minutes is None and fallback.pm_rush_minutes is None
    assert fallback.rush_status.startswith(RUSH_UNAVAILABLE)
    assert "google_routes request failed: HTTP 500: Internal error" in fallback.rush_status
    assert "OSRM free-flow" in fallback.rush_status
    assert fallback.free_flow_minutes == 11.3


def test_google_permission_error_stops_further_calls(tmp_path):
    seen: list[httpx.Request] = []
    denied = httpx.Response(403, json={"error": {"code": 403, "message": "Routes API has not been enabled"}})
    google = GoogleRoutesProvider(API_KEY, transport=httpx.MockTransport(google_handler([denied], seen)))
    batch = google.route_many(ORIGINS, OFFICE)
    assert len(seen) == 1
    assert set(batch.failures) == set(ORIGINS)
    assert all("HTTP 403" in reason for reason in batch.failures.values())


def test_google_empty_response_is_a_failure_not_a_number(tmp_path):
    seen: list[httpx.Request] = []
    empty = httpx.MockTransport(google_handler([httpx.Response(200, json={})], seen))
    google = GoogleRoutesProvider(API_KEY, transport=empty)
    batch = google.route_many({"home": ORIGINS["sunnyvale"]}, OFFICE)
    assert batch.results == {} and batch.failures == {"home": "no route returned"}


def test_route_many_without_key_uses_osrm_only(tmp_path):
    client = make_client(tmp_path, osrm_handler(fixture_table()))
    config = settings(tmp_path)
    results = route_many(ORIGINS, config.office, config, client)
    assert {r.provider for r in results.values()} == {"osrm"}
    assert all(r.rush_status == RUSH_UNAVAILABLE for r in results.values())
    assert client.min_intervals["router.project-osrm.org"] == config.osrm_min_interval_s


def test_route_many_uses_google_only_when_explicitly_enabled(tmp_path, monkeypatch):
    seen: list[httpx.Request] = []
    transport = httpx.MockTransport(google_handler([route_json(7860, "1500s", "690s")], seen))
    keys: list[str] = []

    def provider_with_mock_transport(api_key: str) -> GoogleRoutesProvider:
        keys.append(api_key)
        return GoogleRoutesProvider(api_key, transport=transport)

    monkeypatch.setattr(service, "GoogleRoutesProvider", provider_with_mock_transport)
    client = make_client(tmp_path, lambda request: pytest.fail("OSRM must not be called"))
    config = settings(tmp_path, key=API_KEY).model_copy(update={"google_routes_enabled": True})
    results = route_many({"home": ORIGINS["sunnyvale"]}, config.office, config, client)
    assert keys == [API_KEY]
    assert results["home"].provider == "google_routes"
    assert results["home"].am_rush_minutes == 25.0


def test_parse_duration_accepts_protobuf_durations():
    assert parse_duration("1234s") == 1234.0
    assert parse_duration("0.5s") == 0.5
    with pytest.raises(ValueError):
        parse_duration("1234")


def test_google_maps_directions_url_uses_documented_scheme():
    assert google_maps_directions_url((37.357268, -122.027901), OFFICE) == (
        "https://www.google.com/maps/dir/?api=1&origin=37.357268,-122.027901"
        "&destination=37.408084,-122.018319&travelmode=driving"
    )
