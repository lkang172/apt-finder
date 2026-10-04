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
    noun = "review" if shown == 1 else "reviews"
    if total_count and total_count > shown:
        head = f"Sample only: the {shown} of {total_count} Google {noun} that Google's API shares (chosen by Google, not the full set)"
    else:
        head = f"All {shown} Google {noun} with text"
    years = sorted(r.review_date.year for r in texted if r.review_date)
    if years:
        head += f", dated {years[0]}" if years[0] == years[-1] else f", dated {years[0]}–{years[-1]}"
    ratings = [r.rating for r in texted if r.rating is not None]
    if ratings:
        head += f", averaging {sum(ratings) / len(ratings):.1f}★"

    sentences = [head + "."]
    scope = "this review" if shown == 1 else f"these {shown}"
    if complaints or praise:
        sentences.append(f"In {scope}, complaints: {_phrase(complaints) or 'none identified'}.")
        sentences.append(f"Praise: {_phrase(praise) or 'none identified'}.")
    else:
        sentences.append(f"Keyword analysis found no specific topics in {scope}.")
    if all(r.review_date and now - r.review_date > OLD_AFTER for r in texted):
        sentences.append("All of these reviews are more than 2 years old.")
    return CommentsSummary(" ".join(sentences), METHOD, shown, [r.evidence_id for r in texted])
