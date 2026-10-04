import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from aptfinder.evaluators.base import AssessmentDraft, ClaimDraft

CURRENT_WINDOW = timedelta(days=730)
CATEGORY_EVIDENCE_KINDS = {
    "commute": {"commute_fact"},
    "neighborhood_safety": {"safety_fact", "review"},
}
POSITIVE_FROM_SILENCE = re.compile(
    r"\b(no (?:known |reported )?(?:complaints|issues|problems|pests?|bugs|noise)|is quiet|very quiet|pest[- ]free|completely safe|perfectly safe)\b",
    re.I,
)
MIN_EVIDENCE_FOR = {"high": 8, "medium": 5, "low": 3}
REVIEW_BASED_CATEGORIES = {"noise", "management", "pests", "building_safety", "other_issues"}


@dataclass(frozen=True)
class EvidenceInfo:
    id: str
    property_id: int | None
    kind: str
    source_id: str | None
    categories: tuple[str, ...]
    published_at: datetime | None
    has_url: bool


@dataclass
class Finding:
    check_name: str
    severity: str
    action: str
    detail: str


@dataclass
class AuditResult:
    assessment: AssessmentDraft
    findings: list[Finding] = field(default_factory=list)

    @property
    def corrected(self) -> bool:
        return any(f.action != "noted" for f in self.findings)


def _supports(evidence: EvidenceInfo, category: str) -> bool:
    allowed_kinds = CATEGORY_EVIDENCE_KINDS.get(category)
    if allowed_kinds is not None and evidence.kind not in allowed_kinds:
        return False
    if evidence.kind == "review":
        return category in evidence.categories
    return allowed_kinds is not None or category in evidence.categories


def _downgrade(confidence: str, evidence_count: int) -> str:
    for level in ("high", "medium", "low"):
        if confidence == level and evidence_count < MIN_EVIDENCE_FOR[level]:
            return {"high": "medium", "medium": "low", "low": "insufficient"}[level]
    return confidence


def audit_assessment(draft: AssessmentDraft, property_id: int, evidence: dict[str, EvidenceInfo], now: datetime) -> AuditResult:
    findings: list[Finding] = []
    category = draft.category
    kept_claims: list[ClaimDraft] = []

    for claim in draft.claims:
        valid_ids = []
        for evidence_id in claim.evidence_ids:
            info = evidence.get(evidence_id)
            if info is None:
                findings.append(Finding("evidence_exists", "error", "removed_reference", f"Claim '{claim.text}' cited missing evidence {evidence_id}"))
                continue
            if info.property_id != property_id:
                findings.append(Finding("source_attribution", "error", "removed_reference", f"Evidence {evidence_id} belongs to a different property"))
                continue
            if not _supports(info, category):
                findings.append(Finding("evidence_supports_claim", "error", "removed_reference", f"Evidence {evidence_id} ({info.kind}) cannot support a {category} claim"))
                continue
            if not info.has_url:
                findings.append(Finding("source_url", "info", "noted", f"Evidence {evidence_id} has no source URL; shown as 'Source URL unavailable'"))
            valid_ids.append(evidence_id)
        if not valid_ids:
            findings.append(Finding("no_fabricated_claims", "error", "removed_claim", f"Removed unsupported claim: '{claim.text}'"))
            continue
        claim.evidence_ids = valid_ids

        dates = [evidence[i].published_at for i in valid_ids if evidence[i].kind == "review"]
        if dates and all(d is not None and now - d > CURRENT_WINDOW for d in dates) and claim.is_current:
            years = sorted({d.year for d in dates})
            span = str(years[0]) if len(years) == 1 else f"{years[0]}–{years[-1]}"
            claim.is_current = False
            claim.text = f"{claim.text} (based on reviews from {span})"
            findings.append(Finding("old_evidence_qualified", "warning", "added_qualifier", f"Claim relied only on evidence older than 2 years; qualified as {span}"))
        kept_claims.append(claim)
    draft.claims = kept_claims

    supported_ids = {i for c in kept_claims for i in c.evidence_ids}
    draft.positive_evidence_ids = [i for i in draft.positive_evidence_ids if i in evidence and _supports(evidence[i], category) and evidence[i].property_id == property_id]
    draft.negative_evidence_ids = [i for i in draft.negative_evidence_ids if i in evidence and _supports(evidence[i], category) and evidence[i].property_id == property_id]
    supported_ids |= set(draft.positive_evidence_ids) | set(draft.negative_evidence_ids)

    if draft.score is not None and not supported_ids:
        findings.append(Finding("missing_evidence_not_positive", "error", "removed_score", f"{category} had a score without any valid evidence"))
        draft.score = None
        draft.confidence = "insufficient"
        draft.summary = f"Insufficient evidence to reliably evaluate {category.replace('_', ' ')}."

    if not draft.positive_evidence_ids and draft.summary and POSITIVE_FROM_SILENCE.search(draft.summary) and category not in ("commute",):
        findings.append(Finding("missing_evidence_not_positive", "error", "rewrote_summary", f"Summary implied a positive condition without positive evidence: '{draft.summary}'"))
        draft.summary = f"Insufficient positive evidence; the absence of complaints is not treated as evidence about {category.replace('_', ' ')}."

    if draft.positive_evidence_ids and draft.negative_evidence_ids:
        polarities = {c.polarity for c in draft.claims}
        if not {"positive", "negative"} <= polarities:
            note = f" Contradictory evidence exists: {len(draft.positive_evidence_ids)} positive and {len(draft.negative_evidence_ids)} negative items."
            draft.summary = draft.summary.rstrip() + note
            findings.append(Finding("contradictions_visible", "warning", "added_contradiction_note", note.strip()))

    if draft.score is not None and category in REVIEW_BASED_CATEGORIES:
        downgraded = _downgrade(draft.confidence, draft.evidence_count)
        if downgraded != draft.confidence:
            findings.append(Finding("weak_evidence_confidence", "warning", "downgraded_confidence", f"{draft.confidence} confidence is not supported by {draft.evidence_count} evidence items; set to {downgraded}"))
            draft.confidence = downgraded
            if downgraded == "insufficient":
                draft.score = None
    if draft.score is None and draft.confidence != "insufficient":
        draft.confidence = "insufficient"
    return AuditResult(draft, findings)
