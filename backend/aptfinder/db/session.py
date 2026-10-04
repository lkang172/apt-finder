from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from aptfinder.config import get_settings
from aptfinder.db.models import Base, Source

KNOWN_SOURCES: tuple[tuple[str, str, str, str | None], ...] = (
    ("apartment_list", "Apartment List", "listing", "https://www.apartmentlist.com"),
    ("redfin", "Redfin Rentals", "listing", "https://www.redfin.com"),
    ("trulia", "Trulia Rentals (Zillow feed)", "listing", "https://www.trulia.com"),
    ("official_site", "Official property website", "listing", None),
    ("google_places", "Google Maps (Places API)", "review", "https://maps.google.com"),
    ("osrm", "OSRM routing (OpenStreetMap data)", "routing", "https://project-osrm.org"),
    ("google_routes", "Google Routes API", "routing", "https://developers.google.com/maps/documentation/routes"),
    ("ca_doj", "California DOJ OpenJustice — Crimes and Clearances", "safety", "https://openjustice.doj.ca.gov"),
    ("ca_dof", "California Department of Finance — E-1 Population Estimates", "population", "https://dof.ca.gov"),
    ("census_geocoder", "U.S. Census Bureau Geocoder", "geocoding", "https://geocoding.geo.census.gov"),
    ("aptfinder", "Apt Finder derived computation", "derived", None),
)


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def make_engine(url: str | None = None) -> Engine:
    settings = get_settings()
    resolved = url or settings.resolved_database_url
    if resolved.startswith("sqlite:///") and ":memory:" not in resolved:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(resolved, connect_args={"check_same_thread": False} if resolved.startswith("sqlite") else {})
    _enable_sqlite_foreign_keys(engine)
    return engine


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for source_id, name, kind, homepage in KNOWN_SOURCES:
            if session.get(Source, source_id) is None:
                session.add(Source(id=source_id, name=name, kind=kind, homepage_url=homepage))
        session.commit()


_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _factory
    if _engine is None:
        _engine = make_engine()
        init_db(_engine)
        _factory = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def use_engine(engine: Engine) -> None:
    global _engine, _factory
    init_db(engine)
    _engine = engine
    _factory = sessionmaker(engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    get_engine()
    assert _factory is not None
    session = _factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
