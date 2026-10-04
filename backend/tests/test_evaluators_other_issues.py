from datetime import UTC, datetime, timedelta

import pytest

from aptfinder.evaluators.base import ReviewEvidence
from aptfinder.evaluators.classifier import classify_reviews
from aptfinder.evaluators.other_issues import (
    ISOLATED,
    RECURRING_CURRENT,
    RECURRING_OLD,
    evaluate_other_issues,
    issue_status,
)

NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)
FILLER = "Nice pool and friendly neighbors."


def review(evidence_id, text, days_ago=30):
    date = None if days_ago is None else NOW - timedelta(days=days_ago)
    return ReviewEvidence(evidence_id, "apartment_list", f"https://example.com/{evidence_id}", None, None, date, text)


def run(reviews):
    return evaluate_other_issues(reviews, classify_reviews(reviews), NOW)


def corpus():
    return [
        review("p1", "Parking is a nightmare.", days_ago=60),
        review("p2", "Not enough parking for residents.", days_ago=1200),
        review("m1", "Mold in the bathroom.", days_ago=1500),
        review("m2", "We found mold under the sink.", days_ago=2000),
        review("e1", "The elevator is broken again.", days_ago=90),
        review("f1", FILLER, days_ago=10),
        review("f2", FILLER, days_ago=20),
    ]


def test_issue_status_classification():
    recent = review("a", "x", days_ago=30)
    old = review("b", "x", days_ago=1500)
    older = review("c", "x", days_ago=2500)
    assert issue_status([recent], NOW) == ISOLATED
    assert issue_status([recent, old], NOW) == RECURRING_CURRENT
    assert issue_status([old, older], NOW) == RECURRING_OLD
    assert issue_status([old, review("d", "x", days_ago=None)], NOW) == RECURRING_OLD


def test_recurring_current_old_and_isolated_patterns():
    result = run(corpus())
    assert result.details["issue_patterns"] == {"parking": RECURRING_CURRENT, "mold": RECURRING_OLD, "elevators": ISOLATED}
    assert result.score == 7.8
    assert result.confidence == "low"
    assert result.evidence_count == 7
    assert [c.theme for c in result.claims] == ["parking", "mold"]
    assert result.details["isolated_anecdotes"] == [{
        "theme": "elevators",
        "label": "Elevator problems",
        "evidence_id": "e1",
        "excerpt": "The elevator is broken again.",
        "review_date": (NOW - timedelta(days=90)).date().isoformat(),
    }]
    assert "1 isolated complaint is listed separately and does not affect the score." in result.summary


def test_old_recurring_issue_claim_is_qualified():
    result = run(corpus())
    mold = next(c for c in result.claims if c.theme == "mold")
    assert mold.is_current is False
    assert "recurring but old issue" in mold.text
    assert "all mentions from" in mold.text
    parking = next(c for c in result.claims if c.theme == "parking")
    assert parking.is_current is True
    assert "recurring current issue" in parking.text


def test_fewer_than_five_text_reviews_is_insufficient():
    reviews = [review("a", "Parking is a nightmare."), review("b", "Parking is terrible."), review("c", ""), review("d", FILLER)]
    result = run(reviews)
    assert result.score is None
    assert result.confidence == "insufficient"
    assert "Only 3 reviews with text were available; at least 5 are needed." in result.summary
    assert [c.theme for c in result.claims] == ["parking"]


def test_no_issue_mentions_is_insufficient_not_perfect():
    result = run([review(f"f{i}", FILLER) for i in range(20)])
    assert result.score is None
    assert result.confidence == "insufficient"
    assert "absence of complaints is not treated as evidence" in result.summary


def test_isolated_only_issues_still_score_but_say_nothing_recurred():
    reviews = [review("a", "Mold in the closet.")] + [review(f"f{i}", FILLER) for i in range(5)]
    result = run(reviews)
    assert result.score == 10.0
    assert result.claims == []
    assert result.negative_evidence_ids == ["a"]
    assert "none of the issues raised recurred" in result.summary


@pytest.mark.parametrize(("count", "confidence"), [(5, "low"), (8, "medium"), (15, "high")])
def test_confidence_follows_corpus_size(count, confidence):
    reviews = [review("p1", "Parking is a nightmare."), review("p2", "Parking is limited.")]
    reviews += [review(f"f{i}", FILLER) for i in range(count - 2)]
    assert run(reviews).confidence == confidence


def test_score_floor_is_one():
    themes = [
        "Parking is a nightmare.", "Mold in the bathroom.", "The elevator is always broken.", "Laundry machines are always broken.",
        "Internet is slow.", "Low water pressure.", "Trash is overflowing.",
    ]
    reviews = [review(f"{i}{suffix}", text) for i, text in enumerate(themes) for suffix in "ab"]
    result = run(reviews)
    assert len(result.details["recurring_current"]) == 7
    assert result.score == 1.0
