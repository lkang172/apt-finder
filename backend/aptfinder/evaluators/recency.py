from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from aptfinder.evaluators.base import ReviewEvidence

DAYS_PER_YEAR = 365.25
RECENT_YEARS = 2.0
RECENCY_BANDS = ((2.0, 1.0), (4.0, 0.6), (7.0, 0.3))
STALE_WEIGHT = 0.15
UNKNOWN_DATE_WEIGHT = 0.3


def as_utc(moment: datetime) -> datetime:
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def age_years(review_date: datetime | None, now: datetime) -> float | None:
    if review_date is None:
        return None
    return max(0.0, (as_utc(now) - as_utc(review_date)).total_seconds() / 86400 / DAYS_PER_YEAR)


def recency_weight(review_date: datetime | None, now: datetime) -> float:
    age = age_years(review_date, now)
    if age is None:
        return UNKNOWN_DATE_WEIGHT
    for max_age, weight in RECENCY_BANDS:
        if age <= max_age:
            return weight
    return STALE_WEIGHT


def is_recent(review_date: datetime | None, now: datetime) -> bool:
    age = age_years(review_date, now)
    return age is not None and age <= RECENT_YEARS


def newest_first(reviews: Iterable[ReviewEvidence]) -> list[ReviewEvidence]:
    return sorted(
        reviews,
        key=lambda r: (r.review_date is None, -as_utc(r.review_date).timestamp() if r.review_date else 0.0, r.evidence_id),
    )


def year_span(dates: Iterable[datetime]) -> str:
    years = sorted({as_utc(d).year for d in dates})
    return str(years[0]) if len(years) == 1 else f"{years[0]}–{years[-1]}"


def age_qualifier(dates: Sequence[datetime | None], noun: str = "mention") -> str:
    known = [d for d in dates if d is not None]
    if not known:
        return "review date unavailable" if len(dates) == 1 else "review dates unavailable"
    if len(known) < len(dates):
        return f"{noun}s from {year_span(known)} or undated"
    if len(dates) == 1:
        return f"{noun} from {year_span(known)}"
    return f"all {noun}s from {year_span(known)}"


def recency_note(dates: Sequence[datetime | None], now: datetime, noun: str = "mention") -> tuple[str, bool]:
    recent = sum(1 for d in dates if is_recent(d, now))
    if recent == 0:
        return age_qualifier(dates, noun), False
    if recent == len(dates):
        return ("from the last 2 years" if len(dates) == 1 else "all from the last 2 years"), True
    return f"{recent} from the last 2 years", True
