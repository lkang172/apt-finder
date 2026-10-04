import re
from dataclasses import dataclass
from typing import Any

from aptfinder.collectors.official.common import (
    KNOCK,
    ParsedSite,
    SiteAddress,
    iso_date,
    money,
    unique,
    whole_dollars,
)
from aptfinder.collectors.page_data import as_float, as_int, parse_timestamp
from aptfinder.collectors.types import CollectedUnit
from aptfinder.normalize import MONEY, MONTHLY, ParsedFee

API_BASE = "https://doorway-api.knockrentals.com/v1"
# The init call appears either in a plain <script> or inside a JSON-escaped string (\"...\").
DOORWAY_INIT = re.compile(
    r"""knockDoorway\.init\(\s*\\?["'][^"'\\]+\\?["']\s*,\s*\\?["']community\\?["']\s*,\s*\\?["']([0-9a-f]{16})\\?["']"""
)
PET_KINDS = (("cats", "cats"), ("small_dogs", "small dogs"), ("large_dogs", "large dogs"))


@dataclass
class KnockCommunity:
    property_id: int
    site: ParsedSite
    pricing_hidden: bool


def find_community_id(html: str) -> str | None:
    match = DOORWAY_INIT.search(html)
    return match.group(1) if match else None


def community_url(community_id: str) -> str:
    return f"{API_BASE}/property/community/{community_id}"


def units_url(property_id: int) -> str:
    return f"{API_BASE}/property/{property_id}/units"


def _single_amount(text: str) -> float | None:
    amounts = MONEY.findall(text)
    return float(amounts[0].replace(",", "")) if len(amounts) == 1 else None


def _fees(data: dict[str, Any]) -> list[ParsedFee]:
    fees = []
    leasing = data.get("leasing") or {}
    application_fee = str((leasing.get("application") or {}).get("fee") or "").strip()
    if application_fee:
        amount = _single_amount(application_fee)
        fees.append(ParsedFee("one_time", f"Application fee: {application_fee}", whole_dollars(amount), application_fee, False, True))
    deposit = str((leasing.get("terms") or {}).get("deposit") or "").strip()
    if deposit:
        amount = money(deposit) or _single_amount(deposit)
        fees.append(ParsedFee("deposit", f"Security deposit: {deposit}", whole_dollars(amount), deposit, False, True))

    pets = data.get("pets") or {}
    for field, label, recurring in (("rent", "Pet rent", True), ("deposit", "Pet deposit", False), ("fee", "Pet fee", False)):
        text = str(pets.get(field) or "").strip()
        if not text:
            continue
        amount = money(text) or _single_amount(text)
        shown = f"${text}" if money(text) is not None and not text.startswith("$") else text
        suffix = "/month" if recurring and money(text) is not None else ""
        fees.append(ParsedFee("pet", f"{label}: {shown}{suffix} (only if you have a pet)", whole_dollars(amount), shown, recurring, False))

    parking_notes = str((data.get("parking") or {}).get("notes") or "").strip()
    if parking_notes and MONEY.search(parking_notes):
        amount = _single_amount(parking_notes)
        fees.append(
            ParsedFee(
                "parking",
                f"Parking: {parking_notes}",
                whole_dollars(amount),
                MONEY.search(parking_notes).group(0) if amount is not None else parking_notes,
                True if MONTHLY.search(parking_notes) else None,
                None,
            )
        )
    return fees


def _add_facts(site: ParsedSite, data: dict[str, Any]) -> None:
    utilities = data.get("utilities") or {}
    included = [u["name"] for u in utilities.get("types") or [] if isinstance(u, dict) and u.get("included") and u.get("name")]
    text = (
        f"Utility items marked as included on the property's leasing profile: {', '.join(included)}."
        if included
        else "No utilities are marked as included in rent on the property's leasing profile."
    )
    if utilities.get("estimatedCost"):
        text += f" Estimated utility cost: {utilities['estimatedCost']}."
    if utilities.get("types"):
        site.add_fact("utilities", "Utilities", text, ["price", "other_issues"], {"utilities": utilities})

    parking = data.get("parking") or {}
    kinds = [p["name"] for p in parking.get("types") or [] if isinstance(p, dict) and p.get("available") and p.get("name")]
    parking_parts = [f"Parking types offered: {', '.join(kinds)}."] if kinds else []
    if parking.get("notes"):
        parking_parts.append(str(parking["notes"]).strip())
    site.add_fact("parking", "Parking", " ".join(parking_parts), ["parking"], {"parking": parking})

    pets = data.get("pets") or {}
    allowed = pets.get("allowed") or {}
    pet_parts = []
    if allowed.get("none"):
        pet_parts.append("No pets allowed.")
    else:
        yes = [label for key, label in PET_KINDS if allowed.get(key)]
        no = [label for key, label in PET_KINDS if allowed.get(key) is False]
        if yes:
            pet_parts.append(f"Allowed: {', '.join(yes)}.")
        if no:
            pet_parts.append(f"Not allowed: {', '.join(no)}.")
    if pets.get("notes"):
        pet_parts.append(str(pets["notes"]).strip())
    site.add_fact("pet_policy", "Pet policy", " ".join(pet_parts), ["pets"], {"pets": pets})

    terms = (data.get("leasing") or {}).get("terms") or {}
    lengths = []
    for term in terms.get("leaseLengths") or []:
        if not isinstance(term, dict) or not term.get("isAvailable"):
            continue
        label = str(term.get("leaseLength"))
        if term.get("lengthUnit"):
            label += f" {term['lengthUnit']}"
        if as_int(term.get("upchargeAmount")):
            label += f" (upcharge ${as_int(term['upchargeAmount']):,})"
        lengths.append(label)
    if lengths:
        content = f"Lease terms offered: {'; '.join(lengths)}"
        site.add_fact("lease_terms", "Lease terms offered", content, ["lease"], {"lease_lengths": terms.get("leaseLengths")})


def parse_community(doc: dict[str, Any]) -> KnockCommunity | None:
    prop = doc.get("property") or {}
    data = prop.get("data") or {}
    property_id = as_int(prop.get("id")) or as_int(data.get("property_id"))
    if not property_id:
        return None
    location = data.get("location") or {}
    address = location.get("address") or {}
    coordinates = (location.get("geo") or {}).get("coordinates") or []
    site = ParsedSite(
        platform=KNOCK,
        platform_property_id=str(property_id),
        name=location.get("name") or None,
        address=SiteAddress(
            street_address=address.get("street") or None,
            city=address.get("city") or None,
            state=address.get("state") or None,
            zip=address.get("zip") or None,
            lat=as_float(coordinates[1]) if len(coordinates) == 2 else None,
            lon=as_float(coordinates[0]) if len(coordinates) == 2 else None,
        ),
        fees=_fees(data),
    )
    _add_facts(site, data)
    special = str(((data.get("leasing") or {}).get("terms") or {}).get("leasingSpecial") or "").strip()
    if special:
        site.promotions.append(special)

    doorway = data.get("doorway") or {}
    pricing_hidden = bool(doorway.get("hidePricing")) or bool((prop.get("property_preferences") or {}).get("disable_pricing_availability"))
    if pricing_hidden:
        site.notes.append("The property's Knock profile hides pricing, so no prices were recorded")
    elif doorway.get("availabilityIsActive") is False:
        site.notes.append("The Knock availability panel is turned off on this site; prices come from the property's Knock unit feed")
    return KnockCommunity(property_id=property_id, site=site, pricing_hidden=pricing_hidden)


def add_units(community: KnockCommunity, doc: dict[str, Any]) -> ParsedSite:
    site = community.site
    if community.pricing_hidden:
        return site
    units_data = doc.get("units_data") or {}
    layouts = {layout.get("id"): layout for layout in units_data.get("layouts") or [] if isinstance(layout, dict)}
    unpriced = 0
    for raw in units_data.get("units") or []:
        if not isinstance(raw, dict) or raw.get("hidden") or raw.get("leased") or not raw.get("available"):
            continue
        if raw.get("type") not in (None, "residential"):
            continue
        price = money(raw.get("displayPrice")) or money(raw.get("price"))
        if price is None:
            unpriced += 1
            continue
        layout = layouts.get(raw.get("layoutId")) or {}
        beds = raw.get("bedrooms") if raw.get("bedrooms") is not None else layout.get("bedrooms")
        baths = raw.get("bathrooms") if raw.get("bathrooms") is not None else layout.get("bathrooms")
        sqft = as_int(raw.get("area")) or as_int(layout.get("area"))
        site.units.append(
            CollectedUnit(
                source_unit_key=f"unit:{raw.get('id')}",
                kind="unit",
                label=raw.get("name"),
                floorplan_name=raw.get("layoutName") or layout.get("name"),
                beds=as_int(beds),
                baths=as_float(baths),
                sqft_min=sqft,
                sqft_max=sqft,
                base_rent_min=whole_dollars(price),
                base_rent_max=whole_dollars(price),
                available_on=iso_date(raw.get("availableOn")),
                availability="On notice" if raw.get("noticeGiven") else "Available",
                source_updated_at=parse_timestamp(raw.get("modifiedAt")),
            )
        )
    if unpriced:
        site.notes.append(f"{unpriced} available unit(s) show no published price and were not recorded")
    site.promotions = unique(site.promotions)
    return site
