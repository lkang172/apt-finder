from datetime import UTC, datetime, timedelta

from aptfinder.evaluators.base import ReviewEvidence
from aptfinder.evaluators.comments_summary import summarize_comments

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def review(i, text, rating=1.0, years_ago=1.0, summary=False):
    return ReviewEvidence(f"ev{i}", "google_places", None, f"R{i}", rating, NOW - timedelta(days=365 * years_ago), text, is_summary=summary)


def test_summarizes_complaints_and_praise_with_counts():
    reviews = [
        review(1, "There's a huge cockroach problem in the kitchen."),
        review(2, "Parties are non stop with loud music, very noisy."),
        review(3, "Thin walls, I hear my neighbors."),
        review(4, "Staff were friendly and helpful.", rating=5.0),
        review(5, "Super quiet and peaceful.", rating=5.0, years_ago=3),
    ]
    result = summarize_comments(reviews, NOW)
    assert result.text.startswith("Complaints: ")
    assert "cockroach" in result.text.lower()
    assert "Praise: " in result.text
    assert result.reviews_used == 5 and len(result.evidence_ids) == 5
    assert "not AI-generated" in result.method


def test_no_text_means_no_summary():
    assert summarize_comments([review(1, "   ")], NOW) is None
    assert summarize_comments([], NOW) is None


def test_old_reviews_are_flagged_and_ai_summaries_ignored():
    reviews = [review(1, "Roaches everywhere.", years_ago=5), review(2, "Google AI text", summary=True)]
    result = summarize_comments(reviews, NOW)
    assert "more than 2 years old" in result.text
    assert result.reviews_used == 1


def test_no_topics_found_is_stated_plainly():
    result = summarize_comments([review(1, "We moved in last spring.", rating=4.0)], NOW)
    assert result.text.startswith("No specific complaints or praise topics")

