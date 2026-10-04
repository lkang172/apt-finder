import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from aptfinder.evaluators.base import AssessmentDraft, ClaimDraft, ReviewEvidence
from aptfinder.evaluators.classifier import Mention
from aptfinder.evaluators.lexicon import NEGATIVE, NEUTRAL, POSITIVE, THEMES_BY_NAME
from aptfinder.evaluators.recency import age_years, is_recent, newest_first, recency_note, recency_weight

MIN_RELEVANT_REVIEWS = 3
SCORE_MIDPOINT = 5.5
SCORE_SPAN = 4.5
MIN_SCORE = 1.0
MAX_SCORE = 10.0

HIGH_MIN_REVIEWS = 8
HIGH_MIN_RECENT = 4
HIGH_MIN_SOURCES = 2
HIGH_SINGLE_SOURCE_MIN_REVIEWS = 12
MEDIUM_MIN_REVIEWS = 5
DOMINANT_REVIEW_SHARE = 0.5
OLD_EVIDENCE_YEARS = 4.0
OLD_EVIDENCE_SHARE = 0.7

SUBSCORE_THEME = "subscore"
SUBSCORE_CATEGORIES = {"noise": "noise", "management": "management", "maintenance": "management"}
SUBSCORE_MIN = 1.0
SUBSCORE_MAX = 5.0
SUBSCORE_MIDPOINT = 3.0
MAX_SUMMARY_THEMES = 6

CONFIDENCE_ORDER = ("insufficient", "low", "medium", "high")


@dataclass(frozen=True)
class ScoredItem:
    review: ReviewEvidence
    theme: str
    polarity: str
    value: float
    severity: float
    weight: float
    raw_subscore: float | None = None

    @property
    def evidence_id(self) -> str:
        return self.review.evidence_id

    @property
    def influence(self) -> float:
        return self.weight * self.severity


@dataclass(frozen=True)
class ReviewCategoryConfig:
    category: str
    label: str
    severity: Mapping[str, float] = field(default_factory=dict)
    insufficient_lead: str | None = None
    evidence_noun: str | None = None

    @property
    def noun(self) -> str:
        return self.evidence_noun or self.label


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def round_score(value: float) -> float:
    return math.floor(value * 10 + 0.5 + 1e-9) / 10


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    return singular if count == 1 else (plural_form or f"{singular}s")


def conjugate(phrase: str, count: int) -> str:
    if count != 1:
        return phrase
    verb, _, rest = phrase.partition(" ")
    return f"{verb}s {rest}".strip()


def join_list(parts: Sequence[str]) -> str:
    if len(parts) <= 2:
        return " and ".join(parts)
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def percent(share: float) -> str:
    return f"{round(share * 100)}%"


def index_reviews(reviews: Iterable[ReviewEvidence]) -> dict[str, ReviewEvidence]:
    indexed: dict[str, ReviewEvidence] = {}
    for review in reviews:
        indexed.setdefault(review.evidence_id, review)
    return indexed


def is_valid_subscore(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and SUBSCORE_MIN <= value <= SUBSCORE_MAX


def subscore_value(raw: float) -> float:
    return (raw - SUBSCORE_MIDPOINT) / ((SUBSCORE_MAX - SUBSCORE_MIN) / 2)


def collect_items(
    category: str,
    reviews: Mapping[str, ReviewEvidence],
    mentions: Iterable[Mention],
    now: datetime,
    severity: Mapping[str, float],
    weight_factors: Mapping[str, float],
) -> list[ScoredItem]:
    items: list[ScoredItem] = []
    seen: set[tuple[str, str]] = set()
    for mention in mentions:
        review = reviews.get(mention.evidence_id)
        if review is None or mention.category != category or mention.polarity not in (POSITIVE, NEGATIVE):
            continue
        if (mention.evidence_id, mention.theme) in seen:
            continue
        seen.add((mention.evidence_id, mention.theme))
        weight = recency_weight(review.review_date, now) * weight_factors.get(review.evidence_id, 1.0)
        value = 1.0 if mention.polarity == POSITIVE else -1.0
        items.append(ScoredItem(review, mention.theme, mention.polarity, value, severity.get(mention.theme, 1.0), weight))

    for review in reviews.values():
        raw = [float(v) for key, v in sorted(review.subscores.items()) if SUBSCORE_CATEGORIES.get(key) == category and is_valid_subscore(v)]
        if not raw:
            continue
        mean_raw = sum(raw) / len(raw)
        value = subscore_value(mean_raw)
        polarity = POSITIVE if value > 0 else NEGATIVE if value < 0 else NEUTRAL
        weight = recency_weight(review.review_date, now) * weight_factors.get(review.evidence_id, 1.0)
        items.append(ScoredItem(review, SUBSCORE_THEME, polarity, value, 1.0, weight, mean_raw))
    return items


def distinct_reviews(items: Iterable[ScoredItem]) -> list[ReviewEvidence]:
    return newest_first({item.evidence_id: item.review for item in items}.values())


def net_sentiment(items: Sequence[ScoredItem]) -> float:
    total = sum(item.influence for item in items)
    return sum(item.influence * item.value for item in items) / total if total else 0.0


def sentiment_score(net: float) -> float:
    return round_score(clamp(SCORE_MIDPOINT + SCORE_SPAN * net, MIN_SCORE, MAX_SCORE))


def dominant_review_share(items: Sequence[ScoredItem]) -> float:
    total = sum(item.influence for item in items)
    if not total:
        return 0.0
    per_review: dict[str, float] = {}
    for item in items:
        per_review[item.evidence_id] = per_review.get(item.evidence_id, 0.0) + item.influence
    return max(per_review.values()) / total


def old_evidence_share(items: Sequence[ScoredItem], now: datetime) -> float:
    if not items:
        return 0.0
    old = sum(1 for item in items if (age_years(item.review.review_date, now) or 0.0) > OLD_EVIDENCE_YEARS)
    return old / len(items)


def lower_confidence(level: str) -> str:
    return CONFIDENCE_ORDER[max(1, CONFIDENCE_ORDER.index(level) - 1)]


def evidence_confidence(items: Sequence[ScoredItem], now: datetime) -> tuple[str, list[str]]:
    reviews = distinct_reviews(items)
    count = len(reviews)
    if count < MIN_RELEVANT_REVIEWS:
        return "insufficient", []
    recent = sum(1 for r in reviews if is_recent(r.review_date, now))
    sources = {r.source_id for r in reviews}
    if count >= HIGH_MIN_REVIEWS and recent >= HIGH_MIN_RECENT and (
        len(sources) >= HIGH_MIN_SOURCES or count >= HIGH_SINGLE_SOURCE_MIN_REVIEWS
    ):
        level = "high"
    elif count >= MEDIUM_MIN_REVIEWS:
        level = "medium"
    else:
        level = "low"

    reasons = []
    share = dominant_review_share(items)
    if share > DOMINANT_REVIEW_SHARE:
        reasons.append(f"one review carries {percent(share)} of the evidence weight")
    old_share = old_evidence_share(items, now)
    if old_share > OLD_EVIDENCE_SHARE:
        reasons.append(f"{percent(old_share)} of the evidence is more than 4 years old")
    if not reasons:
        return level, []
    reason_text = join_list(reasons)
    if level == "low":
        return level, [f"Confidence stays low: {reason_text}."]
    lowered = lower_confidence(level)
    return lowered, [f"Confidence lowered from {level} to {lowered}: {reason_text}."]


@dataclass
class ThemeGroup:
    theme: str
    polarity: str
    reviews: list[ReviewEvidence]
    weight: float
    raw_subscores: list[float] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.reviews)


def group_by_theme(items: Iterable[ScoredItem]) -> list[ThemeGroup]:
    groups: dict[tuple[str, str], ThemeGroup] = {}
    for item in items:
        key = (item.theme, item.polarity)
        group = groups.setdefault(key, ThemeGroup(item.theme, item.polarity, [], 0.0))
        if all(r.evidence_id != item.evidence_id for r in group.reviews):
            group.reviews.append(item.review)
        group.weight += item.weight
        if item.raw_subscore is not None:
            group.raw_subscores.append(item.raw_subscore)
    for group in groups.values():
        group.reviews = newest_first(group.reviews)
    return sorted(groups.values(), key=lambda g: (-g.count, -g.weight, g.theme, g.polarity))


def theme_claim(group: ThemeGroup, now: datetime, annotation: str | None = None) -> ClaimDraft:
    spec = THEMES_BY_NAME[group.theme]
    note, current = recency_note([r.review_date for r in group.reviews], now)
    qualifier = f" — {annotation}" if annotation else ""
    text = f"{group.count} {plural(group.count, 'review')} {conjugate(spec.phrase, group.count)}{qualifier} ({note})."
    return ClaimDraft(text, group.polarity, group.theme, [r.evidence_id for r in group.reviews], round(group.weight, 3), current)


SUBSCORE_ADJECTIVES = {POSITIVE: "favorable", NEGATIVE: "unfavorable", NEUTRAL: "neutral"}


def subscore_claim(group: ThemeGroup, label: str, now: datetime) -> ClaimDraft:
    note, current = recency_note([r.review_date for r in group.reviews], now, noun="rating")
    average = sum(group.raw_subscores) / len(group.raw_subscores)
    adjective = SUBSCORE_ADJECTIVES[group.polarity]
    article = "an" if adjective[0] in "aeiou" else "a"
    text = (
        f"{group.count} {plural(group.count, 'review')} {conjugate('give', group.count)} {article} "
        f"{adjective} resident {label} sub-rating (average {average:.1f}/5; {note})."
    )
    return ClaimDraft(text, group.polarity, SUBSCORE_THEME, [r.evidence_id for r in group.reviews], round(group.weight, 3), current)


def sort_claims(claims: Iterable[ClaimDraft]) -> list[ClaimDraft]:
    return sorted(claims, key=lambda c: (-c.weight, c.theme or "", c.polarity, c.text))


def insufficient_summary(config: ReviewCategoryConfig, relevant: int, total: int) -> str:
    lead = config.insufficient_lead or f"Insufficient evidence to reliably evaluate {config.label}."
    if total == 0:
        return f"{lead} No reviews were available to analyze."
    if relevant == 0:
        if total == 1:
            return f"{lead} The only collected review does not discuss {config.label}."
        return f"{lead} None of the {total} collected reviews discuss {config.label}."
    verb = "discusses" if relevant == 1 else "discuss"
    return f"{lead} Only {relevant} of {total} collected {plural(total, 'review')} {verb} {config.label}."


def scored_summary(
    config: ReviewCategoryConfig,
    relevant: int,
    total: int,
    recent: int,
    groups: Sequence[ThemeGroup],
    positive_reviews: int,
    negative_reviews: int,
    notes: Sequence[str],
) -> str:
    text_groups = [g for g in groups if g.theme != SUBSCORE_THEME]
    parts = [f"{g.count} {conjugate(THEMES_BY_NAME[g.theme].phrase, g.count)}" for g in text_groups[:MAX_SUMMARY_THEMES]]
    hidden = len(text_groups) - MAX_SUMMARY_THEMES
    if hidden > 0:
        parts.append(f"{hidden} other {plural(hidden, 'theme')} {'appears' if hidden == 1 else 'appear'} less often")
    subscore_groups = [g for g in groups if g.theme == SUBSCORE_THEME]
    if subscore_groups:
        raws = [raw for g in subscore_groups for raw in g.raw_subscores]
        count = sum(g.count for g in subscore_groups)
        parts.append(f"{count} {conjugate('include', count)} a resident {config.label} sub-rating averaging {sum(raws) / len(raws):.1f}/5")
    lead = (
        f"Of {relevant} {plural(relevant, 'review')} discussing {config.label} "
        f"({recent} from the last 2 years; {total} reviews analyzed), "
    )
    sentences = [lead + join_list(parts) + "."]
    if positive_reviews and negative_reviews:
        sentences.append(
            f"Evidence is mixed: {negative_reviews} {plural(negative_reviews, 'review')} {conjugate('include', negative_reviews)} "
            f"negative and {positive_reviews} {conjugate('include', positive_reviews)} positive {config.noun} evidence."
        )
    sentences.extend(notes)
    return " ".join(sentences)


def evaluate_review_category(
    config: ReviewCategoryConfig,
    reviews: Sequence[ReviewEvidence],
    mentions: Sequence[Mention],
    now: datetime,
    *,
    weight_factors: Mapping[str, float] | None = None,
    theme_annotations: Mapping[str, str] | None = None,
    notes: Sequence[str] = (),
    extra_details: Mapping[str, Any] | None = None,
    extra_claims: Sequence[ClaimDraft] = (),
) -> AssessmentDraft:
    indexed = index_reviews(reviews)
    items = collect_items(config.category, indexed, mentions, now, config.severity, weight_factors or {})
    relevant = distinct_reviews(items)
    recent = sum(1 for r in relevant if is_recent(r.review_date, now))
    positive_ids = [r.evidence_id for r in distinct_reviews(i for i in items if i.polarity == POSITIVE)]
    negative_ids = [r.evidence_id for r in distinct_reviews(i for i in items if i.polarity == NEGATIVE)]
    groups = group_by_theme(items)
    annotations = theme_annotations or {}

    claims = [
        subscore_claim(g, config.label, now) if g.theme == SUBSCORE_THEME else theme_claim(g, now, annotations.get(g.theme))
        for g in groups
    ]
    claims = sort_claims([*claims, *extra_claims])

    details: dict[str, Any] = {
        "reviews_analyzed": len(indexed),
        "relevant_reviews": len(relevant),
        "recent_relevant": recent,
        "theme_counts": {g.theme: g.count for g in groups if g.theme != SUBSCORE_THEME},
        "sources": sorted({r.source_id for r in relevant}),
        "notes": list(notes),
    }
    subscore_raws = [item.raw_subscore for item in items if item.raw_subscore is not None]
    if subscore_raws:
        details["subscores"] = {"count": len(subscore_raws), "average": round(sum(subscore_raws) / len(subscore_raws), 2)}
    details.update(extra_details or {})

    if len(relevant) < MIN_RELEVANT_REVIEWS:
        draft = AssessmentDraft.insufficient(
            config.category, insufficient_summary(config, len(relevant), len(indexed)), len(relevant), **details
        )
        draft.positive_evidence_ids = positive_ids
        draft.negative_evidence_ids = negative_ids
        draft.claims = claims
        return draft

    net = net_sentiment(items)
    confidence, confidence_notes = evidence_confidence(items, now)
    details["net_sentiment"] = round(net, 3)
    details["dominant_review_share"] = round(dominant_review_share(items), 3)
    details["old_evidence_share"] = round(old_evidence_share(items, now), 3)
    details["notes"] = [*details["notes"], *confidence_notes]
    summary = scored_summary(
        config, len(relevant), len(indexed), recent, groups, len(positive_ids), len(negative_ids), details["notes"]
    )
    return AssessmentDraft(
        config.category, sentiment_score(net), confidence, len(relevant), summary, details, positive_ids, negative_ids, claims
    )
