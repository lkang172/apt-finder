import socket
from collections.abc import Callable
from urllib.parse import urlsplit

Resolver = Callable[[str], tuple[str, list[str], list[str]]]

# Hosts that answered automated requests with Cloudflare/anti-bot challenges during validation. Requesting them
# again would only trip their bot management, so they are skipped without any request.
KNOWN_BLOCKED_DOMAINS = {
    "equityapartments.com": "Equity Residential",
    "securecafe.com": "RentCafe/Yardi",
    "rentcafe.com": "RentCafe/Yardi",
}
KNOWN_BLOCKED_CNAME_SUFFIXES = {
    "rentcafecn.com": "RentCafe/Yardi",
    "rentcafecloudflaremvccn.com": "RentCafe/Yardi",
    "securecafe.com": "RentCafe/Yardi",
    "rentcafe.com": "RentCafe/Yardi",
}
KNOWN_BLOCKED_IPS = {"198.190.14.13": "Entrata"}


def _matching_suffix(host: str, suffixes: dict[str, str]) -> str | None:
    host = host.lower().rstrip(".")
    return next((label for suffix, label in suffixes.items() if host == suffix or host.endswith("." + suffix)), None)


def known_blocked_reason(url: str, resolve: Resolver = socket.gethostbyname_ex) -> str | None:
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return None
    platform = _matching_suffix(host, KNOWN_BLOCKED_DOMAINS)
    if platform:
        return f"{host} is a {platform} site that answers automated requests with an anti-bot challenge"
    try:
        canonical, aliases, addresses = resolve(host)
    except (OSError, UnicodeError):
        return None
    for name in (canonical, *aliases):
        platform = _matching_suffix(name, KNOWN_BLOCKED_CNAME_SUFFIXES)
        if platform:
            return f"{host} is hosted by {platform} ({name}), which answers automated requests with an anti-bot challenge"
    for address in addresses:
        if address in KNOWN_BLOCKED_IPS:
            return (
                f"{host} resolves to {address} ({KNOWN_BLOCKED_IPS[address]} hosting), "
                "which answers automated requests with an anti-bot challenge"
            )
    return None
