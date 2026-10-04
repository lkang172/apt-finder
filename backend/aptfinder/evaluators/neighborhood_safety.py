import math
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from aptfinder.evaluators.base import AreaSafetyEvidence, AssessmentDraft, ClaimDraft, ReviewEvidence
from aptfinder.evaluators.classifier import Mention, classify_reviews
from aptfinder.evaluators.lexicon import NEGATIVE, NEUTRAL, POSITIVE
from aptfinder.evaluators.recency import as_utc
from aptfinder.evaluators.scoring import (
    clamp,
    collect_items,
    distinct_reviews,
    group_by_theme,
    index_reviews,
    net_sentiment,
    plural,
    round_score,
    sort_claims,
    theme_claim,
)

CATEGORY = "neighborhood_safety"
# A crime rate equal to the reference scores 5.5; each doubling of the ratio costs 2.25 points, so a ratio of
# 0.5 scores 7.75, 2.0 scores 3.25, and the 1–10 bounds are reached at ratios of 4.0 and 0.25.
RATIO_BASELINE_SCORE = 5.5
RATIO_SLOPE_PER_DOUBLING = 2.25
VIOLENT_WEIGHT = 0.6
PROPERTY_WEIGHT = 0.4
MIN_RESIDENT_REPORTS = 3
MAX_RESIDENT_ADJUSTMENT = 1.0
FAVORABLE_RATIO = 0.9
UNFAVORABLE_RATIO = 1.1
OFFICIAL_DATA_CURRENT_YEARS = 3
CITY_WIDE_CONFIDENCE = "low"
INSUFFICIENT_LEAD = "Insufficient evidence to evaluate neighborhood safety."
CITY_WIDE_CAVEAT = (
    "These are city-wide rates, not neighborhood-specific: crime varies considerably within a city, especially a "
    "large one, and per-resident property crime runs higher in cities with large retail or commercial areas."
)


def crime_ratio(rate: float | None, reference: float | None) -> float | None:
    if rate is None or reference is None or reference <= 0 or rate < 0:
        return None
    return rate / reference


def ratio_score(ratio: float) -> float:
    if ratio <= 0:
        return 10.0
    return clamp(RATIO_BASELINE_SCORE - RATIO_SLOPE_PER_DOUBLING * math.log2(ratio), 1.0, 10.0)


def _ratio_polarity(ratio: float) -> str:
    if ratio < FAVORABLE_RATIO:
        return POSITIVE
    if ratio > UNFAVORABLE_RATIO:
        return NEGATIVE
    return NEUTRAL


def _official_claim(kind: str, area: AreaSafetyEvidence, rate: float, reference: float, ratio: float, weight: float, current: bool) -> ClaimDraft:
    text = (
        f"{kind} crime in {area.jurisdiction} ({area.year}, city-wide): {rate:.1f} per 1,000 residents, "
        f"{ratio:.2f}× the {area.reference_label} rate of {reference:.1f}."
    )
    return ClaimDraft(text, _ratio_polarity(ratio), f"{kind.lower()}_crime_rate", [area.evidence_id], weight, current)


def evaluate_neighborhood_safety(
    area: AreaSafetyEvidence | None,
    reviews: Sequence[ReviewEvidence],
    now: datetime,
    mentions: Sequence[Mention] | None = None,
) -> AssessmentDraft:
    indexed = index_reviews(reviews)
    if mentions is None:
        mentions = classify_reviews(indexed.values())
    items = collect_items(CATEGORY, indexed, mentions, now, {}, {})
    resident_reviews = distinct_reviews(items)
    residents_used = len(resident_reviews) >= MIN_RESIDENT_REPORTS
    resident_claims = [theme_claim(g, now) for g in group_by_theme(items)] if residents_used else []
    resident_positive = [r.evidence_id for r in distinct_reviews(i for i in items if i.polarity == POSITIVE)]
    resident_negative = [r.evidence_id for r in distinct_reviews(i for i in items if i.polarity == NEGATIVE)]
    details: dict[str, Any] = {
        "scope": "city",
        "resident_reports": len(resident_reviews),
        "resident_reports_used": residents_used,
        "resident_report_ids": [r.evidence_id for r in resident_reviews],
    }

    if area is None:
        summary = f"{INSUFFICIENT_LEAD} No official crime data was available for this location."
        if residents_used:
            summary += f" Resident reports alone ({len(resident_reviews)} reviews) are not used to score neighborhood safety."
        return _insufficient(summary, details, resident_claims, resident_positive, resident_negative, residents_used)

    violent_ratio = crime_ratio(area.violent_per_1000, area.reference_violent_per_1000)
    property_ratio = crime_ratio(area.property_per_1000, area.reference_property_per_1000)
    details.update({
        "jurisdiction": area.jurisdiction,
        "year": area.year,
        "violent_per_1000": area.violent_per_1000,
        "property_per_1000": area.property_per_1000,
        "reference_violent_per_1000": area.reference_violent_per_1000,
        "reference_property_per_1000": area.reference_property_per_1000,
        "reference_label": area.reference_label,
        "violent_ratio": None if violent_ratio is None else round(violent_ratio, 3),
        "property_ratio": None if property_ratio is None else round(property_ratio, 3),
        "source_url": area.source_url,
    })
    if violent_ratio is None and property_ratio is None:
        summary = (
            f"{INSUFFICIENT_LEAD} Official crime rates for {area.jurisdiction} ({area.year}) were incomplete, "
            "so no score was computed."
        )
        return _insufficient(summary, details, resident_claims, resident_positive, resident_negative, residents_used)

    current = as_utc(now).year - area.year <= OFFICIAL_DATA_CURRENT_YEARS
    components: list[tuple[float, float]] = []
    claims: list[ClaimDraft] = []
    rate_parts: list[str] = []
    if violent_ratio is not None:
        violent_score = ratio_score(violent_ratio)
        components.append((VIOLENT_WEIGHT, violent_score))
        details["violent_component"] = round(violent_score, 2)
        claims.append(_official_claim("Violent", area, area.violent_per_1000, area.reference_violent_per_1000, violent_ratio, VIOLENT_WEIGHT, current))
        rate_parts.append(
            f"violent crime {area.violent_per_1000:.1f} per 1,000 residents ({violent_ratio:.2f}× the "
            f"{area.reference_label} rate of {area.reference_violent_per_1000:.1f})"
        )
    if property_ratio is not None:
        property_score = ratio_score(property_ratio)
        components.append((PROPERTY_WEIGHT, property_score))
        details["property_component"] = round(property_score, 2)
        claims.append(_official_claim("Property", area, area.property_per_1000, area.reference_property_per_1000, property_ratio, PROPERTY_WEIGHT, current))
        rate_parts.append(
            f"property crime {area.property_per_1000:.1f} per 1,000 residents ({property_ratio:.2f}× the "
            f"{area.reference_label} rate of {area.reference_property_per_1000:.1f})"
        )

    official = sum(w * s for w, s in components) / sum(w for w, _ in components)
    adjustment = round(MAX_RESIDENT_ADJUSTMENT * net_sentiment(items), 2) if residents_used else 0.0
    details["official_score"] = round_score(official)
    details["resident_adjustment"] = adjustment

    sentences = [f"Official city-wide {area.year} data for {area.jurisdiction}: {'; '.join(rate_parts)}."]
    if violent_ratio is None:
        sentences.append("Only the property crime rate was available; violent crime was not scored.")
    elif property_ratio is None:
        sentences.append("Only the violent crime rate was available; property crime was not scored.")
    sentences.append(CITY_WIDE_CAVEAT)
    sentences.append("Confidence is low because the data is not specific to this neighborhood.")
    if not current:
        sentences.append(f"The data is from {area.year} and may not reflect current conditions.")
    resident_note = _resident_note(len(resident_reviews), residents_used, len(resident_positive), len(resident_negative), adjustment)
    if resident_note:
        sentences.append(resident_note)

    official_polarities = {c.polarity for c in claims}
    positive_ids = ([area.evidence_id] if POSITIVE in official_polarities else []) + (resident_positive if residents_used else [])
    negative_ids = ([area.evidence_id] if NEGATIVE in official_polarities else []) + (resident_negative if residents_used else [])
    return AssessmentDraft(
        CATEGORY,
        round_score(clamp(official + adjustment, 1.0, 10.0)),
        CITY_WIDE_CONFIDENCE,
        1 + (len(resident_reviews) if residents_used else 0),
        " ".join(sentences),
        details,
        positive_ids,
        negative_ids,
        sort_claims([*claims, *resident_claims]),
    )


def _resident_note(count: int, used: bool, positive: int, negative: int, adjustment: float) -> str | None:
    if count == 0:
        return None
    if not used:
        return (
            f"{count} resident {plural(count, 'report')} on area safety {'is' if count == 1 else 'are'} too few to "
            "adjust the score."
        )
    return (
        f"{count} resident reports ({negative} negative, {positive} positive) adjust the score by "
        f"{adjustment:+.1f} (at most ±{MAX_RESIDENT_ADJUSTMENT:g})."
    )


def _insufficient(
    summary: str,
    details: dict[str, Any],
    resident_claims: list[ClaimDraft],
    positive: list[str],
    negative: list[str],
    residents_used: bool,
) -> AssessmentDraft:
    draft = AssessmentDraft.insufficient(CATEGORY, summary, 0, **details)
    if residents_used:
        draft.claims = sort_claims(resident_claims)
        draft.positive_evidence_ids = positive
        draft.negative_evidence_ids = negative
        draft.evidence_count = len(details["resident_report_ids"])
    return draft
