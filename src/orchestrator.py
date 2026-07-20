"""Dual-agent orchestration: Generator (Claude) <-> Reviewer (DeepSeek).

run_pipeline() drives the loop described in the design constitution:
1. Generator drafts a design from a concept.
2. Reviewer scores it against the constitution's rubric.
3. If it fails, the Reviewer's feedback is fed back to the Generator for a
   revision, up to `max_attempts`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.generator import generate_design
from src.reviewer import ReviewResult, review_design

DEFAULT_MAX_ATTEMPTS = 3


@dataclass
class PipelineResult:
    design: dict[str, Any]
    review: ReviewResult
    attempts: int
    approved: bool
    history: list[dict[str, Any]] = field(default_factory=list)


def run_pipeline(
    concept: str,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    generator_kwargs: dict[str, Any] | None = None,
    reviewer_kwargs: dict[str, Any] | None = None,
) -> PipelineResult:
    """Run the Generator -> Reviewer loop for `concept` until it passes or
    `max_attempts` is exhausted. Always returns the best-scoring attempt.
    """
    generator_kwargs = generator_kwargs or {}
    reviewer_kwargs = reviewer_kwargs or {}

    history: list[dict[str, Any]] = []
    best_draft: dict[str, Any] | None = None
    best_review: ReviewResult | None = None
    feedback: str | None = None

    for attempt in range(1, max_attempts + 1):
        draft = generate_design(concept, feedback=feedback, **generator_kwargs)
        review = review_design(draft, **reviewer_kwargs)
        history.append({"attempt": attempt, "design": draft, "score": review.score, "feedback": review.feedback})

        if best_review is None or review.score > best_review.score:
            best_draft, best_review = draft, review

        if review.passed:
            return PipelineResult(design=draft, review=review, attempts=attempt, approved=True, history=history)

        feedback = review.feedback

    assert best_draft is not None and best_review is not None
    return PipelineResult(design=best_draft, review=best_review, attempts=max_attempts, approved=False, history=history)
