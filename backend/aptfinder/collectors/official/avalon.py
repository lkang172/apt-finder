import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from aptfinder.collectors.official.common import (
    AVALON,
    ParsedSite,
    SiteAddress,
    format_money,
    iso_date,
    money,
    required_fees,
    unique,
    whole_dollars,
)
from aptfinder.collectors.page_data import as_float, as_int
from aptfinder.collectors.types import CollectedUnit
from aptfinder.normalize import ParsedFee, classify_fee_type

GLOBAL_CONTENT = "Fusion.globalContent="
LAST_MODIFIED = re.compile(r"Fusion\.lastModified=(\d+)")
FEE_NAMES = re.compile(r"required monthly fees\s*\(([^)]+)\)", re.I)
UNIT_STATUS = {
    "VacantAvailable": "Vacant, available",
    "NoticeAvailable": "On notice, available",
}


def is_avalon_page(url: str, html: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return GLOBAL_CONTENT in html and (host.endswith("avaloncommunities.com") or '"communityId":"AVB-' in html)


def _global_content(html: str) -> dict[str, Any] | None:
    start = html.find(GLOBAL_CONTENT)
    if start == -1:
        return None
    content, _ = json.JSONDecoder().raw_decode(html, start + len(GLOBAL_CONTENT))
    return content if isinstance(content, dict) else None


def _last_modified(html: str) -> datetime | None:
    match = LAST_MODIFIED.search(html)
    return datetime.fromtimestamp(int(match.group(1)) / 1000, UTC) if match else None


def _unit(raw: dict[str, Any]) -> tuple[CollectedUnit | None, float | None]:
    quote = raw.get("startingAtPricesUnfurnished") or {}
    prices = quote.get("prices") or {}
    base = money(prices.get("price"))
    total = money(prices.get("totalPrice"))
    if base is None and total is None:
        return None, None
    sqft = as_int(raw.get("squareFeet"))
    status = raw.get("unitStatus")
    unit = CollectedUnit(
        source_unit_key=f"unit:{raw.get('unitId')}",
        kind="unit",
        label=raw.get("unitName"),
        floorplan_name=(raw.get("floorPlan") or {}).get("name"),
        beds=as_int(raw.get("bedroomNumber")),
        baths=as_float(raw.get("bathroomNumber")),
        sqft_min=sqft,
        sqft_max=sqft,
        base_rent_min=whole_dollars(base),
        base_rent_max=whole_dollars(base),
        total_monthly=total,
        required_fees_monthly=required_fees(base, total),
        lease_term_months=as_int(quote.get("leaseTerm")),
        available_on=iso_date(raw.get("availableDateUnfurnished")),
        availability=UNIT_STATUS.get(status, status),
    )
    return unit, money(prices.get("netEffectivePrice"))


def _required_fee(description: str | None, units: list[CollectedUnit]) -> ParsedFee | None:
    differences = sorted({u.required_fees_monthly for u in units if u.required_fees_monthly is not None})
    if not differences or differences[-1] == 0:
        return None
    names = FEE_NAMES.search(description or "")
    label = f"Required monthly fees ({names.group(1).strip()})" if names else "Required monthly fees"
    if len(differences) == 1:
        amount_text = format_money(differences[0])
        detail = "the difference between the published total price and base rent on every listed unit"
    else:
        amount_text = f"{format_money(differences[0])}–{format_money(differences[-1])}"
        detail = "the difference between the published total price and base rent, which varies by unit"
    return ParsedFee(
        fee_type=classify_fee_type(label),
        description=f"{label}: {amount_text}/month, {detail}",
        amount=round(differences[0]) if len(differences) == 1 else None,
        amount_text=amount_text,
        recurring=True,
        mandatory=True,
    )


def _add_policy_facts(site: ParsedSite, content: dict[str, Any]) -> None:
    utilities = [
        f"{u['name']}: paid by {str(u['responsibleSide']).lower()}"
        for u in content.get("utilities") or []
        if isinstance(u, dict) and u.get("name") and u.get("responsibleSide") not in (None, "", "N/A")
    ]
    site.add_fact("utilities", "Utilities", "; ".join(utilities), ["price", "other_issues"], {"utilities": content.get("utilities")})

    policies = content.get("policies") or {}
    site.add_fact("parking_policy", "Resident parking policy", policies.get("residentPolicy"), ["parking"])
    pet_parts = [policies.get("petPolicy") or ""]
    if as_int(policies.get("maximumPets")):
        pet_parts.append(f"Maximum pets: {policies['maximumPets']}.")
    breeds = (policies.get("restrictedBreeds") or {}).get("breeds") or []
    if breeds:
        pet_parts.append(f"Restricted breeds: {', '.join(breeds)}.")
    site.add_fact("pet_policy", "Pet policy", " ".join(p for p in pet_parts if p), ["pets"], {"allowed_pets": content.get("allowedPets")})

    for group in content.get("communityFilters") or []:
        if isinstance(group, dict) and group.get("name") == "LeaseTerms":
            terms = sorted({as_int(o.get("value")) for o in group.get("options") or [] if isinstance(o, dict)} - {None})
            if terms:
                content = f"Lease terms offered (months): {', '.join(map(str, terms))}"
                site.add_fact("lease_terms", "Lease terms offered", content, ["lease"], {"months": terms})


def parse_community_page(html: str) -> ParsedSite | None:
    content = _global_content(html)
    if not content or not content.get("communityId"):
        return None
    address = content.get("address") or {}
    coordinates = content.get("coordinates") or {}
    site = ParsedSite(
        platform=AVALON,
        platform_property_id=str(content["communityId"]),
        name=content.get("name"),
        address=SiteAddress(
            street_address=address.get("addressLine1"),
            city=address.get("city"),
            state=address.get("state"),
            zip=address.get("zip"),
            lat=as_float(coordinates.get("latitude")),
            lon=as_float(coordinates.get("longitude")),
        ),
        source_updated_at=_last_modified(html),
    )

    net_effective_lines = []
    unpriced = 0
    for raw in content.get("units") or []:
        unit, net_effective = _unit(raw)
        if unit is None:
            unpriced += 1
            continue
        site.units.append(unit)
        if net_effective is not None and unit.base_rent_min is not None and net_effective < unit.base_rent_min:
            term = f" ({unit.lease_term_months}-month lease)" if unit.lease_term_months else ""
            net_effective_lines.append(
                f"Unit {unit.label}: net effective {format_money(net_effective)}/month vs. base rent "
                f"{format_money(unit.base_rent_min)}{term}"
            )
    if unpriced:
        site.notes.append(f"{unpriced} listed unit(s) have no published unfurnished price and were not recorded")

    summary = content.get("unitsSummary") or {}
    pricing_description = summary.get("pricingDescription") or next(
        (u.get("pricingDescription") for u in content.get("units") or [] if u.get("pricingDescription")), None
    )
    site.add_fact("pricing_disclosure", "Pricing disclosure", pricing_description, ["price"])
    fee = _required_fee(pricing_description, site.units)
    if fee:
        site.fees.append(fee)

    promotions = [p for p in summary.get("promotions") or content.get("promotions") or [] if isinstance(p, dict)]
    site.promotions = unique([f"{p.get('promotionTitle') or ''} {p.get('promotionDescription') or ''}" for p in promotions])
    if promotions:
        lines = [
            p.get("promotionTitle") + (f" (offer end date listed: {p['promotionEndDate']})" if p.get("promotionEndDate") else "")
            for p in promotions
            if p.get("promotionTitle")
        ]
        site.add_fact("promotions", "Current promotions", "; ".join(unique(lines)), ["price"], {"promotions": promotions})
    if net_effective_lines:
        site.add_fact(
            "net_effective_prices",
            "Net-effective prices (after promotions, not base rent)",
            "; ".join(net_effective_lines),
            ["price"],
        )
        site.promotions.append("Net-effective prices published (after promotions, not base rent): " + "; ".join(net_effective_lines))

    _add_policy_facts(site, content)
    return site
