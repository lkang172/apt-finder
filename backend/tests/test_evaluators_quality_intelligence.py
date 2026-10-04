from datetime import UTC, datetime, timedelta

from aptfinder.evaluators.base import RatingEvidence, ReviewEvidence
from aptfinder.evaluators.classifier import classify_reviews
from aptfinder.evaluators.intelligence import build_review_intelligence
from aptfinder.evaluators.review_quality import assess_review_quality

NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)


def review(evidence_id, text="Nice place overall with a decent gym.", days_ago=30, source="apartment_list", rating=None):
    date = None if days_ago is None else NOW - timedelta(days=days_ago)
    return ReviewEvidence(evidence_id, source, None, None, rating, date, text)


def varied_texts(count):
    words = ["gym", "pool", "kitchen", "balcony", "courtyard", "lobby", "garden", "rooftop", "bike room", "dog park",
             "clubhouse", "office", "trail", "patio", "closet", "laundry room", "view", "location", "carport", "spa"]
    return [f"Review {i} talks about the {words[i % len(words)]} and item {i * 7}." for i in range(count)]


def test_no_reviews_is_insufficient():
    result = assess_review_quality([], [], NOW)
    assert result.confidence == "insufficient"
    assert result.summary == "Review data: No reviews found"
    assert result.score is None


def test_rating_summaries_without_review_text_are_reported():
    result = assess_review_quality([], [RatingEvidence("rt", "apartment_list", 4.2, 12, 5.0, None)], NOW)
    assert result.summary.startswith("Review data: No reviews found")
    assert "12 reviews" in result.summary


def test_large_recent_multi_source_corpus_is_high_confidence():
    texts = varied_texts(16)
    reviews = [review(f"r{i}", texts[i], days_ago=40 * i + 5, source="yelp" if i % 3 == 0 else "apartment_list") for i in range(16)]
    result = assess_review_quality(reviews, [], NOW)
    assert result.confidence == "high"
    assert result.details["total_reviews"] == 16
    assert result.details["source_count"] == 2
    assert result.details["suspicious_burst"] is None
    assert result.details["near_duplicate_pairs"] == []


def test_single_source_never_reaches_high():
    texts = varied_texts(20)
    reviews = [review(f"r{i}", texts[i], days_ago=40 * i + 5) for i in range(20)]
    result = assess_review_quality(reviews, [], NOW)
    assert result.confidence == "medium"
    assert result.details["single_source"] is True
    assert "All reviews come from a single source (apartment_list)." in result.summary


def test_age_distribution_buckets():
    reviews = [review("a", days_ago=100), review("b", days_ago=365 * 3), review("c", days_ago=365 * 5),
               review("d", days_ago=365 * 9), review("e", days_ago=None)]
    distribution = assess_review_quality(reviews, [], NOW).details["age_distribution"]
    assert distribution == {"under_2_years": 1, "2_to_4_years": 1, "4_to_7_years": 1, "over_7_years": 1, "unknown": 1}


def test_burst_of_reviews_is_flagged_and_lowers_confidence():
    texts = varied_texts(10)
    reviews = [review(f"b{i}", texts[i], days_ago=100 + i, source="yelp" if i % 2 else "apartment_list") for i in range(5)]
    reviews += [review(f"s{i}", texts[5 + i], days_ago=200 + 90 * i) for i in range(5)]
    result = assess_review_quality(reviews, [], NOW)
    burst = result.details["suspicious_burst"]
    assert burst["count"] == 5 and burst["share"] == 0.5
    assert burst["evidence_ids"] == ["b0", "b1", "b2", "b3", "b4"]
    assert result.confidence == "low"
    assert "Possible burst: 5 of 10 reviews were posted within 14 days" in result.summary


def test_two_reviews_close_together_are_not_a_burst():
    texts = varied_texts(5)
    reviews = [review("a", texts[0], days_ago=10), review("b", texts[1], days_ago=12)]
    reviews += [review(f"r{i}", texts[2 + i], days_ago=200 * (i + 1)) for i in range(3)]
    assert assess_review_quality(reviews, [], NOW).details["suspicious_burst"] is None


def test_near_identical_texts_are_flagged():
    text = "Amazing apartment with friendly staff and great amenities, highly recommend living here."
    reviews = [review("a", text), review("b", text.replace("highly", "really")), review("c", "Totally different words in this one.")]
    result = assess_review_quality(reviews, [], NOW)
    assert result.details["near_duplicate_pairs"][0]["evidence_ids"] == ["a", "b"]
    duplicate_claim = next(c for c in result.claims if c.theme == "duplicate_text")
    assert duplicate_claim.evidence_ids == ["a", "b"]


def test_management_change_and_rating_conflict_are_reported():
    reviews = [
        review("old1", days_ago=900), review("old2", days_ago=800),
        review("chg", "Under new management since spring.", days_ago=400), review("new", days_ago=100),
    ]
    ratings = [RatingEvidence("rt1", "apartment_list", 4.5, 30, 5.0, None), RatingEvidence("rt2", "yelp", 6.0, 10, 10.0, None)]
    result = assess_review_quality(reviews, ratings, NOW)
    change = result.details["management_change"]
    assert change["detected"] and change["reviews_before_change"] == 2 and change["evidence_ids"] == ["chg"]
    assert result.details["ratings_conflict"]["gap"] == 1.5
    conflict_claim = next(c for c in result.claims if c.theme == "rating_conflict")
    assert conflict_claim.evidence_ids == ["rt1", "rt2"]


def test_intelligence_lists_only_repeated_themes_with_labels():
    reviews = [
        review("a", "Thin walls. Staff are friendly and helpful.", days_ago=30),
        review("b", "Paper thin walls.", days_ago=60),
        review("c", "Friendly staff and a quiet building.", days_ago=900),
        review("d", "Parking is a nightmare.", days_ago=90),
    ]
    intel = build_review_intelligence(reviews, classify_reviews(reviews), NOW)
    assert intel["criticized"] == [
        {"theme": "thin_walls", "label": "Thin walls", "count": 2, "recent_count": 2, "evidence_ids": ["a", "b"]}
    ]
    assert intel["praised"] == [
        {"theme": "helpful_staff", "label": "Friendly, helpful staff", "count": 2, "recent_count": 1, "evidence_ids": ["a", "c"]}
    ]


def test_intelligence_returns_empty_lists_when_nothing_repeats():
    reviews = [review("a", "Thin walls."), review("b", "Very quiet.")]
    intel = build_review_intelligence(reviews, classify_reviews(reviews), NOW)
    assert intel["praised"] == [] and intel["criticized"] == []
    assert len(intel["recent_trends"]) == 1
    assert intel["recent_trends"][0].startswith("Not enough review history to compare periods")


def test_recent_trends_compare_periods_when_history_exists():
    reviews = [review(f"n{i}", "Thin walls everywhere.", days_ago=30 + i) for i in range(3)]
    reviews += [review("n3", "Great gym.", days_ago=200)]
    reviews += [review(f"o{i}", "Nice courtyard and a decent gym.", days_ago=1000 + 30 * i) for i in range(4)]
    intel = build_review_intelligence(reviews, classify_reviews(reviews), NOW)
    assert intel["recent_trends"] == [
        "Thin walls: mentioned in 3 of 4 reviews from the last 24 months vs. 0 of 4 older reviews (more frequent recently)."
    ]


def test_outliers_include_rating_gaps_and_uncorroborated_allegations():
    reviews = [review(f"r{i}", "Lovely place.", days_ago=30 + i, rating=5.0) for i in range(4)]
    reviews.append(review("low", "Terrible experience. Bed bugs in the bedroom.", days_ago=10, rating=1.0))
    intel = build_review_intelligence(reviews, classify_reviews(reviews), NOW)
    texts = [o["text"] for o in intel["outliers"]]
    assert intel["outliers"][0]["evidence_id"] == "low"
    assert texts[0].startswith("Single uncorroborated report of bed bugs")
    assert any(t.startswith("Rated 1/5 versus a 4.2/5 average across 5 rated reviews") for t in texts)
    assert {o["evidence_id"] for o in intel["outliers"]} == {"low"}


def test_corroborated_allegations_are_not_outliers():
    reviews = [review("a", "Bed bugs in our unit."), review("b", "We also had bed bugs.")]
    intel = build_review_intelligence(reviews, classify_reviews(reviews), NOW)
    assert intel["outliers"] == []
