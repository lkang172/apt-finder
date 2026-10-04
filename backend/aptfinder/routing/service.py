import logging
from collections.abc import Hashable, Mapping
from dataclasses import replace

from aptfinder.config import Office, Settings
from aptfinder.http import PoliteClient
from aptfinder.routing.base import RUSH_UNAVAILABLE, LatLon, RouteResult, RoutingProvider
from aptfinder.routing.google_routes import GoogleRoutesProvider
from aptfinder.routing.osrm import OSRM_HOST, OsrmProvider

log = logging.getLogger(__name__)


def route_many[K: Hashable](
    origins: Mapping[K, LatLon],
    office: Office,
    settings: Settings,
    client: PoliteClient,
    traffic_provider: RoutingProvider | None = None,
) -> dict[K, RouteResult]:
    destination = (office.lat, office.lon)
    client.min_intervals.setdefault(OSRM_HOST, settings.osrm_min_interval_s)
    osrm = OsrmProvider(client)

    if traffic_provider is None and settings.google_maps_api_key:
        traffic_provider = GoogleRoutesProvider(settings.google_maps_api_key)
    if traffic_provider is None:
        batch = osrm.route_many(origins, destination)
        _log_failures(batch.failures)
        return batch.results

    traffic = traffic_provider.route_many(origins, destination)
    results = dict(traffic.results)
    if traffic.failures:
        fallback = osrm.route_many({key: origins[key] for key in traffic.failures}, destination)
        for key, route in fallback.results.items():
            note = f"the {traffic_provider.provider_id} request failed: {traffic.failures[key]}"
            if route.free_flow_minutes is None:
                status = f"{route.rush_status} ({note})"
            else:
                status = f"{RUSH_UNAVAILABLE} ({note}; showing OSRM free-flow time without traffic)"
            results[key] = replace(route, rush_status=status)
        _log_failures(fallback.failures)
    return results


def _log_failures(failures: Mapping[Hashable, str]) -> None:
    for key, reason in failures.items():
        log.warning("No route computed for %r: %s", key, reason)
