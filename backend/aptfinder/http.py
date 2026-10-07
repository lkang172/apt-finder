import gzip
import hashlib
import json
import logging
import random
import re
import time
from collections.abc import Callable
from functools import lru_cache
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

log = logging.getLogger(__name__)

RobotsRules = list[tuple[bool, str]]

BLOCK_PAGE_MARKERS = (
    "<title>Client Challenge</title>",
    "px-captcha",
    "cf-chl-",
    "Access Denied</title>",
    "Pardon Our Interruption",
)
# These strings also appear inside normal pages (bot-management scripts, contact-form CAPTCHAs), so they
# only indicate a challenge when the page is too small to contain real content.
INTERSTITIAL_HINTS = (
    "awsWafCookieDomainList",
    "gokuProps",
    "AwsWafIntegration",
    "/cdn-cgi/challenge-platform/",
    "g-recaptcha",
)
INTERSTITIAL_MAX_CHARS = 20_000


def looks_like_challenge(text: str) -> bool:
    if any(marker in text for marker in BLOCK_PAGE_MARKERS):
        return True
    return len(text) < INTERSTITIAL_MAX_CHARS and any(hint in text for hint in INTERSTITIAL_HINTS)


def parse_robots(text: str, user_agent: str = "*") -> RobotsRules:
    """Allow/Disallow rules for our crawler per RFC 9309: the group naming our product token, else the `*` group.

    Unlike urllib.robotparser, blank lines do not end a group and `*`/`$` patterns are supported."""
    token = user_agent.split("/", 1)[0].strip().lower()
    groups: dict[str, RobotsRules] = {}
    agents: list[str] = []
    in_rules = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        field, value = (part.strip() for part in line.split(":", 1))
        field = field.lower()
        if field == "user-agent":
            if in_rules:
                agents, in_rules = [], False
            agents.append(value.lower())
        elif field in ("allow", "disallow"):
            in_rules = True
            for agent in agents:
                rules = groups.setdefault(agent, [])
                if value:
                    rules.append((field == "allow", value))
    return groups[token] if token in groups else groups.get("*", [])


@lru_cache(maxsize=1024)
def _robots_pattern(pattern: str) -> re.Pattern[str]:
    anchored = pattern.endswith("$")
    body = re.escape(pattern[:-1] if anchored else pattern).replace(r"\*", ".*")
    return re.compile(body + ("$" if anchored else ""))


def robots_allows(rules: RobotsRules, url: str) -> bool:
    """Longest matching rule wins; Allow wins a tie (RFC 9309)."""
    parts = urlsplit(url)
    target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    best: tuple[int, bool] | None = None
    for allow, pattern in rules:
        if _robots_pattern(pattern).match(target) and (best is None or len(pattern) > best[0] or (len(pattern) == best[0] and allow)):
            best = (len(pattern), allow)
    return best is None or best[1]


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
        self._robots: dict[str, RobotsRules | None] = {}
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
        self._ensure_not_blocked(host)
        cached = self._read_cache(url, ttl)
        if cached is not None:
            return cached
        self._ensure_robots_allow(url)

        response = self._request_with_policy(url, accept)
        text = response.text
        if looks_like_challenge(text):
            self._block(host, f"anti-bot challenge page returned for {url}")
        if response.status_code == 202:
            # Bot-mitigation layers (e.g. AWS WAF) answer 202 with an interstitial instead of content.
            self._block(host, f"HTTP 202 interstitial instead of content for {url}")
        if response.status_code != 200:
            raise FetchError(f"HTTP {response.status_code} for {url}")
        return self._write_cache(url, str(response.url), response.status_code, text)

    def get_bytes(self, url: str, accept: str = "*/*") -> bytes:
        """Uncached binary download under the same robots.txt, throttling, and blocking policy."""
        self._ensure_not_blocked(urlsplit(url).netloc)
        self._ensure_robots_allow(url)
        response = self._request_with_policy(url, accept)
        if response.status_code != 200:
            raise FetchError(f"HTTP {response.status_code} for {url}")
        return response.content

    def _ensure_not_blocked(self, host: str) -> None:
        if host in self.blocked_hosts:
            raise SourceBlocked(f"{host} blocked earlier in this run: {self.blocked_hosts[host]}")

    def _ensure_robots_allow(self, url: str) -> None:
        if not self._robots_allows(url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")

    def _request_with_policy(self, url: str, accept: str) -> httpx.Response:
        host = urlsplit(url).netloc
        current = url
        for attempt in range(self.max_retries + 1):
            transport_error: httpx.HTTPError | None = None
            for _redirect in range(5):
                self._throttle(urlsplit(current).netloc)
                self.network_requests += 1
                try:
                    response = self._client.get(current, headers={"Accept": accept})
                except httpx.HTTPError as exc:
                    transport_error = exc
                    break
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

            if transport_error is not None:
                # DNS or connection failures are usually transient; retry with backoff, then report.
                if attempt < self.max_retries:
                    self._sleep(5.0 * (2**attempt))
                    continue
                raise FetchError(f"could not fetch {url}: {transport_error}") from transport_error
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

    def allowed(self, url: str) -> bool:
        """Whether robots.txt permits fetching `url` (loads and caches the host's robots.txt)."""
        return self._robots_allows(url)

    def _robots_allows(self, url: str) -> bool:
        parts = urlsplit(url)
        host = parts.netloc
        if host not in self._robots:
            self._robots[host] = self._load_robots(f"{parts.scheme}://{host}/robots.txt")
        rules = self._robots[host]
        return True if rules is None else robots_allows(rules, url)

    def _load_robots(self, robots_url: str) -> RobotsRules | None:
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
                return [(False, "/")]
            cached = self._write_cache(robots_url, str(response.url), response.status_code, response.text)
        return parse_robots(cached.text, self.user_agent)

    def _cache_meta_path(self, url: str) -> Path:
        return self.cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()}.json"

    def _read_cache(self, url: str, ttl: timedelta) -> FetchResult | None:
        meta_path = self._cache_meta_path(url)
        if not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text())
        if meta.get("status") != 200:
            return None
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
