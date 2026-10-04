import hashlib
import logging
import re
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

from aptfinder.collectors.page_data import (
    as_float,
    as_int,
    json_ld_blocks,
    next_flight_rows,
    parse_timestamp,
    walk,
)
from aptfinder.collectors.types import (
    CollectedFact,
    CollectedListing,
    CollectedRating,
    CollectedReview,
    CollectedUnit,
    DiscoveryStub,
)
from aptfinder.config import SearchCity
from aptfinder.http import FetchResult, PoliteClient
from aptfinder.normalize import ParsedFee, parse_fee_text

log = logging.getLogger(__name__)

BASE_URL = "https://www.apartmentlist.com"
SOURCE_ID = "apartment_list"
MAX_CITY_PAGES = 15
SUBSCORE_KEYS = {
    "valueScore": "value",
    "amenitiesScore": "amenities",
    "locationScore": "location",
    "managementScore": "management",
    "maintenanceScore": "maintenance",
    "parkingScore": "parking",
    "noiseScore": "noise",
}


def parse_city_page(html: str) -> tuple[list[DiscoveryStub], int | None]:
    stubs: dict[str, DiscoveryStub] = {}
    total = None
    for row in next_flight_rows(html):
        for node in walk(row):
            if total is None and isinstance(node.get("total_count"), int):
                total = node["total_count"]
            if "rental_id" in node and "prices" in node and "slug" in node:
                prices = {int(k): as_int(v) for k, v in (node.get("prices") or {}).items() if str(k).isdigit()}
                stubs[node["rental_id"]] = DiscoveryStub(
                    source_id=SOURCE_ID,
                    source_listing_id=node["rental_id"],
                    url=BASE_URL + node["slug"],
                    name=node.get("display_name") or node["slug"].rsplit("/", 1)[-1],
                    city=None,
                    lat=as_float(node.get("lat")),
                    lon=as_float(node.get("lon")),
                    min_price_by_beds=prices,
                )
    return list(stubs.values()), total


def _find_listing(rows: list[Any]) -> dict[str, Any] | None:
    for row in rows:
        for node in walk(row):
            if "available_units" in node and "rental_id" in node:
                return node
    return None


def _find_reviews(rows: list[Any]) -> tuple[list[dict[str, Any]], int | None, dict[str, Any] | None]:
    reviews: list[dict[str, Any]] = []
    total = None
    summary = None
    for row in rows:
        for node in walk(row):
            items = node.get("reviews")
            if isinstance(items, list) and items and isinstance(items[0], dict) and "submitDate" in items[0]:
                reviews = items
                total = node.get("reviewsTotal")
            if summary is None and isinstance(node.get("reviewSummary"), dict):
                summary = node["reviewSummary"]
    return reviews, total, summary


def _image_url(html: str) -> str | None:
    for block in json_ld_blocks(html):
        if isinstance(block, dict) and block.get("@type") == "Product":
            images = block.get("image")
            if isinstance(images, list) and images:
                return images[0].get("url")
            if isinstance(images, dict):
                return images.get("url")
    return None


def _units(listing: dict[str, Any]) -> list[CollectedUnit]:
    units = []
    for plan in listing.get("available_units") or []:
        beds = as_int(plan.get("bed"))
        baths = as_float(plan.get("bath"))
        plan_units = plan.get("units") or []
        for unit in plan_units:
            base = as_int(unit.get("base_price")) or as_int(unit.get("price"))
            if not base:
                continue
            sqft = as_int(unit.get("sqft")) or as_int(plan.get("sqft"))
            units.append(
                CollectedUnit(
                    source_unit_key=f"unit:{unit.get('id')}",
                    kind="unit",
                    label=unit.get("display_name") or unit.get("name"),
                    floorplan_name=plan.get("name"),
                    beds=beds,
                    baths=baths,
                    sqft_min=sqft,
                    sqft_max=sqft,
                    base_rent_min=base,
                    base_rent_max=base,
                    total_monthly=as_float(unit.get("total_price")),
                    required_fees_monthly=as_float(unit.get("required_fees")),
                    lease_term_months=as_int(unit.get("lease_length")),
                    available_on=unit.get("available_on"),
                    availability=unit.get("availability"),
                    source_updated_at=parse_timestamp(unit.get("updated_at")),
                )
            )
        if not plan_units and as_int(plan.get("price")):
            units.append(
                CollectedUnit(
                    source_unit_key=f"plan:{plan.get('id')}",
                    kind="floorplan",
                    label=None,
                    floorplan_name=plan.get("name"),
                    beds=beds,
                    baths=baths,
                    sqft_min=as_int(plan.get("sqft")),
                    sqft_max=as_int(plan.get("sqft_max")) or as_int(plan.get("sqft")),
                    base_rent_min=as_int(plan.get("price")),
                    base_rent_max=as_int(plan.get("price_max")) or as_int(plan.get("price")),
                    source_updated_at=parse_timestamp(listing.get("updated_at")),
                )
            )
    return units


def _fees(listing: dict[str, Any]) -> list[ParsedFee]:
    fees = list(parse_fee_text(listing.get("additional_fees_text")))
    for field, label in (
        ("deposit_fee_text", "Security deposit"),
        ("application_fee_text", "Application fee"),
        ("move_in_fees_text", "Move-in fees"),
    ):
        text = (listing.get(field) or "").strip()
        if text:
            amount_match = re.fullmatch(r"\$+\s?(\d[\d,]*)", text.split()[0]) if text.split() else None
            fees.append(
                ParsedFee(
                    "deposit" if field == "deposit_fee_text" else "one_time",
                    f"{label}: {text.replace('$$', '$')}",
                    as_int(amount_match.group(1)) if amount_match and len(text.split()) <= 3 else None,
                    text.replace("$$", "$"),
                    False,
                    True if field != "move_in_fees_text" else None,
                )
            )
    for spot in listing.get("parking") or []:
        comment = (spot.get("comment") or "").strip()
        fee = as_int(spot.get("space_fee"))
        if not comment and fee is None:
            continue
        description = f"Parking: {comment}" if comment else "Parking"
        if fee is not None:
            description += f" (${fee})"
        recurring = None
        if re.search(r"replacement|one[- ]time", comment, re.I):
            recurring = False
        fees.append(ParsedFee("parking", description, fee, f"${fee}" if fee is not None else None, recurring, None))
    general = ((listing.get("pet_policies") or {}).get("general")) or {}
    if as_int(general.get("rent")):
        fees.append(ParsedFee("pet", f"Pet rent: ${as_int(general['rent'])}/month (only if you have a pet)", as_int(general["rent"]), f"${general['rent']}", True, False))
    return fees


def _amenity_names(items: Any) -> list[str]:
    return [i.get("display_name") for i in items or [] if isinstance(i, dict) and i.get("display_name")]


def _facts(listing: dict[str, Any], url: str) -> list[CollectedFact]:
    facts = []

    def add(key: str, title: str, content: str | None, categories: list[str], data: dict | None = None, fact_url: str | None = None):
        if content:
            facts.append(CollectedFact(key, title, content.strip(), categories, data or {}, fact_url or url))

    for disclaimer in listing.get("fee_disclaimers") or []:
        add("pricing_disclosure", "Pricing disclosure", disclaimer.get("description"), ["price"])
    fee_url = (listing.get("fees") or {}).get("fee_url")
    if fee_url:
        add("fee_document", "Fee schedule document linked by listing", "The listing links an external fee schedule document.", ["price"], {"fee_url": fee_url}, fee_url)
    add("utilities_included", "Utilities included", listing.get("utilities_included_text"), ["price", "other_issues"])
    add("parking_details", "Parking details", listing.get("parking_details_text"), ["parking"])
    add("storage_details", "Storage details", listing.get("storage_details_text"), ["amenities"])
    add("lease_terms", "Lease terms offered", listing.get("lease_terms_text"), ["lease"])
    add("income_requirement", "Income requirement", listing.get("income_requirement_text"), ["lease"])
    add("management_company", "Property management company", listing.get("pmc_display_name"), ["management"])
    pets = listing.get("pet_policies") or {}
    if pets:
        allowed = pets.get("allowed")
        kinds = ", ".join(pets.get("allowed_pets") or [])
        text = ("Pets allowed" + (f" ({kinds})" if kinds else "")) if allowed else ("No pets allowed" if allowed is False else None)
        add("pet_policy", "Pet policy", text, ["pets"], {"pet_policies": pets})
    community = _amenity_names(listing.get("community_amenities"))
    unit = _amenity_names(listing.get("unit_amenities"))
    if community or unit:
        add("amenities", "Amenities listed", "; ".join(unit + community), ["amenities"], {"unit": unit, "community": community})
    built = listing.get("year_built")
    units = listing.get("total_units_count")
    if built or units:
        add("building", "Building facts", ", ".join(p for p in (f"Built {built}" if built else "", f"{units} units" if units else "") if p), ["property"], {"year_built": built, "total_units": units})
    for special in listing.get("specials") or []:
        if special.get("raw_text"):
            add(f"special_{special.get('id')}", "Rent special", special["raw_text"], ["price"], {"expires_at": special.get("expires_at")})
    return facts


def _review_key(review: dict[str, Any]) -> str:
    basis = f"{review.get('propertyId')}|{review.get('submitDate')}|{review.get('authorName')}|{(review.get('detail') or '')[:200]}"
    return hashlib.sha1(basis.encode()).hexdigest()[:24]


def _reviews(raw_reviews: list[dict[str, Any]]) -> list[CollectedReview]:
    reviews = []
    for raw in raw_reviews:
        if raw.get("moderated") not in (None, "keep"):
            continue
        subscores = {name: raw[key] for key, name in SUBSCORE_KEYS.items() if isinstance(raw.get(key), (int, float))}
        reviews.append(
            CollectedReview(
                source_review_key=_review_key(raw),
                reviewer=raw.get("authorName"),
                rating=as_float(raw.get("overallScore")),
                review_date=parse_timestamp(raw.get("submitDate")),
                text=(raw.get("detail") or "").strip(),
                subscores=subscores,
                extra={"channel": raw.get("type"), "moderated": raw.get("moderated"), "reviewer_relationship": "toured or leased (per Apartment List)"},
            )
        )
    return reviews


def parse_listing_page(html: str, url: str, fetch: FetchResult) -> CollectedListing | None:
    rows = list(next_flight_rows(html))
    listing = _find_listing(rows)
    if listing is None:
        return None
    raw_reviews, reviews_total, summary = _find_reviews(rows)
    reviews = _reviews(raw_reviews)
    notes = []
    rating = None
    if summary and as_int(summary.get("rating_count")):
        count = as_int(summary["rating_count"])
        rated = [r.rating for r in reviews if r.rating is not None]
        if len(rated) == count:
            average = round(sum(rated) / len(rated), 2)
            note = "Average computed from all collected reviews"
        else:
            average = as_float(summary.get("overall"))
            note = f"Average as reported by Apartment List; {len(rated)} of {count} reviews collected"
        rating = CollectedRating(average=average, count=count, scale=5.0, source_url=url + "#ldp-jump-reviews", note=note)
    elif summary is None and not raw_reviews:
        rating = CollectedRating(average=None, count=0, scale=5.0, source_url=url, note="No verified reviews listed on Apartment List")
    if reviews_total and reviews_total > len(raw_reviews):
        notes.append(f"Apartment List reports {reviews_total} reviews but only {len(raw_reviews)} were present on the page")

    return CollectedListing(
        source_id=SOURCE_ID,
        source_listing_id=listing["rental_id"],
        url=url,
        name=listing.get("display_name") or listing.get("name") or listing["rental_id"],
        street_address=listing.get("street_address") or listing.get("street"),
        city=listing.get("city"),
        state=listing.get("state"),
        zip=listing.get("zip"),
        lat=as_float(listing.get("lat")),
        lon=as_float(listing.get("lon")),
        fetch=fetch,
        image_url=_image_url(html),
        official_website_url=listing.get("website_url") or None,
        source_updated_at=parse_timestamp(listing.get("updated_at")),
        units=_units(listing),
        fees=_fees(listing),
        promotions=[s["raw_text"].strip() for s in listing.get("specials") or [] if s.get("raw_text") and s.get("relevant", True)],
        reviews=reviews,
        rating=rating,
        facts=_facts(listing, url),
        notes=notes,
    )


class ApartmentListCollector:
    source_id = SOURCE_ID

    def __init__(self, client: PoliteClient, listing_ttl: timedelta):
        self.client = client
        self.listing_ttl = listing_ttl

    def discover(self, city: SearchCity) -> Iterator[DiscoveryStub]:
        base = f"{BASE_URL}/{city.apartment_list_slug}"
        seen: set[str] = set()
        for page in range(1, MAX_CITY_PAGES + 1):
            url = base if page == 1 else f"{base}/page-{page}"
            result = self.client.get(url, ttl=self.listing_ttl)
            stubs, total = parse_city_page(result.text)
            new = [s for s in stubs if s.source_listing_id not in seen]
            for stub in new:
                stub.city = city.name
                seen.add(stub.source_listing_id)
                yield stub
            if not new or (total is not None and len(seen) >= total):
                return

    def fetch_listing(self, stub: DiscoveryStub) -> CollectedListing | None:
        result = self.client.get(stub.url, ttl=self.listing_ttl)
        return parse_listing_page(result.text, stub.url, result)
