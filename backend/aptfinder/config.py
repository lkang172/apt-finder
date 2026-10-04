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
    redfin_city_path: str


SEARCH_CITIES: tuple[SearchCity, ...] = (
    SearchCity("Foster City", "peninsula", "ca/foster-city", "city/6524/CA/Foster-City"),
    SearchCity("San Mateo", "peninsula", "ca/san-mateo", "city/17490/CA/San-Mateo"),
    SearchCity("Belmont", "peninsula", "ca/belmont", "city/1362/CA/Belmont"),
    SearchCity("San Carlos", "peninsula", "ca/san-carlos", "city/16687/CA/San-Carlos"),
    SearchCity("Redwood City", "peninsula", "ca/redwood-city", "city/15525/CA/Redwood-City"),
    SearchCity("Menlo Park", "peninsula", "ca/menlo-park", "city/11961/CA/Menlo-Park"),
    SearchCity("Palo Alto", "peninsula", "ca/palo-alto", "city/14325/CA/Palo-Alto"),
    SearchCity("Mountain View", "south_bay", "ca/mountain-view", "city/12739/CA/Mountain-View"),
    SearchCity("Los Altos", "south_bay", "ca/los-altos", "city/11018/CA/Los-Altos"),
    SearchCity("Sunnyvale", "south_bay", "ca/sunnyvale", "city/19457/CA/Sunnyvale"),
    SearchCity("Santa Clara", "south_bay", "ca/santa-clara", "city/17675/CA/Santa-Clara"),
    SearchCity("Cupertino", "south_bay", "ca/cupertino", "city/4561/CA/Cupertino"),
    SearchCity("Campbell", "south_bay", "ca/campbell", "city/2673/CA/Campbell"),
    SearchCity("San Jose", "south_bay", "ca/san-jose", "city/17420/CA/San-Jose"),
    SearchCity("Milpitas", "south_bay", "ca/milpitas", "city/12204/CA/Milpitas"),
    SearchCity("Fremont", "east_bay", "ca/fremont", "city/6671/CA/Fremont"),
    SearchCity("Newark", "east_bay", "ca/newark", "city/13111/CA/Newark"),
    SearchCity("Union City", "east_bay", "ca/union-city", "city/20321/CA/Union-City"),
)

# Cities that are inside the search corridor but are not searched directly;
# listings may still surface here from neighboring-city result pages.
ADDITIONAL_ALLOWED_CITIES: dict[str, str] = {
    "East Palo Alto": "peninsula",
    "Atherton": "peninsula",
    "Stanford": "peninsula",
    "Los Altos Hills": "south_bay",
    "Alviso": "south_bay",
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

    min_rent: int = 2100
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
    api_user_agent: str = "apt-finder/0.1 (personal apartment research; https://github.com/lkang172/apt-finder)"
    apartment_list_min_interval_s: float = 4.0
    redfin_min_interval_s: float = 8.0
    redfin_max_pages_per_city: int = 3
    trulia_min_interval_s: float = 15.0
    trulia_max_pages_per_city: int = 3
    shared_widget_min_interval_s: float = 10.0
    osrm_min_interval_s: float = 1.5

    google_maps_api_key: str = ""
    google_refresh_days: int = 30
    google_text_search_monthly_budget: int = 2000
    google_details_monthly_budget: int = 800
    google_routes_enabled: bool = False

    @property
    def resolved_database_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir / 'aptfinder.db'}"

    @property
    def office(self) -> Office:
        return Office(self.office_label, self.office_address, self.office_lat, self.office_lon, self.office_geocode_source)


@lru_cache
def get_settings() -> Settings:
    return Settings()
