import json
import logging
from collections.abc import Hashable, Iterator, Mapping
from datetime import timedelta
from urllib.parse import urlsplit

from aptfinder.http import FetchError, FetchResult, PoliteClient
from aptfinder.routing.base import (
    RUSH_UNAVAILABLE,
    LatLon,
    RouteBatch,
    RouteResult,
    RoutingError,
    format_lat_lon,
    meters_to_miles,
    seconds_to_minutes,
)

log = logging.getLogger(__name__)

PROVIDER_ID = "osrm"
OSRM_BASE_URL = "https://router.project-osrm.org"
OSRM_HOST = urlsplit(OSRM_BASE_URL).netloc
OSRM_CACHE_TTL = timedelta(days=7)
# Small batches stay well under the demo server's table-size limit and keep each request URL,
# which is stored as the evidence source URL, under 2,000 characters.
MAX_ORIGINS_PER_REQUEST = 60
SNAP_WARNING_METERS = 300.0

METHODOLOGY = (
    "Free-flow driving time and distance from OSRM (the public router.project-osrm.org demo server) using "
    "OpenStreetMap road data and typical road speeds. It does not account for traffic, so it is a best-case "
    "time; rush-hour estimates are unavailable without a traffic-aware routing API. The OpenStreetMap "
    "directions link uses a different OSRM instance, so its numbers may differ slightly."
)


class OsrmProvider:
    provider_id = PROVIDER_ID

    def __init__(self, client: PoliteClient, base_url: str = OSRM_BASE_URL):
        self.client = client
        self.base_url = base_url.rstrip("/")

    def route_many[K: Hashable](self, origins: Mapping[K, LatLon], destination: LatLon) -> RouteBatch[K]:
        batch: RouteBatch[K] = RouteBatch()
        keys_by_point: dict[LatLon, list[K]] = {}
        for key, point in origins.items():
            keys_by_point.setdefault(_rounded(point), []).append(key)

        for chunk in _chunks(sorted(keys_by_point), MAX_ORIGINS_PER_REQUEST):
            url = self.table_url(chunk, destination)
            try:
                fetch = self.client.get(url, ttl=OSRM_CACHE_TTL, accept="application/json")
                routes = parse_table_response(fetch, chunk, destination)
            except (FetchError, RoutingError) as exc:
                log.warning("OSRM table request failed for %d origins: %s", len(chunk), exc)
                for point in chunk:
                    for key in keys_by_point[point]:
                        batch.failures[key] = f"OSRM request failed: {exc}"
                continue
            for point, route in zip(chunk, routes, strict=True):
                for key in keys_by_point[point]:
                    batch.results[key] = route
        return batch

    def table_url(self, origins: list[LatLon], destination: LatLon) -> str:
        coordinates = ";".join(_lon_lat(p) for p in [*origins, destination])
        sources = ";".join(str(i) for i in range(len(origins)))
        return (
            f"{self.base_url}/table/v1/driving/{coordinates}"
            f"?sources={sources}&destinations={len(origins)}&annotations=duration,distance"
        )


def parse_table_response(fetch: FetchResult, origins: list[LatLon], destination: LatLon) -> list[RouteResult]:
    try:
        payload = json.loads(fetch.text)
    except json.JSONDecodeError as exc:
        raise RoutingError(f"invalid JSON: {exc}") from exc
    if payload.get("code") != "Ok":
        raise RoutingError(f"response code {payload.get('code')!r}: {payload.get('message', 'no message')}")

    durations = payload.get("durations") or []
    distances = payload.get("distances") or []
    sources = payload.get("sources") or []
    if len(durations) != len(origins) or len(distances) != len(origins):
        raise RoutingError(f"{len(durations)} result rows for {len(origins)} origins")

    routes = []
    for i, origin in enumerate(origins):
        duration_s = durations[i][0]
        distance_m = distances[i][0]
        snap_m = sources[i].get("distance") if i < len(sources) else None
        routes.append(_route(fetch, origin, destination, duration_s, distance_m, snap_m))
    return routes


def osm_directions_url(origin: LatLon, destination: LatLon) -> str:
    route = f"{format_lat_lon(origin)};{format_lat_lon(destination)}"
    return f"https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route={route}"


def _route(
    fetch: FetchResult,
    origin: LatLon,
    destination: LatLon,
    duration_s: float | None,
    distance_m: float | None,
    snap_m: float | None,
) -> RouteResult:
    methodology = METHODOLOGY
    confidence = "medium"
    rush_status = RUSH_UNAVAILABLE
    if duration_s is None or distance_m is None:
        duration_s = distance_m = None
        confidence = "insufficient"
        rush_status = (
            f"{RUSH_UNAVAILABLE}. OSRM found no drivable route from these coordinates, "
            "so distance and free-flow time are unavailable too."
        )
    elif snap_m is not None and snap_m > SNAP_WARNING_METERS:
        confidence = "low"
        methodology += (
            f" The property coordinates are {snap_m:.0f} m from the nearest routable road, "
            "so the coordinates or the route may be inaccurate."
        )
    return RouteResult(
        provider=PROVIDER_ID,
        origin_lat=origin[0],
        origin_lon=origin[1],
        destination_lat=destination[0],
        destination_lon=destination[1],
        distance_miles=None if distance_m is None else meters_to_miles(distance_m),
        free_flow_minutes=None if duration_s is None else seconds_to_minutes(duration_s),
        am_rush_minutes=None,
        pm_rush_minutes=None,
        rush_status=rush_status,
        computed_at=fetch.fetched_at,
        source_url=fetch.url,
        view_url=osm_directions_url(origin, destination),
        methodology=methodology,
        confidence=confidence,
    )


def _rounded(point: LatLon) -> LatLon:
    return (round(point[0], 6), round(point[1], 6))


def _lon_lat(point: LatLon) -> str:
    return f"{point[1]:.6f},{point[0]:.6f}"


def _chunks[T](items: list[T], size: int) -> Iterator[list[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
