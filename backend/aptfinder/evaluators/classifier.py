import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from functools import cache
from typing import Protocol

from aptfinder.evaluators.base import ReviewEvidence
from aptfinder.evaluators.lexicon import (
    ANAPHORA_START,
    CLAUSE_END,
    LIST_CONNECTORS,
    NEGATION_EXCEPTIONS,
    NEGATION_FILLER,
    NEGATION_WINDOW,
    NEGATIVE,
    NEGATORS,
    NEUTRAL,
    POST_NEGATION,
    RECURRENCE,
    THEMES,
    THEMES_BY_NAME,
    ThemeSpec,
)

logger = logging.getLogger(__name__)

MAX_EXCERPT_CHARS = 280
EXCERPT_LEAD_CHARS = 120

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\s*\n+\s*|(?<=[.!?])(?=[A-Z][a-z])")
_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?|[^\sa-z0-9]", re.IGNORECASE)
_POST_NEGATION = re.compile(POST_NEGATION, re.IGNORECASE)
_CLAUSE_END = re.compile(CLAUSE_END, re.IGNORECASE)
_RECURRENCE = re.compile(RECURRENCE, re.IGNORECASE)
_ANAPHORA_START = re.compile(ANAPHORA_START, re.IGNORECASE)
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', " ": " "})


@dataclass(frozen=True)
class Mention:
    category: str
    theme: str
    polarity: str
    excerpt: str
    evidence_id: str
    recurring: bool = False


class SemanticClassifier(Protocol):
    def classify(self, review: ReviewEvidence) -> list[Mention]: ...


@dataclass(frozen=True)
class _Token:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class _Match:
    spec: ThemeSpec
    start: int
    end: int
    negatable: bool
    order: int


def normalize_text(text: str) -> str:
    return (text or "").translate(_QUOTES)


def _collapse(text: str) -> str:
    return " ".join(text.split())


def split_sentences(text: str) -> list[str]:
    return [_collapse(part) for part in _SENTENCE_SPLIT.split(normalize_text(text)) if part and part.strip()]


def _excerpt(sentence: str, start: int, end: int) -> str:
    if len(sentence) <= MAX_EXCERPT_CHARS:
        return sentence
    window_start = max(0, min(start - EXCERPT_LEAD_CHARS, len(sentence) - MAX_EXCERPT_CHARS))
    window_end = min(len(sentence), window_start + MAX_EXCERPT_CHARS)
    window_end = max(window_end, min(len(sentence), end))
    prefix = "…" if window_start > 0 else ""
    suffix = "…" if window_end < len(sentence) else ""
    return f"{prefix}{sentence[window_start:window_end].strip()}{suffix}"


def _is_negator(word: str) -> bool:
    return word in NEGATORS or word.endswith("n't")


def _starts_exception(tokens: Sequence[_Token], index: int) -> bool:
    phrase = " ".join(t.text for t in tokens[index:index + 4])
    return any(phrase == exception or phrase.startswith(exception + " ") for exception in NEGATION_EXCEPTIONS)


def _negated_before(tokens: Sequence[_Token], match_start: int) -> bool:
    first = next((i for i, t in enumerate(tokens) if t.start >= match_start), len(tokens))
    skipped = 0
    for index in range(first - 1, -1, -1):
        word = tokens[index].text
        if _is_negator(word):
            return not _starts_exception(tokens, index)
        if word not in NEGATION_FILLER or skipped >= NEGATION_WINDOW:
            return False
        skipped += 1
    return False


def _negated_after(sentence: str, match_end: int) -> bool:
    remainder = _CLAUSE_END.split(sentence[match_end:], maxsplit=1)[0]
    return bool(_POST_NEGATION.match(remainder))


def _continues_negated_list(sentence: str, previous: _Match, current: _Match) -> bool:
    if previous.spec.polarity != current.spec.polarity or current.start < previous.end:
        return False
    gap = [t.lower() for t in _TOKEN.findall(sentence[previous.end:current.start])]
    return len(gap) <= 4 and all(word in LIST_CONNECTORS for word in gap)


def describes_recurrence(sentence: str, following: str) -> bool:
    if _RECURRENCE.search(sentence):
        return True
    return bool(following and _ANAPHORA_START.match(following) and _RECURRENCE.search(following))


class LexiconClassifier:
    def __init__(self, themes: Sequence[ThemeSpec] = THEMES):
        self._themes = {spec.theme: spec for spec in themes}
        self._patterns: list[tuple[int, ThemeSpec, re.Pattern[str], bool]] = []
        for order, spec in enumerate(themes):
            for fragment in spec.patterns:
                self._patterns.append((order, spec, re.compile(rf"\b(?:{fragment})\b", re.IGNORECASE), True))
            for fragment in spec.fixed_patterns:
                self._patterns.append((order, spec, re.compile(rf"\b(?:{fragment})\b", re.IGNORECASE), False))

    def classify(self, review: ReviewEvidence) -> list[Mention]:
        sentences = split_sentences(review.text)
        mentions: dict[tuple[str, str], Mention] = {}
        for index, sentence in enumerate(sentences):
            following = sentences[index + 1] if index + 1 < len(sentences) else ""
            for match, spec in self._sentence_themes(sentence):
                key = (spec.category, spec.theme)
                recurring = spec.polarity == NEGATIVE and describes_recurrence(sentence, following)
                existing = mentions.get(key)
                if existing is None:
                    mentions[key] = Mention(
                        spec.category, spec.theme, spec.polarity, _excerpt(sentence, match.start, match.end),
                        review.evidence_id, recurring,
                    )
                elif recurring and not existing.recurring:
                    mentions[key] = replace(existing, recurring=True)
        return list(mentions.values())

    def _raw_matches(self, sentence: str) -> list[_Match]:
        return [
            _Match(spec, found.start(), found.end(), negatable, order)
            for order, spec, pattern, negatable in self._patterns
            for found in pattern.finditer(sentence)
        ]

    def _resolve_overlaps(self, matches: list[_Match]) -> list[_Match]:
        accepted: list[_Match] = []
        for match in sorted(matches, key=lambda m: (-(m.end - m.start), m.start, m.order, not m.negatable)):
            if match.spec.polarity == NEUTRAL:
                if not any(a.spec.theme == match.spec.theme for a in accepted):
                    accepted.append(match)
                continue
            overlaps = any(
                a.spec.category == match.spec.category and a.spec.polarity != NEUTRAL
                and a.start < match.end and match.start < a.end
                for a in accepted
            )
            if not overlaps:
                accepted.append(match)
        return sorted(accepted, key=lambda m: (m.start, m.end, m.order))

    def _sentence_themes(self, sentence: str) -> Iterable[tuple[_Match, ThemeSpec]]:
        tokens = [_Token(t.group().lower(), t.start(), t.end()) for t in _TOKEN.finditer(sentence)]
        matches = self._resolve_overlaps(self._raw_matches(sentence))
        present = {m.spec.theme for m in matches}
        previous: _Match | None = None
        previous_negated = False
        # Negation is evaluated over every match before suppression so a suppressed list head
        # ("never had any bugs or roaches") still passes its negation on to the rest of the list.
        for match in matches:
            negated = match.negatable and (
                _negated_before(tokens, match.start)
                or _negated_after(sentence, match.end)
                or (previous is not None and previous_negated and _continues_negated_list(sentence, previous, match))
            )
            previous, previous_negated = match, negated
            if present.intersection(match.spec.suppressed_by):
                continue
            if not negated:
                yield match, match.spec
            elif match.spec.negated_theme is not None:
                yield match, self._themes[match.spec.negated_theme]


class LLMClassifier:
    """Placeholder for a future model-backed classifier.

    An implementation must return only Mentions whose theme exists in the lexicon catalog, whose polarity matches
    that theme, and whose excerpt is verbatim review text; classify_reviews drops anything else. It must never infer
    a positive mention from the absence of complaints. Until it exists, use LexiconClassifier.
    """

    def __init__(self, model: str | None = None):
        self.model = model

    def classify(self, review: ReviewEvidence) -> list[Mention]:
        raise NotImplementedError("LLM classification is not implemented; use LexiconClassifier")


@cache
def default_classifier() -> LexiconClassifier:
    return LexiconClassifier()


def is_valid_mention(mention: Mention, review: ReviewEvidence) -> bool:
    spec = THEMES_BY_NAME.get(mention.theme)
    if spec is None or spec.category != mention.category or spec.polarity != mention.polarity:
        return False
    if mention.evidence_id != review.evidence_id:
        return False
    quoted = _collapse(normalize_text(mention.excerpt).strip("…"))
    return bool(quoted) and quoted in _collapse(normalize_text(review.text))


def classify_reviews(reviews: Iterable[ReviewEvidence], classifier: SemanticClassifier | None = None) -> list[Mention]:
    active = classifier or default_classifier()
    mentions: list[Mention] = []
    seen: set[tuple[str, str, str]] = set()
    for review in reviews:
        for mention in active.classify(review):
            key = (mention.evidence_id, mention.category, mention.theme)
            if key in seen:
                continue
            if not is_valid_mention(mention, review):
                logger.warning("Dropped unsupported mention %s/%s for %s", mention.category, mention.theme, review.evidence_id)
                continue
            seen.add(key)
            mentions.append(mention)
    return mentions
