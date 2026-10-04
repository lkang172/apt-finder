from dataclasses import dataclass, field

from aptfinder.evaluators.base import AssessmentDraft

BASE_WEIGHTS: dict[str, float] = {
    "commute": 0.25,
    "noise": 0.20,
    "management": 0.20,
    "building_safety": 0.075,
    "neighborhood_safety": 0.075,
    "pests": 0.10,
    "other_issues": 0.10,
}
CATEGORY_LABELS = {
    "commute": "Commute",
    "noise": "Noise",
    "management": "Management",
    "building_safety": "Building safety",
    "neighborhood_safety": "Neighborhood safety",
    "pests": "Pests",
    "other_issues": "Other recurring issues",
}
CONFIDENCE_VALUE = {"high": 1.0, "medium": 0.66, "low": 0.33}
MIN_COVERAGE = 0.30
MIN_SCORED_CATEGORIES = 2


@dataclass
class OverallResult:
    score: float | None
    confidence: str
    components: list[dict] = field(default_factory=list)
    excluded_categories: list[dict] = field(default_factory=list)
    confidence_reasons: list[str] = field(default_factory=list)


def compute_overall(assessments: dict[str, AssessmentDraft]) -> OverallResult:
    scored = {
        category: a for category, a in assessments.items()
        if category in BASE_WEIGHTS and a.score is not None and a.confidence in CONFIDENCE_VALUE
    }
    excluded = [
        {"category": c, "label": CATEGORY_LABELS[c], "reason": "Insufficient evidence; excluded and remaining weights renormalized"}
        for c in BASE_WEIGHTS if c not in scored
    ]
    coverage = sum(BASE_WEIGHTS[c] for c in scored)
    reasons = []
    if excluded:
        names = ", ".join(e["label"] for e in excluded)
        reasons.append(f"{names} lacked sufficient evidence ({round((1 - coverage) * 100)}% of the scoring weight excluded)")

    if len(scored) < MIN_SCORED_CATEGORIES or coverage < MIN_COVERAGE:
        reasons.append(
            f"Too little evidence for an overall score: {len(scored)} categories covering {round(coverage * 100)}% of the weight"
        )
        return OverallResult(None, "insufficient", [], excluded, reasons)

    components = []
    weighted_score = 0.0
    weighted_confidence = 0.0
    for category, assessment in scored.items():
        weight = BASE_WEIGHTS[category]
        weighted_score += weight * assessment.score
        weighted_confidence += weight * CONFIDENCE_VALUE[assessment.confidence]
        components.append(
            {
                "category": category,
                "label": CATEGORY_LABELS[category],
                "score": assessment.score,
                "confidence": assessment.confidence,
                "base_weight": weight,
                "effective_weight": round(weight / coverage, 4),
            }
        )
        if assessment.confidence == "low":
            reasons.append(f"{CATEGORY_LABELS[category]} is scored with low confidence")
    components.sort(key=lambda c: -c["base_weight"])

    score = round(weighted_score / coverage, 1)
    index = coverage * (weighted_confidence / coverage)
    confidence = "high" if index >= 0.70 else "medium" if index >= 0.45 else "low"
    commute = scored.get("commute")
    if commute and commute.details.get("basis") == "free_flow":
        reasons.append("Commute uses free-flow driving time; rush-hour traffic is not reflected")
    if not reasons and confidence != "high":
        reasons.append("Component confidence levels limit overall confidence")
    return OverallResult(score, confidence, components, excluded, reasons)
