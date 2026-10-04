import pytest

from aptfinder.normalize import (
    estimate_effective_rent,
    extract_unit_number,
    normalize_street_address,
    parse_fee_text,
    parse_promotion,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1055 Manet Drive", "1055 manet dr"),
        ("1055 MANET DR.", "1055 manet dr"),
        ("720 N Fair Oaks Ave", "720 n fair oaks ave"),
        ("720 North Fair Oaks Avenue", "720 n fair oaks ave"),
        ("88 Bush St #2191", "88 bush st"),
        ("2645 California St Apt 310", "2645 california st"),
        ("1515 N Milpitas Blvd Spc 28", "1515 n milpitas blvd"),
        ("Central Park Apartments", None),
        (None, None),
    ],
)
def test_normalize_street_address(raw, expected):
    assert normalize_street_address(raw) == expected


def test_extract_unit_number():
    assert extract_unit_number("88 Bush St #2191") == "2191"
    assert extract_unit_number("2645 California St Apt 310") == "310"
    assert extract_unit_number("1055 Manet Drive") is None


def test_fee_text_parsing_keeps_unknown_amounts_unknown():
    fees = parse_fee_text("Renter's insurance required, Valet Trash: $25/month")
    assert len(fees) == 2
    insurance, trash = fees
    assert insurance.fee_type == "insurance" and insurance.amount is None and insurance.mandatory is True
    assert trash.fee_type == "trash" and trash.amount == 25 and trash.recurring is True
    assert trash.mandatory is None


def test_fee_text_one_time_and_ranges():
    fees = parse_fee_text("$$600-$800, based on credit approval")
    assert fees[0].amount is None
    assert "$600" in fees[0].amount_text or "600" in fees[0].amount_text
    app = parse_fee_text("$$49 per applicant")[0]
    assert app.recurring is False and app.amount == 49


def test_fee_text_thousands_separator_not_split():
    fees = parse_fee_text("Parking: $1,500 per month")
    assert len(fees) == 1 and fees[0].amount == 1500 and fees[0].fee_type == "parking"


def test_empty_fee_text():
    assert parse_fee_text("") == []
    assert parse_fee_text(None) == []


def test_hedged_promotion_is_not_converted_to_effective_rent():
    promo = parse_promotion("Up to one week free base rent on select homes. Minimum lease term applies.")
    assert promo.free_weeks == 1 and not promo.is_definite
    assert estimate_effective_rent(2800, 12, promo) == (None, None)


def test_definite_promotion_effective_rent():
    promo = parse_promotion("8 weeks free on 12-month leases")
    assert promo.is_definite and promo.free_weeks == 8
    effective, method = estimate_effective_rent(3000, 12, promo)
    assert effective == round(3000 * (52 - 8) / 52)
    assert "Not a quoted price" in method


def test_month_free_promotion():
    promo = parse_promotion("One month free!")
    assert promo.free_weeks == pytest.approx(52 / 12)


def test_effective_rent_requires_lease_term():
    promo = parse_promotion("6 weeks free")
    assert estimate_effective_rent(2900, None, promo) == (None, None)


def test_promotion_without_free_period():
    promo = parse_promotion("Reduced deposit on approved credit")
    assert promo.free_weeks is None and not promo.is_definite
