from typing import Any

from aptfinder.evaluators.base import AssessmentDraft, ClaimDraft, CommuteEvidence
from aptfinder.evaluators.lexicon import NEGATIVE, NEUTRAL, POSITIVE
from aptfinder.evaluators.scoring import clamp, round_score

CATEGORY = "commute"
BEST_MINUTES = 10.0
WORST_MINUTES = 45.0
POSITIVE_SCORE = 7.0
NEGATIVE_SCORE = 4.0
COMMUTE_CONFIDENCE = "medium"
INSUFFICIENT_LEAD = "Commute: N/A — insufficient evidence."


def commute_score(minutes: float) -> float:
    fraction = (minutes - BEST_MINUTES) / (WORST_MINUTES - BEST_MINUTES)
    return round_score(clamp(10.0 - 9.0 * fraction, 1.0, 10.0))


def format_minutes(minutes: float) -> str:
    rounded = round(minutes)
    return f"{rounded}" if abs(minutes - rounded) < 0.05 else f"{minutes:.1f}"


def _valid(minutes: float | None) -> bool:
    return minutes is not None and minutes >= 0


def evaluate_commute(commute: CommuteEvidence | None) -> AssessmentDraft:
    if commute is None:
        return AssessmentDraft.insufficient(CATEGORY, f"{INSUFFICIENT_LEAD} No route estimate is available for this property.")

    details: dict[str, Any] = {
        "provider": commute.provider,
        "distance_miles": commute.distance_miles,
        "free_flow_minutes": commute.free_flow_minutes,
        "am_rush_minutes": commute.am_rush_minutes,
        "pm_rush_minutes": commute.pm_rush_minutes,
        "rush_status": commute.rush_status,
        "source_url": commute.source_url,
    }
    rush = [(label, m) for label, m in (("AM", commute.am_rush_minutes), ("PM", commute.pm_rush_minutes)) if _valid(m)]
    distance = f", {commute.distance_miles:.1f} miles" if commute.distance_miles is not None else ""

    if rush:
        minutes = sum(m for _, m in rush) / len(rush)
        breakdown = ", ".join(f"{label} {format_minutes(m)}" for label, m in rush)
        if len(rush) == 2:
            summary = (
                f"Rush-hour drive averages {format_minutes(minutes)} min ({breakdown}){distance}, "
                f"from {commute.provider}'s traffic model."
            )
            basis = "rush_average"
        else:
            missing = "PM" if rush[0][0] == "AM" else "AM"
            summary = (
                f"{rush[0][0]} rush-hour drive of {format_minutes(minutes)} min{distance}, from {commute.provider}'s "
                f"traffic model; no {missing} rush-hour estimate is available."
            )
            basis = f"{rush[0][0].lower()}_rush"
        claim_text = f"Driving to the office takes about {format_minutes(minutes)} min at rush hour ({breakdown}){distance}."
    elif _valid(commute.free_flow_minutes):
        minutes = commute.free_flow_minutes
        status = f" ({commute.rush_status})" if commute.rush_status else ""
        summary = (
            f"Free-flow drive of {format_minutes(minutes)} min{distance}, from {commute.provider}. This is driving time "
            f"with no traffic; a rush-hour estimate is unavailable{status}, so peak commutes are likely longer."
        )
        basis = "free_flow"
        claim_text = f"Driving to the office takes about {format_minutes(minutes)} min with no traffic (free-flow){distance}."
    else:
        details["basis"] = None
        return AssessmentDraft.insufficient(
            CATEGORY, f"{INSUFFICIENT_LEAD} The route estimate has no driving time.", 0, **details
        )

    score = commute_score(minutes)
    details["basis"] = basis
    details["minutes_used"] = round(minutes, 1)
    polarity = POSITIVE if score >= POSITIVE_SCORE else NEGATIVE if score <= NEGATIVE_SCORE else NEUTRAL
    claim = ClaimDraft(claim_text, polarity, "drive_time", [commute.evidence_id], 1.0, True)
    return AssessmentDraft(
        CATEGORY,
        score,
        COMMUTE_CONFIDENCE,
        1,
        summary,
        details,
        [commute.evidence_id] if polarity == POSITIVE else [],
        [commute.evidence_id] if polarity == NEGATIVE else [],
        [claim],
    )
