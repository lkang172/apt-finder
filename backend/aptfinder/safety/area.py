import unicodedata
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta

from aptfinder.config import Settings
from aptfinder.evaluators.base import AreaSafetyEvidence
from aptfinder.http import PoliteClient
from aptfinder.safety import openjustice, population
from aptfinder.safety.openjustice import AgencyYear
from aptfinder.safety.population import PopulationEstimates
from aptfinder.safety.reference_files import ReferenceFile, fetch_reference_file

STATUS_OK = "ok"
STATUS_NO_CITY_AGENCY = "no_city_agency"

# DOJ agency names that differ from the DOF E-1 city names (after accent and hyphen normalization).
AGENCY_NAME_ALIASES = {
    "angels city": "angels camp",
    "carmel by the sea": "carmel",
    "suisun city": "suisun",
}

NOT_SUBSTITUTED = (
    "Cities without their own agency row are usually policed under contract by a county sheriff or a joint "
    "police authority whose totals cover a wider area, so those totals are not substituted for city-level data."
)


@dataclass(frozen=True)
class StatewideReference:
    label: str
    year: int
    violent_count: int
    property_count: int
    population: int
    violent_per_1000: float | None
    property_per_1000: float | None
    agencies_missing_counts: int


@dataclass(frozen=True)
class AreaSafetyRecord:
    city: str
    county: str | None
    status: str
    year: int
    jurisdiction: str | None
    violent_count: int | None
    property_count: int | None
    population: int | None
    violent_per_1000: float | None
    property_per_1000: float | None
    reference: StatewideReference
    source_name: str
    source_url: str
    population_source: str
    population_source_url: str
    population_as_of: date
    retrieved_at: datetime
    methodology: str
    reason: str | None = None

    def to_evidence(self, evidence_id: str) -> AreaSafetyEvidence:
        return AreaSafetyEvidence(
            evidence_id=evidence_id,
            jurisdiction=self.jurisdiction or self.city,
            year=self.year,
            violent_per_1000=self.violent_per_1000,
            property_per_1000=self.property_per_1000,
            reference_violent_per_1000=self.reference.violent_per_1000,
            reference_property_per_1000=self.reference.property_per_1000,
            reference_label=self.reference.label,
            source_url=self.source_url,
        )


@dataclass(frozen=True)
class AreaSafetyData:
    year: int
    reference: StatewideReference
    records: dict[str, AreaSafetyRecord] = field(repr=False)
    unlisted_template: AreaSafetyRecord = field(repr=False)

    def lookup(self, city: str) -> AreaSafetyRecord:
        record = self.records.get(normalize_place(city))
        if record is not None:
            return record
        return replace(
            self.unlisted_template,
            city=city,
            reason=(
                f"{city} is not listed as an incorporated city in the DOF E-1 population estimates, so there is "
                "no city-level crime rate to attach. If it is a neighborhood of a larger city, that city's "
                "record applies; county sheriff totals are not substituted."
            ),
        )


def load_area_safety(settings: Settings, client: PoliteClient) -> AreaSafetyData:
    ttl = timedelta(days=settings.reference_cache_ttl_days)
    reference_dir = settings.data_dir / "reference"
    crimes_file = fetch_reference_file(client, openjustice.discover_crimes_csv_url(client, ttl), reference_dir, ttl)
    population_file = fetch_reference_file(client, population.discover_e1_url(client, ttl), reference_dir, ttl)
    crimes = openjustice.parse_crimes_csv(crimes_file.read_text())
    year = max(row.year for row in crimes)
    estimates = population.parse_e1_workbook(population_file.path, target_year=year)
    return build_area_safety(crimes, estimates, crimes_file, population_file)


def build_area_safety(
    crimes: list[AgencyYear],
    estimates: PopulationEstimates,
    crimes_file: ReferenceFile,
    population_file: ReferenceFile,
) -> AreaSafetyData:
    year = max(row.year for row in crimes)
    first_year = min(row.year for row in crimes)
    latest = [row for row in crimes if row.year == year]
    reference = _statewide_reference(latest, estimates, year)
    agencies = {(_county_key(row.county), normalize_place(row.agency)): row for row in latest}
    last_reported: dict[tuple[str, str], int] = {}
    for row in crimes:
        key = (_county_key(row.county), normalize_place(row.agency))
        last_reported[key] = max(row.year, last_reported.get(key, row.year))

    population_label = f"{population.SOURCE_NAME}, {_long_date(estimates.as_of)} estimate"
    if estimates.released:
        population_label += f" (released {estimates.released})"
    template = AreaSafetyRecord(
        city="",
        county=None,
        status=STATUS_NO_CITY_AGENCY,
        year=year,
        jurisdiction=None,
        violent_count=None,
        property_count=None,
        population=None,
        violent_per_1000=None,
        property_per_1000=None,
        reference=reference,
        source_name=openjustice.SOURCE_NAME,
        source_url=crimes_file.url,
        population_source=population_label,
        population_source_url=population_file.url,
        population_as_of=estimates.as_of,
        retrieved_at=min(crimes_file.fetched_at, population_file.fetched_at),
        methodology=_methodology(year, estimates.as_of, reference),
    )

    records: dict[str, AreaSafetyRecord] = {}
    for city in estimates.cities:
        keys = [(_county_key(city.county), name) for name in _name_candidates(city.name)]
        agency = next((agencies[k] for k in keys if k in agencies), None)
        if agency is None:
            last = max((last_reported[k] for k in keys if k in last_reported), default=None)
            record = replace(
                template,
                city=city.name,
                county=city.county,
                population=city.population,
                reason=_no_agency_reason(city.name, year, first_year, last),
            )
        else:
            record = replace(
                template,
                city=city.name,
                county=city.county,
                status=STATUS_OK,
                jurisdiction=agency.agency,
                violent_count=agency.violent,
                property_count=agency.property,
                population=city.population,
                violent_per_1000=per_1000(agency.violent, city.population),
                property_per_1000=per_1000(agency.property, city.population),
            )
        for _, name in keys:
            records[name] = record
    return AreaSafetyData(year, reference, records, template)


def per_1000(count: int | None, residents: int | None) -> float | None:
    if count is None or not residents:
        return None
    return round(count / residents * 1000, 2)


def normalize_place(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(ascii_name.replace("-", " ").replace(",", " ").lower().split())


def _name_candidates(e1_name: str) -> list[str]:
    base, _, parenthetical = e1_name.partition("(")
    names = [normalize_place(base)]
    if parenthetical:
        names.append(normalize_place(parenthetical.rstrip(")")))
    names += [AGENCY_NAME_ALIASES[n] for n in names if n in AGENCY_NAME_ALIASES]
    return names


def _county_key(county: str) -> str:
    return normalize_place(county).removesuffix(" county")


def _statewide_reference(latest: list[AgencyYear], estimates: PopulationEstimates, year: int) -> StatewideReference:
    violent = sum(row.violent for row in latest if row.violent is not None)
    property_ = sum(row.property for row in latest if row.property is not None)
    missing = sum(1 for row in latest if row.violent is None or row.property is None)
    return StatewideReference(
        label=f"California statewide (all reporting agencies), {year}",
        year=year,
        violent_count=violent,
        property_count=property_,
        population=estimates.state_population,
        violent_per_1000=per_1000(violent, estimates.state_population),
        property_per_1000=per_1000(property_, estimates.state_population),
        agencies_missing_counts=missing,
    )


def _no_agency_reason(city: str, year: int, first_year: int, last_year: int | None) -> str:
    if last_year is None:
        history = f"it has no agency row in any year from {first_year} to {year}"
    else:
        history = f"its most recent agency row is from {last_year}"
    return (
        f"No city-level agency data: the California DOJ Crimes and Clearances data for {year} has no agency row "
        f"for {city}; {history}. {NOT_SUBSTITUTED}"
    )


def _methodology(year: int, as_of: date, reference: StatewideReference) -> str:
    population_note = "" if as_of.year == year else f" (the closest estimate available for {year})"
    missing_note = (
        f" {reference.agencies_missing_counts} agency rows had blank counts and are left out of the statewide sum."
        if reference.agencies_missing_counts
        else ""
    )
    return (
        "Counts are crimes known to the city's own law enforcement agency, as reported to the California DOJ "
        f"Criminal Justice Statistics Center for calendar year {year} (Crimes and Clearances, including Arson). "
        "Violent crimes are homicide, rape, robbery, and aggravated assault; property crimes are burglary, motor "
        "vehicle theft, and larceny-theft (arson is not included). Rates are per 1,000 residents using the "
        f"California Department of Finance E-1 population estimate for {_long_date(as_of)}{population_note}. "
        f"The statewide reference divides the sum of every reporting California agency for {year} (including "
        "sheriff, state, transit, and campus agencies) by the E-1 state population for the same date."
        f"{missing_note} These are jurisdiction-wide figures for reported crime only: they do not describe a "
        "specific block or building, reporting practices vary between agencies, and cities with many commuters, "
        "shoppers, or visitors can show higher per-resident rates."
    )


def _long_date(value: date) -> str:
    return f"{value:%B} {value.day}, {value.year}"
