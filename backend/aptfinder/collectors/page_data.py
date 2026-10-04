import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

FLIGHT_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', re.S)
LD_JSON = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)


def next_flight_text(html: str) -> str:
    return "".join(json.loads(f'"{chunk}"') for chunk in FLIGHT_CHUNK.findall(html))


def iter_flight_rows(html: str) -> Iterator[tuple[str, Any]]:
    """Parses React Server Component rows. Text rows (`T<hex byte length>,`) are length-prefixed and are
    not newline-terminated, so rows must be consumed by byte length rather than split on newlines."""
    data = next_flight_text(html).encode("utf-8")
    pos = 0
    while pos < len(data):
        colon = data.find(b":", pos)
        if colon == -1:
            return
        if not re.fullmatch(rb"[0-9a-f]+", data[pos:colon]):
            newline = data.find(b"\n", pos)
            if newline == -1:
                return
            pos = newline + 1
            continue
        pos = colon + 1
        if data[pos:pos + 1] == b"T":
            comma = data.find(b",", pos)
            length = int(data[pos + 1:comma], 16)
            yield "text", data[comma + 1:comma + 1 + length].decode("utf-8", errors="replace")
            pos = comma + 1 + length
            continue
        newline = data.find(b"\n", pos)
        end = len(data) if newline == -1 else newline
        payload = data[pos:end]
        pos = end + 1
        if payload[:1] in (b"[", b"{"):
            try:
                yield "json", json.loads(payload)
            except json.JSONDecodeError:
                continue


def next_flight_rows(html: str) -> Iterator[Any]:
    return (value for kind, value in iter_flight_rows(html) if kind == "json")


def next_flight_texts(html: str) -> list[str]:
    return [value for kind, value in iter_flight_rows(html) if kind == "text"]


def walk(node: Any) -> Iterator[dict[str, Any]]:
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def json_ld_blocks(html: str) -> list[Any]:
    blocks = []
    for raw in LD_JSON.findall(html):
        try:
            blocks.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return blocks


def parse_timestamp(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = float(str(value).replace(",", "").replace("$", ""))
    except ValueError:
        return None
    return round(number)


def as_float(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None
