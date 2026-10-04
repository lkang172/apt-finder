import html as html_lib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from aptfinder.collectors.page_data import as_float, as_int, json_ld_blocks, walk
from aptfinder.collectors.types import CollectedFact, CollectedUnit
from aptfinder.normalize import ParsedFee

AVALON = "avalon"
JONAH = "jonah"
KNOCK = "knock"
SIGHTMAP = "sightmap"

PLATFORM_LABELS = {
    AVALON: "AvalonBay community page (server-rendered unit data)",
    JONAH: "Jonah Digital floor-plans page (server-rendered unit data)",
    KNOCK: "Knock leasing widget embedded in the official site",
    SIGHTMAP: "SightMap (Engrain) interactive map embedded in the official site",
}

SINGLE_AMOUNT = re.compile(r"\$?\s*(\d[\d,]*(?:\.\d+)?)")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
LEASE_MONTHS = re.compile(r"(\d+)\s*(?:months?|mo\b)", re.I)


@dataclass
class SiteAddress:
    street_address: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    lat: float | None = None
    lon: float | None = None


@dataclass
class ParsedSite:
    platform: str
    platform_property_id: str
    name: str | None
    address: SiteAddress
    units: list[CollectedUnit] = field(default_factory=list)
    fees: list[ParsedFee] = field(default_factory=list)
    promotions: list[str] = field(default_factory=list)
    facts: list[CollectedFact] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    source_updated_at: datetime | None = None

    def add_fact(self, key: str, title: str, content: str | None, categories: list[str], data: dict | None = None) -> None:
        text = re.sub(r"\s+", " ", content or "").strip()
        if text:
            self.facts.append(CollectedFact(key, title, text, categories, data or {}))


def money(value: Any) -> float | None:
    # Zero, blanks, and placeholders such as "Call for details" mean the price is not published.
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        amount = float(value)
    else:
        match = SINGLE_AMOUNT.fullmatch(str(value).strip())
        if not match:
            return None
        amount = float(match.group(1).replace(",", ""))
    return amount if amount > 0 else None


def whole_dollars(amount: float | None) -> int | None:
    return None if amount is None else round(amount)


def required_fees(base: float | None, total: float | None) -> float | None:
    if base is None or total is None or total < base:
        return None
    return round(total - base, 2)


def format_money(amount: float) -> str:
    return f"${amount:,.0f}" if float(amount).is_integer() else f"${amount:,.2f}"


def iso_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = ISO_DATE.match(value.strip())
    return match.group(0) if match else None


def epoch_date(value: Any) -> str | None:
    seconds = as_int(value)
    if seconds is None or seconds <= 0:
        return None
    # Platforms store midnight in a US time zone; the UTC calendar date is the same day for every US zone.
    return datetime.fromtimestamp(seconds, UTC).date().isoformat()


def parse_beds(value: Any) -> int | None:
    if isinstance(value, str) and value.strip().lower() == "studio":
        return 0
    return as_int(value)


def parse_lease_months(value: Any) -> int | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return int(value)
    match = LEASE_MONTHS.search(str(value or ""))
    return int(match.group(1)) if match else None


def visible_text(fragment: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", fragment, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def unique(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        text = re.sub(r"\s+", " ", item or "").strip()
        if text:
            seen.setdefault(text, None)
    return list(seen)


def site_host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def json_ld_apartment_complex(html: str) -> dict[str, Any] | None:
    for block in json_ld_blocks(html):
        for node in walk(block):
            types = node.get("@type")
            types = types if isinstance(types, list) else [types]
            if "ApartmentComplex" in types and isinstance(node.get("address"), dict):
                return node
    return None


def _clean(value: Any) -> str | None:
    return str(value).strip() or None if value else None


def address_from_json_ld(node: dict[str, Any] | None) -> SiteAddress:
    if not node:
        return SiteAddress()
    address = node.get("address") or {}
    geo = node.get("geo") if isinstance(node.get("geo"), dict) else {}
    return SiteAddress(
        street_address=_clean(address.get("streetAddress")),
        city=_clean(address.get("addressLocality")),
        state=_clean(address.get("addressRegion")),
        zip=_clean(address.get("postalCode")),
        lat=as_float(geo.get("latitude")),
        lon=as_float(geo.get("longitude")),
    )
