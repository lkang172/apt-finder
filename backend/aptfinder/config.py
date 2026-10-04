from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class SearchCity:
    name: str
    region: str
    apartment_list_slug: str


SEARCH_CITIES: tuple[SearchCity, ...] = (
    SearchCity("Foster City", "peninsula", "ca/foster-city"),
    SearchCity("San Mateo", "peninsula", "ca/san-mateo"),
    SearchCity("Belmont", "peninsula", "ca/belmont"),
    SearchCity("San Carlos", "peninsula", "ca/san-carlos"),
    SearchCity("Redwood City", "peninsula", "ca/redwood-city"),
    SearchCity("Menlo Park", "peninsula", "ca/menlo-park"),
    SearchCity("Palo Alto", "peninsula", "ca/palo-alto"),
    SearchCity("Mountain View", "south_bay", "ca/mountain-view"),
    SearchCity("Los Altos", "south_bay", "ca/los-altos"),
    SearchCity("Sunnyvale", "south_bay", "ca/sunnyvale"),
    SearchCity("Santa Clara", "south_bay", "ca/santa-clara"),
    SearchCity("Cupertino", "south_bay", "ca/cupertino"),
    SearchCity("Campbell", "south_bay", "ca/campbell"),
    SearchCity("San Jose", "south_bay", "ca/san-jose"),
    SearchCity("Milpitas", "south_bay", "ca/milpitas"),
    SearchCity("Fremont", "east_bay", "ca/fremont"),
    SearchCity("Newark", "east_bay", "ca/newark"),
    SearchCity("Union City", "east_bay", "ca/union-city"),
)

# Cities that are inside the search corridor but are not searched directly;
# listings may still surface here from neighboring-city result pages.
ADDITIONAL_ALLOWED_CITIES: dict[str, str] = {
    "East Palo Alto": "peninsula",
    "Atherton": "peninsula",
    "Stanford": "peninsula",
    "Saratoga": "south_bay",
    "Los Altos Hills": "south_bay",
}


@dataclass(frozen=True)
class Office:
    label: str
    address: str
    lat: float
    lon: float
    geocode_source: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", env_prefix="APTFINDER_", extra="ignore")

    data_dir: Path = REPO_ROOT / "data"
    database_url: str = ""

    min_rent: int = 2500
    max_rent: int = 3000
    allowed_bedrooms: tuple[int, ...] = (0, 1)

    office_label: str = "Google Sunnyvale — Humboldt buildings"
    office_address: str = "242 Humboldt Ct, Sunnyvale, CA 94089"
    office_lat: float = 37.408084124783
    office_lon: float = -122.018319487984
    office_geocode_source: str = "U.S. Census Bureau Geocoder (Public_AR_Current), matched 242 HUMBOLDT CT, SUNNYVALE, CA, 94089"

    price_freshness_hours: int = 72
    source_update_max_age_days: int = 21
    listing_cache_ttl_hours: int = 12
    reference_cache_ttl_days: int = 30

    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
    )
    apartment_list_min_interval_s: float = 4.0
    redfin_min_interval_s: float = 8.0
    redfin_max_pages_per_city: int = 3
    osrm_min_interval_s: float = 1.5

    google_maps_api_key: str = ""

    @property
    def resolved_database_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir / 'aptfinder.db'}"

    @property
    def office(self) -> Office:
        return Office(self.office_label, self.office_address, self.office_lat, self.office_lon, self.office_geocode_source)


@lru_cache
def get_settings() -> Settings:
    return Settings()
