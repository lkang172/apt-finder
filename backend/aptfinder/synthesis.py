from typing import Protocol

from aptfinder.evaluators.base import AssessmentDraft, ReviewEvidence


class Synthesizer(Protocol):
    """Optional rewording step between evaluation and the evidence audit. Implementations may only
    rephrase `draft.summary` from the cited evidence; scores, confidence, and claims are fixed."""

    def summarize(self, draft: AssessmentDraft, reviews: list[ReviewEvidence]) -> str | None: ...


class DeterministicSynthesizer:
    def summarize(self, draft: AssessmentDraft, reviews: list[ReviewEvidence]) -> str | None:
        return None


def apply_synthesis(synthesizer: Synthesizer, drafts: dict[str, AssessmentDraft], reviews: list[ReviewEvidence]) -> None:
    for draft in drafts.values():
        rewritten = synthesizer.summarize(draft, reviews)
        if rewritten:
            draft.summary = rewritten
