import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from aptfinder.evaluators import REVIEW_QUALITY, classify_reviews, evaluate_all
from aptfinder.evaluators.base import (
    CATEGORIES,
    CONFIDENCE_LEVELS,
    AreaSafetyEvidence,
    CommuteEvidence,
    RatingEvidence,
    ReviewEvidence,
)

NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)
TEXTS = [
    ("The walls are paper thin. Staff is friendly and helpful.", 30, 3.0, {"noise": 2, "management": 4}),
    ("Quiet community, never had bugs. Maintenance fixed everything quickly.", 100, 5.0, {"noise": 5, "maintenance": 5}),
    ("Thin walls and the upstairs neighbors stomp all day. Parking is a nightmare.", 200, 3.0, {}),
    ("We had roaches. They keep coming back every summer. Parking is a nightmare too.", 400, 2.0, {}),
    ("Under new management. The office never returns calls.", 800, 2.0, {}),
    ("Roaches in the kitchen. Management was rude.", 1500, 1.0, {}),
    ("Caltrain horns all night. Mold in the bathroom.", 2000, 3.0, {}),
    ("Mold everywhere and the elevator is always broken.", 3000, 2.0, {}),
    ("Great place, the elevator is broken a lot.", None, 4.0, {}),
    ("Packages get stolen all the time. Feel safe walking at night though.", 50, 4.0, {}),
    ("Package theft is common here and my car was broken into.", 120, 2.0, {}),
    ("Someone stole my bike from the bike room. The neighborhood is safe though.", 300, 3.0, {}),
]


def inputs():
    reviews = [
        ReviewEvidence(f"rev-{i}", "yelp" if i % 4 == 0 else "apartment_list", f"https://example.com/{i}", f"user{i}", rating,
                       None if days is None else NOW - timedelta(days=days), text, subscores)
        for i, (text, days, rating, subscores) in enumerate(TEXTS)
    ]
    ratings = [RatingEvidence("rating-1", "apartment_list", 3.4, 40, 5.0, "https://example.com/al")]
    commute = CommuteEvidence("commute-1", "OSRM", 14.2, 24.0, None, None, "Unavailable — traffic-aware routing API required", None)
    area = AreaSafetyEvidence("area-1", "Sunnyvale", 2023, 2.0, 18.0, 4.4, 20.4, "California statewide", "https://example.com/crime")
    return reviews, ratings, commute, area


def test_all_categories_and_review_quality_are_returned():
    reviews, ratings, commute, area = inputs()
    results = evaluate_all(reviews, ratings, commute, area, NOW)
    assert list(results) == [*CATEGORIES, REVIEW_QUALITY]
    for category, draft in results.items():
        assert draft.category == category
        assert draft.confidence in CONFIDENCE_LEVELS
        if category != REVIEW_QUALITY:
            assert (draft.score is None) == (draft.confidence == "insufficient")
    intelligence = results[REVIEW_QUALITY].details["intelligence"]
    assert set(intelligence) == {"praised", "criticized", "recent_trends", "outliers"}


def test_claims_cite_existing_evidence_only():
    reviews, ratings, commute, area = inputs()
    known = {r.evidence_id for r in reviews} | {r.evidence_id for r in ratings} | {commute.evidence_id, area.evidence_id}
    results = evaluate_all(reviews, ratings, commute, area, NOW)
    for draft in results.values():
        for claim in draft.claims:
            assert claim.evidence_ids, claim.text
            assert set(claim.evidence_ids) <= known, claim.text
            assert claim.polarity in ("positive", "negative", "neutral")
        assert set(draft.positive_evidence_ids) <= known
        assert set(draft.negative_evidence_ids) <= known
    intelligence = results[REVIEW_QUALITY].details["intelligence"]
    for stat in intelligence["praised"] + intelligence["criticized"]:
        assert set(stat["evidence_ids"]) <= known
    assert all(o["evidence_id"] in known for o in intelligence["outliers"])


def test_scored_categories_have_supporting_evidence():
    reviews, ratings, commute, area = inputs()
    for draft in evaluate_all(reviews, ratings, commute, area, NOW).values():
        if draft.score is not None:
            assert draft.claims and draft.evidence_count > 0
            assert 1.0 <= draft.score <= 10.0


def test_output_is_deterministic_and_json_safe():
    first = evaluate_all(*inputs(), NOW)
    second = evaluate_all(*inputs(), NOW)
    assert {k: asdict(v) for k, v in first.items()} == {k: asdict(v) for k, v in second.items()}
    json.dumps({k: asdict(v) for k, v in first.items()})


def test_precomputed_mentions_give_identical_results():
    reviews, ratings, commute, area = inputs()
    mentions = classify_reviews(reviews)
    shared = evaluate_all(reviews, ratings, commute, area, NOW, mentions=mentions)
    fresh = evaluate_all(reviews, ratings, commute, area, NOW)
    assert {k: asdict(v) for k, v in shared.items()} == {k: asdict(v) for k, v in fresh.items()}


def test_empty_inputs_never_produce_scores():
    results = evaluate_all([], [], None, None, NOW)
    for category in CATEGORIES:
        assert results[category].score is None
        assert results[category].confidence == "insufficient"
        assert results[category].claims == []
    assert results[REVIEW_QUALITY].summary == "Review data: No reviews found"


def test_duplicate_review_ids_are_counted_once():
    reviews, ratings, commute, area = inputs()
    results = evaluate_all(reviews + reviews[:3], ratings, commute, area, NOW)
    assert results["noise"].details["reviews_analyzed"] == len(reviews)
    assert results[REVIEW_QUALITY].details["total_reviews"] == len(reviews)


def test_naive_review_dates_are_treated_as_utc():
    reviews, ratings, commute, area = inputs()
    naive = [ReviewEvidence(r.evidence_id, r.source_id, r.source_url, r.reviewer, r.rating,
                            r.review_date.replace(tzinfo=None) if r.review_date else None, r.text, r.subscores) for r in reviews]
    aware = evaluate_all(reviews, ratings, commute, area, NOW)
    assert {k: asdict(v) for k, v in evaluate_all(naive, ratings, commute, area, NOW).items()} == {k: asdict(v) for k, v in aware.items()}
