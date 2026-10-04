import json
import logging
import math
import re
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from aptfinder.collectors.page_data import as_float, as_int, json_ld_blocks, parse_timestamp, walk
from aptfinder.collectors.types import CollectedFact, CollectedListing, CollectedUnit, DiscoveryStub
from aptfinder.config import SearchCity
from aptfinder.http import FetchResult, PoliteClient
from aptfinder.normalize import MONEY, ParsedFee, classify_fee_type, extract_unit_number

log = logging.getLogger(__name__)

BASE_URL = "https://www.trulia.com"
SOURCE_ID = "trulia"
# Matches the pipeline's stub-prefilter margin so the search never hides a listing the prefilter would keep.
PRICE_CEILING_MARGIN = 150
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', re.S)
LISTING_PATH = re.compile(r"^/(building|home)/[^/]+-(\d+)/?$")
TYPED_HOME_ID = re.compile(r"^(\d+)_(BUILDING_ID|ZPID)$")
UNIT_PREFIX = re.compile(r"^(?:unit|apt\.?|apartment|#)\s*", re.I)
BASE_RENT_FEE = re.compile(r"^(?:monthly\s+)?(?:base\s+)?rent$", re.I)
MONEY_ONLY = re.compile(r"\$\s?\d[\d,]*(?:\.\d{1,2})?\s*(?:/\s?mo(?:nth)?)?")
SQFT_TEXT = re.compile(r"([\d,]+)(?:\s*-\s*([\d,]+))?\s*sq\s*ft", re.I)
MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
PRICING_DISCLOSURE = re.compile(r"\b(total monthly leasing prices?|prices? (?:shown )?include|excludes? variable)\b", re.I)
CONCESSION_WORDS = re.compile(
    r"\b(free|off|waived?|discount\w*|credit|concession|special|reduced|save|savings|gift card|look and lease)\b|\$\s?\d", re.I
)
ELIGIBILITY_TAG = re.compile(r"income|affordable|senior|55\s*\+|62\s*\+|student|military", re.I)


def next_data(html: str) -> dict[str, Any] | None:
    match = NEXT_DATA.search(html)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def listing_id_from_url(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.netloc and parts.netloc != urlsplit(BASE_URL).netloc:
        return None
    match = LISTING_PATH.match(parts.path)
    return f"{match.group(1)}:{match.group(2)}" if match else None


def _listing_id_from_typed_id(value: Any) -> str | None:
    match = TYPED_HOME_ID.match(value) if isinstance(value, str) else None
    if not match:
        return None
    return f"{'building' if match.group(2) == 'BUILDING_ID' else 'home'}:{match.group(1)}"


def _bed_values(node: Any) -> list[int]:
    if not isinstance(node, dict):
        return []
    low, high = as_int(node.get("min")), as_int(node.get("max"))
    if low is not None and high is not None and 0 <= low <= high:
        return list(range(low, high + 1))
    value = as_int(node.get("value"))
    if value is not None:
        return [value]
    if node.get("__typename") == "HOME_StudioBedroom" or str(node.get("formattedValue") or "").strip().lower() == "studio":
        return [0]
    return []


def _single_bed(node: Any) -> int | None:
    values = _bed_values(node)
    return values[0] if len(values) == 1 else None


def _baths(node: Any) -> float | None:
    if not isinstance(node, dict):
        return None
    value = as_float(node.get("value"))
    if value is None and as_float(node.get("min")) is not None and node.get("min") == node.get("max"):
        value = as_float(node.get("min"))
    return value


def _price_range(node: Any) -> tuple[int | None, int | None]:
    if not isinstance(node, dict):
        return None, None
    low = as_int(node.get("min") if node.get("min") is not None else node.get("price"))
    high = as_int(node.get("max")) or low
    if not low or low <= 0:
        return None, None
    return low, high


def _sqft_range(node: Any) -> tuple[int | None, int | None]:
    if not isinstance(node, dict):
        return None, None
    low, high = as_int(node.get("min")), as_int(node.get("max"))
    if low is None and high is None:
        match = SQFT_TEXT.search(str(node.get("formattedDimension") or ""))
        if match:
            low = as_int(match.group(1))
            high = as_int(match.group(2)) or low
    return low or high, high or low


def _unit_label(name: Any) -> str | None:
    if not isinstance(name, str) or not name.strip():
        return None
    return UNIT_PREFIX.sub("", name.strip()) or name.strip()


def _date_part(value: Any) -> str | None:
    # Trulia encodes availability as local midnight in UTC (e.g. 2026-12-02T08:00:00+00:00 is "Available Dec 2").
    return value[:10] if isinstance(value, str) and re.match(r"\d{4}-\d{2}-\d{2}", value) else None


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = MARKDOWN_LINK.sub(lambda m: "" if m.group(1).strip().lower() == "learn more" else m.group(1), value)
    text = re.sub(r"\s+", " ", text.replace("**", "")).strip()
    return text or None


def _squash(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return re.sub(r"\s+", " ", value).strip() or None


def _stub(home: dict[str, Any], searched_beds: list[int]) -> DiscoveryStub | None:
    path = home.get("url") or ""
    if home.get("__typename") == "HOME_RoomForRent" or (home.get("metadata") or {}).get("unifiedListingType") == "RENTAL_R4R":
        log.info("Skipping Trulia room-for-rent listing %s", path)
        return None
    listing_id = listing_id_from_url(path)
    if listing_id is None:
        log.info("Skipping Trulia search result without a building or home page: %s", path)
        return None
    low, _high = _price_range(home.get("price"))
    # Unknown bedrooms fall back to the searched bedroom range so the stub survives to the detail fetch.
    beds = _bed_values(home.get("bedrooms")) or searched_beds
    location = home.get("location") or {}
    coordinates = location.get("coordinates") or {}
    return DiscoveryStub(
        source_id=SOURCE_ID,
        source_listing_id=listing_id,
        url=BASE_URL + urlsplit(path).path,
        name=_squash(location.get("communityLocation")) or _squash(location.get("streetAddress")) or _squash(location.get("partialLocation")) or path,
        city=location.get("city"),
        lat=as_float(coordinates.get("latitude")),
        lon=as_float(coordinates.get("longitude")),
        # Trulia computes each card's price and bedroom range over the units matching the search filters,
        # so the card minimum is the cheapest matching unit: a lower bound for every bedroom count shown.
        # (Cards marked "Total price" show totals, but Trulia never yields a base rent for those listings.)
        min_price_by_beds={b: low for b in beds},
    )


def parse_search_page(html: str) -> tuple[list[DiscoveryStub], int | None]:
    """Returns the page's stubs and the total number of result pages."""
    search = (((next_data(html) or {}).get("props") or {}).get("searchData")) or {}
    filters = ((search.get("details") or {}).get("filters")) or {}
    searched_beds = _bed_values(filters.get("bedrooms"))
    stubs: dict[str, DiscoveryStub] = {}
    for home in search.get("homes") or []:
        stub = _stub(home, searched_beds) if isinstance(home, dict) else None
        if stub is not None:
            stubs.setdefault(stub.source_listing_id, stub)
    total, limit = as_int(search.get("totalHomes")), as_int(filters.get("limit"))
    pages = math.ceil(total / limit) if total is not None and limit else None
    return list(stubs.values()), pages


def _prices_include_required_fees(details: dict[str, Any]) -> bool | None:
    flag = (details.get("activeForRentListing") or {}).get("isTotalMonthlyFeeIncluded")
    type_description = str((details.get("price") or {}).get("typeDescription") or "").lower()
    if flag is True or "total" in type_description:
        return True
    return False if flag is False else None


def _price_fields(low: int, high: int | None, totals: bool) -> dict[str, Any]:
    if totals:
        return {"base_rent_min": None, "base_rent_max": None, "total_monthly": float(low)}
    return {"base_rent_min": low, "base_rent_max": high or low}


def _floorplan_units(details: dict[str, Any], updated_at: datetime | None, totals: bool) -> list[CollectedUnit]:
    units: list[CollectedUnit] = []
    used_keys: set[str] = set()
    for group in (details.get("floorPlans") or {}).get("floorPlanGroups") or []:
        group_beds = _single_bed(group.get("bedrooms"))
        for plan in group.get("plans") or []:
            if plan.get("isRoomForRent"):
                continue
            plan_beds = _single_bed(plan.get("bedrooms"))
            plan_beds = group_beds if plan_beds is None else plan_beds
            plan_baths = _baths(plan.get("bathrooms"))
            plan_units = [u for u in plan.get("units") or [] if isinstance(u, dict) and not u.get("isRoomForRent")]
            for unit in plan_units:
                low, high = _price_range(unit.get("priceRange"))
                if low is None:
                    continue
                label = _unit_label(unit.get("name"))
                key = f"unit:{unit['id']}" if unit.get("id") else f"unit:{plan.get('name')}:{label}"
                if key in used_keys:
                    key = f"{key}:{label}"
                used_keys.add(key)
                sqft_min, sqft_max = _sqft_range(unit.get("floorSpace"))
                beds = _single_bed(unit.get("bedrooms"))
                units.append(
                    CollectedUnit(
                        source_unit_key=key,
                        kind="unit",
                        label=label,
                        floorplan_name=plan.get("name"),
                        beds=plan_beds if beds is None else beds,
                        baths=_baths(unit.get("bathrooms")) or plan_baths,
                        sqft_min=sqft_min,
                        sqft_max=sqft_max,
                        available_on=_date_part(unit.get("availabilityDate")),
                        availability=unit.get("availabilityText") or None,
                        source_updated_at=updated_at,
                        **_price_fields(low, high, totals),
                    )
                )
            if plan_units:
                continue
            low, high = _price_range(plan.get("priceRange"))
            if low is None:
                continue
            sqft_min, sqft_max = _sqft_range(plan.get("floorSpace"))
            units.append(
                CollectedUnit(
                    source_unit_key=f"plan:{plan.get('id') or plan.get('name')}",
                    kind="floorplan",
                    label=None,
                    floorplan_name=plan.get("name"),
                    beds=plan_beds,
                    baths=plan_baths,
                    sqft_min=sqft_min,
                    sqft_max=sqft_max,
                    availability=plan.get("availabilityText") or None,
                    source_updated_at=updated_at,
                    **_price_fields(low, high, totals),
                )
            )
    return units


def _single_unit(details: dict[str, Any], listing_id: str, updated_at: datetime | None, totals: bool) -> list[CollectedUnit]:
    low, _high = _price_range(details.get("price"))
    if low is None:
        return []
    sqft_min, sqft_max = _sqft_range(details.get("floorSpace"))
    available = details.get("formattedAvailableDate")
    return [
        CollectedUnit(
            source_unit_key=f"unit:{listing_id.split(':', 1)[1]}",
            kind="unit",
            label=extract_unit_number((details.get("location") or {}).get("streetAddress")),
            floorplan_name=None,
            beds=_single_bed(details.get("bedrooms")),
            baths=_baths(details.get("bathrooms")),
            sqft_min=sqft_min,
            sqft_max=sqft_max,
            availability=f"Available {available}" if isinstance(available, str) and available.strip() else None,
            source_updated_at=updated_at,
            **_price_fields(low, low, totals),
        )
    ]


def _fee(name: Any, value_text: Any, low: int | None, high: int | None, recurring: bool | None, mandatory: bool | None, section: str) -> ParsedFee | None:
    name = name.strip() if isinstance(name, str) else ""
    if not name or BASE_RENT_FEE.match(name):
        return None
    text = value_text.strip() if isinstance(value_text, str) else ""
    amount = amount_text = None
    if low is not None:
        amount = low if high in (None, low) else None
        amount_text = f"${low:,}" if amount is not None else f"${low:,}–${high:,}"
    elif text and MONEY_ONLY.fullmatch(text):
        amount = round(float(MONEY.search(text).group(1).replace(",", "")))
        amount_text = text
    elif text and MONEY.search(text):
        amount_text = text
    if recurring is False:
        fee_type = "deposit" if "deposit" in name.lower() else "one_time"
    else:
        fee_type = classify_fee_type(name)
    display = amount_text or text or "amount not stated"
    return ParsedFee(fee_type, f"{name} ({section}): {display}", amount, amount_text, recurring, mandatory)


CALCULATOR_SECTIONS = (
    ("monthlyRequiredFees", True, True, "required monthly fee"),
    ("oneTimeRequiredFees", False, True, "required one-time fee"),
    ("monthlyOptionalFees", True, False, "optional monthly fee"),
    ("oneTimeOptionalFees", False, False, "optional one-time fee"),
)


def _fees(details: dict[str, Any]) -> list[ParsedFee]:
    costs = details.get("rentalCostsAndFees") or {}
    fees: list[ParsedFee] = []
    breakdown = ((costs.get("costAndFeeCalculator") or {}).get("fees")) or {}
    for section, recurring, mandatory, label in CALCULATOR_SECTIONS:
        for item in breakdown.get(section) or []:
            fee = (item or {}).get("fee") or {}
            amount = fee.get("amount") or {}
            low = as_int(fee.get("min")) if fee.get("min") is not None else as_int(amount.get("value"))
            high = as_int(fee.get("max")) if fee.get("max") is not None else low
            parsed = _fee(fee.get("displayValue"), amount.get("displayText"), low, high, recurring, mandatory, label)
            if parsed:
                fees.append(parsed)
    for section in costs.get("rentalFeeSections") or []:
        title = str(section.get("sectionTitle") or "")
        recurring = True if re.search(r"monthly", title, re.I) else False if re.search(r"one[- ]time", title, re.I) else None
        mandatory = True if re.search(r"required", title, re.I) else False if re.search(r"optional", title, re.I) else None
        for item in section.get("rentalFees") or []:
            parsed = _fee(item.get("title"), item.get("formattedValue"), None, None, recurring, mandatory, title.lower() or "fee")
            if parsed:
                fees.append(parsed)
    return fees


def _special_offers(details: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Splits Trulia's special-offer entries into real promotions and pricing disclosures that Trulia shows
    in the same slot (e.g. "Total monthly leasing prices include base rent...")."""
    promotions, disclosures = [], []
    for offer in details.get("specialOffers") or []:
        if not isinstance(offer, dict):
            continue
        text = " — ".join(t.strip() for t in (offer.get("description"), offer.get("subText")) if isinstance(t, str) and t.strip())
        if not text:
            continue
        if PRICING_DISCLOSURE.search(text) and not CONCESSION_WORDS.search(text):
            disclosures.append(text)
        else:
            promotions.append(text)
    return promotions, disclosures


def _image_url(html: str) -> str | None:
    for block in json_ld_blocks(html):
        if isinstance(block, dict) and block.get("@type") == "Product":
            image = block.get("image")
            image = image[0] if isinstance(image, list) and image else image
            if isinstance(image, str) and image.startswith("https://"):
                return image
    return None


def _zillow_group_statements(details: dict[str, Any]) -> list[str]:
    statements = []
    for node in walk(details):
        for key, value in node.items():
            if key != "label" and isinstance(value, str) and "part of Zillow Group" in value:
                statements.append(f'page states "{value.strip()}"')
        if node.get("label") == "Trulia Corporate" and any(
            isinstance(child, dict) and child.get("label") == "About Zillow Group" for child in node.get("children") or []
        ):
            statements.append('page lists "About Zillow Group" under "Trulia Corporate"')
    return list(dict.fromkeys(statements))


def _feed_provenance(details: dict[str, Any], url: str) -> CollectedFact | None:
    history_sources = sorted({
        e["source"].strip() for e in details.get("priceHistory") or []
        if isinstance(e, dict) and isinstance(e.get("source"), str) and e["source"].strip() not in ("", "N/A")
    })
    listing_source = (((details.get("activeListing") or {}).get("provider") or {}).get("listingSource")) or {}
    attributions = [
        value.strip()
        for node in walk({k: v for k, v in listing_source.items() if k in ("attribution", "alternativeSources")})
        for key, value in node.items()
        if key not in ("__typename", "logoUrl", "url") and isinstance(value, str) and value.strip()
    ]
    zillow_group = _zillow_group_statements(details)
    typed_id = details.get("typedHomeId")
    zpid = typed_id.removesuffix("_ZPID") if isinstance(typed_id, str) and typed_id.endswith("_ZPID") else None
    signals = (
        [f"price history source: {s}" for s in history_sources]
        + [f"listing source attribution: {a}" for a in attributions]
        + ([f"listed under Zillow property ID (zpid) {zpid}"] if zpid else [])
        + zillow_group
    )
    if not signals:
        return None
    content = (
        "Trulia is a Zillow Group site and carries Zillow Group's rental listing feed, so this listing is not an "
        f"independent confirmation of sources fed by Zillow. Evidence on the page: {'; '.join(signals)}."
    )
    return CollectedFact(
        "feed_provenance", "Listing feed provenance", content, ["listing"],
        {"network": "Zillow Group", "independent_source": False, "signals": signals, "price_history_sources": history_sources, "zpid": zpid},
        url,
    )


def _pet_policy(details: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    summary = (details.get("petPolicy") or {}).get("formattedPetsAllowed")
    cards = (((details.get("activeForRentListing") or {}).get("petPolicy")) or {}).get("cards") or []
    parts = []
    for card in cards:
        if not isinstance(card, dict) or not card.get("label") or not card.get("statusLabel"):
            continue
        extras = [f"{f['label']}: {f['value']}" for f in card.get("facts") or [] if f.get("label") and f.get("value") and f["value"] != "n/a"]
        extras += [r for r in card.get("restrictions") or [] if isinstance(r, str)]
        parts.append(f"{card['label']}: {card['statusLabel']}" + (f" ({'; '.join(extras)})" if extras else ""))
    if not summary and not parts:
        return None
    content = ". ".join(p for p in (summary, "; ".join(parts)) if p)
    return content, {"summary": summary, "cards": cards}


def _lease_terms(details: dict[str, Any]) -> str | None:
    for node in walk(details.get("features") or {}):
        if node.get("formattedName") == "Lease Term" and isinstance(node.get("formattedValue"), str):
            return node["formattedValue"]
    return None


def _facts(details: dict[str, Any], url: str, updated_at: datetime | None, disclosures: list[str], totals: bool | None) -> list[CollectedFact]:
    facts: list[CollectedFact] = []

    def add(key: str, title: str, content: str | None, categories: list[str], data: dict[str, Any] | None = None) -> None:
        if content:
            facts.append(CollectedFact(key, title, content, categories, data or {}, url))

    tags = [t["formattedName"] for t in details.get("heroTags") or [] if isinstance(t, dict) and t.get("formattedName") and t.get("level") != "STATUS"]
    add("listing_tags", "Trulia listing tags", ", ".join(tags), ["listing"], {"tags": tags})
    restrictions = [tag.title() for tag in tags if ELIGIBILITY_TAG.search(tag)]
    if restrictions:
        add("eligibility", "Eligibility restrictions", f"Listed as: {', '.join(restrictions)}. Eligibility requirements may apply.",
            ["eligibility"], {"restrictions": restrictions, "source_tags": [t for t in tags if ELIGIBILITY_TAG.search(t)]})
    pets = _pet_policy(details)
    if pets:
        add("pet_policy", "Pet policy", pets[0], ["pets"], pets[1])
    unit_details = details.get("unitDetails") or {}
    available, total = as_int(unit_details.get("availableRentalUnits")), as_int(unit_details.get("totalUnitsInBuilding"))
    if available is not None:
        add("units_available", "Units available", f"{available} {'unit' if available == 1 else 'units'} listed as available" + (f" ({total} units in the building)" if total else ""),
            ["property"], {"available": available, "total_units": total})
    lease_terms = _lease_terms(details)
    add("lease_terms", "Lease terms offered", f"Lease Term: {lease_terms}" if lease_terms else None, ["lease"])
    if updated_at:
        add("source_last_modified", "Source last modified", f"Trulia lists this listing as last modified on {updated_at.date().isoformat()}.",
            ["listing"], {"last_modified": updated_at.isoformat()})
    price = details.get("price") or {}
    pricing = [
        _clean_text((price.get("typeDescriptionDetails") or {}).get("text")) if totals else None,
        *disclosures,
        _clean_text((details.get("priceDisclaimer") or {}).get("markdown")),
        _clean_text(((details.get("floorPlans") or {}).get("priceDisclaimer") or {}).get("markdown")),
    ]
    pricing = list(dict.fromkeys(p for p in pricing if p))
    add("pricing_disclosure", "Pricing disclosure", " ".join(pricing), ["price"], {"disclosures": pricing, "prices_include_required_fees": totals})
    feed = _feed_provenance(details, url)
    if feed:
        facts.append(feed)
    return facts


def parse_building_page(html: str, url: str, fetch: FetchResult) -> CollectedListing | None:
    """Parses a Trulia `/building/` page (unit-level floor plans) or a single-unit `/home/` page."""
    details = (((next_data(html) or {}).get("props") or {}).get("homeDetails"))
    listing_id = listing_id_from_url(url)
    if not isinstance(details, dict) or listing_id is None:
        return None
    page_id = _listing_id_from_typed_id(details.get("typedHomeId"))
    if page_id and page_id != listing_id:
        log.warning("Trulia page %s describes %s, not %s; ignoring it", url, page_id, listing_id)
        return None

    location = details.get("location") or {}
    coordinates = location.get("coordinates") or {}
    updated_at = parse_timestamp((details.get("activeListing") or {}).get("lastDateModified"))
    totals = _prices_include_required_fees(details)
    is_single_unit = not (details.get("floorPlans") or {}).get("floorPlanGroups") and details.get("__typename") == "HOME_Property"
    notes = []
    if is_single_unit:
        notes.append("Single-unit listing (Trulia home page), not a multi-unit building")

    units: list[CollectedUnit] = []
    if (details.get("currentStatus") or {}).get("isActiveForRent") is False:
        notes.append("Trulia shows this listing as no longer for rent; its price was not recorded")
    elif totals is None:
        notes.append("Trulia did not state whether listed prices include required fees; prices were not recorded")
    else:
        units = _single_unit(details, listing_id, updated_at, totals) if is_single_unit else _floorplan_units(details, updated_at, totals)
        if totals:
            notes.append("Trulia lists total monthly prices (base rent plus required monthly fees) for this property, so base rent per unit is not separately known")

    promotions, disclosures = _special_offers(details)
    street = location.get("streetAddress")
    return CollectedListing(
        source_id=SOURCE_ID,
        source_listing_id=listing_id,
        url=url,
        name=details.get("name") or street or location.get("homeFormattedAddress") or location.get("jsonLdSchemaFullLocation") or url,
        street_address=street,
        city=location.get("city"),
        state=location.get("stateCode"),
        zip=location.get("zipCode"),
        lat=as_float(coordinates.get("latitude")),
        lon=as_float(coordinates.get("longitude")),
        fetch=fetch,
        image_url=_image_url(html),
        source_updated_at=updated_at,
        units=units,
        fees=_fees(details),
        promotions=promotions,
        facts=_facts(details, url, updated_at, disclosures, totals),
        notes=notes,
    )


class TruliaCollector:
    source_id = SOURCE_ID

    def __init__(self, client: PoliteClient, listing_ttl: timedelta, max_pages: int, max_rent: int, allowed_beds: tuple[int, ...] = (0, 1)):
        self.client = client
        self.listing_ttl = listing_ttl
        self.max_pages = max_pages
        self.max_rent = max_rent
        self.allowed_beds = allowed_beds

    def search_url(self, city: SearchCity, page: int = 1) -> str:
        # No lower price bound: Trulia filters prices per unit, but a ceiling alone can never hide a qualifying unit.
        slug = f"{city.name.replace(' ', '_')},CA"
        beds = f"{min(self.allowed_beds)}-{max(self.allowed_beds)}_beds"
        url = f"{BASE_URL}/for_rent/{slug}/{beds}/0-{self.max_rent + PRICE_CEILING_MARGIN}_price/"
        return url if page == 1 else f"{url}{page}_p/"

    def discover(self, city: SearchCity) -> Iterator[DiscoveryStub]:
        seen: set[str] = set()
        for page in range(1, self.max_pages + 1):
            url = self.search_url(city, page)
            if not self._allowed(url):
                return
            result = self.client.get(url, ttl=self.listing_ttl)
            stubs, pages = parse_search_page(result.text)
            if not stubs and page == 1:
                log.warning("No Trulia search results could be parsed from %s", url)
            new = [s for s in stubs if s.source_listing_id not in seen]
            for stub in new:
                seen.add(stub.source_listing_id)
                yield stub
            if not new or (pages is not None and page >= pages):
                return

    def fetch_listing(self, stub: DiscoveryStub) -> CollectedListing | None:
        if not self._allowed(stub.url):
            return None
        result = self.client.get(stub.url, ttl=self.listing_ttl)
        return parse_building_page(result.text, stub.url, result)

    def _allowed(self, url: str) -> bool:
        if self.client.allowed(url):
            return True
        log.info("Skipping %s: disallowed by Trulia robots.txt", url)
        return False
