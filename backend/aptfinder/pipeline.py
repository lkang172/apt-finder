import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from aptfinder.collectors.apartment_list import ApartmentListCollector
from aptfinder.collectors.official_sites import OfficialSiteCollector, OfficialSiteTarget
from aptfinder.collectors.redfin import RedfinCollector
from aptfinder.collectors.trulia import TruliaCollector
from aptfinder.collectors.types import DiscoveryStub
from aptfinder.config import SEARCH_CITIES, SearchCity, Settings
from aptfinder.db.models import CollectionRun, Evidence, Property, utcnow
from aptfinder.geo import CORRIDOR
from aptfinder.http import FetchError, PoliteClient, SourceBlocked
from aptfinder.enrichment import attach_area_safety, collect_google_reviews, compute_commutes
from aptfinder.evaluation import area_input, commute_input, persist_assessments, rating_inputs, review_inputs
from aptfinder.evaluators import evaluate_all
from aptfinder.store import upsert_listing
from aptfinder.synthesis import DeterministicSynthesizer, Synthesizer, apply_synthesis
from aptfinder.verification import evaluate_property_status

log = logging.getLogger(__name__)

PREFILTER_MARGIN = 150
# Redfin is opt-in: it began blocking this network and syndicates the same Zillow feed as other sources.
DEFAULT_SOURCES = ("apartment_list",)
# Official sites are checked for properties that could still qualify on price.
OFFICIAL_SITE_FILTERS = {"price_and_unit_type", "price_freshness"}


@dataclass
class RunContext:
    run: CollectionRun
    settings: Settings
    client: PoliteClient
    limitations: list[dict] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def note(self, source_id: str, message: str) -> None:
        log.warning("%s: %s", source_id, message)
        self.limitations.append({"source_id": source_id, "message": message})

    def bump(self, key: str, amount: int = 1) -> None:
        self.stats[key] = self.stats.get(key, 0) + amount


def make_client(settings: Settings) -> PoliteClient:
    return PoliteClient(
        settings.data_dir,
        settings.user_agent,
        min_intervals={
            "www.apartmentlist.com": settings.apartment_list_min_interval_s,
            "www.redfin.com": settings.redfin_min_interval_s,
            "www.trulia.com": settings.trulia_min_interval_s,
            "doorway-api.knockrentals.com": settings.shared_widget_min_interval_s,
            "sightmap.com": settings.shared_widget_min_interval_s,
            "router.project-osrm.org": settings.osrm_min_interval_s,
        },
    )


def make_api_client(settings: Settings) -> PoliteClient:
    """Open-data and routing APIs ask callers to identify the application in the User-Agent."""
    return PoliteClient(
        settings.data_dir,
        settings.api_user_agent,
        min_intervals={"router.project-osrm.org": settings.osrm_min_interval_s},
        default_interval=1.0,
    )


def _stub_in_corridor(stub: DiscoveryStub) -> bool:
    if stub.lat is None or stub.lon is None:
        return True
    return any(box.contains(stub.lat, stub.lon) for box in CORRIDOR)


def _collectors(ctx: RunContext, sources: Iterable[str]) -> list:
    ttl = timedelta(hours=ctx.settings.listing_cache_ttl_hours)
    available = {
        "apartment_list": lambda: ApartmentListCollector(ctx.client, ttl),
        "redfin": lambda: RedfinCollector(ctx.client, ttl, ctx.settings.redfin_max_pages_per_city),
        "trulia": lambda: TruliaCollector(
            ctx.client, ttl, ctx.settings.trulia_max_pages_per_city, ctx.settings.max_rent, ctx.settings.allowed_bedrooms
        ),
    }
    return [available[s]() for s in sources if s in available]


def collect_listings(session: Session, ctx: RunContext, cities: Iterable[SearchCity], sources: Iterable[str]) -> None:
    settings = ctx.settings
    cap = settings.max_rent + PREFILTER_MARGIN
    for collector in _collectors(ctx, sources):
        source = collector.source_id
        stubs: dict[str, DiscoveryStub] = {}
        try:
            for city in cities:
                try:
                    for stub in collector.discover(city):
                        ctx.bump(f"{source}.discovered")
                        if stub.source_listing_id in stubs:
                            continue
                        if not stub.may_have_qualifying_unit(settings.allowed_bedrooms, cap):
                            ctx.bump(f"{source}.prefiltered_price")
                            continue
                        if not _stub_in_corridor(stub):
                            ctx.bump(f"{source}.prefiltered_geography")
                            continue
                        stubs[stub.source_listing_id] = stub
                except FetchError as exc:
                    if isinstance(exc, SourceBlocked):
                        raise
                    ctx.note(source, f"Discovery failed for {city.name}: {exc}")
        except SourceBlocked as exc:
            ctx.note(source, f"Stopped discovery after the site signaled rate limiting or blocking: {exc}")

        ctx.bump(f"{source}.candidates", len(stubs))
        for stub in stubs.values():
            try:
                listing = collector.fetch_listing(stub)
            except SourceBlocked as exc:
                ctx.note(source, f"Stopped fetching listings after the site signaled rate limiting or blocking: {exc}")
                break
            except FetchError as exc:
                ctx.note(source, f"Could not fetch {stub.url}: {exc}")
                continue
            if listing is None:
                ctx.note(source, f"Listing data not found on {stub.url}")
                continue
            if listing.city is None:
                listing.city = stub.city
            upsert_listing(session, listing, ctx.run.id, utcnow())
            session.commit()
            ctx.bump(f"{source}.listings_saved")


def official_site_targets(session: Session) -> list[tuple[Property, str]]:
    rows = session.execute(
        select(Property, Evidence.source_url)
        .join(Evidence, Evidence.property_id == Property.id)
        .where(Evidence.title == "Official property website", Evidence.source_id != "official_site", Evidence.source_url.is_not(None))
        .order_by(Property.id, Evidence.collected_at.desc())
    ).all()
    targets: dict[int, tuple[Property, str]] = {}
    for prop, url in rows:
        if prop.id in targets:
            continue
        reasons = {r.get("filter") for r in prop.exclusion_reasons or []}
        if prop.status in ("included", "needs_reverification") or reasons <= OFFICIAL_SITE_FILTERS:
            targets[prop.id] = (prop, url)
    return list(targets.values())


def collect_official_sites(session: Session, ctx: RunContext) -> None:
    collector = OfficialSiteCollector(ctx.client, timedelta(hours=ctx.settings.listing_cache_ttl_hours))
    unsupported: list[str] = []
    for prop, url in official_site_targets(session):
        ctx.bump("official_site.candidates")
        target = OfficialSiteTarget(prop.name, url, prop.street_address, prop.city, prop.zip, prop.lat, prop.lon)
        try:
            listing = collector.collect(target)
        except SourceBlocked as exc:
            ctx.note("official_site", f"{prop.name}: stopped after the site signaled rate limiting or blocking: {exc}")
            continue
        if listing is None:
            unsupported.append(prop.name)
            continue
        if listing.city is None:
            listing.city = prop.city
        upsert_listing(session, listing, ctx.run.id, utcnow(), property_hint=prop.id)
        session.commit()
        ctx.bump("official_site.listings_saved")
    if unsupported:
        ctx.note(
            "official_site",
            f"{len(unsupported)} official websites have no readable price data (unsupported or blocked leasing platform): "
            + ", ".join(sorted(unsupported)),
        )


def apply_hard_filters(session: Session, settings: Settings, now: datetime) -> dict[str, int]:
    counts: dict[str, int] = {}
    for prop in session.scalars(select(Property)):
        status = evaluate_property_status(session, prop, settings, now)
        prop.status = status.status
        prop.exclusion_reasons = status.reasons
        prop.price_status = status.price.status if status.price else None
        counts[status.status] = counts.get(status.status, 0) + 1
    session.commit()
    return counts


def _included(session: Session) -> list[Property]:
    return list(session.scalars(select(Property).where(Property.status == "included").order_by(Property.id)))


def enrich_and_evaluate(
    session: Session,
    ctx: RunContext,
    api_client: PoliteClient,
    now: datetime,
    synthesizer: Synthesizer | None = None,
) -> None:
    settings = ctx.settings
    included = _included(session)
    if settings.google_maps_api_key:
        rating_excluded = [
            p for p in session.scalars(select(Property).where(Property.status == "excluded"))
            if any(r.get("filter") == "review_rating" for r in p.exclusion_reasons or [])
        ]
        ctx.bump("google_places.properties", collect_google_reviews(session, settings, included + rating_excluded, now, ctx.note))
        ctx.stats.update({f"status_after_google.{k}": v for k, v in apply_hard_filters(session, settings, now).items()})
        included = _included(session)
    else:
        ctx.note("google_places", "Google reviews not checked: set APTFINDER_GOOGLE_MAPS_API_KEY to enable Google ratings, review summaries, and reviews")
    ctx.bump("commutes_computed", compute_commutes(session, api_client, settings, included, ctx.note))
    ctx.bump("area_safety_attached", attach_area_safety(session, api_client, settings, included, ctx.note))
    synthesizer = synthesizer or DeterministicSynthesizer()
    for prop in included:
        reviews = review_inputs(session, prop)
        drafts = evaluate_all(reviews, rating_inputs(session, prop), commute_input(session, prop), area_input(session, prop), now)
        quality = drafts.pop("review_quality", None)
        apply_synthesis(synthesizer, drafts, reviews)
        persist_assessments(session, prop, drafts, ctx.run.id, now, review_quality=quality)
        session.commit()
        ctx.bump("properties_evaluated")


def start_run(session: Session) -> CollectionRun:
    run = CollectionRun(started_at=utcnow(), status="running")
    session.add(run)
    session.commit()
    return run


def finish_run(session: Session, ctx: RunContext, failed: bool = False) -> None:
    ctx.run.finished_at = utcnow()
    ctx.run.stats = ctx.stats
    ctx.run.limitations = ctx.limitations
    ctx.run.status = "failed" if failed else ("completed_with_limitations" if ctx.limitations else "completed")
    session.commit()


def resolve_cities(names: Iterable[str] | None) -> list[SearchCity]:
    if not names:
        return list(SEARCH_CITIES)
    wanted = {n.strip().lower() for n in names}
    return [c for c in SEARCH_CITIES if c.name.lower() in wanted]


def execute_run(
    run_id: int,
    settings: Settings,
    cities: Iterable[str] | None = None,
    sources: Iterable[str] = DEFAULT_SOURCES,
    skip_collection: bool = False,
) -> RunContext:
    sources = list(sources)
    from aptfinder.db.session import session_scope

    client = make_client(settings)
    api_client = make_api_client(settings)
    with session_scope() as session:
        run = session.get(CollectionRun, run_id)
        ctx = RunContext(run, settings, client)
        try:
            if not skip_collection:
                collect_listings(session, ctx, resolve_cities(cities), sources)
            ctx.stats.update({f"status.{k}": v for k, v in apply_hard_filters(session, settings, utcnow()).items()})
            if not skip_collection and "official_site" in sources:
                collect_official_sites(session, ctx)
                ctx.stats.update({f"status_after_official_sites.{k}": v for k, v in apply_hard_filters(session, settings, utcnow()).items()})
            enrich_and_evaluate(session, ctx, api_client, utcnow())
            ctx.stats["network_requests"] = client.network_requests + api_client.network_requests
            finish_run(session, ctx)
        except Exception as exc:
            log.exception("Run %s failed", run_id)
            session.rollback()
            ctx.note("aptfinder", f"Run failed: {exc}")
            ctx.stats["network_requests"] = client.network_requests + api_client.network_requests
            finish_run(session, ctx, failed=True)
            raise
        finally:
            client.close()
            api_client.close()
    return ctx
