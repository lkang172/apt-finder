from datetime import timedelta

import httpx
import pytest

from aptfinder.http import FetchError, PoliteClient, RobotsDisallowed, SourceBlocked

ROBOTS = "User-agent: *\nDisallow: /private/\n"


class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_client(tmp_path, handler, interval=4.0):
    fake = FakeTime()
    client = PoliteClient(
        tmp_path,
        "test-agent",
        min_intervals={"example.com": interval},
        transport=httpx.MockTransport(handler),
        sleep=fake.sleep,
        clock=fake.clock,
    )
    return client, fake


def test_robots_disallow_is_enforced(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        return httpx.Response(200, text="ok")

    client, _ = make_client(tmp_path, handler)
    with pytest.raises(RobotsDisallowed):
        client.get("https://example.com/private/page", ttl=timedelta(hours=1))
    assert client.get("https://example.com/public", ttl=timedelta(hours=1)).text == "ok"


def test_missing_robots_allows_everything(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text="ok")

    client, _ = make_client(tmp_path, handler)
    assert client.get("https://example.com/private/x", ttl=timedelta(hours=1)).status == 200


def test_429_blocks_host_for_rest_of_run(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="")
        return httpx.Response(429, headers={"retry-after": "60"})

    client, _ = make_client(tmp_path, handler)
    with pytest.raises(SourceBlocked):
        client.get("https://example.com/a", ttl=timedelta(hours=1))
    with pytest.raises(SourceBlocked):
        client.get("https://example.com/b", ttl=timedelta(hours=1))
    assert calls.count("/b") == 0
    assert "example.com" in client.blocked_hosts


def test_ratelimit_redirect_blocks_host(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="")
        return httpx.Response(302, headers={"location": "https://ratelimited.example.com/"})

    client, _ = make_client(tmp_path, handler)
    with pytest.raises(SourceBlocked):
        client.get("https://example.com/a", ttl=timedelta(hours=1))


def test_challenge_page_blocks_host(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="")
        return httpx.Response(200, text="<html><title>Client Challenge</title></html>")

    client, _ = make_client(tmp_path, handler)
    with pytest.raises(SourceBlocked):
        client.get("https://example.com/a", ttl=timedelta(hours=1))


def test_cache_hit_within_ttl_skips_network(tmp_path):
    hits = []

    def handler(request):
        hits.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="")
        return httpx.Response(200, text="page body")

    client, _ = make_client(tmp_path, handler)
    first = client.get("https://example.com/p", ttl=timedelta(hours=1))
    second = client.get("https://example.com/p", ttl=timedelta(hours=1))
    assert not first.from_cache and second.from_cache
    assert second.text == "page body"
    assert hits.count("/p") == 1
    assert (tmp_path / "raw" / first.storage_path).exists()


def test_requests_to_same_host_are_spaced(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="")
        return httpx.Response(200, text=request.url.path)

    client, fake = make_client(tmp_path, handler, interval=4.0)
    client.get("https://example.com/1", ttl=timedelta(0))
    client.get("https://example.com/2", ttl=timedelta(0))
    client.get("https://example.com/3", ttl=timedelta(0))
    assert len(fake.sleeps) >= 2
    assert all(s >= 4.0 for s in fake.sleeps)


def test_cross_host_redirect_is_not_followed(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="")
        return httpx.Response(301, headers={"location": "https://other.com/x"})

    client, _ = make_client(tmp_path, handler)
    with pytest.raises(FetchError):
        client.get("https://example.com/a", ttl=timedelta(hours=1))
    assert "example.com" not in client.blocked_hosts


def test_aws_waf_interstitial_blocks_and_is_not_cached(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="")
        return httpx.Response(202, text="<script>window.awsWafCookieDomainList = ['example.com'];</script>")

    client, _ = make_client(tmp_path, handler)
    with pytest.raises(SourceBlocked):
        client.get("https://example.com/a", ttl=timedelta(hours=1))
    assert not list((tmp_path / "http_cache").glob("*.json")) or all(
        '"status": 200' in p.read_text() for p in (tmp_path / "http_cache").glob("*.json")
    )


def test_bare_202_without_markers_still_blocks(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="")
        return httpx.Response(202, text="<html></html>")

    client, _ = make_client(tmp_path, handler)
    with pytest.raises(SourceBlocked):
        client.get("https://example.com/a", ttl=timedelta(hours=1))


def test_non_200_cache_entries_are_ignored(tmp_path):
    import json

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="")
        return httpx.Response(200, text="real content")

    client, _ = make_client(tmp_path, handler)
    first = client.get("https://example.com/p", ttl=timedelta(hours=1))
    meta = next(p for p in (tmp_path / "http_cache").glob("*.json") if json.loads(p.read_text())["url"].endswith("/p"))
    data = json.loads(meta.read_text())
    data["status"] = 202
    meta.write_text(json.dumps(data))
    again = client.get("https://example.com/p", ttl=timedelta(hours=1))
    assert not again.from_cache and first.text == again.text
