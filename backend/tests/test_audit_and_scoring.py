from datetime import UTC, datetime, timedelta

import pytest

from aptfinder.audit import EvidenceInfo, audit_assessment
from aptfinder.evaluators.base import AssessmentDraft, ClaimDraft
from aptfinder.scoring import BASE_WEIGHTS, compute_overall

NOW = datetime(2026, 10, 3, tzinfo=UTC)
REVIEW_CATEGORIES = ("noise", "management", "pests", "building_safety", "neighborhood_safety", "other_issues")


def review(evidence_id: str, years_ago: float = 0.5, property_id: int = 1, has_url: bool = True) -> EvidenceInfo:
    return EvidenceInfo(evidence_id, property_id, "review", "apartment_list", REVIEW_CATEGORIES, NOW - timedelta(days=365 * years_ago), has_url)


def noise_draft(claims: list[ClaimDraft], score: float | None = 4.0, confidence: str = "low", count: int = 3, positive=(), negative=()) -> AssessmentDraft:
    return AssessmentDraft("noise", score, confidence, count, "Of 3 noise-related reviews, 3 mention thin walls.",
                           {}, list(positive), list(negative), claims)


def test_missing_evidence_reference_removes_claim_and_score():
    draft = noise_draft([ClaimDraft("3 reviews mention thin walls", "negative", "thin_walls", ["ev_missing"])], negative=["ev_missing"])
    result = audit_assessment(draft, 1, {}, NOW)
    assert result.assessment.claims == []
    assert result.assessment.score is None and result.assessment.confidence == "insufficient"
    assert {f.check_name for f in result.findings} >= {"evidence_exists", "no_fabricated_claims", "missing_evidence_not_positive"}


def test_evidence_from_other_property_is_rejected():
    evidence = {"ev_a": review("ev_a", property_id=2)}
    result = audit_assessment(noise_draft([ClaimDraft("x", "negative", "thin_walls", ["ev_a"])]), 1, evidence, NOW)
    assert result.assessment.claims == []
    assert any(f.check_name == "source_attribution" for f in result.findings)


def test_wrong_kind_cannot_support_category():
    fact = EvidenceInfo("ev_fact", 1, "listing_fact", "apartment_list", ("parking",), None, True)
    draft = AssessmentDraft("commute", 8.0, "medium", 1, "s", claims=[ClaimDraft("short commute", "positive", None, ["ev_fact"])])
    result = audit_assessment(draft, 1, {"ev_fact": fact}, NOW)
    assert result.assessment.score is None
    assert any(f.check_name == "evidence_supports_claim" for f in result.findings)


def test_old_evidence_gets_age_qualifier():
    evidence = {f"ev_{i}": review(f"ev_{i}", years_ago=5 + i) for i in range(3)}
    claim = ClaimDraft("3 reviews mention thin walls", "negative", "thin_walls", list(evidence))
    result = audit_assessment(noise_draft([claim], negative=list(evidence)), 1, evidence, NOW)
    kept = result.assessment.claims[0]
    assert kept.is_current is False
    assert "based on reviews from" in kept.text


def test_weak_evidence_cannot_be_high_confidence():
    evidence = {f"ev_{i}": review(f"ev_{i}") for i in range(3)}
    draft = noise_draft([ClaimDraft("x", "negative", "thin_walls", list(evidence))], confidence="high", count=3, negative=list(evidence))
    result = audit_assessment(draft, 1, evidence, NOW)
    assert result.assessment.confidence == "medium"
    assert any(f.check_name == "weak_evidence_confidence" for f in result.findings)


def test_positive_summary_without_positive_evidence_is_rewritten():
    evidence = {f"ev_{i}": review(f"ev_{i}") for i in range(3)}
    draft = noise_draft([ClaimDraft("x", "negative", "thin_walls", list(evidence))], negative=list(evidence))
    draft.summary = "The property is quiet with no complaints."
    result = audit_assessment(draft, 1, evidence, NOW)
    assert "not treated as evidence" in result.assessment.summary


def test_hidden_contradiction_is_surfaced():
    evidence = {f"ev_{i}": review(f"ev_{i}") for i in range(4)}
    draft = noise_draft(
        [ClaimDraft("3 mention thin walls", "negative", "thin_walls", ["ev_0", "ev_1", "ev_2"])],
        negative=["ev_0", "ev_1", "ev_2"], positive=["ev_3"], count=4,
    )
    result = audit_assessment(draft, 1, evidence, NOW)
    assert "Contradictory evidence exists" in result.assessment.summary


def test_missing_source_url_is_noted_not_hidden():
    evidence = {f"ev_{i}": review(f"ev_{i}", has_url=False) for i in range(3)}
    result = audit_assessment(noise_draft([ClaimDraft("x", "negative", "thin_walls", list(evidence))], negative=list(evidence)), 1, evidence, NOW)
    assert result.assessment.score == 4.0
    assert any(f.check_name == "source_url" and f.severity == "info" for f in result.findings)


def test_valid_assessment_passes_unchanged():
    evidence = {f"ev_{i}": review(f"ev_{i}") for i in range(3)}
    result = audit_assessment(noise_draft([ClaimDraft("3 mention thin walls", "negative", "thin_walls", list(evidence))], negative=list(evidence)), 1, evidence, NOW)
    assert not result.corrected and result.assessment.score == 4.0


def test_city_level_safety_with_single_fact_keeps_low_confidence_score():
    fact = EvidenceInfo("ev_doj", 1, "safety_fact", "ca_doj", ("neighborhood_safety",), None, True)
    draft = AssessmentDraft("neighborhood_safety", 6.0, "low", 1, "City-wide data", claims=[ClaimDraft("City-wide rates below state", "positive", None, ["ev_doj"])], positive_evidence_ids=["ev_doj"])
    result = audit_assessment(draft, 1, {"ev_doj": fact}, NOW)
    assert result.assessment.score == 6.0 and result.assessment.confidence == "low"


def assessment(category: str, score: float | None, confidence: str, **details) -> AssessmentDraft:
    return AssessmentDraft(category, score, confidence if score is not None else "insufficient", 5, "s", details)


def test_weights_sum_to_one():
    assert sum(BASE_WEIGHTS.values()) == pytest.approx(1.0)


def test_missing_categories_are_excluded_and_renormalized_not_neutral():
    result = compute_overall({
        "commute": assessment("commute", 9.0, "medium"),
        "noise": assessment("noise", 5.0, "medium"),
        "management": assessment("management", None, "insufficient"),
    })
    assert result.score == pytest.approx(round((0.25 * 9 + 0.20 * 5) / 0.45, 1))
    excluded = {e["category"] for e in result.excluded_categories}
    assert {"management", "pests", "other_issues", "building_safety", "neighborhood_safety"} <= excluded
    assert any("lacked sufficient evidence" in r for r in result.confidence_reasons)


def test_too_little_coverage_gives_no_overall_score():
    result = compute_overall({"commute": assessment("commute", 9.0, "medium")})
    assert result.score is None and result.confidence == "insufficient"


def test_full_high_confidence_coverage():
    result = compute_overall({c: assessment(c, 8.0, "high") for c in BASE_WEIGHTS})
    assert result.score == 8.0 and result.confidence == "high"
    assert result.excluded_categories == []


def test_free_flow_commute_reduces_confidence_with_reason():
    result = compute_overall({
        "commute": assessment("commute", 9.0, "medium", basis="free_flow"),
        "neighborhood_safety": assessment("neighborhood_safety", 6.0, "low"),
        "noise": assessment("noise", 6.0, "low"),
    })
    assert result.confidence == "low"
    assert any("free-flow" in r for r in result.confidence_reasons)
    assert all(c["effective_weight"] > c["base_weight"] for c in result.components)
