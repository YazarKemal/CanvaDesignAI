"""Canva Prompt Workbench orchestration — the three-stage flow.

Single-engine architecture: Architect, Generator and Reviewer all run on
DeepSeek.

    user request
        │
        ▼
    Architect (DeepSeek)  -> technical design brief (Canva expert)
        │
        ▼
    Generator (DeepSeek)  -> Canva automation card (3 mandatory components)
        │
        ▼
    Reviewer (DeepSeek)   -> score; if < pass_threshold, feed feedback back
                             to the Generator and retry (up to max_attempts)

If the Generator's own output fails schema validation or trips the
code-level forbidden-chat-phrase guard (src/schema.py), that failure is
treated the same as a low Reviewer score: fed back as feedback and retried,
rather than crashing the whole pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.architect import build_brief
from src.generator import generate_prompt
from src.reviewer import ReviewResult, review_prompt
from src.schema import PromptValidationError

DEFAULT_MAX_ATTEMPTS = 3


class PipelineError(RuntimeError):
    """Raised when the Generator could not produce a valid card within max_attempts."""


@dataclass
class PipelineResult:
    card: dict[str, Any]
    brief: dict[str, Any]
    review: ReviewResult
    attempts: int
    approved: bool
    history: list[dict[str, Any]] = field(default_factory=list)


def run_pipeline(
    concept: str,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    architect_kwargs: dict[str, Any] | None = None,
    generator_kwargs: dict[str, Any] | None = None,
    reviewer_kwargs: dict[str, Any] | None = None,
) -> PipelineResult:
    """Run Architect -> Generator -> Reviewer for `concept`.

    The Architect runs once to fix the brief; the Generator then revises
    against Reviewer feedback (or its own validation failures) until it
    passes or `max_attempts` is exhausted. Always returns the best-scoring
    attempt. Raises PipelineError if no attempt ever produced a valid card.
    """
    architect_kwargs = architect_kwargs or {}
    generator_kwargs = generator_kwargs or {}
    reviewer_kwargs = reviewer_kwargs or {}

    brief = build_brief(concept, **architect_kwargs)

    history: list[dict[str, Any]] = []
    best_card: dict[str, Any] | None = None
    best_review: ReviewResult | None = None
    feedback: str | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            card = generate_prompt(brief, concept=concept, feedback=feedback, **generator_kwargs)
        except PromptValidationError as exc:
            feedback = str(exc)
            history.append({"attempt": attempt, "card": None, "score": 0.0, "feedback": feedback})
            continue

        review = review_prompt(card, **reviewer_kwargs)
        history.append({"attempt": attempt, "card": card, "score": review.score, "feedback": review.feedback})

        if best_review is None or review.score > best_review.score:
            best_card, best_review = card, review

        if review.passed:
            return PipelineResult(
                card=card, brief=brief, review=review, attempts=attempt, approved=True, history=history
            )

        feedback = review.feedback

    if best_card is None or best_review is None:
        raise PipelineError(
            f"Generator failed to produce a valid card in {max_attempts} attempts. "
            f"Last error: {feedback}"
        )

    return PipelineResult(
        card=best_card, brief=brief, review=best_review, attempts=max_attempts, approved=False, history=history
    )
