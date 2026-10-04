import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import openpyxl
import pytest

from aptfinder.config import Settings
from aptfinder.http import PoliteClient, RobotsDisallowed
from aptfinder.safety import openjustice, population
from aptfinder.safety.area import STATUS_NO_CITY_AGENCY, STATUS_OK, build_area_safety, load_area_safety
from aptfinder.safety.reference_files import ReferenceFile, fetch_reference_file

FIXTURES = Path(__file__).parent / "fixtures"
SYNTHETIC_CSV = FIXTURES / "safety_crimes_synthetic.csv"
CSV_URL = openjustice.CRIMES_CSV_URL
XLSX_URL = population.E1_XLSX_URL

# Synthetic populations mirroring the DOF E-1 workbook layout; none of these numbers are real.
COUNTIES = [
    ("Example", 185_000, 210_500, [
        ("Example", 50_000, 50_500),
        ("Alphaville", 100_000, 125_000),
        ("Betatown", 20_000, 20_000),
        ("Deltaport", 10_000, 10_000),
        ("Unincorporated", 5_000, 5_000),
    ]),
    ("Emptyshire", 1_000, 1_001, []),
    ("Sample", 25_000, 25_100, [
        ("Peña Heights", 15_000, 15_050),
        ("El Puerto de Ejemplo (Puerto)", 6_000, 6_020),
        ("Unincorporated", 4_000, 4_030),
    ]),
    ("San Francisco", 800_000, 801_000, []),
]


def write_e1_workbook(path: Path) -> Path:
    workbook = openpyxl.Workbook()
    about = workbook.active
    about.title = "About the Data"
    about["B2"] = "California Department of Finance"
    about["B8"] = "Released: May 1, 2026"
    header = ["Total Population\n1/1/2025", "Total Population\n1/1/2026", "Percent\nChange"]
    city_sheet = workbook.create_sheet("E-1 CityCounty2026")
    county_sheet = workbook.create_sheet("E-1 CountyState2026")
    for sheet, first in ((city_sheet, "State/County/City"), (county_sheet, "State/County")):
        sheet.append(["About the Data"])
        sheet.append(["E-1: Population Estimates with Annual Percent Change"])
        sheet.append([" January 1, 2025 and 2026"])
        sheet.append([first, *header])
        sheet.append(["California", 1_000_000, 1_010_000, 1.0])
    for county, pop_2025, pop_2026, cities in COUNTIES:
        county_sheet.append([county, pop_2025, pop_2026, 0.1])
        city_sheet.append([county, pop_2025, pop_2026, 0.1])
        for city, city_2025, city_2026 in cities:
            city_sheet.append([city, city_2025, city_2026, 0.1])
    workbook.save(path)
    return path


def reference_file(url: str, path: Path) -> ReferenceFile:
    return ReferenceFile(url, path, datetime(2026, 10, 3, tzinfo=UTC), "sha", from_cache=False)


@pytest.fixture
def area(tmp_path):
    crimes = openjustice.parse_crimes_csv(SYNTHETIC_CSV.read_text())
    workbook = write_e1_workbook(tmp_path / "e1.xlsx")
    estimates = population.parse_e1_workbook(workbook, target_year=2025)
    sources = reference_file(CSV_URL, SYNTHETIC_CSV), reference_file(XLSX_URL, workbook)
    return build_area_safety(crimes, estimates, *sources)


def test_e1_parser_separates_counties_from_cities_and_picks_matching_year(tmp_path):
    workbook = write_e1_workbook(tmp_path / "e1.xlsx")
    estimates = population.parse_e1_workbook(workbook, target_year=2025)
    assert estimates.as_of == date(2025, 1, 1)
    assert estimates.state_population == 1_000_000
    assert estimates.released == "May 1, 2026"
    cities = {(c.county, c.name): c.population for c in estimates.cities}
    assert cities[("Example", "Example")] == 50_000
    assert cities[("Example", "Alphaville")] == 100_000
    assert cities[("San Francisco", "San Francisco")] == 800_000
    assert not any(name in ("Unincorporated", "Emptyshire") for _, name in cities)
    assert len(cities) == 7


@pytest.mark.parametrize(
    ("target_year", "as_of", "alphaville"),
    [(2027, date(2026, 1, 1), 125_000), (2019, date(2025, 1, 1), 100_000)],
)
def test_e1_parser_falls_back_to_closest_population_year(tmp_path, target_year, as_of, alphaville):
    estimates = population.parse_e1_workbook(write_e1_workbook(tmp_path / "e1.xlsx"), target_year=target_year)
    assert estimates.as_of == as_of
    assert next(c.population for c in estimates.cities if c.name == "Alphaville") == alphaville


def test_city_rates_use_the_city_agency_and_latest_year(area):
    alphaville = area.lookup("Alphaville")
    assert area.year == 2025
    assert alphaville.status == STATUS_OK
    assert (alphaville.violent_count, alphaville.property_count, alphaville.population) == (250, 3000, 100_000)
    assert alphaville.violent_per_1000 == 2.5
    assert alphaville.property_per_1000 == 30.0
    assert area.lookup("Betatown").violent_per_1000 == 0.25
    example = area.lookup("example")
    assert (example.jurisdiction, example.violent_per_1000, example.property_per_1000) == ("Example", 2.0, 20.0)
    assert area.lookup("San Francisco").property_per_1000 == 25.0


def test_statewide_reference_sums_every_agency_for_the_year(area):
    reference = area.reference
    assert (reference.violent_count, reference.property_count, reference.population) == (3807, 26660, 1_000_000)
    assert reference.violent_per_1000 == 3.81
    assert reference.property_per_1000 == 26.66
    assert reference.agencies_missing_counts == 1
    assert reference.label == "California statewide (all reporting agencies), 2025"


def test_city_without_its_own_agency_never_gets_sheriff_totals(area):
    deltaport = area.lookup("Deltaport")
    assert deltaport.status == STATUS_NO_CITY_AGENCY
    assert deltaport.jurisdiction is None
    assert deltaport.violent_per_1000 is None and deltaport.property_per_1000 is None
    assert deltaport.violent_count is None and deltaport.property_count is None
    assert deltaport.population == 10_000
    assert deltaport.reason.startswith("No city-level agency data")
    assert "most recent agency row is from 2010" in deltaport.reason
    assert "not substituted" in deltaport.reason
    evidence = deltaport.to_evidence("ev-delta")
    assert evidence.violent_per_1000 is None and evidence.reference_violent_per_1000 == 3.81


def test_non_city_agencies_and_unlisted_places_are_not_city_records(area):
    for name in ("CSU Alphaville", "Example Co. Sheriff's Department", "Sample Transit District", "Stanford"):
        record = area.lookup(name)
        assert record.status == STATUS_NO_CITY_AGENCY
        assert record.violent_per_1000 is None
        assert "not listed as an incorporated city" in record.reason


def test_city_name_variants_match_doj_agency_names(area):
    assert area.lookup("Peña Heights").jurisdiction == "Pena-Heights"
    puerto = area.lookup("Puerto")
    assert puerto.city == "El Puerto de Ejemplo (Puerto)"
    assert puerto.violent_per_1000 == 2.0
    assert area.lookup("El Puerto de Ejemplo") is puerto


def test_records_carry_sources_and_methodology(area):
    record = area.lookup("Alphaville")
    assert record.source_url == CSV_URL
    assert record.population_source_url == XLSX_URL
    assert "January 1, 2025 estimate (released May 1, 2026)" in record.population_source
    assert "per 1,000 residents" in record.methodology and "arson is not included" in record.methodology
    evidence = record.to_evidence("ev-alpha")
    assert (evidence.jurisdiction, evidence.year, evidence.violent_per_1000) == ("Alphaville", 2025, 2.5)
    assert evidence.reference_property_per_1000 == 26.66
    assert evidence.source_url == CSV_URL


def test_latest_annual_file_ignores_monthly_and_older_files():
    listing = json.loads((FIXTURES / "safety_openjustice_files.json").read_text())
    assert openjustice.latest_annual_file_url(listing) == CSV_URL
    assert openjustice.latest_annual_file_url({"data": []}) is None


def make_client(tmp_path, handler) -> PoliteClient:
    return PoliteClient(tmp_path, "test-agent", transport=httpx.MockTransport(handler), sleep=lambda _s: None)


def test_file_discovery_falls_back_to_known_urls(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = make_client(tmp_path, handler)
    assert openjustice.discover_crimes_csv_url(client, timedelta(days=30)) == openjustice.CRIMES_CSV_URL
    assert population.discover_e1_url(client, timedelta(days=30)) == population.E1_XLSX_URL


def test_e1_discovery_picks_newest_workbook_link(tmp_path):
    page = (
        '<a href="/media/docs/forecasting/Demographics/estimates-e1/E-1_2025_InternetVersion.xlsx">2025</a>'
        '<a href="/media/docs/forecasting/Demographics/estimates-e1/E-1_2027_InternetVersion.xlsx">2027</a>'
        '<a href="/media/docs/forecasting/Demographics/estimates-e1/RankCities_2027.xlsx">rank</a>'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404) if request.url.path == "/robots.txt" else httpx.Response(200, text=page)

    url = population.discover_e1_url(make_client(tmp_path, handler), timedelta(days=30))
    assert url == "https://dof.ca.gov/media/docs/forecasting/Demographics/estimates-e1/E-1_2027_InternetVersion.xlsx"


def test_reference_files_are_cached_until_they_expire(tmp_path):
    downloads: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
        downloads.append(request.url.path)
        return httpx.Response(200, content=b"\x00binary\xff")

    client = make_client(tmp_path / "http", handler)
    dest = tmp_path / "reference"
    first = fetch_reference_file(client, "https://example.org/files/data.xlsx", dest, timedelta(days=30))
    second = fetch_reference_file(client, "https://example.org/files/data.xlsx", dest, timedelta(days=30))
    assert first.path.read_bytes() == b"\x00binary\xff"
    assert not first.from_cache and second.from_cache and second.sha256 == first.sha256
    assert downloads == ["/files/data.xlsx"]

    fetch_reference_file(client, "https://example.org/files/data.xlsx", dest, timedelta(0))
    assert len(downloads) == 2
    with pytest.raises(RobotsDisallowed):
        fetch_reference_file(client, "https://example.org/private/x.csv", dest, timedelta(days=30))


def test_load_area_safety_downloads_discovers_and_builds_records(tmp_path):
    listing = (FIXTURES / "safety_openjustice_files.json").read_text()
    workbook = write_e1_workbook(tmp_path / "source.xlsx").read_bytes()
    e1_page = '<a href="/media/docs/forecasting/Demographics/estimates-e1/E-1_2026_InternetVersion.xlsx">E-1</a>'
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        requested.append(url)
        if request.url.path.startswith("/jsonapi/file/file"):
            return httpx.Response(200, text=listing, headers={"content-type": "application/vnd.api+json"})
        if url == CSV_URL:
            return httpx.Response(200, content=SYNTHETIC_CSV.read_bytes())
        if url == population.E1_PAGE_URL:
            return httpx.Response(200, text=e1_page)
        if url == XLSX_URL:
            return httpx.Response(200, content=workbook)
        return httpx.Response(404)

    settings = Settings(data_dir=tmp_path / "data")
    client = make_client(settings.data_dir, handler)
    area = load_area_safety(settings, client)
    assert area.lookup("Alphaville").violent_per_1000 == 2.5
    assert area.lookup("Alphaville").source_url == CSV_URL
    assert (settings.data_dir / "reference" / "Crimes_and_Clearances_with_Arson-1985-2025.csv").exists()

    count = len(requested)
    load_area_safety(settings, client)
    assert len(requested) == count
