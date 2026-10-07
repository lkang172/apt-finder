import json
import logging
import math
import re
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from aptfinder.collectors.page_data import as_float, as_int, json_ld_blocks, parse_timestamp
from aptfinder.collectors.types import CollectedFact, CollectedListing, CollectedUnit, DiscoveryStub
from aptfinder.config import SearchCity
from aptfinder.http import FetchResult, PoliteClient
from aptfinder.normalize import MONEY, ParsedFee, extract_unit_number

log = logging.getLogger(__name__)

BASE_URL = "https://www.apartmentguide.com"
SOURCE_ID = "apartment_guide"
# Observed on every city page; `listingSearch.total` counts listings, not pages.
PAGE_SIZE = 50
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', re.S)
# `/a/<slug>-<id>/` is a property page; `/rent/<slug>-LV<id>/` is a single rental (Rent.'s "Lovely" feed).
LISTING_PATH = re.compile(r"^/(a|rent)/[^/]+-([A-Za-z0-9]+)/?$")
OG_IMAGE = re.compile(r'<meta property="og:image" content="([^"]+)"')
SKIP_PROPERTY_TYPE = re.compile(r"house|condo|room", re.I)
MONEY_ONLY = re.compile(r"\$\s?\d[\d,]*(?:\.\d{1,2})?")
PRICING_DISCLOSURE = re.compile(r"\b(total monthly leasing prices?|prices? (?:shown )?include|excludes? variable)\b", re.I)
CONCESSION_WORDS = re.compile(
    r"\b(free|off|waived?|discount\w*|credit|concession|special|reduced|save|savings|gift card|look and lease|bonus)\b|\$\s?\d", re.I
)
ELIGIBILITY_PHRASE = (
    r"income[- ](?:restricted|protected|qualified|capped|limits?)|senior|age[- ]restricted|55\s*\+|62\s*\+|"
    r"affordable|below[- ]market[- ]rate|\bbmr\b|low[- ]income|student|military"
)
# Names and floor-plan names are short, so any eligibility word counts.
ELIGIBILITY_NAME = re.compile(rf"\b(?:{ELIGIBILITY_PHRASE})\b", re.I)
# Marketing descriptions mention "senior" and "income" in passing, so only explicit housing-type phrases count.
ELIGIBILITY_DESCRIPTION = re.compile(
    r"\b(income[- ]restricted|age[- ]restricted|senior (?:living|housing|community|apartments?|citizens?)|55\s*\+|62\s*\+)", re.I
)
OTHER_NETWORKS = {"ZILLOW": "Zillow Group"}
PLAN_AVAILABILITY = {"AVAILABLE_WITH_COUNT": "Available now"}


def next_data(html: str) -> dict[str, Any] | None:
    match = NEXT_DATA.search(html)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def page_data(html: str) -> dict[str, Any]:
    return ((((next_data(html) or {}).get("props") or {}).get("pageProps") or {}).get("pageData")) or {}


def listing_id_from_url(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.netloc and parts.netloc != urlsplit(BASE_URL).netloc:
        return None
    match = LISTING_PATH.match(parts.path)
    return match.group(2) if match else None


def is_single_rental_url(url: str) -> bool:
    match = LISTING_PATH.match(urlsplit(url).path)
    return bool(match) and match.group(1) == "rent"


def _money(value: Any) -> int | None:
    """Exact dollar amounts only ("$2,475", 500); text such as "Contact for details" yields None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return as_int(value) if value > 0 else None
    if isinstance(value, str) and MONEY_ONLY.fullmatch(value.strip()):
        amount = as_int(MONEY.search(value).group(1))
        return amount if amount else None
    return None


def _money_text(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return f"${as_int(value):,}" if value > 0 else None
    text = value.strip() if isinstance(value, str) else ""
    return text or None


def _price_range(node: Any) -> tuple[int | None, int | None]:
    if not isinstance(node, dict):
        return None, None
    low, high = _money(node.get("min")), _money(node.get("max"))
    if low is None:
        return None, None
    return low, high if high is not None and high >= low else low


def _date_part(value: Any) -> str | None:
    return value[:10] if isinstance(value, str) and re.match(r"\d{4}-\d{2}-\d{2}", value) else None


def _available_label(date: str | None) -> str | None:
    # The page renders a future move-in date as "Available Oct 27".
    if date is None:
        return None
    parsed = datetime.strptime(date, "%Y-%m-%d")
    return f"Available {parsed:%b} {parsed.day}"


def _squash(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return re.sub(r"\s+", " ", value).strip() or None


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [v.strip() for v in value if isinstance(v, str) and v.strip()]
    return []


def card_stub(card: dict[str, Any], fallback_beds: tuple[int, ...]) -> DiscoveryStub | None:
    path = card.get("urlPathname") or ""
    path_id = listing_id_from_url(BASE_URL + path) if path.startswith("/") else None
    if path_id is None:
        log.info("Skipping ApartmentGuide search result without a listing page: %s", path)
        return None
    property_type = card.get("propertyType")
    if isinstance(property_type, str) and SKIP_PROPERTY_TYPE.search(property_type):
        log.info("Skipping ApartmentGuide %s listing %s", property_type, path)
        return None
    # `bedCountData` holds the cheapest listed price per bedroom count (it matched the minimum of the card's
    # floor plans on every observed card); `price` is the cheapest price across all bedroom counts, so it is a
    # lower bound for every bedroom count when the per-bedroom data is missing.
    price = _money(card.get("price"))
    prices: dict[int, int | None] = {}
    for entry in card.get("bedCountData") or []:
        beds = as_int(entry.get("beds")) if isinstance(entry, dict) else None
        if beds is not None:
            prices[beds] = _money((entry.get("prices") or {}).get("low"))
    if not prices:
        bed_range = card.get("bedRange") or {}
        low, high = as_int(bed_range.get("min")), as_int(bed_range.get("max"))
        beds = list(range(low, high + 1)) if low is not None and high is not None and 0 <= low <= high else list(fallback_beds)
        prices = {b: price for b in beds}
    location = card.get("location") or {}
    return DiscoveryStub(
        source_id=SOURCE_ID,
        source_listing_id=str(card.get("id") or path_id),
        url=BASE_URL + urlsplit(path).path,
        name=_squash(card.get("name")) or _squash(card.get("addressFull")) or path,
        city=location.get("city"),
        lat=as_float(location.get("lat")),
        lon=as_float(location.get("lng")),
        min_price_by_beds=prices,
    )


def parse_search_page(html: str, fallback_beds: tuple[int, ...] = (0, 1)) -> tuple[list[DiscoveryStub], int | None]:
    """Returns the page's stubs and the total number of listings for the city."""
    search = ((page_data(html).get("location") or {}).get("listingSearch")) or {}
    stubs: dict[str, DiscoveryStub] = {}
    for card in search.get("listings") or []:
        stub = card_stub(card, fallback_beds) if isinstance(card, dict) else None
        if stub is not None:
            stubs.setdefault(stub.source_listing_id, stub)
    return list(stubs.values()), as_int(search.get("total"))


def _price_fields(low: int, high: int | None, totals: bool) -> dict[str, Any]:
    if totals:
        return {"base_rent_min": None, "base_rent_max": None, "total_monthly": float(low)}
    return {"base_rent_min": low, "base_rent_max": high or low}


def _baths(plan: dict[str, Any]) -> float | None:
    full, half = as_float(plan.get("bathCount")), as_float(plan.get("halfBathCount"))
    if full is None and half is None:
        return None
    return (full or 0) + 0.5 * (half or 0) or None


def _plan_sqft(plan: dict[str, Any]) -> tuple[int | None, int | None]:
    sqft_range = plan.get("sqFtRange") or {}
    low = as_int(sqft_range.get("min")) or as_int(plan.get("sqFt"))
    high = as_int(sqft_range.get("max")) or low
    return low, high if high and low and high >= low else low


def _units(listing: dict[str, Any], listing_id: str, single_rental: bool, updated_at: datetime | None, totals: bool) -> tuple[list[CollectedUnit], list[str]]:
    units: list[CollectedUnit] = []
    notes: list[str] = []
    used_keys: set[str] = set()
    for plan in listing.get("floorPlans") or []:
        if not isinstance(plan, dict):
            continue
        term = plan.get("priceTerm")
        if isinstance(term, str) and term.strip() and term.strip() != "/mo":
            notes.append(f"Floor plan {plan.get('name')} is priced per {term.strip().lstrip('/')} rather than per month; its price was not recorded")
            continue
        beds, baths = as_int(plan.get("bedCount")), _baths(plan)
        plan_sqft_min, plan_sqft_max = _plan_sqft(plan)
        plan_units = [u for u in plan.get("units") or [] if isinstance(u, dict)]
        for unit in plan_units:
            rent = _money(unit.get("rent"))
            if rent is None:
                continue
            label = _squash(unit.get("unitId"))
            key = f"unit:{label}" if label else f"unit:{plan.get('id') or plan.get('name')}:{len(units)}"
            if key in used_keys:
                key = f"{key}:{len(units)}"
            used_keys.add(key)
            available_on = _date_part(unit.get("dateAvailable"))
            # `minSqft` is the unit's stated floor area; the plan's range caps it when the plan is larger.
            sqft_min = as_int(unit.get("minSqft")) or plan_sqft_min
            sqft_max = max(sqft_min, plan_sqft_max) if sqft_min and plan_sqft_max else sqft_min
            units.append(
                CollectedUnit(
                    source_unit_key=key,
                    kind="unit",
                    label=label,
                    floorplan_name=_squash(plan.get("name")),
                    beds=beds,
                    baths=baths,
                    sqft_min=sqft_min,
                    sqft_max=sqft_max,
                    available_on=available_on,
                    availability="Available now" if unit.get("isAvailable") is True else _available_label(available_on),
                    source_updated_at=updated_at,
                    **_price_fields(rent, rent, totals),
                )
            )
        if plan_units:
            continue
        low, high = _price_range(plan.get("priceRange"))
        if low is None:
            continue
        available_on = _date_part(plan.get("availableDate"))
        status = plan.get("availabilityStatusCode")
        availability = _squash(plan.get("availabilityText")) or PLAN_AVAILABILITY.get(status) or (
            _available_label(available_on) if status == "UNAVAILABLE_WITH_FUTURE_MOVE_DATE" else None
        )
        units.append(
            CollectedUnit(
                source_unit_key=f"unit:{listing_id}" if single_rental else f"plan:{plan.get('id') or plan.get('name')}",
                kind="unit" if single_rental else "floorplan",
                label=extract_unit_number(listing.get("address")) if single_rental else None,
                floorplan_name=_squash(plan.get("name")),
                beds=beds,
                baths=baths,
                sqft_min=plan_sqft_min,
                sqft_max=plan_sqft_max,
                available_on=available_on,
                availability=availability,
                source_updated_at=updated_at,
                **_price_fields(low, high, totals),
            )
        )
    return units, notes


def _fee(fee_type: str, label: str, value: Any, recurring: bool | None, mandatory: bool | None) -> ParsedFee | None:
    text = _money_text(value)
    if text is None:
        return None
    amount = _money(value)
    return ParsedFee(fee_type, f"{label}: {text}", amount, text if amount is not None or MONEY.search(text) else None, recurring, mandatory)


def _fees(listing: dict[str, Any]) -> list[ParsedFee]:
    fees: list[ParsedFee] = []
    costs = listing.get("fees") or {}
    for field, label in (("applicationFee", "Application fee"), ("adminFee", "Admin fee"), ("brokerFee", "Broker fee")):
        fee = _fee("one_time", label, costs.get(field), False, True)
        if fee:
            fees.append(fee)
    amenity = costs.get("amenity") or {}
    if amenity.get("fee") is not None:
        fee_type = str(amenity.get("feeType") or "").lower()
        recurring = True if "month" in fee_type else False if re.search(r"one[- ]?time|move[- ]in", fee_type) else None
        label = "Amenity fee" + (f" ({amenity['feeType']})" if amenity.get("feeType") else "")
        if amenity.get("notes"):
            label += f", {_squash(amenity['notes'])}"
        fee = _fee("amenity", label, amenity["fee"], recurring, None)
        if fee:
            fees.append(fee)
    for policy in listing.get("petPolicies") or []:
        if not isinstance(policy, dict):
            continue
        label = _squash(policy.get("label")) or _squash(policy.get("id")) or "Pets"
        for field, name, recurring in (("additionalRent", "Pet rent", True), ("deposit", "Pet deposit", False), ("initialFee", "Pet fee", False)):
            fee = _fee("pet", f"{name} ({label})", policy.get(field), recurring, False)
            if fee:
                suffix = "/month (only if you have a pet)" if recurring else " (only if you have a pet)"
                fees.append(ParsedFee(fee.fee_type, fee.description + suffix, fee.amount, fee.amount_text, fee.recurring, fee.mandatory))
    for spot in listing.get("parking") or []:
        if not isinstance(spot, dict):
            continue
        value = spot.get("perSpaceFee") if spot.get("perSpaceFee") is not None else spot.get("assignedFee")
        comments = _squash(spot.get("comments"))
        if value is None and not comments:
            continue
        label = f"Parking ({spot.get('type') or 'type not stated'})" + (f", {comments}" if comments else "")
        fee = _fee("parking", label, value, None, None) if value is not None else ParsedFee("parking", label, None, None, None, None)
        if fee:
            fees.append(fee)
    for plan in listing.get("floorPlans") or []:
        if not isinstance(plan, dict):
            continue
        fee = _fee("deposit", f"Security deposit ({_squash(plan.get('name')) or 'floor plan'})", plan.get("deposit"), False, True)
        if fee:
            fees.append(fee)
        for unit in plan.get("units") or []:
            if isinstance(unit, dict):
                fee = _fee("deposit", f"Security deposit (unit {_squash(unit.get('unitId')) or '?'})", unit.get("deposit"), False, True)
                if fee:
                    fees.append(fee)
    return list(dict.fromkeys(fees))


def _deals(listing: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Splits the deals slot into real promotions and pricing disclosures shown in the same slot."""
    texts = [_squash(d.get("description")) for d in listing.get("deals") or [] if isinstance(d, dict)]
    texts = [t for t in texts if t] or ([_squash(listing.get("dealsText"))] if _squash(listing.get("dealsText")) else [])
    promotions, disclosures = [], []
    for text in dict.fromkeys(texts):
        if PRICING_DISCLOSURE.search(text) and not CONCESSION_WORDS.search(text):
            disclosures.append(text)
        else:
            promotions.append(text)
    return promotions, disclosures


def _eligibility(listing: dict[str, Any], url: str) -> CollectedFact | None:
    restrictions: list[str] = []
    evidence: list[str] = []
    limits = [
        {"max_occupants": as_int(row.get("maxOccupants")), "max_annual_income": _squash(row.get("maxAnnualIncome"))}
        for row in listing.get("incomeRestrictions") or [] if isinstance(row, dict)
    ]
    if limits:
        restrictions.append("Income Restricted")
        evidence.append("page lists income limits by household size")
    for badge in _strings(listing.get("categoryBadges")):
        if ELIGIBILITY_NAME.search(badge):
            restrictions.append(badge.title())
            evidence.append(f'listing badge "{badge}"')
    plan_names = [_squash(p.get("name")) for p in listing.get("floorPlans") or [] if isinstance(p, dict) and _squash(p.get("name"))]
    for text, where in [(_squash(listing.get("name")), "listing name"), *[(n, f'floor plan "{n}"') for n in plan_names]]:
        match = ELIGIBILITY_NAME.search(text or "")
        if match:
            restrictions.append(re.sub(r"\s+", " ", match.group(0)).title())
            evidence.append(f"{where} contains \"{match.group(0)}\"")
    match = ELIGIBILITY_DESCRIPTION.search(listing.get("description") or "")
    if match:
        restrictions.append(re.sub(r"\s+", " ", match.group(0)).title())
        evidence.append(f'description contains "{match.group(0)}"')
    restrictions = list(dict.fromkeys(restrictions))
    if not restrictions:
        return None
    content = f"Listed as: {', '.join(restrictions)}. Eligibility requirements may apply."
    if limits:
        table = "; ".join(
            f"{row['max_occupants']} occupant{'s' if row['max_occupants'] != 1 else ''}: {row['max_annual_income']}"
            for row in limits if row["max_occupants"] is not None and row["max_annual_income"]
        )
        if table:
            content += f" Maximum annual income by household size: {table}."
    return CollectedFact("eligibility", "Eligibility restrictions", content, ["eligibility"],
                         {"restrictions": restrictions, "income_limits": limits, "evidence": evidence}, url)


def _pet_policy(listing: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    policies = [p for p in listing.get("petPolicies") or [] if isinstance(p, dict)]
    parts = []
    for policy in policies:
        label = _squash(policy.get("label")) or _squash(policy.get("id"))
        if not label:
            continue
        extras = [_squash(policy.get("comment"))]
        if _money(policy.get("additionalRent")):
            extras.append(f"pet rent ${_money(policy['additionalRent']):,}/month")
        if _money(policy.get("deposit")):
            extras.append(f"deposit ${_money(policy['deposit']):,}")
        if _money(policy.get("initialFee")):
            extras.append(f"one-time fee ${_money(policy['initialFee']):,}")
        if policy.get("maximumPets"):
            extras.append(f"max {policy['maximumPets']} pets")
        if policy.get("weightRestriction"):
            extras.append(f"weight limit {policy['weightRestriction']}")
        extras = [e for e in extras if e]
        parts.append(label + (f" ({'; '.join(extras)})" if extras else ""))
    if not parts:
        return None
    return "; ".join(parts), {"policies": policies}


def _feed_provenance(listing: dict[str, Any], url: str) -> CollectedFact:
    tplsource = _squash(listing.get("tplsource"))
    feed = _squash((listing.get("mlsInfo") or {}).get("feed"))
    network = OTHER_NETWORKS.get((tplsource or "").upper())
    signals = [s for s in (f"tplsource: {tplsource}" if tplsource else None, f"feed: {feed}" if feed else None) if s]
    content = (
        "ApartmentGuide is a Rent. network site (Rent. is owned by Redfin, a Rocket Companies subsidiary), so this "
        "listing shares its feed with Rent.com and Redfin Rentals. "
    )
    if network:
        content += f"The page attributes the listing to {network} (tplsource {tplsource}), so it is not an independent confirmation of sources fed by {network}."
    else:
        content += f"Feed attribution on the page: {'; '.join(signals) if signals else 'none'}."
    return CollectedFact(
        "feed_provenance", "Listing feed provenance", content, ["listing"],
        {"network": "Rent. (Redfin / Rocket Companies)", "tplsource": tplsource, "feed": feed, "attributed_network": network,
         "independent_source": network is None, "shares_feed_with": ["redfin"] + (["trulia"] if network == "Zillow Group" else []), "signals": signals},
        url,
    )


def _facts(listing: dict[str, Any], url: str, updated_at: datetime | None, disclosures: list[str], totals: bool | None) -> list[CollectedFact]:
    facts: list[CollectedFact] = []

    def add(key: str, title: str, content: str | None, categories: list[str], data: dict[str, Any] | None = None) -> None:
        if content:
            facts.append(CollectedFact(key, title, content, categories, data or {}, url))

    badges = _strings(listing.get("categoryBadges"))
    add("listing_tags", "ApartmentGuide listing badges", ", ".join(badges), ["listing"], {"tags": badges, "property_type": listing.get("propertyType")})
    eligibility = _eligibility(listing, url)
    if eligibility:
        facts.append(eligibility)
    pets = _pet_policy(listing)
    if pets:
        add("pet_policy", "Pet policy", pets[0], ["pets"], pets[1])
    parking = [p for p in listing.get("parking") or [] if isinstance(p, dict)]
    parking_parts = []
    for spot in parking:
        part = _squash(spot.get("type")) or "Parking"
        details = [_squash(spot.get("comments")), "assigned" if spot.get("assigned") is True else None,
                   f"{spot['totalSpaces']} spaces" if spot.get("totalSpaces") else None,
                   f"${_money(spot['perSpaceFee']):,} per space" if _money(spot.get("perSpaceFee")) else None]
        details = [d for d in details if d]
        parking_parts.append(part + (f" ({'; '.join(details)})" if details else ""))
    add("parking_details", "Parking details", "; ".join(parking_parts), ["parking"], {"parking": parking})
    available, total = as_int(listing.get("unitsAvailable")), as_int(listing.get("totalUnits"))
    if available is not None:
        add("units_available", "Units available", f"{available} {'unit' if available == 1 else 'units'} listed as available" + (f" ({total} units in the building)" if total else ""),
            ["property"], {"available": available, "total_units": total})
    terms = _strings(listing.get("leasingTerms")) + _strings(listing.get("specialTerms"))
    add("lease_terms", "Lease terms offered", "; ".join(dict.fromkeys(terms)), ["lease"], {"terms": terms})
    manager = _squash((listing.get("propertyManagementCompany") or {}).get("name"))
    add("management_company", "Property management company", manager, ["management"])
    costs = listing.get("fees") or {}
    utilities = costs.get("utilities") or {}
    included = utilities.get("included") or {}
    included_text = "; ".join(_strings(included.get("utilities")) + _strings(included.get("notes")))
    add("utilities_included", "Utilities included", included_text, ["price", "other_issues"], {"included": included})
    add("utilities_tenant_paid", "Utilities paid by tenant", "; ".join(_strings(utilities.get("tenantPaid"))), ["price"], {"tenant_paid": utilities.get("tenantPaid")})
    insurance = {k: v for k, v in (costs.get("insurance") or {}).items() if v not in (None, "", [], False)}
    add("renters_insurance", "Renters insurance", "; ".join(f"{k}: {v}" for k, v in insurance.items()), ["lease"], insurance)
    if updated_at:
        add("source_last_modified", "Source last modified", f"ApartmentGuide lists this listing as last updated on {updated_at.date().isoformat()}.",
            ["listing"], {"last_modified": updated_at.isoformat()})
    pricing = list(dict.fromkeys(p for p in (*disclosures, _squash(listing.get("disclaimer"))) if p))
    add("pricing_disclosure", "Pricing disclosure", " ".join(pricing), ["price"], {"disclosures": pricing, "prices_include_required_fees": totals})
    amenities = [_squash(a.get("amenity")) for a in listing.get("amenitiesWithSubcategories") or [] if isinstance(a, dict) and _squash(a.get("amenity"))]
    add("amenities", "Amenities listed", "; ".join(dict.fromkeys(amenities)), ["amenities"], {"amenities": amenities})
    facts.append(_feed_provenance(listing, url))
    percent, count = as_float(listing.get("ratingPercent")), as_int(listing.get("ratingCount"))
    if percent is not None and count is not None:
        add("source_rating", "ApartmentGuide rating",
            f"ApartmentGuide shows a rating of {percent:g}% from {count} rating(s); the page does not state the scale behind the percentage, so it is not converted to a star rating.",
            ["review_quality"], {"rating_percent": percent, "rating_count": count})
    return facts


def _image_url(html: str) -> str | None:
    for block in json_ld_blocks(html):
        about = block.get("about") if isinstance(block, dict) else None
        image = (about or {}).get("image") if isinstance(about, dict) else None
        url = image.get("contentUrl") if isinstance(image, dict) else image
        if isinstance(url, str) and url.startswith("https://"):
            return url
    match = OG_IMAGE.search(html)
    return match.group(1) if match and match.group(1).startswith("https://") else None


def parse_listing_page(html: str, url: str, fetch: FetchResult) -> CollectedListing | None:
    """Parses an ApartmentGuide `/a/` property page or `/rent/` single-rental page."""
    listing = page_data(html).get("listing")
    listing_id = listing_id_from_url(url)
    if not isinstance(listing, dict) or listing_id is None:
        return None
    page_id = str(listing.get("id") or "")
    if page_id and page_id != listing_id:
        log.warning("ApartmentGuide page %s describes %s, not %s; ignoring it", url, page_id, listing_id)
        return None
    if listing.get("roomForRent") is True:
        log.info("Skipping ApartmentGuide room-for-rent listing %s", url)
        return None

    location = listing.get("location") or {}
    updated_at = parse_timestamp(listing.get("updatedAt"))
    totals = listing.get("hasTotalCostWithFees")
    totals = totals if isinstance(totals, bool) else None
    single_rental = is_single_rental_url(url)
    notes = []
    if single_rental:
        notes.append("Single-unit rental listing (ApartmentGuide /rent/ page), not a multi-unit property page")
    property_type = listing.get("propertyType")
    if isinstance(property_type, str) and property_type.upper() != "APARTMENTS":
        notes.append(f"ApartmentGuide lists the property type as {property_type}")

    units: list[CollectedUnit] = []
    if listing.get("offMarket") is True:
        notes.append("ApartmentGuide shows this listing as off market; its prices were not recorded")
    elif totals is None:
        notes.append("ApartmentGuide did not state whether listed prices include required fees; prices were not recorded")
    else:
        units, unit_notes = _units(listing, listing_id, single_rental, updated_at, totals)
        notes.extend(unit_notes)
        if totals:
            notes.append("ApartmentGuide lists total monthly prices (base rent plus required monthly fees) for this property, so base rent per unit is not separately known")

    promotions, disclosures = _deals(listing)
    street = _squash(listing.get("address"))
    return CollectedListing(
        source_id=SOURCE_ID,
        source_listing_id=listing_id,
        url=url,
        name=_squash(listing.get("name")) or street or _squash(listing.get("addressFull")) or url,
        street_address=street,
        city=location.get("city"),
        state=location.get("stateAbbr"),
        zip=location.get("zip"),
        lat=as_float(location.get("lat")),
        lon=as_float(location.get("lng")),
        fetch=fetch,
        image_url=_image_url(html),
        official_website_url=_squash(listing.get("website")),
        source_updated_at=updated_at,
        units=units,
        fees=_fees(listing),
        promotions=promotions,
        facts=_facts(listing, url, updated_at, disclosures, totals),
        notes=notes,
    )


class ApartmentGuideCollector:
    source_id = SOURCE_ID

    def __init__(self, client: PoliteClient, listing_ttl: timedelta, max_pages: int, max_rent: int, allowed_beds: tuple[int, ...] = (0, 1)):
        self.client = client
        self.listing_ttl = listing_ttl
        self.max_pages = max_pages
        # Price and bedroom refinements are query strings that robots.txt disallows (`/*?*max_price=*`), so the
        # unfiltered city page is fetched and `max_rent`/`allowed_beds` only shape the discovery stubs.
        self.max_rent = max_rent
        self.allowed_beds = allowed_beds

    def search_url(self, city: SearchCity, page: int = 1) -> str:
        # City slugs replace spaces with hyphens (e.g. /apartments/California/Mountain-View/); page N is /page-N/.
        url = f"{BASE_URL}/apartments/California/{city.name.replace(' ', '-')}/"
        return url if page == 1 else f"{url}page-{page}/"

    def discover(self, city: SearchCity) -> Iterator[DiscoveryStub]:
        seen: set[str] = set()
        for page in range(1, self.max_pages + 1):
            url = self.search_url(city, page)
            if not self._allowed(url):
                return
            result = self.client.get(url, ttl=self.listing_ttl)
            stubs, total = parse_search_page(result.text, self.allowed_beds)
            if not stubs and page == 1:
                log.warning("No ApartmentGuide search results could be parsed from %s", url)
            new = [s for s in stubs if s.source_listing_id not in seen]
            for stub in new:
                seen.add(stub.source_listing_id)
                yield stub
            pages = math.ceil(total / PAGE_SIZE) if total else None
            if not new or (pages is not None and page >= pages):
                return

    def fetch_listing(self, stub: DiscoveryStub) -> CollectedListing | None:
        if not self._allowed(stub.url):
            return None
        result = self.client.get(stub.url, ttl=self.listing_ttl)
        return parse_listing_page(result.text, stub.url, result)

    def _allowed(self, url: str) -> bool:
        if self.client.allowed(url):
            return True
        log.info("Skipping %s: disallowed by ApartmentGuide robots.txt", url)
        return False
