from aptfinder import pipeline
from aptfinder.collectors.types import DiscoveryStub
from aptfinder.config import SEARCH_CITIES, Settings
from aptfinder.http import FetchError
from aptfinder.pipeline import RunContext, collect_listings, start_run


class DownCollector:
    source_id = "fake"

    def __init__(self):
        self.fetches = 0

    def discover(self, city):
        for i in range(8):
            yield DiscoveryStub("fake", f"id{i}", f"https://fake.example/{i}", f"Listing {i}", None, None, city.name, {1: 2500})

    def fetch_listing(self, stub):
        self.fetches += 1
        raise FetchError(f"could not fetch {stub.url}: no route")


def test_repeated_fetch_failures_stop_the_source(session, monkeypatch):
    collector = DownCollector()
    monkeypatch.setattr(pipeline, "_collectors", lambda ctx, sources: [collector])
    ctx = RunContext(start_run(session), Settings(_env_file=None), None)
    collect_listings(session, ctx, [SEARCH_CITIES[0]], ["fake"])
    assert ctx.stats["fake.candidates"] == 8
    assert collector.fetches == pipeline.MAX_CONSECUTIVE_FETCH_FAILURES
    assert any("consecutive fetch failures" in note["message"] for note in ctx.limitations)
