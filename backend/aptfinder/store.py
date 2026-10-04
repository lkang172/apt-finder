from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from aptfinder.collectors.types import CollectedListing, CollectedUnit
from aptfinder.db.models import (
    Evidence,
    FeeObservation,
    ListingSource,
    PriceObservation,
    Property,
    RatingSummary,
    RawDocument,
    Review,
    Unit,
    utcnow,
)
from aptfinder.dedupe import PropertyKey, key_for, match_property
from aptfinder.geo import evaluate_location
from aptfinder.ids import stable_id
from aptfinder.normalize import estimate_effective_rent, normalize_street_address, parse_promotion

BEDS_LABEL = {0: "Studio", 1: "1 bedroom"}


def record_raw_document(session: Session, source_id: str, listing: CollectedListing) -> RawDocument:
    fetch = listing.fetch
    existing = session.scalar(
        select(RawDocument).where(RawDocument.url == fetch.url, RawDocument.content_sha256 == fetch.content_sha256)
    )
    if existing:
        return existing
    doc = RawDocument(
        source_id=source_id,
        url=fetch.url,
        fetched_at=fetch.fetched_at,
        http_status=fetch.status,
        content_sha256=fetch.content_sha256,
        storage_path=fetch.storage_path,
    )
    session.add(doc)
    session.flush()
    return doc


def _property_keys(session: Session) -> list[PropertyKey]:
    return [
        key_for(p.id, p.name, p.street_address, p.zip, p.city, p.lat, p.lon)
        for p in session.scalars(select(Property))
    ]


def resolve_property(session: Session, listing: CollectedListing) -> tuple[Property, str]:
    existing_link = session.scalar(
        select(ListingSource).where(
            ListingSource.source_id == listing.source_id,
            ListingSource.source_listing_id == listing.source_listing_id,
        )
    )
    if existing_link:
        return existing_link.property, "previously linked listing"

    candidate = key_for(0, listing.name, listing.street_address, listing.zip, listing.city, listing.lat, listing.lon)
    match = match_property(candidate, _property_keys(session))
    if match:
        return session.get(Property, match.property_id), match.reason

    decision = evaluate_location(listing.city, listing.lat, listing.lon)
    prop = Property(
        name=listing.name,
        street_address=listing.street_address,
        normalized_address=normalize_street_address(listing.street_address),
        city=listing.city,
        state=listing.state or "CA",
        zip=listing.zip,
        lat=listing.lat,
        lon=listing.lon,
        geo_source=listing.source_id if listing.lat is not None else None,
        region=decision.region,
    )
    session.add(prop)
    session.flush()
    return prop, "new property"


def _refresh_property_fields(prop: Property, listing: CollectedListing, now: datetime) -> None:
    prop.last_seen_at = now
    prefer_listing = listing.source_id == "apartment_list" or prop.geo_source is None
    if prefer_listing:
        prop.name = listing.name or prop.name
        prop.street_address = listing.street_address or prop.street_address
        prop.normalized_address = normalize_street_address(prop.street_address)
        prop.city = listing.city or prop.city
        prop.zip = listing.zip or prop.zip
        if listing.lat is not None and listing.lon is not None:
            prop.lat, prop.lon, prop.geo_source = listing.lat, listing.lon, listing.source_id
    if listing.image_url and (prop.image_url is None or listing.source_id == "apartment_list"):
        prop.image_url, prop.image_source_id = listing.image_url, listing.source_id
    prop.region = evaluate_location(prop.city, prop.lat, prop.lon).region


def _upsert_evidence(session: Session, evidence_id: str, **fields) -> Evidence:
    evidence = session.get(Evidence, evidence_id)
    if evidence is None:
        evidence = Evidence(id=evidence_id, first_collected_at=fields.get("collected_at") or utcnow(), **fields)
        session.add(evidence)
    else:
        for key, value in fields.items():
            setattr(evidence, key, value)
    return evidence


def _price_content(listing: CollectedListing, unit: CollectedUnit) -> str:
    beds = BEDS_LABEL.get(unit.beds, f"{unit.beds} bedroom") if unit.beds is not None else "Unknown bedrooms"
    where = f"unit {unit.label}" if unit.label else f"floor plan {unit.floorplan_name or 'unnamed'}"
    if unit.base_rent_min is not None:
        rent = f"${unit.base_rent_min:,}" if unit.base_rent_min == unit.base_rent_max else f"${unit.base_rent_min:,}–${unit.base_rent_max:,}"
        text = f"{beds}, {where}: advertised base rent {rent}"
    else:
        text = f"{beds}, {where}: total price ${unit.total_monthly:,.0f} (base rent not published separately)"
    if unit.total_monthly and unit.base_rent_min is not None and unit.total_monthly != unit.base_rent_min:
        text += f"; published total ${unit.total_monthly:,.2f} including ${unit.required_fees_monthly or 0:,.2f} required monthly fees"
    if unit.lease_term_months:
        text += f"; {unit.lease_term_months}-month lease"
    if unit.sqft_min:
        text += f"; {unit.sqft_min:,} sq ft" if unit.sqft_min == unit.sqft_max else f"; {unit.sqft_min:,}–{unit.sqft_max:,} sq ft"
    return text


def upsert_listing(session: Session, listing: CollectedListing, run_id: int | None, now: datetime | None = None) -> tuple[Property, ListingSource]:
    now = now or utcnow()
    collected_at = listing.fetch.fetched_at
    raw = record_raw_document(session, listing.source_id, listing)
    prop, _reason = resolve_property(session, listing)
    _refresh_property_fields(prop, listing, now)

    link = session.scalar(
        select(ListingSource).where(
            ListingSource.source_id == listing.source_id,
            ListingSource.source_listing_id == listing.source_listing_id,
        )
    )
    if link is None:
        link = ListingSource(property_id=prop.id, source_id=listing.source_id, source_listing_id=listing.source_listing_id, first_seen_at=now)
        session.add(link)
    link.url = listing.url
    link.name = listing.name
    link.street_address = listing.street_address
    link.city = listing.city
    link.zip = listing.zip
    link.lat = listing.lat
    link.lon = listing.lon
    link.last_seen_at = now
    link.last_raw_document_id = raw.id
    link.facts = {
        "official_website_url": listing.official_website_url,
        "promotions": listing.promotions,
        "notes": listing.notes,
        "source_updated_at": listing.source_updated_at.isoformat() if listing.source_updated_at else None,
    }
    session.flush()

    common = {"property_id": prop.id, "source_id": listing.source_id, "collected_at": collected_at, "raw_document_id": raw.id}

    if listing.official_website_url:
        _upsert_evidence(
            session, stable_id("ev", listing.source_id, listing.source_listing_id, "official_website"),
            kind="listing_fact", source_url=listing.official_website_url, source_page_url=listing.url,
            title="Official property website", content=f"{listing.name} lists its official website as {listing.official_website_url}",
            categories=["listing"], data={"key": "official_website"}, **common,
        )
    for fact in listing.facts:
        _upsert_evidence(
            session, stable_id("ev", listing.source_id, listing.source_listing_id, "fact", fact.key),
            kind="listing_fact", source_url=fact.url or listing.url, source_page_url=listing.url,
            title=fact.title, content=fact.content, categories=fact.categories, data={"key": fact.key, **fact.data}, **common,
        )

    promotion_text = " | ".join(listing.promotions) or None
    promotion = parse_promotion(promotion_text)
    for collected in listing.units:
        unit = session.scalar(select(Unit).where(Unit.listing_source_id == link.id, Unit.source_unit_key == collected.source_unit_key))
        if unit is None:
            unit = Unit(listing_source_id=link.id, property_id=prop.id, source_unit_key=collected.source_unit_key, kind=collected.kind)
            session.add(unit)
        unit.property_id = prop.id
        unit.label = collected.label
        unit.floorplan_name = collected.floorplan_name
        unit.kind = collected.kind
        unit.beds = collected.beds
        unit.baths = collected.baths
        unit.sqft_min = collected.sqft_min
        unit.sqft_max = collected.sqft_max
        session.flush()

        evidence_id = stable_id("ev", "price", listing.source_id, listing.source_listing_id, collected.source_unit_key, listing.fetch.content_sha256)
        if session.get(Evidence, evidence_id) is not None:
            continue
        effective, method = (None, None)
        if collected.base_rent_min is not None:
            effective, method = estimate_effective_rent(collected.base_rent_min, collected.lease_term_months, promotion)
        _upsert_evidence(
            session, evidence_id, kind="price", source_url=listing.url, source_page_url=listing.url,
            title="Advertised price", content=_price_content(listing, collected), categories=["price"],
            data={"unit_key": collected.source_unit_key, "beds": collected.beds, "base_rent_min": collected.base_rent_min,
                  "base_rent_max": collected.base_rent_max, "total_monthly": collected.total_monthly},
            published_at=collected.source_updated_at, **common,
        )
        session.add(
            PriceObservation(
                unit_id=unit.id, property_id=prop.id, listing_source_id=link.id, run_id=run_id,
                collected_at=collected_at, source_updated_at=collected.source_updated_at,
                base_rent_min=collected.base_rent_min, base_rent_max=collected.base_rent_max,
                total_monthly=collected.total_monthly, required_fees_monthly=collected.required_fees_monthly,
                lease_term_months=collected.lease_term_months, available_on=collected.available_on,
                availability=collected.availability, is_promotional=promotion is not None, promotion_text=promotion_text,
                effective_rent_estimate=effective, effective_rent_method=method, source_url=listing.url,
                raw_document_id=raw.id, evidence_id=evidence_id,
            )
        )

    for fee in listing.fees:
        evidence_id = stable_id("ev", "fee", listing.source_id, listing.source_listing_id, fee.description, listing.fetch.content_sha256)
        if session.get(Evidence, evidence_id) is not None:
            continue
        _upsert_evidence(
            session, evidence_id, kind="fee", source_url=listing.url, source_page_url=listing.url,
            title=f"Fee disclosure ({fee.fee_type})", content=fee.description, categories=["price", "fees"],
            data={"fee_type": fee.fee_type, "amount": fee.amount, "recurring": fee.recurring, "mandatory": fee.mandatory}, **common,
        )
        session.add(
            FeeObservation(
                property_id=prop.id, listing_source_id=link.id, run_id=run_id, collected_at=collected_at,
                fee_type=fee.fee_type, amount_monthly=fee.amount if fee.recurring else None, amount_text=fee.amount_text,
                mandatory=fee.mandatory, recurring=fee.recurring, description=fee.description,
                source_url=listing.url, evidence_id=evidence_id,
            )
        )

    for review in listing.reviews:
        evidence_id = stable_id("ev", "review", listing.source_id, review.source_review_key)
        page_url = listing.rating.source_url if listing.rating and listing.rating.source_url else listing.url
        review_categories = ["noise", "management", "pests", "building_safety", "neighborhood_safety", "other_issues", "review_quality"]
        _upsert_evidence(
            session, evidence_id, kind="review", source_url=review.review_url, source_page_url=page_url,
            title=f"Review by {review.reviewer or 'anonymous reviewer'}", content=review.text or "(rating only, no text)",
            categories=review_categories,
            data={"rating": review.rating, "reviewer": review.reviewer, "subscores": review.subscores, **review.extra},
            published_at=review.review_date, property_id=prop.id, source_id=listing.source_id,
            collected_at=collected_at, raw_document_id=raw.id,
        )
        existing_review = session.get(Review, evidence_id)
        if existing_review is None:
            session.add(
                Review(
                    evidence_id=evidence_id, property_id=prop.id, source_id=listing.source_id,
                    source_review_key=review.source_review_key, reviewer=review.reviewer, rating=review.rating,
                    review_date=review.review_date, text=review.text, subscores=review.subscores,
                    review_url=review.review_url, source_page_url=page_url, extra=review.extra, collected_at=collected_at,
                )
            )
        else:
            existing_review.property_id = prop.id

    if listing.rating is not None:
        rating = listing.rating
        evidence_id = stable_id("ev", "rating", listing.source_id, listing.source_listing_id, listing.fetch.content_sha256)
        if session.get(Evidence, evidence_id) is None:
            content = (
                f"{rating.average:.1f} / {rating.scale:g} average across {rating.count} review(s)"
                if rating.average is not None and rating.count
                else "No reviews listed"
            )
            if rating.note:
                content += f" — {rating.note}"
            _upsert_evidence(
                session, evidence_id, kind="rating_summary", source_url=rating.source_url, source_page_url=listing.url,
                title="Review rating summary", content=content, categories=["review_quality"],
                data={"average": rating.average, "count": rating.count, "scale": rating.scale}, **common,
            )
            session.add(
                RatingSummary(
                    property_id=prop.id, source_id=listing.source_id, average=rating.average, count=rating.count,
                    scale=rating.scale, observed_at=collected_at, source_url=rating.source_url, evidence_id=evidence_id,
                )
            )
    session.flush()
    return prop, link
