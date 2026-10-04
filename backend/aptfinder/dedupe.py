import re
from dataclasses import dataclass

from aptfinder.geo import haversine_meters
from aptfinder.normalize import normalize_street_address

SAME_SITE_METERS = 80.0
NAME_ASSIST_METERS = 40.0
GENERIC_NAME_TOKENS = {"apartments", "apartment", "apts", "the", "at", "of", "homes", "residences", "living", "community", "and"}


@dataclass(frozen=True)
class PropertyKey:
    id: int
    name: str | None
    normalized_address: str | None
    zip: str | None
    city: str | None
    lat: float | None
    lon: float | None


@dataclass(frozen=True)
class MatchResult:
    property_id: int
    reason: str


def name_tokens(name: str | None) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9]+", (name or "").lower()))
    return tokens - GENERIC_NAME_TOKENS


def _street_number(normalized: str | None) -> str | None:
    return normalized.split()[0] if normalized else None


def _street_name(normalized: str | None) -> str | None:
    return " ".join(normalized.split()[1:]) if normalized else None


def match_property(candidate: PropertyKey, existing: list[PropertyKey]) -> MatchResult | None:
    """Matches on structured signals only. Similar names alone never merge two properties."""
    for other in existing:
        if candidate.normalized_address and candidate.normalized_address == other.normalized_address:
            same_area = (candidate.zip and candidate.zip == other.zip) or (
                candidate.city and other.city and candidate.city.lower() == other.city.lower()
            )
            if same_area:
                return MatchResult(other.id, f"same normalized address ({candidate.normalized_address})")

    if candidate.lat is None or candidate.lon is None:
        return None
    best: tuple[float, MatchResult] | None = None
    for other in existing:
        if other.lat is None or other.lon is None:
            continue
        distance = haversine_meters(candidate.lat, candidate.lon, other.lat, other.lon)
        if distance > SAME_SITE_METERS:
            continue
        same_number = _street_number(candidate.normalized_address) is not None and _street_number(
            candidate.normalized_address
        ) == _street_number(other.normalized_address)
        same_street = _street_name(candidate.normalized_address) is not None and _street_name(
            candidate.normalized_address
        ) == _street_name(other.normalized_address)
        a, b = name_tokens(candidate.name), name_tokens(other.name)
        name_overlap = len(a & b) / len(a | b) if a and b else 0.0
        reason = None
        if same_number and same_street:
            reason = f"same street address within {distance:.0f} m"
        elif same_number and name_overlap >= 0.5:
            reason = f"same street number and matching name within {distance:.0f} m"
        elif distance <= NAME_ASSIST_METERS and name_overlap >= 0.6 and (same_street or same_number):
            reason = f"matching name and street within {distance:.0f} m"
        if reason and (best is None or distance < best[0]):
            best = (distance, MatchResult(other.id, reason))
    return best[1] if best else None


def key_for(id_: int, name: str | None, street: str | None, zip_: str | None, city: str | None, lat: float | None, lon: float | None) -> PropertyKey:
    return PropertyKey(id_, name, normalize_street_address(street), zip_, city, lat, lon)
