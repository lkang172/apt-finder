import re
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timedelta
from itertools import combinations
from typing import Any

from aptfinder.evaluators.base import AssessmentDraft, ClaimDraft, RatingEvidence, ReviewEvidence
from aptfinder.evaluators.classifier import Mention, classify_reviews, normalize_text
from aptfinder.evaluators.lexicon import NEGATIVE, NEUTRAL
from aptfinder.evaluators.recency import age_years, as_utc, is_recent, newest_first
from aptfinder.evaluators.scoring import index_reviews, lower_confidence, percent, plural

CATEGORY = "review_quality"
BURST_WINDOW = timedelta(days=14)
BURST_MIN_SHARE = 0.4
BURST_MIN_TOTAL = 5
BURST_MIN_REVIEWS = 3
DUPLICATE_JACCARD = 0.8
DUPLICATE_MIN_TOKENS = 5
SINGLE_SOURCE_SHARE = 0.8
RATING_CONFLICT_GAP = 1.0
HIGH_MIN_REVIEWS = 15
HIGH_MIN_RECENT = 5
HIGH_MIN_SOURCES = 2
MEDIUM_MIN_REVIEWS = 8
MEDIUM_MIN_RECENT = 2
AGE_BUCKETS = (("under_2_years", 2.0), ("2_to_4_years", 4.0), ("4_to_7_years", 7.0))
AGE_BUCKET_LABELS = {
    "under_2_years": "under 2 years",
    "2_to_4_years": "2–4 years",
    "4_to_7_years": "4–7 years",
    "over_7_years": "over 7 years",
    "unknown": "undated",
}
NO_REVIEWS_SUMMARY = "Review data: No reviews found"

_WORD = re.compile(r"[a-z0-9']+")


def age_distribution(reviews: Sequence[ReviewEvidence], now: datetime) -> dict[str, int]:
    buckets = {name: 0 for name in AGE_BUCKET_LABELS}
    for review in reviews:
        age = age_years(review.review_date, now)
        if age is None:
            buckets["unknown"] += 1
            continue
        bucket = next((name for name, limit in AGE_BUCKETS if age <= limit), "over_7_years")
        buckets[bucket] += 1
    return buckets


def find_burst(reviews: Sequence[ReviewEvidence]) -> dict[str, Any] | None:
    total = len(reviews)
    dated = sorted(((as_utc(r.review_date), r.evidence_id) for r in reviews if r.review_date is not None))
    if total < BURST_MIN_TOTAL or not dated:
        return None
    best: tuple[int, int, int] | None = None
    for start in range(len(dated)):
        end = start
        while end + 1 < len(dated) and dated[end + 1][0] - dated[start][0] <= BURST_WINDOW:
            end += 1
        if best is None or end - start + 1 > best[0]:
            best = (end - start + 1, start, end)
    count, start, end = best
    if count < BURST_MIN_REVIEWS or count / total < BURST_MIN_SHARE:
        return None
    return {
        "count": count,
        "total": total,
        "share": round(count / total, 3),
        "start": dated[start][0].date().isoformat(),
        "end": dated[end][0].date().isoformat(),
        "evidence_ids": sorted(evidence_id for _, evidence_id in dated[start:end + 1]),
    }


def _tokens(text: str) -> frozenset[str]:
    return frozenset(_WORD.findall(normalize_text(text).lower()))


def near_duplicate_pairs(reviews: Sequence[ReviewEvidence]) -> list[dict[str, Any]]:
    tokens = {r.evidence_id: _tokens(r.text) for r in reviews}
    pairs = []
    for first, second in combinations(reviews, 2):
        a, b = tokens[first.evidence_id], tokens[second.evidence_id]
        if len(a) < DUPLICATE_MIN_TOKENS or len(b) < DUPLICATE_MIN_TOKENS:
            continue
        similarity = len(a & b) / len(a | b)
        if similarity >= DUPLICATE_JACCARD:
            pairs.append({"evidence_ids": sorted([first.evidence_id, second.evidence_id]), "similarity": round(similarity, 3)})
    return sorted(pairs, key=lambda p: (-p["similarity"], p["evidence_ids"]))


def normalized_ratings(ratings: Sequence[RatingEvidence]) -> list[dict[str, Any]]:
    usable = [r for r in ratings if r.average is not None and r.count > 0 and r.scale > 0]
    return [
        {"source_id": r.source_id, "average": round(r.average * 5.0 / r.scale, 2), "count": r.count, "evidence_id": r.evidence_id or None}
        for r in sorted(usable, key=lambda r: (r.source_id, r.evidence_id))
    ]


def rating_conflict(summaries: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    if len(summaries) < 2:
        return None
    high = max(summaries, key=lambda s: (s["average"], s["source_id"]))
    low = min(summaries, key=lambda s: (s["average"], s["source_id"]))
    if high["average"] - low["average"] < RATING_CONFLICT_GAP:
        return None
    return {"high": high, "low": low, "gap": round(high["average"] - low["average"], 2)}


def management_change_summary(reviews: dict[str, ReviewEvidence], mentions: Sequence[Mention]) -> dict[str, Any]:
    change_reviews = newest_first(
        {m.evidence_id: reviews[m.evidence_id] for m in mentions if m.theme == "management_change" and m.evidence_id in reviews}.values()
    )
    dated_changes = [as_utc(r.review_date) for r in change_reviews if r.review_date is not None]
    earliest = min(dated_changes) if dated_changes else None
    dated_reviews = [r for r in reviews.values() if r.review_date is not None]
    before = sum(1 for r in dated_reviews if earliest is not None and as_utc(r.review_date) < earliest)
    return {
        "detected": bool(change_reviews),
        "mention_count": len(change_reviews),
        "earliest_mention": earliest.date().isoformat() if earliest else None,
        "evidence_ids": [r.evidence_id for r in change_reviews],
        "reviews_before_change": before,
        "dated_reviews": len(dated_reviews),
        "majority_before_change": bool(dated_reviews) and before / len(dated_reviews) > 0.5,
    }


def _base_confidence(total: int, recent: int, sources: Counter[str]) -> str:
    max_share = max(sources.values()) / total
    if total >= HIGH_MIN_REVIEWS and recent >= HIGH_MIN_RECENT and len(sources) >= HIGH_MIN_SOURCES and max_share <= SINGLE_SOURCE_SHARE:
        return "high"
    if total >= MEDIUM_MIN_REVIEWS and recent >= MEDIUM_MIN_RECENT:
        return "medium"
    return "low"


def assess_review_quality(
    reviews: Sequence[ReviewEvidence],
    ratings: Sequence[RatingEvidence],
    now: datetime,
    mentions: Sequence[Mention] | None = None,
) -> AssessmentDraft:
    indexed = index_reviews(reviews)
    review_list = newest_first(indexed.values())
    summaries = normalized_ratings(ratings)
    listed_count = sum(s["count"] for s in summaries)
    if not review_list:
        summary = NO_REVIEWS_SUMMARY
        if listed_count:
            summary += f". Rating summaries list {listed_count} {plural(listed_count, 'review')}, but no individual review text was collected."
        return AssessmentDraft.insufficient(
            CATEGORY, summary, 0, total_reviews=0, rating_summaries=summaries, rating_summary_review_count=listed_count
        )
    if mentions is None:
        mentions = classify_reviews(review_list)

    total = len(review_list)
    recent = sum(1 for r in review_list if is_recent(r.review_date, now))
    sources = Counter(r.source_id for r in review_list)
    max_source_share = max(sources.values()) / total
    burst = find_burst(review_list)
    duplicates = near_duplicate_pairs(review_list)
    change = management_change_summary(indexed, mentions)
    conflict = rating_conflict(summaries)
    distribution = age_distribution(review_list, now)

    flags: list[str] = []
    claims: list[ClaimDraft] = []
    if burst:
        flags.append(
            f"Possible burst: {burst['count']} of {total} reviews were posted within 14 days "
            f"({burst['start']} to {burst['end']})."
        )
        claims.append(ClaimDraft(flags[-1], NEGATIVE, "review_burst", burst["evidence_ids"], 1.0, True))
    if duplicates:
        duplicate_ids = sorted({i for pair in duplicates for i in pair["evidence_ids"]})
        flags.append(
            f"{len(duplicates)} {plural(len(duplicates), 'pair')} of reviews {'has' if len(duplicates) == 1 else 'have'} "
            "near-identical text."
        )
        claims.append(ClaimDraft(flags[-1], NEGATIVE, "duplicate_text", duplicate_ids, 1.0, True))
    if change["detected"]:
        if change["earliest_mention"]:
            change_text = (
                f"{change['mention_count']} {plural(change['mention_count'], 'review')} "
                f"{'mentions' if change['mention_count'] == 1 else 'mention'} a management change (earliest dated "
                f"{change['earliest_mention']}); {change['reviews_before_change']} of {change['dated_reviews']} dated "
                "reviews predate it and may describe previous management."
            )
        else:
            change_text = (
                f"{change['mention_count']} {plural(change['mention_count'], 'review')} "
                f"{'mentions' if change['mention_count'] == 1 else 'mention'} a management change of unknown date."
            )
        flags.append(change_text)
        claims.append(ClaimDraft(change_text, NEUTRAL, "management_change", change["evidence_ids"], 1.0, True))
    if conflict:
        high, low = conflict["high"], conflict["low"]
        conflict_text = (
            f"Rating summaries disagree: {high['source_id']} {high['average']:.1f}/5 ({high['count']} reviews) vs. "
            f"{low['source_id']} {low['average']:.1f}/5 ({low['count']} reviews)."
        )
        flags.append(conflict_text)
        rating_ids = [i for i in (high["evidence_id"], low["evidence_id"]) if i]
        if rating_ids:
            claims.append(ClaimDraft(conflict_text, NEGATIVE, "rating_conflict", rating_ids, 1.0, True))
    if len(sources) == 1:
        flags.append(f"All reviews come from a single source ({next(iter(sources))}).")
    elif max_source_share > SINGLE_SOURCE_SHARE:
        dominant = sources.most_common(1)[0][0]
        flags.append(f"{percent(max_source_share)} of reviews come from one source ({dominant}).")

    confidence = _base_confidence(total, recent, sources)
    reasons = []
    if burst:
        reasons.append("a suspicious burst of reviews")
    if duplicates:
        reasons.append("near-identical review text")
    if change["majority_before_change"]:
        reasons.append("most reviews predate a management change")
    for _ in reasons:
        confidence = lower_confidence(confidence)
    if recent == 0:
        confidence = "low"
        reasons.append("no reviews from the last 2 years")

    source_text = ", ".join(f"{source}: {count}" for source, count in sorted(sources.items()))
    sentences = [
        f"{total} {plural(total, 'review')} analyzed ({recent} from the last 2 years) from {len(sources)} "
        f"{plural(len(sources), 'source')} ({source_text})."
    ]
    age_parts = [f"{AGE_BUCKET_LABELS[name]}: {count}" for name, count in distribution.items() if count]
    sentences.append(f"Review age: {'; '.join(age_parts)}.")
    sentences.extend(flags)
    if not burst and not duplicates:
        sentences.append("No suspicious bursts or near-identical reviews were detected.")
    if listed_count > total:
        sentences.append(f"Rating summaries list {listed_count} {plural(listed_count, 'review')}; {total} individual {plural(total, 'review')} {'was' if total == 1 else 'were'} collected.")

    details: dict[str, Any] = {
        "total_reviews": total,
        "recent_reviews": recent,
        "age_distribution": distribution,
        "sources": dict(sorted(sources.items())),
        "source_count": len(sources),
        "max_source_share": round(max_source_share, 3),
        "single_source": len(sources) == 1,
        "rating_summaries": summaries,
        "rating_summary_review_count": listed_count,
        "ratings_conflict": conflict,
        "suspicious_burst": burst,
        "near_duplicate_pairs": duplicates,
        "management_change": change,
        "flags": flags,
        "confidence_reasons": reasons,
    }
    return AssessmentDraft(CATEGORY, None, confidence, total, " ".join(sentences), details, [], [], claims)
