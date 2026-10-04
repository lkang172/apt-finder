import json
import re
from typing import Any, NamedTuple

from aptfinder.collectors.official.common import (
    JONAH,
    ParsedSite,
    address_from_json_ld,
    epoch_date,
    format_money,
    json_ld_apartment_complex,
    money,
    parse_beds,
    required_fees,
    site_host,
    unique,
    visible_text,
    whole_dollars,
)
from aptfinder.collectors.page_data import as_float, as_int
from aptfinder.collectors.types import CollectedUnit
from aptfinder.normalize import ParsedFee

DATA_SCRIPT = re.compile(r'<script[^>]*id="jd-fp-data-script-app"[^>]*>(.*?)</script>', re.S)
GENERATOR = re.compile(r'<meta[^>]+name="generator"[^>]+content="Jonah Systems', re.I)
DISCLAIMER = re.compile(r'<p[^>]*class="[^"]*jd-fp__disclaimer-text[^"]*"[^>]*>(.*?)</p>', re.S)
# Itemized lines that are one-time charges; "Est. Move-in Costs" is skipped because it includes the first month's rent.
ONE_TIME_ITEMS = ("Est. Application Costs", "Est. Move-out Costs")


def has_floorplan_data(html: str) -> bool:
    return 'id="jd-fp-data-script-app"' in html


def is_jonah_site(html: str) -> bool:
    return has_floorplan_data(html) or bool(GENERATOR.search(html))


class Quote(NamedTuple):
    base_low: float | None
    base_high: float | None
    total_low: float | None
    total_high: float | None

    @property
    def priced(self) -> bool:
        return self.base_low is not None or self.total_low is not None


def _quote(entity: dict[str, Any]) -> Quote:
    adjusted = entity.get("adjusted") if isinstance(entity.get("adjusted"), dict) else {}
    low, high = money(entity.get("priceLow")), money(entity.get("priceHigh"))
    # With pricingReflectFees the headline price is the all-in total and base rent sits in the "no_fees" fields.
    if entity.get("pricingReflectFees"):
        base_low = money(adjusted.get("low_no_fees"))
        return Quote(base_low, money(adjusted.get("high_no_fees")) or base_low, low, high or low)
    return Quote(low, high or low, None, None)


def _special_texts(specials: Any) -> list[str]:
    texts = []
    for special in specials or []:
        if isinstance(special, str):
            texts.append(visible_text(special))
        elif isinstance(special, dict):
            parts = [visible_text(str(special.get(k) or "")) for k in ("title", "description", "content")]
            texts.append(" ".join(unique(parts)))
    return unique(texts)


def _unit(raw: dict[str, Any]) -> tuple[CollectedUnit | None, float | None]:
    entity = raw.get("price_entity") or {}
    quote = _quote(entity)
    if not quote.priced:
        return None, None
    sqft = as_int(raw.get("square_feet"))
    unit = CollectedUnit(
        source_unit_key=f"unit:{raw.get('id_value') or raw.get('id')}",
        kind="unit",
        label=raw.get("apartment_number"),
        floorplan_name=raw.get("floorplan_title"),
        beds=parse_beds(raw.get("bedrooms")),
        baths=as_float(raw.get("bathrooms")),
        sqft_min=sqft,
        sqft_max=sqft,
        base_rent_min=whole_dollars(quote.base_low),
        base_rent_max=whole_dollars(quote.base_high),
        total_monthly=quote.total_low,
        required_fees_monthly=required_fees(quote.base_low, quote.total_low),
        lease_term_months=as_int(entity.get("term")),
        available_on=epoch_date(raw.get("available_date")),
        availability=raw.get("available_display"),
    )
    return unit, quote.total_high


def _floorplan(raw: dict[str, Any]) -> CollectedUnit | None:
    entity = raw.get("price_entity") or {}
    quote = _quote(entity)
    if not quote.priced:
        return None
    return CollectedUnit(
        source_unit_key=f"plan:{raw.get('id')}",
        kind="floorplan",
        label=None,
        floorplan_name=raw.get("title"),
        beds=parse_beds(raw.get("bedrooms")),
        baths=as_float(raw.get("bathrooms")),
        sqft_min=as_int(raw.get("square_feet")),
        sqft_max=as_int(raw.get("max_square_feet")) or as_int(raw.get("square_feet")),
        base_rent_min=whole_dollars(quote.base_low),
        base_rent_max=whole_dollars(quote.base_high),
        total_monthly=quote.total_low,
        required_fees_monthly=required_fees(quote.base_low, quote.total_low),
        lease_term_months=as_int(entity.get("term")),
        available_on=epoch_date(raw.get("available_date_min")),
    )


def _one_time_fees(units: list[dict[str, Any]]) -> list[ParsedFee]:
    values: dict[str, set[str]] = {}
    tooltips: dict[str, str] = {}
    for raw in units:
        itemized = (raw.get("price_entity") or {}).get("itemized")
        items = itemized.get("items") if isinstance(itemized, dict) else None
        for item in items or []:
            label = item.get("label")
            if label in ONE_TIME_ITEMS and item.get("value"):
                values.setdefault(label, set()).add(str(item["value"]))
                tooltips.setdefault(label, item.get("tooltip") or "")
    fees = []
    for label, amounts in values.items():
        amount_text = next(iter(amounts)) if len(amounts) == 1 else f"varies by unit ({', '.join(sorted(amounts))})"
        amount = money(amount_text) if len(amounts) == 1 else None
        description = f"{label}: {amount_text}" + (f". {tooltips[label]}" if tooltips[label] else "")
        fees.append(ParsedFee("one_time", description, whole_dollars(amount), amount_text, False, None))
    return fees


def parse_floorplans_page(html: str, page_url: str) -> ParsedSite | None:
    match = DATA_SCRIPT.search(html)
    if not match:
        return None
    data = json.loads(match.group(1))
    complex_node = json_ld_apartment_complex(html)
    site = ParsedSite(
        platform=JONAH,
        platform_property_id=site_host(page_url),
        name=(complex_node or {}).get("name"),
        address=address_from_json_ld(complex_node),
    )

    raw_units = [u for u in data.get("units") or [] if isinstance(u, dict)]
    range_lines, grid_lines, grid = [], [], {}
    unpriced = 0
    for raw in raw_units:
        unit, total_high = _unit(raw)
        if unit is None:
            unpriced += 1
            continue
        site.units.append(unit)
        site.promotions.extend(_special_texts(raw.get("specials")))
        if unit.total_monthly is not None and total_high is not None and total_high != unit.total_monthly:
            range_lines.append(f"Unit {unit.label}: {format_money(unit.total_monthly)}–{format_money(total_high)}")
        terms = [t for t in raw.get("lease_terms") or [] if isinstance(t, dict)]
        if terms:
            grid_lines.append(f"Unit {unit.label}: " + "; ".join(str(t.get("termOptionDisplay") or t.get("termDisplay")) for t in terms))
            grid[str(unit.label)] = {str(t.get("term")): t.get("priceLow") for t in terms}
    if not raw_units:
        site.units = [plan for plan in map(_floorplan, (f for f in data.get("floorplans") or [] if isinstance(f, dict))) if plan]
    if unpriced:
        site.notes.append(f"{unpriced} listed unit(s) show no published price and were not recorded")
    site.promotions = unique(site.promotions)
    site.fees = _one_time_fees(raw_units)

    disclaimer = DISCLAIMER.search(html)
    site.add_fact("pricing_disclosure", "Pricing disclosure", visible_text(disclaimer.group(1)) if disclaimer else None, ["price"])
    if range_lines:
        site.add_fact(
            "total_price_ranges",
            "Published total monthly price ranges",
            "The official site publishes the total monthly price as a range; the low end is recorded as the unit's total. "
            + "; ".join(range_lines),
            ["price"],
        )
    if grid_lines:
        site.add_fact("lease_term_prices", "Prices by lease term", "; ".join(grid_lines), ["price", "lease"], {"by_unit": grid})
    if complex_node:
        pets = complex_node.get("jonah:petPolicy")
        if pets or complex_node.get("petsAllowed") is not None:
            allowed = complex_node.get("petsAllowed")
            prefix = "Pets allowed." if allowed is True else "No pets allowed." if allowed is False else ""
            site.add_fact("pet_policy", "Pet policy", " ".join(p for p in (prefix, pets or "") if p), ["pets"])
    return site
