import re
from datetime import UTC, datetime

import pytest

from aptfinder.evaluators.base import ReviewEvidence
from aptfinder.evaluators.classifier import (
    LexiconClassifier,
    LLMClassifier,
    Mention,
    classify_reviews,
    split_sentences,
)
from aptfinder.evaluators.lexicon import NEGATIVE, NEUTRAL, POSITIVE, TEXT_CATEGORIES, THEMES, THEMES_BY_NAME

CLASSIFIER = LexiconClassifier()


def review(text: str, evidence_id: str = "r1") -> ReviewEvidence:
    return ReviewEvidence(evidence_id, "apartment_list", None, None, None, datetime(2026, 1, 1, tzinfo=UTC), text)


def themes(text: str) -> set[tuple[str, str]]:
    return {(m.theme, m.polarity) for m in CLASSIFIER.classify(review(text))}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("No roaches at all.", {("no_pests", POSITIVE)}),
        ("We never had bugs.", {("no_pests", POSITIVE)}),
        ("No pest problems in two years.", {("no_pests", POSITIVE)}),
        ("Never had any issues with bugs.", {("no_pests", POSITIVE)}),
        ("I haven't seen a single roach.", {("no_pests", POSITIVE)}),
        ("No roaches, ants, or mice.", {("no_pests", POSITIVE)}),
        ("Never had any bugs or roaches here.", {("no_pests", POSITIVE)}),
        ("It's not noisy.", {("quiet", POSITIVE)}),
        ("The neighbors weren't loud.", {("quiet", POSITIVE)}),
        ("Wasn't loud.", {("quiet", POSITIVE)}),
        ("Noise has never been an issue.", {("quiet", POSITIVE)}),
        ("I can't hear my neighbors at all.", {("quiet", POSITIVE)}),
        ("I never had a package stolen.", {("secure_building", POSITIVE)}),
        ("I don't feel safe walking around the neighborhood at night.", {("area_crime", NEGATIVE)}),
        ("Staff is not helpful.", {("professionalism", NEGATIVE)}),
        ("Not quiet at all.", {("other_noise", NEGATIVE)}),
    ],
)
def test_negation_flips_to_the_opposite_explicit_theme(text, expected):
    assert themes(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("I had no idea there were roaches.", {("cockroaches", NEGATIVE)}),
        ("Not to mention the roaches.", {("cockroaches", NEGATIVE)}),
        ("If you don't like thin walls, look elsewhere.", {("thin_walls", NEGATIVE)}),
        ("No AC and the walls are thin.", {("air_conditioning", NEGATIVE), ("thin_walls", NEGATIVE)}),
        ("No hot water for three days.", {("plumbing", NEGATIVE)}),
        ("Quiet hours are not enforced.", {("neighbor_noise", NEGATIVE)}),
        ("No one respects quiet hours.", {("neighbor_noise", NEGATIVE)}),
        ("We hear the trains but it's not bad.", {("train", NEGATIVE)}),
        ("They never fixed the AC.", {("maintenance", NEGATIVE), ("air_conditioning", NEGATIVE)}),
    ],
)
def test_negators_outside_the_phrase_scope_do_not_flip_complaints(text, expected):
    assert themes(text) == expected


def test_negated_issue_without_positive_counterpart_is_dropped_not_inverted():
    assert themes("No parking issues.") == set()
    assert themes("No mold anywhere.") == set()


def test_specific_pest_is_not_double_counted_as_generic_bugs():
    assert themes("Bed bugs in the unit next door.") == {("bed_bugs", NEGATIVE)}
    assert themes("The place is infested with cockroaches.") == {("cockroaches", NEGATIVE)}


def test_same_theme_is_counted_once_per_review():
    mentions = CLASSIFIER.classify(review("Thin walls. Seriously, the walls are paper thin. Thin walls everywhere."))
    assert [(m.category, m.theme) for m in mentions] == [("noise", "thin_walls")]
    assert mentions[0].excerpt == "Thin walls."


def test_recurrence_language_is_detected_in_sentence_or_follow_up():
    follow_up = CLASSIFIER.classify(review("We had roaches. They keep coming back every summer."))
    assert follow_up[0].theme == "cockroaches" and follow_up[0].recurring
    once = CLASSIFIER.classify(review("We saw a roach once. The pool is great and always clean."))
    assert once[0].theme == "cockroaches" and not once[0].recurring


@pytest.mark.parametrize(
    "text",
    [
        "The area is sketchy.",
        "There are a lot of homeless people around.",
        "It's a ghetto neighborhood.",
        "Shady characters hang out by the corner store.",
        "The neighborhood is low income.",
    ],
)
def test_stereotype_language_never_becomes_a_safety_signal(text):
    categories = {m.category for m in CLASSIFIER.classify(review(text))}
    assert not categories & {"building_safety", "neighborhood_safety"}


def test_management_change_is_a_neutral_marker_alongside_opinions():
    found = themes("Under new management and the new managers are great.")
    assert found == {("management_change", NEUTRAL), ("helpful_staff", POSITIVE)}


def test_neighborhood_reports_suppress_generic_building_safety():
    assert themes("I feel safe walking at night.") == {("area_safe", POSITIVE)}
    assert themes("Feels very safe, the gated garage works well.") == {("secure_building", POSITIVE)}


def test_excerpts_are_verbatim_sentences():
    text = "Love the gym.\nThe walls are thin and sound travels.  Great staff!"
    mentions = CLASSIFIER.classify(review(text))
    sentences = split_sentences(text)
    assert all(m.excerpt in sentences for m in mentions)


def test_theme_catalog_is_consistent():
    names = [spec.theme for spec in THEMES]
    assert len(names) == len(set(names))
    for spec in THEMES:
        assert spec.category in TEXT_CATEGORIES
        assert spec.polarity in (POSITIVE, NEGATIVE, NEUTRAL)
        assert spec.patterns or spec.fixed_patterns
        for fragment in (*spec.patterns, *spec.fixed_patterns):
            re.compile(fragment)
        if spec.negated_theme is not None:
            target = THEMES_BY_NAME[spec.negated_theme]
            assert target.category == spec.category
            assert target.polarity != spec.polarity
        for other in spec.suppressed_by:
            assert other in THEMES_BY_NAME


def test_llm_classifier_is_a_stub():
    with pytest.raises(NotImplementedError):
        LLMClassifier().classify(review("Thin walls."))


class FabricatingClassifier:
    def classify(self, r: ReviewEvidence) -> list[Mention]:
        return [
            Mention("noise", "thin_walls", NEGATIVE, "Thin walls.", r.evidence_id),
            Mention("noise", "quiet", POSITIVE, "It is very quiet.", r.evidence_id),
            Mention("noise", "thin_walls", POSITIVE, "Thin walls.", r.evidence_id),
            Mention("noise", "made_up_theme", NEGATIVE, "Thin walls.", r.evidence_id),
            Mention("pests", "bed_bugs", NEGATIVE, "Thin walls.", "someone-else"),
        ]


def test_classify_reviews_drops_unsupported_classifier_output():
    mentions = classify_reviews([review("Thin walls. Great pool.")], FabricatingClassifier())
    assert [(m.theme, m.polarity) for m in mentions] == [("thin_walls", NEGATIVE)]


def test_classify_reviews_uses_lexicon_by_default():
    mentions = classify_reviews([review("Roaches everywhere.", "a"), review("Very quiet.", "b")])
    assert {(m.evidence_id, m.theme) for m in mentions} == {("a", "cockroaches"), ("b", "quiet")}
