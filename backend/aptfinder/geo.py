import math
from dataclasses import dataclass

from aptfinder.config import ADDITIONAL_ALLOWED_CITIES, SEARCH_CITIES


@dataclass(frozen=True)
class Box:
    name: str
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    def contains(self, lat: float, lon: float) -> bool:
        return self.min_lat <= lat <= self.max_lat and self.min_lon <= lon <= self.max_lon


# Northern edges: Foster City / north San Mateo on the Peninsula, Union City in the East Bay.
# Southern edge: south San Jose. Hayward, Oakland, San Francisco, and Morgan Hill all fall outside.
CORRIDOR = (
    Box("peninsula_south_bay", 37.19, 37.592, -122.36, -121.72),
    Box("east_bay", 37.45, 37.635, -122.12, -121.85),
)

ALLOWED_CITIES: dict[str, str] = {c.name.lower(): c.region for c in SEARCH_CITIES} | {
    name.lower(): region for name, region in ADDITIONAL_ALLOWED_CITIES.items()
}


@dataclass(frozen=True)
class GeoDecision:
    allowed: bool
    region: str | None
    reason: str


def normalize_city(city: str | None) -> str:
    return " ".join((city or "").replace(",", " ").split()).lower()


def evaluate_location(city: str | None, lat: float | None, lon: float | None) -> GeoDecision:
    region = ALLOWED_CITIES.get(normalize_city(city))
    if region is None:
        return GeoDecision(False, None, f"City '{city or 'unknown'}' is outside the search area")
    if lat is None or lon is None:
        return GeoDecision(True, region, "Coordinates unavailable; allowed by city only")
    if not any(box.contains(lat, lon) for box in CORRIDOR):
        return GeoDecision(False, region, f"Coordinates ({lat:.4f}, {lon:.4f}) fall outside the search corridor")
    return GeoDecision(True, region, "City and coordinates inside the search corridor")


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
