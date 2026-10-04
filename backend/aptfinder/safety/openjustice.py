import csv
import io
import json
import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.parse import urljoin

from aptfinder.http import FetchError, PoliteClient

log = logging.getLogger(__name__)

SOURCE_NAME = "California DOJ OpenJustice, Crimes and Clearances (including Arson)"
DATA_HOST_URL = "https://data-openjustice.doj.ca.gov"
CRIMES_CSV_URL = f"{DATA_HOST_URL}/sites/default/files/dataset/2026-07/Crimes_and_Clearances_with_Arson-1985-2025.csv"
FILE_LISTING_URL = (
    f"{DATA_HOST_URL}/jsonapi/file/file?filter%5Bfilename%5D%5Boperator%5D=CONTAINS"
    "&filter%5Bfilename%5D%5Bvalue%5D=Crimes_and_Clearances_with_Arson&page%5Blimit%5D=50"
)
ANNUAL_FILENAME = re.compile(r"^Crimes_and_Clearances_with_Arson-(\d{4})-(\d{4})\.csv$")


@dataclass(frozen=True)
class AgencyYear:
    year: int
    county: str
    agency: str
    violent: int | None
    property: int | None


def latest_annual_file_url(listing: dict[str, Any]) -> str | None:
    candidates = []
    for item in listing.get("data") or []:
        attributes = item.get("attributes") or {}
        match = ANNUAL_FILENAME.match(attributes.get("filename") or "")
        path = (attributes.get("uri") or {}).get("url")
        if match and path and attributes.get("status", True):
            candidates.append((int(match.group(2)), attributes.get("created") or "", urljoin(DATA_HOST_URL, path)))
    return max(candidates)[2] if candidates else None


def discover_crimes_csv_url(client: PoliteClient, ttl: timedelta) -> str:
    try:
        fetch = client.get(FILE_LISTING_URL, ttl=ttl, accept="application/vnd.api+json")
        url = latest_annual_file_url(json.loads(fetch.text))
    except (FetchError, json.JSONDecodeError) as exc:
        log.warning("Could not list OpenJustice files (%s); using %s", exc, CRIMES_CSV_URL)
        return CRIMES_CSV_URL
    return url or CRIMES_CSV_URL


def parse_crimes_csv(text: str) -> list[AgencyYear]:
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        year = _count(row.get("Year"))
        agency = (row.get("NCICCode") or "").strip()
        if year is None or not agency:
            continue
        rows.append(
            AgencyYear(
                year=year,
                county=(row.get("County") or "").strip(),
                agency=agency,
                violent=_count(row.get("Violent_sum")),
                property=_count(row.get("Property_sum")),
            )
        )
    return rows


def _count(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    return int(float(value))
