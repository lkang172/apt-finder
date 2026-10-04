from collections.abc import Sequence
from datetime import datetime
from typing import Any

from aptfinder.evaluators.base import ReviewEvidence
from aptfinder.evaluators.classifier import Mention, split_sentences
from aptfinder.evaluators.lexicon import NEGATIVE, POSITIVE, THEMES_BY_NAME
from aptfinder.evaluators.recency import as_utc, is_recent, newest_first
from aptfinder.evaluators.scoring import index_reviews, plural

MIN_THEME_MENTIONS = 2
TREND_MIN_PERIOD_REVIEWS = 3
TREND_MIN_RATE_CHANGE = 0.15
MAX_TRENDS = 5
OUTLIER_RATING_GAP = 2.0
MIN_RATED_REVIEWS_FOR_OUTLIERS = 3
STRONG_ALLEGATION_THEMES = ("bed_bugs", "cockroaches", "rodents", "mold", "car_break_ins", "burglary")
OUTLIER_EXCERPT_CHARS = 160


def theme_label(theme: str) -> str:
    spec = THEMES_BY_NAME.get(theme)
    return spec.label if spec else theme.replace("_", " ").capitalize()


def _theme_reviews(indexed: dict[str, ReviewEvidence], mentions: Sequence[Mention], polarity: str) -> dict[str, list[ReviewEvidence]]:
    grouped: dict[str, dict[str, ReviewEvidence]] = {}
    for mention in mentions:
        if mention.polarity == polarity and mention.evidence_id in indexed:
            grouped.setdefault(mention.theme, {})[mention.evidence_id] = indexed[mention.evidence_id]
    return {theme: newest_first(reviews.values()) for theme, reviews in grouped.items()}


def _theme_stats(indexed: dict[str, ReviewEvidence], mentions: Sequence[Mention], polarity: str, now: datetime) -> list[dict[str, Any]]:
    stats = [
        {
            "theme": theme,
            "label": theme_label(theme),
            "count": len(reviews),
            "recent_count": sum(1 for r in reviews if is_recent(r.review_date, now)),
            "evidence_ids": [r.evidence_id for r in reviews],
        }
        for theme, reviews in _theme_reviews(indexed, mentions, polarity).items()
        if len(reviews) >= MIN_THEME_MENTIONS
    ]
    return sorted(stats, key=lambda s: (-s["count"], -s["recent_count"], s["theme"]))


def _recent_trends(indexed: dict[str, ReviewEvidence], mentions: Sequence[Mention], now: datetime) -> list[str]:
    recent_ids = {r.evidence_id for r in indexed.values() if is_recent(r.review_date, now)}
    older_ids = {r.evidence_id for r in indexed.values() if r.review_date is not None and r.evidence_id not in recent_ids}
    if len(recent_ids) < TREND_MIN_PERIOD_REVIEWS or len(older_ids) < TREND_MIN_PERIOD_REVIEWS:
        return [
            f"Not enough review history to compare periods: {len(recent_ids)} dated "
            f"{plural(len(recent_ids), 'review')} from the last 24 months and {len(older_ids)} older "
            f"(at least {TREND_MIN_PERIOD_REVIEWS} needed in each)."
        ]
    themes: dict[str, set[str]] = {}
    for mention in mentions:
        if mention.polarity in (POSITIVE, NEGATIVE) and mention.evidence_id in indexed:
            themes.setdefault(mention.theme, set()).add(mention.evidence_id)

    changes = []
    for theme, ids in themes.items():
        recent_count = len(ids & recent_ids)
        older_count = len(ids & older_ids)
        if recent_count + older_count < MIN_THEME_MENTIONS or max(recent_count, older_count) < MIN_THEME_MENTIONS:
            continue
        change = recent_count / len(recent_ids) - older_count / len(older_ids)
        if abs(change) >= TREND_MIN_RATE_CHANGE:
            changes.append((theme, change, recent_count, older_count))
    if not changes:
        return ["No notable change in review themes between the last 24 months and older reviews."]
    changes.sort(key=lambda c: (-abs(c[1]), c[0]))
    return [
        f"{theme_label(theme)}: mentioned in {recent_count} of {len(recent_ids)} reviews from the last 24 months vs. "
        f"{older_count} of {len(older_ids)} older reviews ({'more' if change > 0 else 'less'} frequent recently)."
        for theme, change, recent_count, older_count in changes[:MAX_TRENDS]
    ]


def _shorten(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= OUTLIER_EXCERPT_CHARS:
        return collapsed
    return collapsed[:OUTLIER_EXCERPT_CHARS].rsplit(" ", 1)[0] + "…"


def _date_label(review: ReviewEvidence) -> str:
    return as_utc(review.review_date).date().isoformat() if review.review_date else "undated"


def _outliers(indexed: dict[str, ReviewEvidence], mentions: Sequence[Mention]) -> list[dict[str, str]]:
    outliers: list[dict[str, str]] = []
    negative = _theme_reviews(indexed, mentions, NEGATIVE)
    for theme in STRONG_ALLEGATION_THEMES:
        reviews = negative.get(theme, [])
        if len(reviews) != 1:
            continue
        review = reviews[0]
        excerpt = next((m.excerpt for m in mentions if m.theme == theme and m.evidence_id == review.evidence_id), "")
        outliers.append({
            "text": f"Single uncorroborated report of {theme_label(theme).lower()} ({_date_label(review)}): “{_shorten(excerpt)}”",
            "evidence_id": review.evidence_id,
        })

    rated = [r for r in newest_first(indexed.values()) if r.rating is not None]
    if len(rated) >= MIN_RATED_REVIEWS_FOR_OUTLIERS:
        mean = sum(r.rating for r in rated) / len(rated)
        for review in rated:
            if abs(review.rating - mean) < OUTLIER_RATING_GAP:
                continue
            first_sentence = next(iter(split_sentences(review.text)), "")
            quote = f": “{_shorten(first_sentence)}”" if first_sentence else ""
            outliers.append({
                "text": (
                    f"Rated {review.rating:g}/5 versus a {mean:.1f}/5 average across {len(rated)} rated reviews "
                    f"({_date_label(review)}){quote}"
                ),
                "evidence_id": review.evidence_id,
            })
    return outliers


def build_review_intelligence(reviews: Sequence[ReviewEvidence], mentions: Sequence[Mention], now: datetime) -> dict[str, Any]:
    indexed = index_reviews(reviews)
    return {
        "praised": _theme_stats(indexed, mentions, POSITIVE, now),
        "criticized": _theme_stats(indexed, mentions, NEGATIVE, now),
        "recent_trends": _recent_trends(indexed, mentions, now),
        "outliers": _outliers(indexed, mentions),
    }
