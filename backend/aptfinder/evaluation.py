from collections.abc import Callable
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from aptfinder.audit import EvidenceInfo, audit_assessment
from aptfinder.db.models import (
    AuditFinding,
    CategoryAssessment,
    Claim,
    ClaimEvidence,
    CommuteResult,
    Evidence,
    OverallScore,
    Property,
    Review,
)
from aptfinder.evaluators.base import (
    CATEGORIES,
    AreaSafetyEvidence,
    AssessmentDraft,
    CommuteEvidence,
    RatingEvidence,
    ReviewEvidence,
)
from aptfinder.scoring import compute_overall
from aptfinder.verification import latest_ratings

EvaluateAll = Callable[..., dict[str, AssessmentDraft]]


def review_inputs(session: Session, prop: Property) -> list[ReviewEvidence]:
    rows = session.execute(
        select(Review, Evidence).join(Evidence, Review.evidence_id == Evidence.id).where(Review.property_id == prop.id)
    ).all()
    return [
        ReviewEvidence(
            evidence_id=review.evidence_id,
            source_id=review.source_id,
            source_url=evidence.source_url or evidence.source_page_url,
            reviewer=review.reviewer,
            rating=review.rating,
            review_date=review.review_date,
            text=review.text or "",
            subscores={k: float(v) for k, v in (review.subscores or {}).items() if isinstance(v, (int, float))},
        )
        for review, evidence in rows
    ] + [
        ReviewEvidence(
            evidence_id=summary.id,
            source_id=summary.source_id,
            source_url=summary.source_url or summary.source_page_url,
            reviewer="Google AI summary",
            rating=None,
            review_date=summary.published_at,
            text=summary.content,
            is_summary=True,
        )
        for summary in session.scalars(
            select(Evidence)
            .where(Evidence.property_id == prop.id, Evidence.kind == "review_summary")
            .order_by(Evidence.collected_at.desc())
            .limit(1)
        )
    ]


def rating_inputs(session: Session, prop: Property) -> list[RatingEvidence]:
    return [
        RatingEvidence(r.evidence_id or "", r.source_id, r.average, r.count, r.scale, r.source_url)
        for r in latest_ratings(session, prop)
    ]


def commute_input(session: Session, prop: Property) -> CommuteEvidence | None:
    commute = session.scalars(
        select(CommuteResult).where(CommuteResult.property_id == prop.id).order_by(CommuteResult.computed_at.desc())
    ).first()
    if commute is None or commute.evidence_id is None:
        return None
    return CommuteEvidence(
        evidence_id=commute.evidence_id,
        provider=commute.provider,
        distance_miles=commute.distance_miles,
        free_flow_minutes=commute.free_flow_minutes,
        am_rush_minutes=commute.am_rush_minutes,
        pm_rush_minutes=commute.pm_rush_minutes,
        rush_status=commute.rush_status,
        source_url=commute.source_url,
    )


def area_input(session: Session, prop: Property) -> AreaSafetyEvidence | None:
    evidence = session.scalars(
        select(Evidence)
        .where(Evidence.property_id == prop.id, Evidence.kind == "safety_fact")
        .order_by(Evidence.collected_at.desc())
    ).first()
    if evidence is None or not evidence.data.get("has_city_data"):
        return None
    data = evidence.data
    return AreaSafetyEvidence(
        evidence_id=evidence.id,
        jurisdiction=data["jurisdiction"],
        year=data["year"],
        violent_per_1000=data.get("violent_per_1000"),
        property_per_1000=data.get("property_per_1000"),
        reference_violent_per_1000=data.get("reference_violent_per_1000"),
        reference_property_per_1000=data.get("reference_property_per_1000"),
        reference_label=data.get("reference_label", "California statewide"),
        source_url=evidence.source_url,
    )


def evidence_index(session: Session, prop: Property) -> dict[str, EvidenceInfo]:
    return {
        e.id: EvidenceInfo(
            id=e.id,
            property_id=e.property_id,
            kind=e.kind,
            source_id=e.source_id,
            categories=tuple(e.categories or ()),
            published_at=e.published_at,
            has_url=bool(e.source_url or e.source_page_url),
        )
        for e in session.scalars(select(Evidence).where(Evidence.property_id == prop.id))
    }


def _clear_previous(session: Session, prop: Property) -> None:
    assessment_ids = select(CategoryAssessment.id).where(CategoryAssessment.property_id == prop.id)
    claim_ids = select(Claim.id).where(Claim.assessment_id.in_(assessment_ids))
    session.execute(delete(ClaimEvidence).where(ClaimEvidence.claim_id.in_(claim_ids)))
    session.execute(delete(Claim).where(Claim.assessment_id.in_(assessment_ids)))
    session.execute(delete(CategoryAssessment).where(CategoryAssessment.property_id == prop.id))
    session.execute(delete(AuditFinding).where(AuditFinding.property_id == prop.id))
    session.flush()


def persist_assessments(
    session: Session,
    prop: Property,
    drafts: dict[str, AssessmentDraft],
    run_id: int | None,
    now: datetime,
    review_quality: AssessmentDraft | None = None,
) -> dict[str, AssessmentDraft]:
    _clear_previous(session, prop)
    index = evidence_index(session, prop)
    audited: dict[str, AssessmentDraft] = {}
    for category in CATEGORIES:
        draft = drafts.get(category) or AssessmentDraft.insufficient(category, f"Insufficient evidence to evaluate {category.replace('_', ' ')}.")
        result = audit_assessment(draft, prop.id, index, now)
        audited[category] = result.assessment
        _write_assessment(session, prop, result.assessment, run_id, now, "corrected" if result.corrected else "passed")
        for finding in result.findings:
            session.add(
                AuditFinding(property_id=prop.id, category=category, check_name=finding.check_name,
                             severity=finding.severity, action=finding.action, detail=finding.detail, created_at=now)
            )
    if review_quality is not None:
        _write_assessment(session, prop, review_quality, run_id, now, "passed", with_claims=False)

    overall = compute_overall(audited)
    row = session.get(OverallScore, prop.id) or OverallScore(property_id=prop.id)
    row.run_id = run_id
    row.score = overall.score
    row.confidence = overall.confidence
    row.components = overall.components
    row.excluded_categories = overall.excluded_categories
    row.confidence_reasons = overall.confidence_reasons
    row.computed_at = now
    session.add(row)
    session.flush()
    return audited


def _write_assessment(session: Session, prop: Property, draft: AssessmentDraft, run_id: int | None, now: datetime, audit_status: str, with_claims: bool = True) -> None:
    assessment = CategoryAssessment(
        property_id=prop.id, run_id=run_id, category=draft.category, score=draft.score, confidence=draft.confidence,
        evidence_count=draft.evidence_count, summary=draft.summary, details=draft.details,
        positive_evidence_ids=draft.positive_evidence_ids, negative_evidence_ids=draft.negative_evidence_ids,
        computed_at=now, audit_status=audit_status,
    )
    if with_claims:
        for claim_draft in draft.claims:
            claim = Claim(property_id=prop.id, text=claim_draft.text, polarity=claim_draft.polarity, theme=claim_draft.theme,
                          weight=claim_draft.weight, is_current=claim_draft.is_current)
            for evidence_id in dict.fromkeys(claim_draft.evidence_ids):
                claim.evidence_links.append(ClaimEvidence(evidence_id=evidence_id))
            assessment.claims.append(claim)
    session.add(assessment)
