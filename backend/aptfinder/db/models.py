from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Stores UTC; SQLite drops tzinfo, so it is reattached on load."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetimes are not allowed")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: UTCDateTime, dict[str, Any]: JSON, list[Any]: JSON}


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32))
    homepage_url: Mapped[str | None] = mapped_column(String(500))


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(String(32), default="running")
    stats: Mapped[dict[str, Any]] = mapped_column(default=dict)
    limitations: Mapped[list[Any]] = mapped_column(default=list)


class RawDocument(Base):
    __tablename__ = "raw_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    url: Mapped[str] = mapped_column(String(2000))
    fetched_at: Mapped[datetime]
    http_status: Mapped[int]
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_path: Mapped[str] = mapped_column(String(500))


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    street_address: Mapped[str | None] = mapped_column(String(300))
    normalized_address: Mapped[str | None] = mapped_column(String(300), index=True)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(2))
    zip: Mapped[str | None] = mapped_column(String(10))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    geo_source: Mapped[str | None] = mapped_column(String(64))
    region: Mapped[str | None] = mapped_column(String(32))
    image_url: Mapped[str | None] = mapped_column(String(1000))
    image_source_id: Mapped[str | None] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    status: Mapped[str] = mapped_column(String(32), default="candidate")
    exclusion_reasons: Mapped[list[Any]] = mapped_column(default=list)
    price_status: Mapped[str | None] = mapped_column(String(32))

    listing_sources: Mapped[list["ListingSource"]] = relationship(back_populates="property")


class ListingSource(Base):
    __tablename__ = "listing_sources"
    __table_args__ = (UniqueConstraint("source_id", "source_listing_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    source_listing_id: Mapped[str] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(2000))
    name: Mapped[str | None] = mapped_column(String(300))
    street_address: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(100))
    zip: Mapped[str | None] = mapped_column(String(10))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    facts: Mapped[dict[str, Any]] = mapped_column(default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_raw_document_id: Mapped[int | None] = mapped_column(ForeignKey("raw_documents.id"))

    property: Mapped[Property] = relationship(back_populates="listing_sources")
    source: Mapped[Source] = relationship()


class Unit(Base):
    __tablename__ = "units"
    __table_args__ = (UniqueConstraint("listing_source_id", "source_unit_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_source_id: Mapped[int] = mapped_column(ForeignKey("listing_sources.id"), index=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    source_unit_key: Mapped[str] = mapped_column(String(200))
    label: Mapped[str | None] = mapped_column(String(200))
    floorplan_name: Mapped[str | None] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16))
    beds: Mapped[int | None]
    baths: Mapped[float | None] = mapped_column(Float)
    sqft_min: Mapped[int | None]
    sqft_max: Mapped[int | None]


class PriceObservation(Base):
    __tablename__ = "price_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    listing_source_id: Mapped[int] = mapped_column(ForeignKey("listing_sources.id"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("collection_runs.id"))
    collected_at: Mapped[datetime]
    source_updated_at: Mapped[datetime | None]
    base_rent_min: Mapped[int | None]
    base_rent_max: Mapped[int | None]
    total_monthly: Mapped[float | None] = mapped_column(Float)
    required_fees_monthly: Mapped[float | None] = mapped_column(Float)
    lease_term_months: Mapped[int | None]
    available_on: Mapped[str | None] = mapped_column(String(10))
    availability: Mapped[str | None] = mapped_column(String(32))
    is_promotional: Mapped[bool] = mapped_column(Boolean, default=False)
    promotion_text: Mapped[str | None] = mapped_column(Text)
    effective_rent_estimate: Mapped[int | None]
    effective_rent_method: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    raw_document_id: Mapped[int | None] = mapped_column(ForeignKey("raw_documents.id"))
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"))


class FeeObservation(Base):
    __tablename__ = "fee_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    listing_source_id: Mapped[int] = mapped_column(ForeignKey("listing_sources.id"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("collection_runs.id"))
    collected_at: Mapped[datetime]
    fee_type: Mapped[str] = mapped_column(String(32))
    amount_monthly: Mapped[int | None]
    amount_text: Mapped[str | None] = mapped_column(String(200))
    mandatory: Mapped[bool | None] = mapped_column(Boolean)
    recurring: Mapped[bool | None] = mapped_column(Boolean)
    description: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"))


class Evidence(Base):
    """Canonical evidence record. IDs are deterministic so refreshes update rather than duplicate."""

    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    source_url: Mapped[str | None] = mapped_column(String(2000))
    source_page_url: Mapped[str | None] = mapped_column(String(2000))
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    categories: Mapped[list[Any]] = mapped_column(default=list)
    published_at: Mapped[datetime | None]
    first_collected_at: Mapped[datetime] = mapped_column(default=utcnow)
    collected_at: Mapped[datetime] = mapped_column(default=utcnow)
    is_derived: Mapped[bool] = mapped_column(Boolean, default=False)
    derived_from: Mapped[list[Any]] = mapped_column(default=list)
    raw_document_id: Mapped[int | None] = mapped_column(ForeignKey("raw_documents.id"))

    source: Mapped[Source] = relationship()


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("source_id", "source_review_key"),)

    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id"), primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    source_review_key: Mapped[str] = mapped_column(String(200))
    reviewer: Mapped[str | None] = mapped_column(String(200))
    rating: Mapped[float | None] = mapped_column(Float)
    rating_scale: Mapped[float] = mapped_column(Float, default=5.0)
    review_date: Mapped[datetime | None]
    text: Mapped[str] = mapped_column(Text, default="")
    subscores: Mapped[dict[str, Any]] = mapped_column(default=dict)
    review_url: Mapped[str | None] = mapped_column(String(2000))
    source_page_url: Mapped[str | None] = mapped_column(String(2000))
    extra: Mapped[dict[str, Any]] = mapped_column(default=dict)
    collected_at: Mapped[datetime] = mapped_column(default=utcnow)


class RatingSummary(Base):
    __tablename__ = "rating_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    average: Mapped[float | None] = mapped_column(Float)
    count: Mapped[int]
    scale: Mapped[float] = mapped_column(Float, default=5.0)
    observed_at: Mapped[datetime]
    source_url: Mapped[str | None] = mapped_column(String(2000))
    match_confidence: Mapped[str] = mapped_column(String(16), default="exact")
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"))


class GooglePlaceMatch(Base):
    """Outcome of the latest Google Maps lookup for a property, including failures to match."""

    __tablename__ = "google_place_matches"

    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    place_id: Mapped[str | None] = mapped_column(String(200))
    display_name: Mapped[str | None] = mapped_column(String(300))
    formatted_address: Mapped[str | None] = mapped_column(String(300))
    maps_url: Mapped[str | None] = mapped_column(String(2000))
    distance_meters: Mapped[float | None] = mapped_column(Float)
    match_confidence: Mapped[str | None] = mapped_column(String(16))
    checked_at: Mapped[datetime]
    reason: Mapped[str | None] = mapped_column(Text)


class CommuteResult(Base):
    __tablename__ = "commute_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    distance_miles: Mapped[float | None] = mapped_column(Float)
    free_flow_minutes: Mapped[float | None] = mapped_column(Float)
    am_rush_minutes: Mapped[float | None] = mapped_column(Float)
    pm_rush_minutes: Mapped[float | None] = mapped_column(Float)
    rush_status: Mapped[str] = mapped_column(Text)
    computed_at: Mapped[datetime]
    source_url: Mapped[str | None] = mapped_column(String(2000))
    view_url: Mapped[str | None] = mapped_column(String(2000))
    methodology: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(16))
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"))


class CategoryAssessment(Base):
    __tablename__ = "category_assessments"
    __table_args__ = (UniqueConstraint("property_id", "category"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("collection_runs.id"))
    category: Mapped[str] = mapped_column(String(32))
    score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String(16))
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    positive_evidence_ids: Mapped[list[Any]] = mapped_column(default=list)
    negative_evidence_ids: Mapped[list[Any]] = mapped_column(default=list)
    computed_at: Mapped[datetime] = mapped_column(default=utcnow)
    audit_status: Mapped[str] = mapped_column(String(16), default="pending")

    claims: Mapped[list["Claim"]] = relationship(back_populates="assessment", cascade="all, delete-orphan")


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("category_assessments.id"), index=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    polarity: Mapped[str] = mapped_column(String(16))
    theme: Mapped[str | None] = mapped_column(String(64))
    weight: Mapped[float] = mapped_column(Float, default=0.0)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

    assessment: Mapped[CategoryAssessment] = relationship(back_populates="claims")
    evidence_links: Mapped[list["ClaimEvidence"]] = relationship(cascade="all, delete-orphan")


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"

    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), default="supports")


class OverallScore(Base):
    __tablename__ = "overall_scores"

    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("collection_runs.id"))
    score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String(16))
    components: Mapped[list[Any]] = mapped_column(default=list)
    excluded_categories: Mapped[list[Any]] = mapped_column(default=list)
    confidence_reasons: Mapped[list[Any]] = mapped_column(default=list)
    computed_at: Mapped[datetime] = mapped_column(default=utcnow)


class AuditFinding(Base):
    __tablename__ = "audit_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    category: Mapped[str | None] = mapped_column(String(32))
    check_name: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
