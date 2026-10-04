import gzip
import hashlib
import json
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger(__name__)

CHALLENGE_MARKERS = (
    "<title>Client Challenge</title>",
    "px-captcha",
    "cf-chl-",
    "g-recaptcha",
    "Access Denied</title>",
    "Pardon Our Interruption",
)


class FetchError(Exception):
    pass


class SourceBlocked(FetchError):
    """The host signaled rate limiting or blocking; stop using it for the rest of the run."""


class RobotsDisallowed(FetchError):
    pass


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str
    status: int
    text: str
    fetched_at: datetime
    from_cache: bool
    content_sha256: str
    storage_path: str


class PoliteClient:
    def __init__(
        self,
        data_dir: Path,
        user_agent: str,
        min_intervals: dict[str, float] | None = None,
        default_interval: float = 2.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        max_retries: int = 2,
    ):
        self.cache_dir = data_dir / "http_cache"
        self.raw_dir = data_dir / "raw"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent
        self.min_intervals = min_intervals or {}
        self.default_interval = default_interval
        self.max_retries = max_retries
        self._sleep = sleep
        self._clock = clock
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self.blocked_hosts: dict[str, str] = {}
        self.network_requests = 0
        self._client = httpx.Client(
            headers={
                "User-Agent": user_agent,
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=httpx.Timeout(30.0),
            follow_redirects=False,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def get(self, url: str, *, ttl: timedelta, accept: str = "text/html,application/xhtml+xml") -> FetchResult:
        host = urlsplit(url).netloc
        if host in self.blocked_hosts:
            raise SourceBlocked(f"{host} blocked earlier in this run: {self.blocked_hosts[host]}")

        cached = self._read_cache(url, ttl)
        if cached is not None:
            return cached

        if not self._robots_allows(url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")

        response = self._request_with_policy(url, accept)
        text = response.text
        if any(marker in text for marker in CHALLENGE_MARKERS):
            self._block(host, f"anti-bot challenge page returned for {url}")
        if response.status_code >= 400:
            raise FetchError(f"HTTP {response.status_code} for {url}")
        return self._write_cache(url, str(response.url), response.status_code, text)

    def _request_with_policy(self, url: str, accept: str) -> httpx.Response:
        host = urlsplit(url).netloc
        current = url
        for attempt in range(self.max_retries + 1):
            for _redirect in range(5):
                self._throttle(urlsplit(current).netloc)
                self.network_requests += 1
                response = self._client.get(current, headers={"Accept": accept})
                if response.is_redirect:
                    target = urljoin(current, response.headers.get("location", ""))
                    target_host = urlsplit(target).netloc
                    if "ratelimit" in target_host or "captcha" in target.lower():
                        self._block(host, f"redirected to {target}")
                    if target_host != host:
                        raise FetchError(f"cross-host redirect from {url} to {target}")
                    current = target
                    continue
                break
            else:
                raise FetchError(f"too many redirects for {url}")

            if response.status_code == 429:
                self._block(host, f"HTTP 429 (Retry-After: {response.headers.get('retry-after', 'n/a')})")
            if response.status_code == 403:
                self._block(host, f"HTTP 403 for {current}")
            if response.status_code >= 500 and attempt < self.max_retries:
                self._sleep(5.0 * (2**attempt))
                continue
            return response
        raise FetchError(f"exhausted retries for {url}")

    def _block(self, host: str, reason: str) -> None:
        self.blocked_hosts[host] = reason
        log.warning("Stopping requests to %s: %s", host, reason)
        raise SourceBlocked(reason)

    def _throttle(self, host: str) -> None:
        interval = self.min_intervals.get(host, self.default_interval)
        last = self._last_request.get(host)
        if last is not None:
            jitter = random.uniform(0, interval * 0.25)
            wait = interval + jitter - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_request[host] = self._clock()

    def _robots_allows(self, url: str) -> bool:
        parts = urlsplit(url)
        host = parts.netloc
        if host not in self._robots:
            self._robots[host] = self._load_robots(f"{parts.scheme}://{host}/robots.txt")
        parser = self._robots[host]
        return True if parser is None else parser.can_fetch(self.user_agent, url)

    def _load_robots(self, robots_url: str) -> RobotFileParser | None:
        cached = self._read_cache(robots_url, timedelta(days=1))
        if cached is None:
            host = urlsplit(robots_url).netloc
            self._throttle(host)
            self.network_requests += 1
            try:
                response = self._client.get(robots_url, follow_redirects=True)
            except httpx.HTTPError as exc:
                raise FetchError(f"could not fetch {robots_url}: {exc}") from exc
            if response.status_code == 429:
                self._block(host, "HTTP 429 on robots.txt")
            # RFC 9309: a 4xx robots.txt means no restrictions; 5xx means assume full disallow.
            if 400 <= response.status_code < 500:
                return None
            if response.status_code >= 500:
                parser = RobotFileParser()
                parser.parse(["User-agent: *", "Disallow: /"])
                return parser
            cached = self._write_cache(robots_url, str(response.url), response.status_code, response.text)
        parser = RobotFileParser()
        parser.parse(cached.text.splitlines())
        return parser

    def _cache_meta_path(self, url: str) -> Path:
        return self.cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()}.json"

    def _read_cache(self, url: str, ttl: timedelta) -> FetchResult | None:
        meta_path = self._cache_meta_path(url)
        if not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text())
        fetched_at = datetime.fromisoformat(meta["fetched_at"])
        if datetime.now(UTC) - fetched_at > ttl:
            return None
        body_path = self.raw_dir / meta["storage_path"]
        if not body_path.exists():
            return None
        text = gzip.decompress(body_path.read_bytes()).decode("utf-8")
        return FetchResult(
            url=url,
            final_url=meta["final_url"],
            status=meta["status"],
            text=text,
            fetched_at=fetched_at,
            from_cache=True,
            content_sha256=meta["content_sha256"],
            storage_path=meta["storage_path"],
        )

    def _write_cache(self, url: str, final_url: str, status: int, text: str) -> FetchResult:
        body = text.encode("utf-8")
        sha = hashlib.sha256(body).hexdigest()
        storage_path = f"{sha[:2]}/{sha}.gz"
        body_path = self.raw_dir / storage_path
        if not body_path.exists():
            body_path.parent.mkdir(parents=True, exist_ok=True)
            body_path.write_bytes(gzip.compress(body))
        fetched_at = datetime.now(UTC)
        self._cache_meta_path(url).write_text(
            json.dumps(
                {
                    "url": url,
                    "final_url": final_url,
                    "status": status,
                    "fetched_at": fetched_at.isoformat(),
                    "content_sha256": sha,
                    "storage_path": storage_path,
                }
            )
        )
        return FetchResult(url, final_url, status, text, fetched_at, False, sha, storage_path)
