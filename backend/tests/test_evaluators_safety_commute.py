from datetime import UTC, datetime, timedelta

import pytest

from aptfinder.evaluators.base import AreaSafetyEvidence, CommuteEvidence, ReviewEvidence
from aptfinder.evaluators.commute import commute_score, evaluate_commute
from aptfinder.evaluators.neighborhood_safety import evaluate_neighborhood_safety, ratio_score

NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)


def area(violent=2.2, prop=10.2, year=2023, jurisdiction="Sunnyvale") -> AreaSafetyEvidence:
    return AreaSafetyEvidence("area-1", jurisdiction, year, violent, prop, 4.4, 20.4, "California statewide", "https://example.com/crime")


def review(evidence_id, text, days_ago=30):
    return ReviewEvidence(evidence_id, "apartment_list", None, None, None, NOW - timedelta(days=days_ago), text)


def commute(free_flow=None, am=None, pm=None, distance=12.0) -> CommuteEvidence:
    return CommuteEvidence("commute-1", "OSRM", distance, free_flow, am, pm, "Unavailable — traffic-aware routing API required", None)


@pytest.mark.parametrize(("ratio", "score"), [(1.0, 5.5), (0.5, 7.75), (2.0, 3.25), (0.25, 10.0), (4.0, 1.0), (0.1, 10.0), (10.0, 1.0)])
def test_ratio_score_mapping(ratio, score):
    assert ratio_score(ratio) == pytest.approx(score)


def test_ratio_score_is_monotone():
    ratios = [0.2, 0.4, 0.7, 1.0, 1.3, 2.0, 3.0, 5.0]
    scores = [ratio_score(r) for r in ratios]
    assert scores == sorted(scores, reverse=True)


def test_city_level_data_is_never_above_low_confidence_and_says_so():
    result = evaluate_neighborhood_safety(area(), [], NOW)
    assert result.confidence == "low"
    assert result.score == round(0.6 * 7.75 + 0.4 * 7.75, 1)
    assert "city-wide" in result.summary
    assert "not neighborhood-specific" in result.summary
    assert "2023" in result.summary and "Sunnyvale" in result.summary
    assert "property crime runs higher in cities with large retail or commercial areas" in result.summary
    assert all(c.evidence_ids == ["area-1"] for c in result.claims)
    assert result.positive_evidence_ids == ["area-1"]
    assert result.details["scope"] == "city"


def test_high_crime_city_scores_low_and_cites_negative_evidence():
    result = evaluate_neighborhood_safety(area(violent=8.8, prop=40.8), [], NOW)
    assert result.score == 3.3
    assert result.confidence == "low"
    assert result.negative_evidence_ids == ["area-1"]
    assert {c.polarity for c in result.claims} == {"negative"}


def test_missing_area_is_insufficient():
    result = evaluate_neighborhood_safety(None, [], NOW)
    assert result.score is None
    assert result.confidence == "insufficient"
    assert "No official crime data" in result.summary


def test_only_one_rate_is_used_and_disclosed():
    result = evaluate_neighborhood_safety(area(prop=None), [], NOW)
    assert result.score == 7.8
    assert "Only the violent crime rate was available" in result.summary
    assert [c.theme for c in result.claims] == ["violent_crime_rate"]


def test_no_usable_rates_is_insufficient():
    result = evaluate_neighborhood_safety(area(violent=None, prop=None), [], NOW)
    assert result.score is None
    assert "incomplete" in result.summary


def test_resident_reports_adjust_score_by_at_most_one():
    reviews = [
        review("a", "There's a lot of crime in the area."),
        review("b", "I don't feel safe walking around the neighborhood at night."),
        review("c", "Car thefts nearby are common, crime in the neighborhood is rising."),
    ]
    baseline = evaluate_neighborhood_safety(area(), [], NOW)
    adjusted = evaluate_neighborhood_safety(area(), reviews, NOW)
    assert adjusted.details["resident_adjustment"] == -1.0
    assert adjusted.score == pytest.approx(baseline.score - 1.0)
    assert adjusted.confidence == "low"
    resident_claims = [c for c in adjusted.claims if c.theme == "area_crime"]
    assert resident_claims and set(resident_claims[0].evidence_ids) == {"a", "b", "c"}
    assert adjusted.evidence_count == 4


def test_fewer_than_three_resident_reports_do_not_adjust():
    reviews = [review("a", "There's a lot of crime in the area."), review("b", "Safe neighborhood.")]
    result = evaluate_neighborhood_safety(area(), reviews, NOW)
    assert result.details["resident_adjustment"] == 0.0
    assert result.details["resident_reports"] == 2
    assert all(c.evidence_ids == ["area-1"] for c in result.claims)
    assert "too few to adjust the score" in result.summary


def test_stale_official_data_is_qualified():
    result = evaluate_neighborhood_safety(area(year=2018), [], NOW)
    assert all(c.is_current is False for c in result.claims)
    assert "may not reflect current conditions" in result.summary


@pytest.mark.parametrize(("minutes", "score"), [(5, 10.0), (10, 10.0), (27.5, 5.5), (45, 1.0), (60, 1.0), (17, 8.2)])
def test_commute_score_mapping(minutes, score):
    assert commute_score(minutes) == score


def test_free_flow_commute_says_no_traffic():
    result = evaluate_commute(commute(free_flow=27.5))
    assert result.score == 5.5
    assert result.confidence == "medium"
    assert "Free-flow" in result.summary
    assert "no traffic" in result.summary
    assert "rush-hour estimate is unavailable" in result.summary
    assert result.details["basis"] == "free_flow"
    assert result.claims[0].evidence_ids == ["commute-1"]


def test_rush_hour_average_is_preferred_over_free_flow():
    result = evaluate_commute(commute(free_flow=15, am=30, pm=40))
    assert result.details["minutes_used"] == 35.0
    assert result.score == commute_score(35)
    assert result.confidence == "medium"
    assert "traffic model" in result.summary
    assert result.negative_evidence_ids == ["commute-1"]


def test_single_rush_estimate_is_used_and_gap_disclosed():
    result = evaluate_commute(commute(free_flow=15, am=30))
    assert result.details["basis"] == "am_rush"
    assert result.score == commute_score(30)
    assert "no PM rush-hour estimate" in result.summary


def test_commute_insufficient_without_route_or_minutes():
    assert evaluate_commute(None).score is None
    missing = evaluate_commute(commute())
    assert missing.score is None
    assert missing.confidence == "insufficient"
    assert missing.claims == []


def test_fast_commute_is_positive_evidence():
    result = evaluate_commute(commute(free_flow=8))
    assert result.score == 10.0
    assert result.positive_evidence_ids == ["commute-1"]
    assert result.claims[0].polarity == "positive"
