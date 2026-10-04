from collections.abc import Callable, Sequence
from datetime import datetime

from aptfinder.evaluators.base import (
    CATEGORIES,
    AreaSafetyEvidence,
    AssessmentDraft,
    CommuteEvidence,
    RatingEvidence,
    ReviewEvidence,
)
from aptfinder.evaluators.classifier import Mention, SemanticClassifier, classify_reviews
from aptfinder.evaluators.commute import evaluate_commute
from aptfinder.evaluators.intelligence import build_review_intelligence
from aptfinder.evaluators.neighborhood_safety import evaluate_neighborhood_safety
from aptfinder.evaluators.other_issues import evaluate_other_issues
from aptfinder.evaluators.review_categories import (
    evaluate_building_safety,
    evaluate_management,
    evaluate_noise,
    evaluate_pests,
)
from aptfinder.evaluators.review_quality import assess_review_quality
from aptfinder.evaluators.scoring import index_reviews

REVIEW_QUALITY = "review_quality"


def evaluate_all(
    reviews: Sequence[ReviewEvidence],
    ratings: Sequence[RatingEvidence],
    commute: CommuteEvidence | None,
    area: AreaSafetyEvidence | None,
    now: datetime,
    *,
    mentions: Sequence[Mention] | None = None,
    classifier: SemanticClassifier | None = None,
) -> dict[str, AssessmentDraft]:
    # Keys are CATEGORIES in order, then "review_quality" (score is always None; its details["intelligence"]
    # holds the praised/criticized/trends/outliers dict the API reads). Reviews are classified once and shared.
    review_list = list(index_reviews(reviews).values())
    shared = list(mentions) if mentions is not None else classify_reviews(review_list, classifier)
    evaluators: dict[str, Callable[[], AssessmentDraft]] = {
        "commute": lambda: evaluate_commute(commute),
        "noise": lambda: evaluate_noise(review_list, shared, now),
        "management": lambda: evaluate_management(review_list, shared, now),
        "pests": lambda: evaluate_pests(review_list, shared, now),
        "building_safety": lambda: evaluate_building_safety(review_list, shared, now),
        "neighborhood_safety": lambda: evaluate_neighborhood_safety(area, review_list, now, shared),
        "other_issues": lambda: evaluate_other_issues(review_list, shared, now),
    }
    results = {category: evaluators[category]() for category in CATEGORIES}
    individual = [r for r in review_list if not r.is_summary]
    individual_ids = {r.evidence_id for r in individual}
    individual_mentions = [m for m in shared if m.evidence_id in individual_ids]
    quality = assess_review_quality(individual, ratings, now, individual_mentions)
    quality.details["intelligence"] = build_review_intelligence(individual, individual_mentions, now)
    results[REVIEW_QUALITY] = quality
    return results
