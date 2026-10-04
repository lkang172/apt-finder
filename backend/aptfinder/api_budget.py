from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from aptfinder.db.models import ApiUsage

# Google Maps Platform bills and resets free usage per calendar month in Pacific Time.
BILLING_ZONE = ZoneInfo("America/Los_Angeles")

TEXT_SEARCH_PRO = "places_text_search_pro"
PLACE_DETAILS_ENTERPRISE_ATMOSPHERE = "places_details_enterprise_atmosphere"
FREE_MONTHLY_CAPS = {
    TEXT_SEARCH_PRO: 5000,
    PLACE_DETAILS_ENTERPRISE_ATMOSPHERE: 1000,
}


class BudgetExhausted(Exception):
    pass


def billing_period(now: datetime) -> str:
    return now.astimezone(BILLING_ZONE).strftime("%Y-%m")


def effective_budget(sku: str, configured: int) -> int:
    return max(0, min(configured, FREE_MONTHLY_CAPS[sku]))


def calls_this_period(session: Session, sku: str, now: datetime) -> int:
    row = session.get(ApiUsage, (billing_period(now), sku))
    return row.count if row else 0


def reserve_call(session: Session, sku: str, configured_budget: int, now: datetime) -> int:
    """Counts the call before it is made (failed calls included) and refuses once the budget is reached."""
    budget = effective_budget(sku, configured_budget)
    period = billing_period(now)
    row = session.get(ApiUsage, (period, sku))
    if row is None:
        row = ApiUsage(period=period, sku=sku, count=0)
        session.add(row)
    if row.count >= budget:
        raise BudgetExhausted(f"{sku}: {row.count} of {budget} allowed calls already used in {period}")
    row.count += 1
    session.commit()
    return budget - row.count
