import json
import re
from typing import Any

from aptfinder.collectors.official.common import (
    SIGHTMAP,
    ParsedSite,
    address_from_json_ld,
    format_money,
    iso_date,
    json_ld_apartment_complex,
    money,
    parse_lease_months,
    required_fees,
    unique,
    whole_dollars,
)
from aptfinder.collectors.page_data import as_float, as_int
from aptfinder.collectors.types import CollectedUnit
from aptfinder.normalize import ParsedFee, classify_fee_type

EMBED_URL = re.compile(r"https?://sightmap\.com/embed/(?!api\.js)([a-z0-9]{8,})")
G5_SIGHTMAP_ID = re.compile(r'"sightmapID"\s*:\s*"([a-z0-9]{8,})"')
DATA_URL = re.compile(r"https://sightmap\.com/app/api/v1/[a-z0-9]+/sightmaps/\d+")
FREQUENCY_TEXT = {"month": "per month", "year": "per year", "one time": "one-time"}


def find_embed_url(html: str) -> str | None:
    match = EMBED_URL.search(html) or G5_SIGHTMAP_ID.search(html)
    return f"https://sightmap.com/embed/{match.group(1)}" if match else None


def data_urls(embed_html: str) -> list[str]:
    marker = embed_html.find("__APP_CONFIG__")
    if marker == -1:
        return []
    config, _ = json.JSONDecoder().raw_decode(embed_html, embed_html.index("{", marker))
    hrefs = [str(s.get("href") or "") for s in config.get("sightmaps") or [] if isinstance(s, dict)]
    return [href for href in hrefs if DATA_URL.fullmatch(href)]


def _plan_name(plan: dict[str, Any]) -> str | None:
    name = plan.get("name")
    # Some feeds store the PMS record as a JSON string in "name"; "filter_label" is what the map displays then.
    if isinstance(name, str) and name.lstrip().startswith("{"):
        try:
            inner = json.loads(name)
        except json.JSONDecodeError:
            inner = {}
        return plan.get("filter_label") or (inner.get("name") if isinstance(inner, dict) else None)
    return name or plan.get("filter_label")


def _expense_definitions(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    expenses = data.get("expenses") or {}
    items = expenses.values() if isinstance(expenses, dict) else expenses
    return {str(e.get("id")): e for e in items if isinstance(e, dict)}


def _fees(data: dict[str, Any], raw_units: list[dict[str, Any]]) -> list[ParsedFee]:
    if data.get("expense_display_option") in (None, "no_expense_display"):
        return []
    definitions = _expense_definitions(data)
    shown: dict[str, set[str]] = {}
    for raw in raw_units:
        for expense_id, amount in (raw.get("static_expense_amounts") or {}).items():
            if isinstance(amount, dict) and amount.get("display_amount"):
                shown.setdefault(str(expense_id), set()).add(str(amount["display_amount"]))
    fees = []
    for expense_id, amounts in shown.items():
        definition = definitions.get(expense_id)
        if not definition or not definition.get("label") or definition.get("is_enabled") is False:
            continue
        label = str(definition["label"]).strip()
        frequency = definition.get("frequency")
        amount_text = next(iter(amounts)) if len(amounts) == 1 else f"varies by unit ({', '.join(sorted(amounts))})"
        is_pet = definition.get("category") == "pets"
        required = bool(definition.get("is_required")) and not is_pet
        parts = [f"{label}: {amount_text} {FREQUENCY_TEXT.get(frequency, str(frequency or '')).strip()}".strip()]
        if is_pet:
            parts.append("only if you have a pet")
        else:
            parts.append("required" if required else "optional")
        if definition.get("disclaimer"):
            parts.append(str(definition["disclaimer"]).strip())
        if "deposit" in label.lower():
            fee_type = "deposit"
        elif frequency == "one time":
            fee_type = "one_time"
        else:
            fee_type = classify_fee_type(label)
        fees.append(
            ParsedFee(
                fee_type=fee_type,
                description="; ".join(parts),
                amount=whole_dollars(money(amount_text)) if len(amounts) == 1 else None,
                amount_text=amount_text,
                recurring=True if frequency == "month" else False if frequency == "one time" else None,
                mandatory=required,
            )
        )
    return fees


def _total_composition(data: dict[str, Any], raw_units: list[dict[str, Any]]) -> str | None:
    definitions = _expense_definitions(data)
    for raw in raw_units:
        extra = raw.get("total_additional_expenses")
        low_extra = extra[0] if isinstance(extra, list) and extra else None
        if not isinstance(low_extra, int | float) or low_extra <= 0:
            continue
        parts, low_sum = [], 0.0
        for expense_id, amount in (raw.get("static_expense_amounts") or {}).items():
            definition = definitions.get(str(expense_id)) or {}
            minimum = as_float((amount or {}).get("min_amount"))
            if definition.get("frequency") != "month" or not definition.get("is_required") or not minimum:
                continue
            low_sum += minimum
            note = "; applies only to residents with pets" if definition.get("category") == "pets" else ""
            parts.append(f"{definition.get('label')} ({amount.get('display_amount')}{note})")
        # Only explain the published difference when the itemized minimums reproduce it exactly.
        if parts and abs(low_sum - low_extra) < 0.01:
            return (
                "The published total monthly price adds these required monthly charges to base rent, "
                f"at their minimum amounts: {'; '.join(parts)}."
            )
        return None
    return None


def parse_sightmap(doc: dict[str, Any], embed_html: str) -> ParsedSite | None:
    data = doc.get("data")
    if not isinstance(data, dict) or not data.get("id"):
        return None
    complex_node = json_ld_apartment_complex(embed_html)
    site = ParsedSite(
        platform=SIGHTMAP,
        platform_property_id=str(data["id"]),
        name=(data.get("asset") or {}).get("name") or (complex_node or {}).get("name"),
        address=address_from_json_ld(complex_node),
    )
    raw_units = [u for u in data.get("units") or [] if isinstance(u, dict)]
    if data.get("show_pricing") is False:
        site.notes.append("The SightMap embed hides pricing, so no prices were recorded")
        return site

    plans = {str(p.get("id")): p for p in data.get("floor_plans") or [] if isinstance(p, dict)}
    display_option = str(data.get("pricing_display_option") or "")
    shows_total = "total" in display_option
    if shows_total and "base" not in display_option:
        site.notes.append("The SightMap embed displays only total monthly prices; base rents come from the same data feed")
    range_lines = []
    unpriced = 0
    for raw in raw_units:
        base = money(raw.get("price"))
        totals = raw.get("total_price") if isinstance(raw.get("total_price"), list) else [raw.get("total_price")]
        total = money(totals[0]) if shows_total and totals else None
        if base is None and total is None:
            unpriced += 1
            continue
        plan = plans.get(str(raw.get("floor_plan_id"))) or {}
        floorplan = _plan_name(plan)
        if (raw.get("affordable_housing_info") or {}).get("is_affordable_housing_unit"):
            floorplan = f"{floorplan} (affordable housing unit)" if floorplan else "Affordable housing unit"
        sqft = as_int(raw.get("area"))
        label = raw.get("unit_number") or raw.get("label")
        site.units.append(
            CollectedUnit(
                source_unit_key=f"unit:{raw.get('id')}",
                kind="unit",
                label=label,
                floorplan_name=floorplan,
                beds=as_int(plan.get("bedroom_count")),
                baths=as_float(plan.get("bathroom_count")),
                sqft_min=sqft,
                sqft_max=sqft,
                base_rent_min=whole_dollars(base),
                base_rent_max=whole_dollars(base),
                total_monthly=total,
                required_fees_monthly=required_fees(base, total),
                lease_term_months=parse_lease_months(raw.get("display_lease_term")),
                available_on=iso_date(raw.get("available_on")),
                availability=raw.get("display_available_on"),
            )
        )
        high = money(totals[-1]) if shows_total and totals else None
        if total is not None and high is not None and high != total:
            range_lines.append(f"Unit {label}: {format_money(total)}–{format_money(high)}")
        if raw.get("specials_description"):
            site.promotions.append(str(raw["specials_description"]).strip())
    if unpriced:
        site.notes.append(f"{unpriced} listed unit(s) show no published price and were not recorded")
    site.promotions = unique(site.promotions)
    site.fees = _fees(data, raw_units)
    if shows_total:
        composition = _total_composition(data, raw_units)
        site.add_fact("total_price_composition", "What the published total includes", composition, ["price", "fees"])

    disclaimer = (data.get("pricing_disclaimer") or {}).get("pricing_disclaimer") or {}
    site.add_fact(
        "pricing_disclosure",
        "Pricing disclosure",
        disclaimer.get("long_description") or disclaimer.get("short_description") or data.get("disclaimer"),
        ["price"],
        {"pricing_display_option": data.get("pricing_display_option"), "monthly_pricing_label": data.get("monthly_pricing_label")},
    )
    if range_lines:
        site.add_fact(
            "total_price_ranges",
            "Published total monthly price ranges",
            "The official site publishes the total monthly price as a range; the low end is recorded as the unit's total. "
            + "; ".join(range_lines),
            ["price"],
        )
    return site
