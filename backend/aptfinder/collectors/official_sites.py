import html as html_lib
import json
import logging
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from aptfinder.collectors.official import avalon, jonah, knock, sightmap
from aptfinder.collectors.official.blocked import (
    KNOWN_BLOCKED_CNAME_SUFFIXES,
    KNOWN_BLOCKED_DOMAINS,
    KNOWN_BLOCKED_IPS,
    Resolver,
    known_blocked_reason,
)
from aptfinder.collectors.official.common import AVALON, JONAH, KNOCK, PLATFORM_LABELS, SIGHTMAP, ParsedSite, site_host
from aptfinder.collectors.types import CollectedFact, CollectedListing
from aptfinder.http import FetchError, FetchResult, PoliteClient, SourceBlocked

__all__ = [
    "KNOWN_BLOCKED_CNAME_SUFFIXES",
    "KNOWN_BLOCKED_DOMAINS",
    "KNOWN_BLOCKED_IPS",
    "OfficialSiteCollector",
    "OfficialSiteTarget",
    "clean_website_url",
    "detect_platform",
    "detect_platforms",
    "floorplans_link",
    "known_blocked_reason",
]

log = logging.getLogger(__name__)

SOURCE_ID = "official_site"
FLOORPLANS_HREF = re.compile(r'href="([^"#?]*/(?:floor-?plans?|availability)(?:\.aspx)?/?)"', re.I)
# PoliteClient refuses cross-host redirects and names the target only in its error message.
CROSS_HOST_REDIRECT = re.compile(r"cross-host redirect from \S+ to (\S+)$")
TRACKING_PARAMS = {"funnelleasing", "gclid", "fbclid", "msclkid"}


@dataclass(frozen=True)
class OfficialSiteTarget:
    name: str
    website_url: str
    street_address: str | None = None
    city: str | None = None
    zip: str | None = None
    lat: float | None = None
    lon: float | None = None


@dataclass
class PlatformResult:
    site: ParsedSite
    page_url: str
    price_fetch: FetchResult
    endpoints: list[str]


def detect_platforms(url: str, html: str) -> list[str]:
    checks = (
        (AVALON, avalon.is_avalon_page(url, html)),
        (JONAH, jonah.is_jonah_site(html)),
        (SIGHTMAP, sightmap.find_embed_url(html) is not None),
        (KNOCK, knock.find_community_id(html) is not None),
    )
    return [platform for platform, found in checks if found]


def detect_platform(url: str, html: str) -> str | None:
    platforms = detect_platforms(url, html)
    return platforms[0] if platforms else None


def _same_site(url: str, other: str) -> bool:
    host, other_host = site_host(url), site_host(other)
    return bool(host) and (host == other_host or host.endswith("." + other_host) or other_host.endswith("." + host))


def clean_website_url(url: str) -> str:
    url = url.strip()
    parts = urlsplit(url if "://" in url else f"https://{url}")
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", urlencode(query), ""))


def floorplans_link(page_url: str, html: str) -> str | None:
    for href in FLOORPLANS_HREF.findall(html):
        url = urljoin(page_url, html_lib.unescape(href))
        if urlsplit(url).scheme in ("http", "https") and url.rstrip("/") != page_url.rstrip("/") and _same_site(url, page_url):
            return url
    return None


class OfficialSiteCollector:
    source_id = SOURCE_ID

    def __init__(self, client: PoliteClient, ttl: timedelta, resolve: Resolver = socket.gethostbyname_ex):
        self.client = client
        self.ttl = ttl
        self._resolve = lru_cache(maxsize=1024)(resolve)
        self._readers: dict[str, Callable[[FetchResult], PlatformResult | None]] = {
            AVALON: self._read_avalon,
            JONAH: self._read_jonah,
            SIGHTMAP: self._read_sightmap,
            KNOCK: self._read_knock,
        }

    def collect(self, prop: OfficialSiteTarget) -> CollectedListing | None:
        blocked = known_blocked_reason(prop.website_url, self._resolve)
        if blocked:
            log.info("Skipping the official site of %s: %s", prop.name, blocked)
            return None
        try:
            return self._collect(prop)
        except SourceBlocked:
            raise
        except Exception as exc:  # one unreadable site must not stop the run
            log.warning("Could not read prices from the official site of %s (%s): %s", prop.name, prop.website_url, exc)
            return None

    def _collect(self, prop: OfficialSiteTarget) -> CollectedListing | None:
        page = self._get_page(clean_website_url(prop.website_url))
        platforms = detect_platforms(page.final_url, page.text)
        if not platforms:
            link = floorplans_link(page.final_url, page.text)
            if link:
                page = self._get_page(link)
                platforms = detect_platforms(page.final_url, page.text)
        if not platforms:
            log.info("No supported pricing platform found on the official site of %s (%s)", prop.name, prop.website_url)
            return None
        for platform in platforms:
            result = self._readers[platform](page)
            if result is not None:
                return self._listing(prop, result)
            log.info("The %s data on the official site of %s (%s) could not be parsed", platform, prop.name, page.final_url)
        return None

    def _get_page(self, url: str) -> FetchResult:
        try:
            return self.client.get(url, ttl=self.ttl)
        except SourceBlocked:
            raise
        except FetchError as exc:
            match = CROSS_HOST_REDIRECT.search(str(exc))
            if not match or not _same_site(match.group(1), url):
                raise
            target = match.group(1)
        blocked = known_blocked_reason(target, self._resolve)
        if blocked:
            raise FetchError(f"{url} redirects to {target}: {blocked}")
        return self.client.get(target, ttl=self.ttl)

    def _get_json(self, url: str) -> tuple[FetchResult, dict]:
        result = self.client.get(url, ttl=self.ttl, accept="application/json")
        document = json.loads(result.text)
        if not isinstance(document, dict):
            raise ValueError(f"unexpected JSON document at {url}")
        return result, document

    def _read_avalon(self, page: FetchResult) -> PlatformResult | None:
        site = avalon.parse_community_page(page.text)
        return PlatformResult(site, page.final_url, page, []) if site else None

    def _read_jonah(self, page: FetchResult) -> PlatformResult | None:
        if not jonah.has_floorplan_data(page.text):
            page = self._get_page(floorplans_link(page.final_url, page.text) or urljoin(page.final_url, "/floorplans/"))
        site = jonah.parse_floorplans_page(page.text, page.final_url)
        return PlatformResult(site, page.final_url, page, []) if site else None

    def _read_sightmap(self, page: FetchResult) -> PlatformResult | None:
        embed_url = sightmap.find_embed_url(page.text)
        embed = self.client.get(embed_url, ttl=self.ttl)
        urls = sightmap.data_urls(embed.text)
        if not urls:
            return None
        data_fetch, document = self._get_json(urls[0])
        site = sightmap.parse_sightmap(document, embed.text)
        if site is None:
            return None
        if len(urls) > 1:
            site.notes.append(f"The SightMap embed lists {len(urls)} maps; only the first ({urls[0]}) was read")
        return PlatformResult(site, page.final_url, data_fetch, [embed_url, urls[0]])

    def _read_knock(self, page: FetchResult) -> PlatformResult | None:
        community_fetch, community_doc = self._get_json(knock.community_url(knock.find_community_id(page.text)))
        community = knock.parse_community(community_doc)
        if community is None:
            return None
        if community.pricing_hidden:
            return PlatformResult(community.site, page.final_url, community_fetch, [community_fetch.url])
        units_fetch, units_doc = self._get_json(knock.units_url(community.property_id))
        site = knock.add_units(community, units_doc)
        return PlatformResult(site, page.final_url, units_fetch, [community_fetch.url, units_fetch.url])

    def _listing(self, prop: OfficialSiteTarget, result: PlatformResult) -> CollectedListing:
        site = result.site
        if result.endpoints:
            source_text = f"Prices were read from {', '.join(result.endpoints)}, which the official page {result.page_url} loads."
        else:
            source_text = f"Prices were read from the structured data embedded in the official page {result.page_url}."
        facts = [
            CollectedFact(
                "platform", "Official website pricing platform", PLATFORM_LABELS[site.platform], ["listing"],
                {"platform": site.platform, "platform_property_id": site.platform_property_id},
            ),
            CollectedFact(
                "data_endpoint", "Official website data source", source_text, ["listing"],
                {"endpoints": result.endpoints or [result.page_url], "price_document": result.price_fetch.url},
                result.endpoints[-1] if result.endpoints else result.page_url,
            ),
            *site.facts,
        ]
        notes = list(site.notes)
        if not site.units:
            notes.append("The official site lists no units with a published price")
        address = site.address
        has_site_coordinates = address.lat is not None and address.lon is not None
        # The price document, not the landing page, is the fetch of record: price evidence ids are derived from
        # its content hash, so a price change must change this document's hash.
        return CollectedListing(
            source_id=SOURCE_ID,
            source_listing_id=f"{site.platform}:{site.platform_property_id}",
            url=result.page_url,
            name=site.name or prop.name,
            street_address=address.street_address or prop.street_address,
            city=address.city or prop.city,
            state=address.state,
            zip=address.zip or prop.zip,
            lat=address.lat if has_site_coordinates else prop.lat,
            lon=address.lon if has_site_coordinates else prop.lon,
            fetch=result.price_fetch,
            official_website_url=prop.website_url,
            source_updated_at=site.source_updated_at,
            units=site.units,
            fees=site.fees,
            promotions=site.promotions,
            facts=facts,
            notes=notes,
        )
