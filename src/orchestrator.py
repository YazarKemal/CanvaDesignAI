"""Canva Prompt Workbench orchestration — the three-stage flow.

    user request
        │
        ▼
    Architect (DeepSeek)  -> technical design brief (Canva expert)
        │
        ▼
    Generator (Claude)    -> copy-paste-ready prompt card
        │
        ▼
    Reviewer (DeepSeek)   -> score; if < pass_threshold, feed feedback back
                             to the Generator and retry (up to max_attempts)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.architect import build_brief
from src.generator import generate_prompt
from src.reviewer import ReviewResult, review_prompt

DEFAULT_MAX_ATTEMPTS = 3


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
    against Reviewer feedback until it passes or `max_attempts` is exhausted.
    Always returns the best-scoring attempt.
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
        card = generate_prompt(brief, concept=concept, feedback=feedback, **generator_kwargs)
        review = review_prompt(card, **reviewer_kwargs)
        history.append({"attempt": attempt, "card": card, "score": review.score, "feedback": review.feedback})

        if best_review is None or review.score > best_review.score:
            best_card, best_review = card, review

        if review.passed:
            return PipelineResult(
                card=card, brief=brief, review=review, attempts=attempt, approved=True, history=history
            )

        feedback = review.feedback

    assert best_card is not None and best_review is not None
    return PipelineResult(
        card=best_card, brief=brief, review=best_review, attempts=max_attempts, approved=False, history=history
    )
