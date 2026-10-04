from aptfinder.dedupe import key_for, match_property

ENCASA_AL = key_for(1, "Encasa", "550 E Weddell Dr", "94089", "Sunnyvale", 37.398975, -122.013364)


def test_same_address_different_formatting_merges():
    redfin = key_for(0, "Encasa", "550 East Weddell Drive", "94089", "Sunnyvale", 37.3981667, -122.0126759)
    match = match_property(redfin, [ENCASA_AL])
    assert match and match.property_id == 1 and "address" in match.reason


def test_unit_suffix_ignored_for_building_match():
    unit = key_for(0, "88 Bush St #2191", "88 Bush St #2191", "95126", "San Jose", 37.33001, -121.9044073)
    building = key_for(5, "Some Tower", "88 Bush St", "95126", "San Jose", 37.3301, -121.9045)
    assert match_property(unit, [building]).property_id == 5


def test_similar_names_far_apart_do_not_merge():
    other = key_for(0, "Encasa", "100 Main St", "94086", "Sunnyvale", 37.3700, -122.0300)
    assert match_property(other, [ENCASA_AL]) is None


def test_similar_names_nearby_but_different_streets_do_not_merge():
    neighbor = key_for(0, "Encasa Two", "601 Morse Ave", "94089", "Sunnyvale", 37.39905, -122.01340)
    assert match_property(neighbor, [ENCASA_AL]) is None


def test_same_address_different_city_does_not_merge():
    elsewhere = key_for(0, "Encasa", "550 E Weddell Dr", "95050", "Santa Clara", None, None)
    assert match_property(elsewhere, [ENCASA_AL]) is None


def test_same_number_and_name_within_radius_merges_when_street_spelling_differs():
    variant = key_for(0, "Encasa Apartments", "550 Weddell Dr", "94089", "Sunnyvale", 37.39880, -122.01320)
    assert match_property(variant, [ENCASA_AL]).property_id == 1


def test_missing_address_and_coordinates_never_merges_on_name():
    nameless = key_for(0, "Encasa", None, None, "Sunnyvale", None, None)
    assert match_property(nameless, [ENCASA_AL]) is None


def test_closest_structured_match_wins():
    near = key_for(2, "Tower A", "100 Pine St", "94089", "Sunnyvale", 37.40000, -122.01000)
    nearer = key_for(3, "Tower B", "100 Pine St", "94089", "Sunnyvale", 37.40001, -122.01001)
    candidate = key_for(0, "X", "100 Pine Street", None, None, 37.40002, -122.01002)
    assert match_property(candidate, [near, nearer]).property_id == 3
