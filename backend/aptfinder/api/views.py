from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from aptfinder.api import schemas as s
from aptfinder.config import Settings
from aptfinder.db.models import (
    AuditFinding,
    CategoryAssessment,
    Claim,
    ClaimEvidence,
    CollectionRun,
    CommuteResult,
    Evidence,
    FeeObservation,
    GooglePlaceMatch,
    ListingSource,
    OverallScore,
    Property,
    Source,
    utcnow,
)
from aptfinder.evaluation import review_inputs
from aptfinder.evaluators.base import CATEGORIES
from aptfinder.evaluators.comments_summary import summarize_comments
from aptfinder.filters import RatingInput, evaluate_rating_filter
from aptfinder.scoring import CATEGORY_LABELS
from aptfinder.verification import PriceVerification, latest_ratings, verify_prices

REVIEW_SOURCE_LABELS = {"apartment_list": "Apartment List", "google_places": "Google", "redfin": "Redfin"}
NOT_EVALUATED = "Not evaluated yet — run the pipeline to evaluate this category."


def age_label(published: datetime | None, now: datetime) -> str | None:
    if published is None:
        return None
    days = (now - published).days
    if days < 1:
        return "today"
    if days < 31:
        return f"{days} day{'s' if days != 1 else ''} ago"
    if days < 365:
        months = days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = days // 365
    return f"{years} year{'s' if years != 1 else ''} ago"


class SourceNames:
    def __init__(self, session: Session):
        self.names = {src.id: src.name for src in session.scalars(select(Source))}

    def __call__(self, source_id: str | None) -> str:
        return self.names.get(source_id or "", source_id or "Unknown source")


def evidence_item(evidence: Evidence, names: SourceNames, now: datetime) -> s.EvidenceItem:
    data = evidence.data or {}
    return s.EvidenceItem(
        id=evidence.id,
        kind=evidence.kind,
        source_id=evidence.source_id,
        source_name=names(evidence.source_id),
        title=evidence.title,
        content=evidence.content,
        published_at=evidence.published_at,
        collected_at=evidence.collected_at,
        source_url=evidence.source_url,
        source_page_url=evidence.source_page_url,
        is_derived=evidence.is_derived,
        categories=list(evidence.categories or []),
        rating=data.get("rating") if evidence.kind == "review" else None,
        reviewer=data.get("reviewer") if evidence.kind == "review" else None,
        age_label=age_label(evidence.published_at, now) if evidence.kind == "review" else None,
        data=data,
    )


def latest_fees(session: Session, prop: Property) -> list[FeeObservation]:
    rows = session.scalars(
        select(FeeObservation).where(FeeObservation.property_id == prop.id).order_by(FeeObservation.collected_at.desc())
    ).all()
    latest_by_listing: dict[int, datetime] = {}
    fees = []
    for fee in rows:
        latest_by_listing.setdefault(fee.listing_source_id, fee.collected_at)
        if fee.collected_at == latest_by_listing[fee.listing_source_id]:
            fees.append(fee)
    return fees


@dataclass
class PropertyContext:
    prop: Property
    price: PriceVerification
    fees: list[FeeObservation]
    commute: CommuteResult | None
    assessments: dict[str, CategoryAssessment]
    overall: OverallScore | None
    listings: list[ListingSource]


def load_context(session: Session, prop: Property, settings: Settings, now: datetime) -> PropertyContext:
    commute = session.scalars(
        select(CommuteResult).where(CommuteResult.property_id == prop.id).order_by(CommuteResult.computed_at.desc())
    ).first()
    assessments = {a.category: a for a in session.scalars(select(CategoryAssessment).where(CategoryAssessment.property_id == prop.id))}
    return PropertyContext(
        prop=prop,
        price=verify_prices(session, prop, settings, now),
        fees=latest_fees(session, prop),
        commute=commute,
        assessments=assessments,
        overall=session.get(OverallScore, prop.id),
        listings=list(session.scalars(select(ListingSource).where(ListingSource.property_id == prop.id))),
    )


def monthly_cost(ctx: PropertyContext) -> s.MonthlyCost:
    qualifying = ctx.price.qualifying
    unknown_required = sorted({f.description for f in ctx.fees if f.mandatory and (f.amount_monthly is None or f.recurring is None) and f.recurring is not False})
    unclear = sorted({f.description for f in ctx.fees if f.recurring and f.mandatory is None and f.fee_type != "pet"})
    if not qualifying:
        return s.MonthlyCost(base_rent_min=None, confirmed_required_fees=None, est_total_min=None, unknown_required=unknown_required, unclear_recurring=unclear)

    declared_property_fees = [f.amount_monthly for f in ctx.fees if f.mandatory and f.recurring and f.amount_monthly]
    best: tuple[float, float | None] | None = None
    for state in qualifying:
        obs = state.observation
        if obs.required_fees_monthly is not None:
            # The source already folded its mandatory monthly fees into the published total; adding
            # fee-text items again would double count them.
            fees = obs.required_fees_monthly
        elif declared_property_fees:
            fees = float(sum(declared_property_fees))
        else:
            fees = None
        total = obs.base_rent_min + (fees or 0)
        if best is None or total < best[0]:
            best = (total, fees)
    total, fees = best
    if fees is None:
        unknown_required = ["Required monthly fees are not published by the listing source"] + unknown_required
    return s.MonthlyCost(
        base_rent_min=min(q.observation.base_rent_min for q in qualifying),
        confirmed_required_fees=round(fees, 2) if fees is not None else None,
        est_total_min=round(total, 2),
        unknown_required=unknown_required,
        unclear_recurring=unclear,
    )


def review_brief(session: Session, prop: Property) -> tuple[s.ReviewBrief, s.RatingFilterView]:
    """The brief covers non-Google review sources (Google has its own brief); the filter view covers all."""
    ratings = latest_ratings(session, prop)
    decision = evaluate_rating_filter([RatingInput(r.source_id, r.average, r.count, r.scale, r.match_confidence) for r in ratings])
    others = [r for r in ratings if r.source_id != "google_places"]
    other_decision = evaluate_rating_filter([RatingInput(r.source_id, r.average, r.count, r.scale, r.match_confidence) for r in others])
    rated = [r for r in others if r.count and r.average is not None]
    count = sum(r.count for r in rated)
    average = round(sum(r.average * 5.0 / r.scale * r.count for r in rated) / count, 2) if count else None
    status = other_decision.status if other_decision.status in ("ok", "no_reviews", "insufficient", "conflict") else "ok"
    explanation = other_decision.explanation
    if other_decision.status == "no_reviews":
        checked = sorted({REVIEW_SOURCE_LABELS.get(r.source_id, r.source_id) for r in others}) or ["no listing source"]
        explanation = f"No reviews found on {', '.join(checked)}"
    filter_explanation = decision.explanation
    if decision.status == "no_reviews" and not any(r.source_id == "google_places" for r in ratings):
        filter_explanation = f"{explanation}; Google reviews not checked"
    return (
        s.ReviewBrief(average=average, count=count, status=status, explanation=explanation),
        s.RatingFilterView(status=decision.status, explanation=filter_explanation),
    )


def google_brief(session: Session, prop: Property, settings: Settings) -> s.GoogleReviewsBrief:
    match = session.get(GooglePlaceMatch, prop.id)
    empty = dict(rating=None, count=None, maps_url=None, summary=None, summary_disclosure=None, summary_flag_url=None,
                 comments_summary=None, comments_summary_method=None, match_confidence=None, observed_at=None)
    if match is None:
        if not settings.google_maps_api_key:
            return s.GoogleReviewsBrief(status="not_configured", explanation="Google reviews not checked — Google Maps API key not configured", **empty)
        return s.GoogleReviewsBrief(status="not_checked", explanation="Google reviews not checked yet — run a refresh", **empty)
    if match.status != "ok":
        status = "no_match" if match.status == "no_match" else "error"
        reason = match.reason or "Google Maps lookup failed"
        return s.GoogleReviewsBrief(status=status, explanation=reason, **{**empty, "observed_at": match.checked_at})
    rating = next((r for r in latest_ratings(session, prop) if r.source_id == "google_places"), None)
    summary = session.scalars(
        select(Evidence).where(Evidence.property_id == prop.id, Evidence.kind == "review_summary")
        .order_by(Evidence.collected_at.desc())
    ).first()
    count = rating.count if rating else None
    google_reviews = [r for r in review_inputs(session, prop) if r.source_id == "google_places" and not r.is_summary]
    comments = summarize_comments(google_reviews, utcnow())
    if rating and rating.average is not None and count:
        explanation = f"{rating.average:.1f} stars across {count} Google ratings; Google returns at most 5 review texts"
    else:
        explanation = "No Google ratings for this place"
    return s.GoogleReviewsBrief(
        status="ok",
        rating=rating.average if rating else None,
        count=count,
        maps_url=match.maps_url,
        summary=summary.content if summary else None,
        summary_disclosure=(summary.data or {}).get("summary_disclosure") if summary else None,
        summary_flag_url=(summary.data or {}).get("flag_url") if summary else None,
        comments_summary=comments.text if comments else None,
        comments_summary_method=comments.method if comments else None,
        match_confidence=match.match_confidence if match.match_confidence in ("exact", "probable", "weak") else None,
        observed_at=match.checked_at,
        explanation=explanation,
    )


def commute_brief(commute: CommuteResult | None) -> s.CommuteBrief | None:
    if commute is None:
        return None
    return s.CommuteBrief(
        distance_miles=commute.distance_miles,
        free_flow_minutes=commute.free_flow_minutes,
        am_rush_minutes=commute.am_rush_minutes,
        pm_rush_minutes=commute.pm_rush_minutes,
        rush_status=commute.rush_status,
    )


def _claims(session: Session, assessment: CategoryAssessment) -> list[Claim]:
    return list(session.scalars(select(Claim).where(Claim.assessment_id == assessment.id).order_by(Claim.weight.desc(), Claim.id)))


def highlights(session: Session, ctx: PropertyContext) -> tuple[s.Highlight | None, s.Highlight | None]:
    best: dict[str, tuple[float, Claim, str]] = {}
    for category, assessment in ctx.assessments.items():
        if category not in CATEGORIES or assessment.score is None:
            continue
        for claim in _claims(session, assessment):
            if claim.polarity not in ("positive", "negative") or not claim.is_current:
                continue
            current = best.get(claim.polarity)
            if current is None or claim.weight > current[0]:
                best[claim.polarity] = (claim.weight, claim, category)

    def make(polarity: str) -> s.Highlight | None:
        if polarity not in best:
            return None
        _, claim, category = best[polarity]
        return s.Highlight(text=claim.text, category=category, claim_id=claim.id)

    return make("positive"), make("negative")


def summary(session: Session, ctx: PropertyContext, names: SourceNames, settings: Settings) -> s.PropertySummary:
    prop = ctx.prop
    qualifying = ctx.price.qualifying
    unit_types = sorted({"studio" if q.unit.beds == 0 else "1br" for q in qualifying}, key=lambda t: t != "studio")
    rents = [q.observation.base_rent_min for q in qualifying] + [q.observation.base_rent_max or q.observation.base_rent_min for q in qualifying]
    sqfts = [v for q in qualifying for v in (q.unit.sqft_min, q.unit.sqft_max) if v]
    cost = monthly_cost(ctx)
    review, _ = review_brief(session, prop)
    scores = {}
    for category in CATEGORIES:
        assessment = ctx.assessments.get(category)
        scores[category] = s.ScoreBrief(score=assessment.score if assessment else None, confidence=assessment.confidence if assessment else "insufficient")
    positive, concern = highlights(session, ctx)
    eligibility = session.scalars(
        select(Evidence).where(Evidence.property_id == prop.id, Evidence.kind == "listing_fact", Evidence.title == "Eligibility restrictions")
    ).all()
    eligibility_notes = sorted({r for e in eligibility for r in (e.data or {}).get("restrictions", [])})
    price_status = ctx.price.status if ctx.price.status in ("verified", "conflict", "stale") else "stale"
    return s.PropertySummary(
        id=prop.id,
        name=prop.name,
        city=prop.city or "Unknown city",
        region=prop.region or "south_bay",
        street_address=prop.street_address,
        lat=prop.lat,
        lon=prop.lon,
        image_url=prop.image_url,
        image_source_name=names(prop.image_source_id) if prop.image_url else None,
        unit_types=unit_types,
        rent_min=min(rents) if rents else None,
        rent_max=max(rents) if rents else None,
        qualifying_rents=sorted({r for q in qualifying for r in (q.observation.base_rent_min, q.observation.base_rent_max) if r is not None and settings.min_rent <= r <= settings.max_rent}),
        est_monthly_total_min=cost.est_total_min,
        has_unknown_required_costs=bool(cost.unknown_required),
        has_promotion=any(q.observation.is_promotional for q in qualifying),
        sqft_min=min(sqfts) if sqfts else None,
        sqft_max=max(sqfts) if sqfts else None,
        price_status=price_status,
        last_verified_at=max((q.observation.collected_at for q in qualifying), default=None),
        commute=commute_brief(ctx.commute),
        review=review,
        overall=s.ScoreBrief(
            score=ctx.overall.score if ctx.overall else None,
            confidence=ctx.overall.confidence if ctx.overall else "insufficient",
        ),
        scores=scores,
        strongest_positive=positive,
        strongest_concern=concern,
        eligibility_notes=eligibility_notes,
        google=google_brief(session, prop, settings),
        source_ids=sorted({ls.source_id for ls in ctx.listings}),
    )


def _assessment_view(session: Session, category: str, assessment: CategoryAssessment | None, names: SourceNames, now: datetime) -> s.AssessmentView:
    label = CATEGORY_LABELS[category]
    if assessment is None:
        return s.AssessmentView(category=category, label=label, score=None, confidence="insufficient", evidence_count=0,
                                summary=NOT_EVALUATED, details={}, claims=[], audit_status="passed")
    claims = []
    for claim in _claims(session, assessment):
        evidence_ids = [link.evidence_id for link in session.scalars(select(ClaimEvidence).where(ClaimEvidence.claim_id == claim.id))]
        evidence = [session.get(Evidence, eid) for eid in evidence_ids]
        claims.append(
            s.ClaimView(
                id=claim.id, text=claim.text, polarity=claim.polarity, theme=claim.theme, is_current=claim.is_current,
                evidence=[evidence_item(e, names, now) for e in evidence if e is not None],
            )
        )
    return s.AssessmentView(
        category=category, label=label, score=assessment.score, confidence=assessment.confidence,
        evidence_count=assessment.evidence_count, summary=assessment.summary, details=assessment.details or {},
        claims=claims, audit_status="corrected" if assessment.audit_status == "corrected" else "passed",
    )


def _review_intelligence(session: Session, ctx: PropertyContext, names: SourceNames, now: datetime) -> s.ReviewIntelligence:
    reviews = session.scalars(
        select(Evidence).where(Evidence.property_id == ctx.prop.id, Evidence.kind.in_(("review", "review_summary"))).order_by(Evidence.published_at.desc())
    ).all()
    quality = ctx.assessments.get("review_quality")
    intel = (quality.details or {}).get("intelligence", {}) if quality else {}
    if quality:
        quality_view = s.ReviewQuality(confidence=quality.confidence, summary=quality.summary, details={k: v for k, v in (quality.details or {}).items() if k != "intelligence"})
    elif not reviews:
        quality_view = s.ReviewQuality(confidence="insufficient", summary="Review data: No reviews found", details={})
    else:
        quality_view = s.ReviewQuality(confidence="insufficient", summary=NOT_EVALUATED, details={})
    return s.ReviewIntelligence(
        praised=[s.ThemeStat(**t) for t in intel.get("praised", [])],
        criticized=[s.ThemeStat(**t) for t in intel.get("criticized", [])],
        recent_trends=list(intel.get("recent_trends", [])),
        outliers=[s.Outlier(**o) for o in intel.get("outliers", [])],
        quality=quality_view,
        reviews=[evidence_item(r, names, now) for r in reviews],
    )


def detail(session: Session, ctx: PropertyContext, names: SourceNames, settings: Settings, now: datetime, run: CollectionRun | None) -> s.PropertyDetail:
    base = summary(session, ctx, names, settings)
    prop = ctx.prop
    _, rating_filter = review_brief(session, prop)

    website_evidence = session.scalars(
        select(Evidence).where(Evidence.property_id == prop.id, Evidence.kind == "listing_fact", Evidence.title == "Official property website")
        .order_by(Evidence.collected_at.desc())
    ).first()
    official = (
        s.OfficialWebsite(url=website_evidence.source_url, source_id=website_evidence.source_id, source_name=names(website_evidence.source_id), evidence_id=website_evidence.id)
        if website_evidence and website_evidence.source_url else None
    )

    units = []
    for state in sorted(ctx.price.units, key=lambda st: (not st.qualifies, st.unit.beds if st.unit.beds is not None else 99, st.observation.base_rent_min or 10**6)):
        obs = state.observation
        units.append(
            s.UnitView(
                id=state.unit.id, source_id=state.source_id, source_name=names(state.source_id), label=state.unit.label,
                floorplan_name=state.unit.floorplan_name, kind=state.unit.kind, beds=state.unit.beds, baths=state.unit.baths,
                sqft_min=state.unit.sqft_min, sqft_max=state.unit.sqft_max, base_rent_min=obs.base_rent_min,
                base_rent_max=obs.base_rent_max, total_monthly=obs.total_monthly, required_fees_monthly=obs.required_fees_monthly,
                lease_term_months=obs.lease_term_months, available_on=obs.available_on, availability=obs.availability,
                is_promotional=obs.is_promotional, promotion_text=obs.promotion_text,
                effective_rent_estimate=obs.effective_rent_estimate, effective_rent_method=obs.effective_rent_method,
                collected_at=obs.collected_at, source_updated_at=obs.source_updated_at, fresh=state.fresh and state.current,
                qualifies=state.qualifies, source_url=obs.source_url,
            )
        )

    listing_source = {ls.id: ls.source_id for ls in ctx.listings}
    fees = [
        s.FeeView(
            fee_type=f.fee_type, description=f.description, amount_monthly=f.amount_monthly, amount_text=f.amount_text,
            mandatory=f.mandatory, recurring=f.recurring, source_id=listing_source.get(f.listing_source_id, "unknown"),
            source_name=names(listing_source.get(f.listing_source_id)), source_url=f.source_url, evidence_id=f.evidence_id,
        )
        for f in ctx.fees
    ]

    conflicts = [
        s.PriceConflictView(
            beds=c.beds, sqft=c.sqft, difference=c.difference,
            sides=[
                s.PriceConflictSide(source_id=p.source_id, source_name=names(p.source_id), price_min=p.base_min, price_max=p.base_max, label=p.label, url=p.source_url)
                for p in (c.a, c.b)
            ],
        )
        for c in ctx.price.conflicts
    ]

    promotions = [
        s.Promotion(text=text, source_id=ls.source_id, source_name=names(ls.source_id), url=ls.url)
        for ls in ctx.listings for text in (ls.facts or {}).get("promotions") or []
    ]

    commute_detail = None
    if ctx.commute:
        c = ctx.commute
        live = (
            f"https://www.google.com/maps/dir/?api=1&origin={prop.lat},{prop.lon}"
            f"&destination={settings.office_lat},{settings.office_lon}&travelmode=driving"
            if prop.lat is not None and prop.lon is not None else None
        )
        commute_detail = s.CommuteView(
            **commute_brief(c).model_dump(), provider=names(c.provider), methodology=c.methodology,
            confidence=c.confidence if c.confidence in ("high", "medium", "low") else "insufficient",
            computed_at=c.computed_at, source_url=c.source_url, view_url=c.view_url, live_traffic_url=live, evidence_id=c.evidence_id,
        )

    overall = ctx.overall
    overall_view = s.OverallView(
        score=overall.score if overall else None,
        confidence=overall.confidence if overall else "insufficient",
        components=[s.OverallComponent(**c) for c in (overall.components if overall else [])],
        excluded_categories=[s.ExcludedCategory(**e) for e in (overall.excluded_categories if overall else [])],
        confidence_reasons=list(overall.confidence_reasons) if overall else [NOT_EVALUATED],
    )

    ratings = [
        s.RatingSummaryView(source_id=r.source_id, source_name=names(r.source_id), average=r.average, count=r.count, source_url=r.source_url, observed_at=r.observed_at)
        for r in latest_ratings(session, prop)
    ]
    facts = session.scalars(
        select(Evidence).where(Evidence.property_id == prop.id, Evidence.kind == "listing_fact").order_by(Evidence.title)
    ).all()
    audit = [
        s.AuditView(category=a.category if a.category in CATEGORIES else None, check_name=a.check_name, severity=a.severity, action=a.action, detail=a.detail)
        for a in session.scalars(select(AuditFinding).where(AuditFinding.property_id == prop.id).order_by(AuditFinding.id))
    ]

    limitations = []
    for ls in ctx.listings:
        limitations.extend(f"{names(ls.source_id)}: {note}" for note in (ls.facts or {}).get("notes") or [])
    if ctx.commute and ctx.commute.am_rush_minutes is None:
        limitations.append(f"Rush-hour commute: {ctx.commute.rush_status}")
    google = google_brief(session, prop, settings)
    if google.status != "ok":
        limitations.append(google.explanation)
    elif google.count and google.count > 5:
        limitations.append(f"Google has {google.count} ratings for this place, but its API returns at most 5 review texts; category scores use those texts and Google's AI summary.")
    if not ratings or all(r.count == 0 for r in ratings):
        limitations.append("No resident reviews were collected from the sources checked; review-based categories cannot be scored.")
    if run:
        sources_here = {ls.source_id for ls in ctx.listings}
        limitations.extend(f"{names(l['source_id'])}: {l['message']}" for l in run.limitations or [] if l.get("source_id") in sources_here)

    return s.PropertyDetail(
        **base.model_dump(),
        zip=prop.zip,
        listings=[s.ListingLink(source_id=ls.source_id, source_name=names(ls.source_id), url=ls.url, name=ls.name, last_seen_at=ls.last_seen_at) for ls in ctx.listings],
        official_website=official,
        units=units,
        fees=fees,
        monthly_cost=monthly_cost(ctx),
        price_conflicts=conflicts,
        promotions=promotions,
        commute_detail=commute_detail,
        assessments=[_assessment_view(session, c, ctx.assessments.get(c), names, now) for c in CATEGORIES],
        overall_detail=overall_view,
        review_intelligence=_review_intelligence(session, ctx, names, now),
        rating_summaries=ratings,
        rating_filter=rating_filter,
        facts=[evidence_item(f, names, now) for f in facts],
        audit=audit,
        limitations=limitations,
    )


def run_info(run: CollectionRun | None) -> s.RunInfo | None:
    if run is None:
        return None
    return s.RunInfo(
        id=run.id, started_at=run.started_at, finished_at=run.finished_at, status=run.status,
        stats={k: int(v) for k, v in (run.stats or {}).items()}, limitations=list(run.limitations or []),
    )
