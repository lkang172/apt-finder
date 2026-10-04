import logging
from collections.abc import Callable, Hashable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from aptfinder.routing.base import (
    LatLon,
    RouteBatch,
    RouteResult,
    RoutingError,
    google_maps_directions_url,
    meters_to_miles,
    seconds_to_minutes,
)

log = logging.getLogger(__name__)

PROVIDER_ID = "google_routes"
COMPUTE_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
FIELD_MASK = "routes.duration,routes.distanceMeters,routes.staticDuration"
PACIFIC = ZoneInfo("America/Los_Angeles")
AM_DEPARTURE = time(8, 30)
PM_DEPARTURE = time(17, 30)
MIN_LEAD_TIME = timedelta(minutes=15)
# Credential, permission, and quota failures affect every request, so stop calling the API for the batch.
FATAL_STATUSES = {401, 403, 429}


@dataclass(frozen=True)
class CommuteDepartures:
    am: datetime
    pm: datetime


@dataclass(frozen=True)
class Leg:
    distance_meters: float
    traffic_seconds: float
    static_seconds: float


class GoogleRoutesError(RoutingError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def next_commute_departures(now: datetime) -> CommuteDepartures:
    day = now.astimezone(PACIFIC).date()
    while day.weekday() >= 5 or _at(day, AM_DEPARTURE) < now + MIN_LEAD_TIME:
        day += timedelta(days=1)
    return CommuteDepartures(am=_at(day, AM_DEPARTURE), pm=_at(day, PM_DEPARTURE))


def methodology(departures: CommuteDepartures) -> str:
    day = f"{departures.am:%A, %B} {departures.am.day}, {departures.am.year}"
    return (
        "Google Routes API (computeRoutes, TRAFFIC_AWARE_OPTIMAL routing, BEST_GUESS traffic model). "
        f"Rush-hour times are Google's predicted travel times for departures on {day} at 8:30 AM Pacific "
        "(home to office) and 5:30 PM Pacific (office to home), based on historical and live traffic patterns; "
        "they are predictions for that future departure time, not observed travel. Holidays are not excluded "
        "when choosing the next weekday. Normal driving time is Google's staticDuration (no traffic) and "
        "distance is for the morning home-to-office route."
    )


class GoogleRoutesProvider:
    provider_id = PROVIDER_ID

    def __init__(
        self,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        if not api_key:
            raise ValueError("Google Routes requires an API key")
        self._api_key = api_key
        self._transport = transport
        self._now = now

    def route_many[K: Hashable](self, origins: Mapping[K, LatLon], destination: LatLon) -> RouteBatch[K]:
        batch: RouteBatch[K] = RouteBatch()
        departures = next_commute_departures(self._now())
        fatal: str | None = None
        with self._http() as http:
            for key, origin in origins.items():
                if fatal:
                    batch.failures[key] = fatal
                    continue
                try:
                    am = self._leg(http, origin, destination, departures.am)
                    pm = self._leg(http, destination, origin, departures.pm)
                except GoogleRoutesError as exc:
                    log.warning("Google Routes failed for %r: %s", key, exc)
                    batch.failures[key] = str(exc)
                    if exc.status_code in FATAL_STATUSES:
                        fatal = str(exc)
                    continue
                batch.results[key] = RouteResult(
                    provider=PROVIDER_ID,
                    origin_lat=origin[0],
                    origin_lon=origin[1],
                    destination_lat=destination[0],
                    destination_lon=destination[1],
                    distance_miles=meters_to_miles(am.distance_meters),
                    free_flow_minutes=seconds_to_minutes(am.static_seconds),
                    am_rush_minutes=seconds_to_minutes(am.traffic_seconds),
                    pm_rush_minutes=seconds_to_minutes(pm.traffic_seconds),
                    rush_status="Available — Google Routes predicted traffic",
                    computed_at=self._now(),
                    source_url=COMPUTE_ROUTES_URL,
                    view_url=google_maps_directions_url(origin, destination),
                    methodology=methodology(departures),
                    confidence="high",
                )
        return batch

    def _http(self) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(30.0),
            transport=self._transport,
            headers={"X-Goog-Api-Key": self._api_key, "X-Goog-FieldMask": FIELD_MASK},
        )

    def _leg(self, http: httpx.Client, origin: LatLon, destination: LatLon, departure: datetime) -> Leg:
        body = {
            "origin": _waypoint(origin),
            "destination": _waypoint(destination),
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
            "trafficModel": "BEST_GUESS",
            "departureTime": departure.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        }
        try:
            response = http.post(COMPUTE_ROUTES_URL, json=body)
        except httpx.HTTPError as exc:
            raise GoogleRoutesError(f"request error: {exc.__class__.__name__}") from exc
        if response.status_code != 200:
            raise GoogleRoutesError(
                f"HTTP {response.status_code}: {_error_message(response)}", status_code=response.status_code
            )
        return parse_leg(response.json())


def parse_leg(payload: dict[str, Any]) -> Leg:
    routes = payload.get("routes") or []
    if not routes:
        raise GoogleRoutesError("no route returned")
    route = routes[0]
    try:
        return Leg(
            distance_meters=float(route["distanceMeters"]),
            traffic_seconds=parse_duration(route["duration"]),
            static_seconds=parse_duration(route["staticDuration"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise GoogleRoutesError(f"unexpected response shape: {exc!r}") from exc


def parse_duration(value: str) -> float:
    if not isinstance(value, str) or not value.endswith("s"):
        raise ValueError(f"not a protobuf duration: {value!r}")
    return float(value[:-1])


def _waypoint(point: LatLon) -> dict[str, Any]:
    return {"location": {"latLng": {"latitude": point[0], "longitude": point[1]}}}


def _at(day: date, at: time) -> datetime:
    return datetime.combine(day, at, tzinfo=PACIFIC)


def _error_message(response: httpx.Response) -> str:
    try:
        return str(response.json()["error"]["message"])
    except (ValueError, KeyError, TypeError):
        return response.reason_phrase or "unknown error"
