from datetime import UTC, datetime, timedelta

import pytest

from aptfinder.evaluators.base import ReviewEvidence
from aptfinder.evaluators.classifier import classify_reviews
from aptfinder.evaluators.recency import recency_weight
from aptfinder.evaluators.review_categories import (
    ISOLATED_INCIDENT,
    RECURRING_PATTERN,
    evaluate_building_safety,
    evaluate_management,
    evaluate_noise,
    evaluate_pests,
    pest_pattern,
)

NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)
FILLER = "Nice pool and close to shopping."


def review(evidence_id, text, days_ago=30, source="apartment_list", subscores=None, date=None):
    review_date = date if date is not None else (None if days_ago is None else NOW - timedelta(days=days_ago))
    return ReviewEvidence(evidence_id, source, f"https://example.com/{evidence_id}", None, None, review_date, text, subscores or {})


def run(evaluator, reviews):
    return evaluator(reviews, classify_reviews(reviews), NOW)


def fillers(count, start=100):
    return [review(f"f{i}", FILLER, days_ago=40 + i) for i in range(start, start + count)]


def test_zero_mentions_never_produce_a_score():
    result = run(evaluate_noise, fillers(14))
    assert result.score is None
    assert result.confidence == "insufficient"
    assert result.evidence_count == 0
    assert result.positive_evidence_ids == [] and result.negative_evidence_ids == []
    assert result.summary == "Insufficient evidence to reliably evaluate noise. None of the 14 collected reviews discuss noise."
    assert "quiet" not in result.summary.lower().replace("discuss noise", "")


def test_two_mentions_are_insufficient_and_state_review_counts():
    reviews = [review("a", "Thin walls."), review("b", "Very quiet place.")] + fillers(12)
    result = run(evaluate_noise, reviews)
    assert result.score is None and result.confidence == "insufficient"
    assert result.evidence_count == 2
    assert "Only 2 of 14 collected reviews discuss noise." in result.summary
    assert result.details["reviews_analyzed"] == 14
    assert result.details["relevant_reviews"] == 2
    assert {c.theme for c in result.claims} == {"thin_walls", "quiet"}


def test_no_reviews_at_all():
    result = run(evaluate_noise, [])
    assert result.score is None
    assert result.summary.endswith("No reviews were available to analyze.")


def test_score_formula_from_net_sentiment():
    all_negative = [review(i, "The walls are paper thin.") for i in "abc"]
    assert run(evaluate_noise, all_negative).score == 1.0
    mixed = [review("a", "Thin walls."), review("b", "Noisy neighbors upstairs."), review("c", "Super quiet.")]
    result = run(evaluate_noise, mixed)
    assert result.score == 4.0
    assert result.details["net_sentiment"] == pytest.approx(-1 / 3, abs=1e-3)
    assert "Evidence is mixed: 2 reviews include negative and 1 includes positive noise evidence." in result.summary


def test_scored_summary_cites_counts_and_details_keys():
    reviews = [
        review("a", "Thin walls."), review("b", "Paper thin walls and footsteps all night."),
        review("c", "Quiet building."), review("d", "Thin walls, you hear everything.", days_ago=1000),
    ] + fillers(3)
    result = run(evaluate_noise, reviews)
    assert result.summary.startswith("Of 4 reviews discussing noise (3 from the last 2 years; 7 reviews analyzed), 3 mention thin walls")
    assert result.details["theme_counts"] == {"thin_walls": 3, "neighbor_noise": 1, "quiet": 1}
    assert result.details["recent_relevant"] == 3
    assert result.evidence_count == 4
    assert result.negative_evidence_ids == ["a", "b", "d"]
    assert result.positive_evidence_ids == ["c"]


def test_explicit_no_pests_is_positive_evidence_but_silence_is_not():
    explicit = [review(i, "Never had any bugs or roaches here.") for i in "abc"]
    scored = run(evaluate_pests, explicit)
    assert scored.score == 10.0
    assert scored.positive_evidence_ids == ["a", "b", "c"]
    assert scored.claims[0].theme == "no_pests" and scored.claims[0].polarity == "positive"

    silent = run(evaluate_pests, fillers(20))
    assert silent.score is None
    assert silent.positive_evidence_ids == []
    assert silent.summary.startswith("Pests: N/A — insufficient evidence.")


def test_neutral_subscores_count_toward_evidence_and_denominator():
    neutral = [review(i, FILLER, subscores={"noise": 3}) for i in "abc"]
    result = run(evaluate_noise, neutral)
    assert result.score == 5.5
    assert result.evidence_count == 3
    assert result.positive_evidence_ids == [] and result.negative_evidence_ids == []
    assert result.claims[0].polarity == "neutral"

    diluted = [review("a", "Thin walls."), review("b", FILLER, subscores={"noise": 3}), review("c", FILLER, subscores={"noise": 3})]
    assert run(evaluate_noise, diluted).score == round(5.5 + 4.5 * (-1 / 3), 1)


def test_subscores_map_to_categories_and_combine_per_review():
    reviews = [review(i, FILLER, subscores={"management": 5, "maintenance": 4, "noise": 1}) for i in "abc"]
    management = run(evaluate_management, reviews)
    assert management.score == round(5.5 + 4.5 * 0.75, 1)
    assert management.details["subscores"] == {"count": 3, "average": 4.5}
    noise = run(evaluate_noise, reviews)
    assert noise.score == 1.0
    assert "unfavorable resident noise sub-rating" in noise.claims[0].text


def test_out_of_range_subscores_are_ignored():
    reviews = [review(i, FILLER, subscores={"noise": 9}) for i in "abc"]
    assert run(evaluate_noise, reviews).score is None


@pytest.mark.parametrize(
    ("days_ago", "weight"),
    [(30, 1.0), (730, 1.0), (365 * 3, 0.6), (365 * 5, 0.3), (365 * 8, 0.15), (None, 0.3)],
)
def test_recency_weights(days_ago, weight):
    date = None if days_ago is None else NOW - timedelta(days=days_ago)
    assert recency_weight(date, NOW) == weight


def test_old_only_evidence_is_not_current_and_states_its_age():
    reviews = [
        review("a", "Thin walls.", date=datetime(2019, 5, 1, tzinfo=UTC)),
        review("b", "Thin walls.", date=datetime(2020, 5, 1, tzinfo=UTC)),
        review("c", "Thin walls.", date=datetime(2021, 5, 1, tzinfo=UTC)),
    ]
    result = run(evaluate_noise, reviews)
    claim = result.claims[0]
    assert claim.is_current is False
    assert "(all mentions from 2019–2021)" in claim.text
    assert claim.weight == pytest.approx(0.15 + 0.3 + 0.3)


def test_mixed_age_claim_is_current_and_reports_recent_count():
    reviews = [review("a", "Thin walls."), review("b", "Thin walls.", days_ago=2000), review("c", "Thin walls.", days_ago=None)]
    claim = run(evaluate_noise, reviews).claims[0]
    assert claim.is_current is True
    assert "(1 from the last 2 years)" in claim.text


def test_undated_only_evidence_is_not_current():
    reviews = [review(i, "Thin walls.", days_ago=None) for i in "abc"]
    claim = run(evaluate_noise, reviews).claims[0]
    assert claim.is_current is False
    assert "review dates unavailable" in claim.text


def test_management_change_halves_weight_of_earlier_reviews():
    reviews = [
        review("old", "Management was rude and unprofessional.", days_ago=500),
        review("change", "Under new management. Staff are friendly and helpful.", days_ago=300),
        review("new", "The office is very responsive.", days_ago=100),
        review("newer", "Friendly staff.", days_ago=50),
    ]
    result = run(evaluate_management, reviews)
    change = result.details["management_change"]
    assert change["detected"] is True
    assert change["reviews_before_change"] == 1
    assert change["earliest_mention"] == (NOW - timedelta(days=300)).date().isoformat()
    rude = next(c for c in result.claims if c.theme == "professionalism")
    assert rude.weight == pytest.approx(0.5)
    assert "may concern previous management" in result.summary
    marker = next(c for c in result.claims if c.theme == "management_change")
    assert marker.polarity == "neutral" and marker.evidence_ids == ["change"]
    assert result.score == round(5.5 + 4.5 * (3 - 0.5) / 3.5, 1)


def test_management_without_change_records_absence():
    reviews = [review(i, "Friendly staff.") for i in "abc"]
    assert run(evaluate_management, reviews).details["management_change"] == {"detected": False}


def test_pest_pattern_recurring_vs_isolated():
    near = [review("a", "Roaches.", days_ago=100), review("b", "Roaches.", days_ago=300)]
    far = [review("a", "Roaches.", days_ago=100), review("b", "Roaches.", days_ago=1600)]
    assert pest_pattern(near, classify_reviews(near))[0] == RECURRING_PATTERN
    assert pest_pattern(far, classify_reviews(far))[0] == ISOLATED_INCIDENT
    single = [review("a", "Saw one roach in the kitchen.")]
    assert pest_pattern(single, classify_reviews(single)) == (ISOLATED_INCIDENT, "a single report")
    infestation = [review("a", "There was a roach infestation in our unit.")]
    assert pest_pattern(infestation, classify_reviews(infestation))[0] == RECURRING_PATTERN


def test_pest_patterns_appear_in_claims_and_details():
    reviews = [
        review("a", "Roaches in the kitchen.", days_ago=100),
        review("b", "We had roaches too.", days_ago=300),
        review("c", "Saw a spider once.", days_ago=200),
        review("d", "Ants in summer.", days_ago=150),
    ]
    result = run(evaluate_pests, reviews)
    patterns = result.details["pest_patterns"]
    assert patterns["cockroaches"]["label"] == RECURRING_PATTERN
    assert patterns["spiders"]["label"] == ISOLATED_INCIDENT
    roach_claim = next(c for c in result.claims if c.theme == "cockroaches")
    assert "recurring property-level pattern" in roach_claim.text
    spider_claim = next(c for c in result.claims if c.theme == "spiders")
    assert "isolated incident" in spider_claim.text
    assert "Cockroaches: recurring property-level pattern" in result.summary


def test_pest_severity_weights_bed_bugs_above_ants():
    bed_bugs = [review("a", "Bed bugs!"), review("b", "No bugs at all."), review("c", "Never seen a roach.")]
    ants = [review("a", "Ants in the kitchen."), review("b", "No bugs at all."), review("c", "Never seen a roach.")]
    assert run(evaluate_pests, bed_bugs).score < run(evaluate_pests, ants).score


def test_high_confidence_requires_volume_recency_and_sources():
    reviews = [review(f"r{i}", "Thin walls.", days_ago=30 + i, source="yelp" if i % 2 else "apartment_list") for i in range(8)]
    assert run(evaluate_noise, reviews).confidence == "high"


def test_single_source_caps_confidence_below_high_until_twelve_reviews():
    eight = [review(f"r{i}", "Thin walls.", days_ago=30 + i) for i in range(8)]
    assert run(evaluate_noise, eight).confidence == "medium"
    twelve = [review(f"r{i}", "Thin walls.", days_ago=30 + i) for i in range(12)]
    assert run(evaluate_noise, twelve).confidence == "high"


def test_confidence_levels_by_relevant_review_count():
    three = [review(f"r{i}", "Thin walls.") for i in range(3)]
    five = [review(f"r{i}", "Thin walls.") for i in range(5)]
    assert run(evaluate_noise, three).confidence == "low"
    assert run(evaluate_noise, five).confidence == "medium"


def test_single_review_dominance_downgrades_confidence():
    reviews = [review("bb", "Bed bugs in my unit.")] + [review(f"u{i}", "Ants in the kitchen.", days_ago=None) for i in range(4)]
    result = run(evaluate_pests, reviews)
    assert result.evidence_count == 5
    assert result.confidence == "low"
    assert result.details["dominant_review_share"] > 0.5
    assert any("one review carries" in note for note in result.details["notes"])


def test_mostly_old_evidence_downgrades_confidence():
    reviews = [review(f"r{i}", "Thin walls.", days_ago=365 * 5 + i) for i in range(5)]
    result = run(evaluate_noise, reviews)
    assert result.confidence == "low"
    assert result.details["old_evidence_share"] == 1.0
    assert "more than 4 years old" in result.summary


def test_building_safety_uses_resident_reports_only():
    reviews = [
        review("a", "Packages get stolen all the time."),
        review("b", "My car was broken into in the garage."),
        review("c", "I feel safe here, the gated garage works well."),
    ]
    result = run(evaluate_building_safety, reviews)
    assert result.score == round(5.5 + 4.5 * (1 - 2.6) / 3.6, 1)
    assert result.negative_evidence_ids == ["a", "b"]
    assert result.positive_evidence_ids == ["c"]


def test_claims_cite_existing_reviews_and_are_sorted_by_weight():
    reviews = [
        review("a", "Thin walls and noisy neighbors.", days_ago=20),
        review("b", "Thin walls.", days_ago=1500),
        review("c", "Quiet at night.", days_ago=3000),
    ]
    result = run(evaluate_noise, reviews)
    ids = {r.evidence_id for r in reviews}
    assert all(c.evidence_ids and set(c.evidence_ids) <= ids for c in result.claims)
    weights = [c.weight for c in result.claims]
    assert weights == sorted(weights, reverse=True)
