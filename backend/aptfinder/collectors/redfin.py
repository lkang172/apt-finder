import json
import logging
import re
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

from aptfinder.collectors.page_data import as_float, as_int, json_ld_blocks, parse_timestamp
from aptfinder.collectors.types import CollectedFact, CollectedListing, CollectedUnit, DiscoveryStub
from aptfinder.config import SearchCity
from aptfinder.http import FetchResult, PoliteClient
from aptfinder.normalize import ParsedFee

log = logging.getLogger(__name__)

BASE_URL = "https://www.redfin.com"
SOURCE_ID = "redfin"
SEARCH_PAGES = ("studio-apartments-for-rent", "1-bedroom-apartments-for-rent")
INITIAL_CONTEXT = re.compile(r"root\.__reactServerState\.InitialContext = (\{.*?\});\s*\n", re.S)
LISTING_ID = re.compile(r"/(?:apartment|home)/(\d+)")


def _parse_bed_range(value: Any) -> list[int]:
    if value is None:
        return []
    text = str(value)
    if "-" in text:
        low, high = (as_int(part) for part in text.split("-", 1))
        if low is None or high is None:
            return []
        return list(range(low, high + 1))
    single = as_int(text)
    return [] if single is None else [single]


def parse_search_page(html: str) -> list[DiscoveryStub]:
    stubs: dict[str, DiscoveryStub] = {}
    for block in json_ld_blocks(html):
        if not isinstance(block, list):
            continue
        places = {item.get("url"): item for item in block if isinstance(item, dict) and item.get("@type") != "Product"}
        offers = {item.get("url"): item for item in block if isinstance(item, dict) and item.get("@type") == "Product"}
        for url, place in places.items():
            match = LISTING_ID.search(url or "")
            if not match:
                continue
            price = as_int(((offers.get(url) or {}).get("offers") or {}).get("price"))
            beds = _parse_bed_range(place.get("numberOfRooms"))
            geo = place.get("geo") or {}
            address = place.get("address") or {}
            name = (place.get("name") or "").split(" - ")[0].strip()
            stubs[match.group(1)] = DiscoveryStub(
                source_id=SOURCE_ID,
                source_listing_id=match.group(1),
                url=url,
                name=name or address.get("streetAddress") or url,
                city=address.get("addressLocality"),
                lat=as_float(geo.get("latitude")),
                lon=as_float(geo.get("longitude")),
                # The search card shows the property's minimum rent across all plans, so it is a lower
                # bound for every bedroom count in range — safe for pre-filtering only.
                min_price_by_beds={b: price for b in beds},
            )
    return list(stubs.values())


def _data_cache(html: str) -> dict[str, Any]:
    match = INITIAL_CONTEXT.search(html)
    if not match:
        return {}
    context = json.loads(match.group(1))
    cache = (context.get("ReactServerAgent.cache") or {}).get("dataCache") or {}
    bodies = {}
    for key, entry in cache.items():
        text = ((entry or {}).get("res") or {}).get("text") or ""
        if text.startswith("{}&&"):
            text = text[4:]
        try:
            bodies[key] = json.loads(text) if text else None
        except json.JSONDecodeError:
            continue
    return bodies


def _body(cache: dict[str, Any], fragment: str) -> Any:
    for key, value in cache.items():
        if fragment in key and value:
            return value
    return None


def _units(floor_plans: dict[str, Any] | None, is_total_price: bool, updated_at) -> tuple[list[CollectedUnit], list[str]]:
    notes = []
    if not floor_plans:
        return [], notes
    groups = floor_plans.get("unitTypesByBedroom") or []
    unit_types: dict[str, dict[str, Any]] = {}
    for group in groups:
        for unit_type in group.get("availableUnitTypes") or []:
            unit_types.setdefault(unit_type.get("unitTypeId") or json.dumps(unit_type, sort_keys=True)[:80], unit_type)

    if is_total_price:
        notes.append("Redfin marks these prices as total prices, so base rent is not separately known")

    def price_fields(low: int | None, high: int | None) -> dict[str, Any]:
        if is_total_price:
            return {"base_rent_min": None, "base_rent_max": None, "total_monthly": float(low) if low else None}
        return {"base_rent_min": low, "base_rent_max": high}

    units = []
    for type_id, unit_type in unit_types.items():
        baths = (as_float(unit_type.get("fullBaths")) or 0) + 0.5 * (as_float(unit_type.get("halfBaths")) or 0) or None
        listed = unit_type.get("units") or []
        for unit in listed:
            price = as_int(unit.get("rentPrice"))
            if not price:
                continue
            units.append(
                CollectedUnit(
                    source_unit_key=f"unit:{unit.get('unitId')}",
                    kind="unit",
                    label=unit.get("name"),
                    floorplan_name=unit_type.get("name"),
                    beds=as_int(unit.get("bedrooms")),
                    baths=baths,
                    sqft_min=as_int(unit.get("sqft")),
                    sqft_max=as_int(unit.get("sqft")),
                    availability=unit.get("status"),
                    source_updated_at=updated_at,
                    **price_fields(price, price),
                )
            )
        if not listed and as_int(unit_type.get("rentPriceMin")):
            units.append(
                CollectedUnit(
                    source_unit_key=f"plan:{type_id}",
                    kind="floorplan",
                    label=None,
                    floorplan_name=unit_type.get("name"),
                    beds=as_int(unit_type.get("bedrooms")),
                    baths=baths,
                    sqft_min=as_int(unit_type.get("sqftMin")),
                    sqft_max=as_int(unit_type.get("sqftMax")),
                    availability=unit_type.get("status"),
                    source_updated_at=updated_at,
                    **price_fields(as_int(unit_type.get("rentPriceMin")), as_int(unit_type.get("rentPriceMax"))),
                )
            )
    return units, notes


def parse_building_page(html: str, url: str, fetch: FetchResult, stub: DiscoveryStub | None = None) -> CollectedListing | None:
    cache = _data_cache(html)
    homecards = _body(cache, "/rentals/homecards?")
    home = ((homecards or {}).get("homes") or [{}])[0]
    home_data = home.get("homeData") or {}
    rental = home.get("rentalExtension") or {}
    address = home_data.get("addressInfo") or {}
    centroid = ((address.get("centroid") or {}).get("centroid")) or {}
    listing_match = LISTING_ID.search(url)
    if not listing_match:
        return None
    updated_at = parse_timestamp(rental.get("lastUpdated"))
    is_total = bool(rental.get("isTotalPrice"))
    units, notes = _units(_body(cache, "/floorPlans?"), is_total, updated_at)

    if not units and stub and stub.min_price_by_beds and "/home/" in url:
        beds = sorted(stub.min_price_by_beds)
        price = next(iter(stub.min_price_by_beds.values()))
        if len(beds) == 1 and price:
            units.append(
                CollectedUnit(
                    source_unit_key="unit:listing", kind="unit", label=None, floorplan_name=None,
                    beds=beds[0], baths=None, sqft_min=None, sqft_max=None,
                    base_rent_min=price, base_rent_max=price,
                )
            )
            notes.append("Single-unit listing; price taken from the Redfin search card")

    fees = []
    policies = _body(cache, "/feesAndPolicies?") or {}
    if as_int(policies.get("applicationFee")):
        fee = as_int(policies["applicationFee"])
        fees.append(ParsedFee("one_time", f"Application fee: ${fee}", fee, f"${fee}", False, True))
    for pet in policies.get("petPolicies") or []:
        rent = as_int(pet.get("petRent"))
        if rent:
            fees.append(ParsedFee("pet", f"Pet rent ({pet.get('policyName')}): ${rent}/month (only if you have a pet)", rent, f"${rent}", True, False))

    facts = []
    amenities = _body(cache, "/amenities?") or {}
    unit_amenities = amenities.get("unitAmenities") or []
    community = amenities.get("communityAmenities") or []
    if unit_amenities or community:
        facts.append(CollectedFact("amenities", "Amenities listed", "; ".join(unit_amenities + community), ["amenities"], {"unit": unit_amenities, "community": community}, url))
    if rental.get("feedSource") or rental.get("feedOriginalSource"):
        facts.append(
            CollectedFact(
                "feed_source", "Listing feed provenance",
                f"Redfin received this listing via {rental.get('feedSource') or 'unknown feed'}"
                + (f" (originally {rental['feedOriginalSource']})" if rental.get("feedOriginalSource") else ""),
                ["listing"], {"feed_source": rental.get("feedSource"), "original_source": rental.get("feedOriginalSource")}, url,
            )
        )

    restrictions = [label for flag, label in (
        ("isIncomeRestricted", "Income-restricted housing"), ("isSeniorLiving", "Senior housing"),
        ("isStudent", "Student housing"), ("isMilitary", "Military housing"),
    ) if rental.get(flag)]
    if restrictions:
        facts.append(CollectedFact("eligibility", "Eligibility restrictions", f"Listed as: {', '.join(restrictions)}. Eligibility requirements may apply.", ["eligibility"], {"restrictions": restrictions}, url))

    street = address.get("formattedStreetLine") or (stub.name if stub else None)
    return CollectedListing(
        source_id=SOURCE_ID,
        source_listing_id=listing_match.group(1),
        url=url,
        name=rental.get("propertyName") or (stub.name if stub else street) or url,
        street_address=street,
        city=address.get("city") or (stub.city if stub else None),
        state=address.get("state"),
        zip=address.get("zip"),
        lat=as_float(centroid.get("latitude")) or (stub.lat if stub else None),
        lon=as_float(centroid.get("longitude")) or (stub.lon if stub else None),
        fetch=fetch,
        source_updated_at=updated_at,
        units=units,
        fees=fees,
        facts=facts,
        notes=notes,
    )


class RedfinCollector:
    source_id = SOURCE_ID

    def __init__(self, client: PoliteClient, listing_ttl: timedelta, max_pages: int):
        self.client = client
        self.listing_ttl = listing_ttl
        self.max_pages = max_pages

    def discover(self, city: SearchCity) -> Iterator[DiscoveryStub]:
        seen: set[str] = set()
        for page_type in SEARCH_PAGES:
            for page in range(1, self.max_pages + 1):
                url = f"{BASE_URL}/{city.redfin_city_path}/{page_type}" + ("" if page == 1 else f"/page-{page}")
                result = self.client.get(url, ttl=self.listing_ttl)
                stubs = [s for s in parse_search_page(result.text) if s.source_listing_id not in seen]
                if not stubs:
                    break
                for stub in stubs:
                    seen.add(stub.source_listing_id)
                    yield stub
                if f"/{page_type}/page-{page + 1}" not in result.text:
                    break

    def fetch_listing(self, stub: DiscoveryStub) -> CollectedListing | None:
        result = self.client.get(stub.url, ttl=self.listing_ttl)
        return parse_building_page(result.text, stub.url, result, stub)
