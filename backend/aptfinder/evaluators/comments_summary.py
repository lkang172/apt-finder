from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from aptfinder.evaluators.base import ReviewEvidence
from aptfinder.evaluators.classifier import classify_reviews
from aptfinder.evaluators.intelligence import theme_label

METHOD = (
    "Keyword-based summary written by Apt Finder from the review texts Google returned "
    "(not AI-generated; Google's API returns at most 5 review texts per place)."
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


def summarize_comments(reviews: Sequence[ReviewEvidence], total_count: int | None, now: datetime) -> CommentsSummary | None:
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

    shown = len(texted)
    head = f"From the {shown} Google review {'text' if shown == 1 else 'texts'} returned"
    if total_count and total_count > shown:
        head += f" (of {total_count} Google ratings)"
    years = sorted(r.review_date.year for r in texted if r.review_date)
    if years:
        head += f", dated {years[0]}" if years[0] == years[-1] else f", dated {years[0]}–{years[-1]}"
    ratings = [r.rating for r in texted if r.rating is not None]
    if ratings:
        head += f", averaging {sum(ratings) / len(ratings):.1f}★"

    sentences = [head + "."]
    if complaints or praise:
        sentences.append(f"Complaints: {_phrase(complaints) or 'none identified'}.")
        sentences.append(f"Praise: {_phrase(praise) or 'none identified'}.")
    else:
        sentences.append("Keyword analysis found no specific topics in these reviews.")
    if all(r.review_date and now - r.review_date > OLD_AFTER for r in texted):
        sentences.append("All of these reviews are more than 2 years old.")
    return CommentsSummary(" ".join(sentences), METHOD, shown, [r.evidence_id for r in texted])
