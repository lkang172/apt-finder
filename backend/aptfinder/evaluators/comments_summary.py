from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from aptfinder.evaluators.base import ReviewEvidence
from aptfinder.evaluators.classifier import classify_reviews
from aptfinder.evaluators.intelligence import theme_label

METHOD = (
    "Keyword-based summary written by Apt Finder (not AI-generated). Google's API shares at most 5 review texts "
    "per place, so topics reflect only that sample; the star rating covers every Google rating."
)
MAX_THEMES = 6
OLD_AFTER = timedelta(days=730)


@dataclass(frozen=True)
class CommentsSummary:
    text: str
    method: str
    reviews_used: int
    evidence_ids: list[str]


def _phrase(counts: Counter) -> str:
    return "; ".join(f"{theme_label(theme).lower()} ({n} {'review' if n == 1 else 'reviews'})" for theme, n in counts.most_common(MAX_THEMES))


def summarize_comments(reviews: Sequence[ReviewEvidence], now: datetime) -> CommentsSummary | None:
    texted = [r for r in reviews if r.text.strip() and not r.is_summary]
    if not texted:
        return None
    complaints: Counter = Counter()
    praise: Counter = Counter()
    for mention in classify_reviews(texted):
        if mention.polarity == "negative":
            complaints[mention.theme] += 1
        elif mention.polarity == "positive":
            praise[mention.theme] += 1

    if complaints or praise:
        sentences = [f"Complaints: {_phrase(complaints) or 'none identified'}.", f"Praise: {_phrase(praise) or 'none identified'}."]
    else:
        sentences = ["No specific complaints or praise topics found in the review texts."]
    if all(r.review_date and now - r.review_date > OLD_AFTER for r in texted):
        sentences.append("All of these reviews are more than 2 years old.")
    return CommentsSummary(" ".join(sentences), METHOD, len(texted), [r.evidence_id for r in texted])
