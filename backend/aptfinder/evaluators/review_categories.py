from collections.abc import Sequence
from datetime import datetime
from typing import Any

from aptfinder.evaluators.base import AssessmentDraft, ClaimDraft, ReviewEvidence
from aptfinder.evaluators.classifier import Mention
from aptfinder.evaluators.lexicon import NEGATIVE, NEUTRAL, THEMES_BY_NAME
from aptfinder.evaluators.recency import as_utc, newest_first, recency_note, recency_weight
from aptfinder.evaluators.scoring import (
    ReviewCategoryConfig,
    collect_items,
    evaluate_review_category,
    index_reviews,
    plural,
)

PEST_SEVERITY = {"bed_bugs": 2.0, "cockroaches": 1.8, "rodents": 1.6, "termites": 1.3}
BUILDING_SAFETY_SEVERITY = {"package_theft": 1.3, "car_break_ins": 1.3, "burglary": 1.3}
PREVIOUS_MANAGEMENT_WEIGHT = 0.5
PEST_RECURRENCE_WINDOW_DAYS = 730
RECURRING_PATTERN = "recurring property-level pattern"
ISOLATED_INCIDENT = "isolated incident"

NOISE = ReviewCategoryConfig("noise", "noise")
MANAGEMENT = ReviewCategoryConfig("management", "management")
PESTS = ReviewCategoryConfig("pests", "pests", PEST_SEVERITY, "Pests: N/A — insufficient evidence.", "pest")
BUILDING_SAFETY = ReviewCategoryConfig("building_safety", "building safety", BUILDING_SAFETY_SEVERITY)


def evaluate_noise(reviews: Sequence[ReviewEvidence], mentions: Sequence[Mention], now: datetime) -> AssessmentDraft:
    return evaluate_review_category(NOISE, reviews, mentions, now)


def evaluate_building_safety(reviews: Sequence[ReviewEvidence], mentions: Sequence[Mention], now: datetime) -> AssessmentDraft:
    return evaluate_review_category(BUILDING_SAFETY, reviews, mentions, now)


def evaluate_management(reviews: Sequence[ReviewEvidence], mentions: Sequence[Mention], now: datetime) -> AssessmentDraft:
    indexed = index_reviews(reviews)
    change_reviews = newest_first(
        {m.evidence_id: indexed[m.evidence_id] for m in mentions
         if m.theme == "management_change" and m.evidence_id in indexed}.values()
    )
    if not change_reviews:
        return evaluate_review_category(MANAGEMENT, reviews, mentions, now, extra_details={"management_change": {"detected": False}})

    dated = [as_utc(r.review_date) for r in change_reviews if r.review_date is not None]
    earliest = min(dated) if dated else None
    weight_factors = {
        r.evidence_id: PREVIOUS_MANAGEMENT_WEIGHT
        for r in indexed.values()
        if earliest is not None and r.review_date is not None and as_utc(r.review_date) < earliest
    }
    relevant_ids = {item.evidence_id for item in collect_items("management", indexed, mentions, now, {}, {})}
    relevant_before = relevant_ids & set(weight_factors)
    count = len(change_reviews)
    lead = f"{count} {plural(count, 'review')} {'mentions' if count == 1 else 'mention'} a management change"
    if earliest is None:
        note = f"{lead} (undated), so it is unclear which reviews concern previous management."
    elif relevant_before:
        before = len(relevant_before)
        note = (
            f"{lead} (earliest dated {earliest:%Y-%m-%d}); {before} management {plural(before, 'review')} "
            f"{'predates' if before == 1 else 'predate'} it and may concern previous management, so "
            f"{'it is' if before == 1 else 'they are'} weighted at half."
        )
    else:
        note = f"{lead} (earliest dated {earliest:%Y-%m-%d}); no management reviews predate it."

    change_note, change_current = recency_note([r.review_date for r in change_reviews], now)
    change_claim = ClaimDraft(
        f"{lead}{f', earliest dated {earliest:%Y-%m-%d}' if earliest else ''} ({change_note}).",
        NEUTRAL, "management_change", [r.evidence_id for r in change_reviews],
        round(sum(recency_weight(r.review_date, now) for r in change_reviews), 3), change_current,
    )
    details: dict[str, Any] = {
        "management_change": {
            "detected": True,
            "mention_count": count,
            "earliest_mention": earliest.date().isoformat() if earliest else None,
            "evidence_ids": [r.evidence_id for r in change_reviews],
            "reviews_before_change": len(relevant_before),
            "previous_management_weight": PREVIOUS_MANAGEMENT_WEIGHT,
        },
    }
    return evaluate_review_category(
        MANAGEMENT, reviews, mentions, now,
        weight_factors=weight_factors, notes=[note], extra_details=details, extra_claims=[change_claim],
    )


def pest_pattern(reviews: Sequence[ReviewEvidence], mentions: Sequence[Mention]) -> tuple[str, str]:
    if any(m.recurring for m in mentions):
        return RECURRING_PATTERN, "a resident describes it as recurring"
    if len(reviews) < 2:
        return ISOLATED_INCIDENT, "a single report"
    dated = sorted(as_utc(r.review_date) for r in reviews if r.review_date is not None)
    if any((later - earlier).days <= PEST_RECURRENCE_WINDOW_DAYS for earlier, later in zip(dated, dated[1:])):
        return RECURRING_PATTERN, f"{len(reviews)} reports, at least 2 within 24 months"
    if len(dated) < len(reviews):
        return RECURRING_PATTERN, f"{len(reviews)} independent reports; timing unverified because some reviews are undated"
    return ISOLATED_INCIDENT, f"{len(reviews)} reports more than 24 months apart"


def evaluate_pests(reviews: Sequence[ReviewEvidence], mentions: Sequence[Mention], now: datetime) -> AssessmentDraft:
    indexed = index_reviews(reviews)
    pest_mentions = [m for m in mentions if m.category == "pests" and m.polarity == NEGATIVE and m.evidence_id in indexed]
    patterns: dict[str, dict[str, Any]] = {}
    for theme in sorted({m.theme for m in pest_mentions}):
        theme_mentions = [m for m in pest_mentions if m.theme == theme]
        theme_reviews = newest_first({m.evidence_id: indexed[m.evidence_id] for m in theme_mentions}.values())
        label, basis = pest_pattern(theme_reviews, theme_mentions)
        patterns[theme] = {"label": label, "reviews": len(theme_reviews), "basis": basis}

    ordered = sorted(patterns.items(), key=lambda kv: (kv[1]["label"] != RECURRING_PATTERN, -kv[1]["reviews"], kv[0]))
    notes = [f"{THEMES_BY_NAME[theme].label}: {info['label']} ({info['basis']})." for theme, info in ordered]
    return evaluate_review_category(
        PESTS, reviews, mentions, now,
        theme_annotations={theme: info["label"] for theme, info in patterns.items()},
        notes=notes,
        extra_details={"pest_patterns": patterns},
    )
