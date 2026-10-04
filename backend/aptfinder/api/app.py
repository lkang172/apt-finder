import threading
from datetime import timedelta

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from aptfinder.api import schemas as s
from aptfinder.api import views
from aptfinder.config import get_settings
from aptfinder.db.models import CollectionRun, Evidence, Property, Source, utcnow
from aptfinder.db.session import session_scope
from aptfinder.pipeline import execute_run, start_run

app = FastAPI(title="Apt Finder API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], allow_methods=["*"], allow_headers=["*"])

STALE_RUN_AFTER = timedelta(hours=6)
_run_lock = threading.Lock()


def _latest_run(session) -> CollectionRun | None:
    return session.scalars(select(CollectionRun).order_by(CollectionRun.id.desc())).first()


@app.get("/api/properties", response_model=s.PropertyListResponse)
def list_properties() -> s.PropertyListResponse:
    settings = get_settings()
    now = utcnow()
    with session_scope() as session:
        names = views.SourceNames(session)
        props = session.scalars(select(Property).where(Property.status == "included").order_by(Property.name)).all()
        items = [views.summary(session, views.load_context(session, p, settings, now), names, settings) for p in props]
        items = [i for i in items if i.unit_types]
        return s.PropertyListResponse(
            items=items,
            total=len(items),
            cities=sorted({i.city for i in items}),
            last_run=views.run_info(_latest_run(session)),
        )


@app.get("/api/properties/{property_id}", response_model=s.PropertyDetail)
def get_property(property_id: int) -> s.PropertyDetail:
    settings = get_settings()
    now = utcnow()
    with session_scope() as session:
        prop = session.get(Property, property_id)
        if prop is None:
            raise HTTPException(404, "Property not found")
        names = views.SourceNames(session)
        return views.detail(session, views.load_context(session, prop, settings, now), names, settings, now, _latest_run(session))


@app.get("/api/evidence/{evidence_id}", response_model=s.EvidenceItem)
def get_evidence(evidence_id: str) -> s.EvidenceItem:
    with session_scope() as session:
        evidence = session.get(Evidence, evidence_id)
        if evidence is None:
            raise HTTPException(404, "Evidence not found")
        return views.evidence_item(evidence, views.SourceNames(session), utcnow())


@app.get("/api/excluded", response_model=list[s.ExcludedProperty])
def list_excluded() -> list[s.ExcludedProperty]:
    with session_scope() as session:
        props = session.scalars(
            select(Property).where(Property.status.in_(("excluded", "needs_reverification"))).order_by(Property.city, Property.name)
        ).all()
        return [
            s.ExcludedProperty(id=p.id, name=p.name, city=p.city, reasons=[s.ExclusionReason(**r) for r in p.exclusion_reasons or []])
            for p in props
        ]


@app.get("/api/runs/latest", response_model=s.RunInfo | None)
def latest_run() -> s.RunInfo | None:
    with session_scope() as session:
        return views.run_info(_latest_run(session))


@app.post("/api/runs", response_model=s.RunStarted, status_code=202)
def trigger_run() -> s.RunStarted:
    if not _run_lock.acquire(blocking=False):
        raise HTTPException(409, "A refresh is already running")
    try:
        with session_scope() as session:
            current = _latest_run(session)
            if current and current.status == "running" and utcnow() - current.started_at < STALE_RUN_AFTER:
                raise HTTPException(409, "A refresh is already running")
            run_id = start_run(session).id
    except Exception:
        _run_lock.release()
        raise

    def work() -> None:
        try:
            execute_run(run_id, get_settings())
        finally:
            _run_lock.release()

    threading.Thread(target=work, name=f"aptfinder-run-{run_id}", daemon=True).start()
    return s.RunStarted(run_id=run_id)


@app.get("/api/meta", response_model=s.Meta)
def meta() -> s.Meta:
    settings = get_settings()
    with session_scope() as session:
        sources = [
            s.SourceInfo(id=src.id, name=src.name, kind=src.kind, homepage_url=src.homepage_url)
            for src in session.scalars(select(Source).order_by(Source.kind, Source.name))
        ]
    return s.Meta(
        office=s.OfficeInfo(label=settings.office_label, address=settings.office_address, lat=settings.office_lat, lon=settings.office_lon),
        search=s.SearchInfo(min_rent=settings.min_rent, max_rent=settings.max_rent, unit_types=["studio", "1br"]),
        sources=sources,
    )
