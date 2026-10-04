from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aptfinder.evaluators.base import AssessmentDraft, ClaimDraft, ReviewEvidence
from aptfinder.evaluators.classifier import Mention
from aptfinder.evaluators.lexicon import NEGATIVE, THEMES_BY_NAME
from aptfinder.evaluators.recency import as_utc, is_recent, newest_first, recency_note, recency_weight
from aptfinder.evaluators.scoring import clamp, conjugate, index_reviews, join_list, plural, round_score, sort_claims

CATEGORY = "other_issues"
MIN_TEXT_REVIEWS = 5
RECURRING_CURRENT_PENALTY = 1.5
RECURRING_OLD_PENALTY = 0.75
HIGH_CONFIDENCE_REVIEWS = 15
MEDIUM_CONFIDENCE_REVIEWS = 8

RECURRING_CURRENT = "recurring_current"
RECURRING_OLD = "recurring_old"
ISOLATED = "isolated"
STATUS_LABELS = {
    RECURRING_CURRENT: "recurring current issue",
    RECURRING_OLD: "recurring but old issue",
    ISOLATED: "isolated anecdote",
}
INSUFFICIENT_LEAD = "Insufficient evidence to evaluate other recurring issues."


@dataclass(frozen=True)
class IssuePattern:
    theme: str
    status: str
    reviews: list[ReviewEvidence]
    mentions: list[Mention]

    @property
    def count(self) -> int:
        return len(self.reviews)


def issue_status(reviews: Sequence[ReviewEvidence], now: datetime) -> str:
    if len(reviews) < 2:
        return ISOLATED
    return RECURRING_CURRENT if any(is_recent(r.review_date, now) for r in reviews) else RECURRING_OLD


def _patterns(indexed: dict[str, ReviewEvidence], mentions: Sequence[Mention], now: datetime) -> list[IssuePattern]:
    issue_mentions = [m for m in mentions if m.category == CATEGORY and m.polarity == NEGATIVE and m.evidence_id in indexed]
    patterns = []
    for theme in sorted({m.theme for m in issue_mentions}):
        theme_mentions = [m for m in issue_mentions if m.theme == theme]
        theme_reviews = newest_first({m.evidence_id: indexed[m.evidence_id] for m in theme_mentions}.values())
        patterns.append(IssuePattern(theme, issue_status(theme_reviews, now), theme_reviews, theme_mentions))
    order = {RECURRING_CURRENT: 0, RECURRING_OLD: 1, ISOLATED: 2}
    return sorted(patterns, key=lambda p: (order[p.status], -p.count, p.theme))


def _claim(pattern: IssuePattern, now: datetime) -> ClaimDraft:
    spec = THEMES_BY_NAME[pattern.theme]
    note, current = recency_note([r.review_date for r in pattern.reviews], now)
    text = (
        f"{pattern.count} {plural(pattern.count, 'review')} {conjugate(spec.phrase, pattern.count)} — "
        f"{STATUS_LABELS[pattern.status]} ({note})."
    )
    weight = sum(recency_weight(r.review_date, now) for r in pattern.reviews)
    return ClaimDraft(text, NEGATIVE, pattern.theme, [r.evidence_id for r in pattern.reviews], round(weight, 3), current)


def _anecdote(pattern: IssuePattern) -> dict[str, Any]:
    review = pattern.reviews[0]
    return {
        "theme": pattern.theme,
        "label": THEMES_BY_NAME[pattern.theme].label,
        "evidence_id": review.evidence_id,
        "excerpt": pattern.mentions[0].excerpt,
        "review_date": as_utc(review.review_date).date().isoformat() if review.review_date else None,
    }


def _describe(patterns: Sequence[IssuePattern]) -> str:
    return "; ".join(f"{THEMES_BY_NAME[p.theme].label.lower()}, {p.count} reviews" for p in patterns)


def _summary(text_reviews: int, current: list[IssuePattern], old: list[IssuePattern], isolated: list[IssuePattern]) -> str:
    parts = []
    if current:
        parts.append(f"{len(current)} recurring current {plural(len(current), 'issue')} ({_describe(current)})")
    if old:
        parts.append(f"{len(old)} recurring but older {plural(len(old), 'issue')} ({_describe(old)})")
    if parts:
        sentences = [f"Across {text_reviews} reviews with text, reviewers describe {join_list(parts)}."]
    else:
        sentences = [
            f"Across {text_reviews} reviews with text, none of the issues raised recurred across multiple reviews; "
            "issues reviewers did not write about cannot be ruled out."
        ]
    if isolated:
        count = len(isolated)
        sentences.append(
            f"{count} isolated {plural(count, 'complaint')} {'is' if count == 1 else 'are'} listed separately and "
            f"{'does' if count == 1 else 'do'} not affect the score."
        )
    if old and not current:
        sentences.append("All recurring issues come from reviews older than 2 years and may no longer apply.")
    return " ".join(sentences)


def evaluate_other_issues(reviews: Sequence[ReviewEvidence], mentions: Sequence[Mention], now: datetime) -> AssessmentDraft:
    indexed = index_reviews(reviews)
    text_reviews = [r for r in indexed.values() if r.text.strip()]
    patterns = _patterns(indexed, mentions, now)
    current = [p for p in patterns if p.status == RECURRING_CURRENT]
    old = [p for p in patterns if p.status == RECURRING_OLD]
    isolated = [p for p in patterns if p.status == ISOLATED]
    claims = sort_claims(_claim(p, now) for p in current + old)
    issue_reviews = newest_first({r.evidence_id: r for p in patterns for r in p.reviews}.values())
    negative_ids = [r.evidence_id for r in issue_reviews]

    details: dict[str, Any] = {
        "reviews_analyzed": len(text_reviews),
        "reviews_with_issue_mentions": len(negative_ids),
        "recent_relevant": sum(1 for r in issue_reviews if is_recent(r.review_date, now)),
        "theme_counts": {p.theme: p.count for p in patterns},
        "issue_patterns": {p.theme: p.status for p in patterns},
        "recurring_current": [p.theme for p in current],
        "recurring_old": [p.theme for p in old],
        "isolated_anecdotes": [_anecdote(p) for p in isolated],
        "notes": [],
    }

    if len(text_reviews) < MIN_TEXT_REVIEWS:
        if text_reviews:
            verb = "was" if len(text_reviews) == 1 else "were"
            summary = (
                f"{INSUFFICIENT_LEAD} Only {len(text_reviews)} {plural(len(text_reviews), 'review')} with text {verb} "
                f"available; at least {MIN_TEXT_REVIEWS} are needed."
            )
        else:
            summary = f"{INSUFFICIENT_LEAD} No reviews with text were available to analyze."
        draft = AssessmentDraft.insufficient(CATEGORY, summary, len(text_reviews), **details)
        draft.negative_evidence_ids = negative_ids
        draft.claims = claims
        return draft

    if not patterns:
        summary = (
            f"{INSUFFICIENT_LEAD} None of the {len(text_reviews)} reviews with text raise issues such as parking, "
            "plumbing, or appliances; the absence of complaints is not treated as evidence."
        )
        return AssessmentDraft.insufficient(CATEGORY, summary, len(text_reviews), **details)

    score = round_score(clamp(10 - RECURRING_CURRENT_PENALTY * len(current) - RECURRING_OLD_PENALTY * len(old), 1.0, 10.0))
    if len(text_reviews) >= HIGH_CONFIDENCE_REVIEWS:
        confidence = "high"
    elif len(text_reviews) >= MEDIUM_CONFIDENCE_REVIEWS:
        confidence = "medium"
    else:
        confidence = "low"
    return AssessmentDraft(
        CATEGORY, score, confidence, len(text_reviews), _summary(len(text_reviews), current, old, isolated), details,
        [], negative_ids, claims,
    )
