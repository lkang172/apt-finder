from collections.abc import Hashable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from urllib.parse import urlencode

from aptfinder.evaluators.base import CommuteEvidence

RUSH_UNAVAILABLE = "Unavailable — traffic-aware routing API required"
LIVE_TRAFFIC_LINK_LABEL = "Check live traffic on Google Maps (convenience link, not evidence)"
METERS_PER_MILE = 1609.344

type LatLon = tuple[float, float]


class RoutingError(Exception):
    pass


@dataclass(frozen=True)
class RouteResult:
    provider: str
    origin_lat: float
    origin_lon: float
    destination_lat: float
    destination_lon: float
    distance_miles: float | None
    free_flow_minutes: float | None
    am_rush_minutes: float | None
    pm_rush_minutes: float | None
    rush_status: str
    computed_at: datetime
    source_url: str | None
    view_url: str | None
    methodology: str
    confidence: str

    @property
    def live_traffic_url(self) -> str:
        origin = (self.origin_lat, self.origin_lon)
        return google_maps_directions_url(origin, (self.destination_lat, self.destination_lon))

    def to_commute_evidence(self, evidence_id: str) -> CommuteEvidence:
        return CommuteEvidence(
            evidence_id=evidence_id,
            provider=self.provider,
            distance_miles=self.distance_miles,
            free_flow_minutes=self.free_flow_minutes,
            am_rush_minutes=self.am_rush_minutes,
            pm_rush_minutes=self.pm_rush_minutes,
            rush_status=self.rush_status,
            source_url=self.source_url,
        )


@dataclass
class RouteBatch[K: Hashable]:
    results: dict[K, RouteResult] = field(default_factory=dict)
    failures: dict[K, str] = field(default_factory=dict)


class RoutingProvider(Protocol):
    provider_id: str

    def route_many[K: Hashable](self, origins: Mapping[K, LatLon], destination: LatLon) -> RouteBatch[K]: ...


def google_maps_directions_url(origin: LatLon, destination: LatLon) -> str:
    """Documented Google Maps URLs scheme; a convenience link for checking live traffic, never evidence."""
    query = urlencode(
        {
            "api": "1",
            "origin": format_lat_lon(origin),
            "destination": format_lat_lon(destination),
            "travelmode": "driving",
        },
        safe=",",
    )
    return f"https://www.google.com/maps/dir/?{query}"


def format_lat_lon(point: LatLon) -> str:
    return f"{point[0]:.6f},{point[1]:.6f}"


def meters_to_miles(meters: float) -> float:
    return round(meters / METERS_PER_MILE, 1)


def seconds_to_minutes(seconds: float) -> float:
    return round(seconds / 60, 1)
