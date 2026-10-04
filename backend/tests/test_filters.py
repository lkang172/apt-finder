from datetime import UTC, datetime, timedelta

import pytest

from aptfinder.filters import (
    PricePoint,
    RatingInput,
    detect_price_conflicts,
    evaluate_rating_filter,
    is_allowed_unit_type,
    is_price_fresh,
    rent_in_range,
)
from aptfinder.geo import evaluate_location


@pytest.mark.parametrize(
    ("base_min", "base_max", "expected"),
    [
        (2500, 2500, True),
        (3000, 3000, True),
        (2499, 2499, False),
        (3001, 3001, False),
        (2750, None, True),
        (2850, 3200, True),
        (2400, 2600, True),
        (2400, 3200, False),
        (0, 0, False),
        (None, None, False),
    ],
)
def test_rent_range_is_inclusive_and_strict(base_min, base_max, expected):
    assert rent_in_range(base_min, base_max, 2500, 3000) is expected


@pytest.mark.parametrize(("beds", "expected"), [(0, True), (1, True), (2, False), (None, False)])
def test_only_studio_and_one_bedroom(beds, expected):
    assert is_allowed_unit_type(beds) is expected


@pytest.mark.parametrize(
    ("city", "lat", "lon", "allowed"),
    [
        ("Foster City", 37.5585, -122.2711, True),
        ("San Mateo", 37.5630, -122.3255, True),
        ("Sunnyvale", 37.3688, -122.0363, True),
        ("San Jose", 37.3382, -121.8863, True),
        ("Fremont", 37.5485, -121.9886, True),
        ("Union City", 37.5934, -122.0438, True),
        ("San Francisco", 37.7749, -122.4194, False),
        ("Oakland", 37.8044, -122.2712, False),
        ("Burlingame", 37.5841, -122.3661, False),
        ("Millbrae", 37.5985, -122.3872, False),
        ("Hayward", 37.6688, -122.0808, False),
        ("Morgan Hill", 37.1305, -121.6544, False),
        ("Gilroy", 37.0058, -121.5683, False),
        ("San Jose", 37.12, -121.70, False),
        ("Sunnyvale", 37.7749, -122.4194, False),
    ],
)
def test_geographic_constraints(city, lat, lon, allowed):
    assert evaluate_location(city, lat, lon).allowed is allowed


def test_geo_without_coordinates_falls_back_to_city():
    decision = evaluate_location("Palo Alto", None, None)
    assert decision.allowed and decision.region == "peninsula"
    assert "Coordinates unavailable" in decision.reason


@pytest.mark.parametrize(
    ("ratings", "exclude", "status"),
    [
        ([RatingInput("google_places", 2.4, 87)], True, "excluded_low_rating"),
        ([RatingInput("google_places", 2.9, 5)], True, "excluded_low_rating"),
        ([RatingInput("google_places", 2.7, 1)], False, "insufficient"),
        ([], False, "no_reviews"),
        ([RatingInput("apartment_list", None, 0)], False, "no_reviews"),
        ([RatingInput("apartment_list", 3.0, 10)], False, "ok"),
        ([RatingInput("google_places", 2.7, 120), RatingInput("apartment_list", 4.1, 18)], False, "conflict"),
        ([RatingInput("google_places", 2.8, 40), RatingInput("apartment_list", 3.1, 4)], True, "excluded_low_rating"),
        ([RatingInput("google_places", 2.9, 4), RatingInput("apartment_list", 3.4, 40)], False, "ok"),
        ([RatingInput("google_places", 2.0, 50, match_confidence="weak")], False, "insufficient"),
        ([RatingInput("x", 5.0, 10, scale=10.0)], True, "excluded_low_rating"),
    ],
)
def test_rating_filter(ratings, exclude, status):
    decision = evaluate_rating_filter(ratings)
    assert decision.exclude is exclude
    assert decision.status == status


def test_price_freshness():
    now = datetime(2026, 10, 3, tzinfo=UTC)
    fresh = timedelta(hours=72)
    max_age = timedelta(days=21)
    assert is_price_fresh(now - timedelta(hours=1), now - timedelta(days=2), now, fresh, max_age)
    assert not is_price_fresh(now - timedelta(hours=80), None, now, fresh, max_age)
    assert not is_price_fresh(now - timedelta(hours=1), now - timedelta(days=30), now, fresh, max_age)
    assert is_price_fresh(now - timedelta(hours=1), None, now, fresh, max_age)


def test_price_conflict_detected_for_same_floorplan_across_sources():
    a = PricePoint("apartment_list", 1, 720, 2875, 2875, "https://a")
    b = PricePoint("redfin", 1, 722, 2995, 2995, "https://b")
    conflicts = detect_price_conflicts([a, b])
    assert len(conflicts) == 1 and conflicts[0].difference == 120


def test_no_conflict_when_ranges_overlap_or_plans_differ():
    a = PricePoint("apartment_list", 1, 720, 2875, 2875, "https://a")
    assert not detect_price_conflicts([a, PricePoint("redfin", 1, 720, 2800, 2950, "https://b")])
    assert not detect_price_conflicts([a, PricePoint("redfin", 1, 900, 3300, 3300, "https://b")])
    assert not detect_price_conflicts([a, PricePoint("redfin", 0, 720, 3300, 3300, "https://b")])
    assert not detect_price_conflicts([a, PricePoint("apartment_list", 1, 720, 3300, 3300, "https://c")])
    assert not detect_price_conflicts([a, PricePoint("redfin", 1, 720, 2910, 2910, "https://b")])


@pytest.mark.parametrize(
    ("restrictions", "name", "excluded"),
    [
        (["Senior Housing"], "Palmia", True),
        (["Affordable Housing"], "Hillsdale Garden", True),
        (["Income-restricted housing"], "X", True),
        (["Student housing"], "X", False),
        ([], "Senior Housing- Palmia, Age 55+ Luxury Apartments", True),
        ([], "Hillsdale Garden - Affordable Housing", True),
        ([], "Oak Street BMR Apartments", True),
        ([], "Central Park Apartments", False),
        ([], "Seniority Plaza Lofts", False),
        ([], "The 55 Lofts", False),
    ],
)
def test_senior_and_income_restricted_housing_excluded(restrictions, name, excluded):
    from aptfinder.filters import excluded_eligibility

    assert (excluded_eligibility(restrictions, name) is not None) is excluded
