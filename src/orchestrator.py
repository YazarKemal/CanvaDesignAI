"""Canva Prompt Workbench orchestration — the three-stage flow.

Single-engine architecture: Architect, Generator and Reviewer all run on
DeepSeek.

    user request (+ optional brand slug)
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

If the Generator's own output fails schema validation, trips the
code-level forbidden-chat-phrase guard, or (when a brand is active)
violates the brand's fonts/colors (src/schema.py), that failure is treated
the same as a low Reviewer score: fed back as feedback and retried, rather
than crashing the whole pipeline.

When `brand` is given, it is resolved once via `src.brand_profiles.load_brand`
and threaded into every stage: the Architect constrains the brief's palette
and text_zone to the brand, the Generator is required to use the brand's
exact fonts/colors, and the Reviewer scores brand_fit against the same
profile. There is no separate "Critic" stage — the Reviewer already fills
that role; brand compliance is scored by the same call, and the factual
parts (exact font/color match) are enforced deterministically in
src/schema.py, not left to LLM judgment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.architect import build_brief
from src.brand_profiles import load_brand
from src.generator import generate_prompt
from src.reviewer import ReviewResult, review_prompt
from src.schema import PromptValidationError
from src.style_presets import load_style

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
    brand: str | None = None,
    style: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    architect_kwargs: dict[str, Any] | None = None,
    generator_kwargs: dict[str, Any] | None = None,
    reviewer_kwargs: dict[str, Any] | None = None,
) -> PipelineResult:
    """Run Architect -> Generator -> Reviewer for `concept`.

    `brand` is a brand profile slug (config/brands/<slug>.json). When
    given, every stage is constrained to that brand's fonts/colors; when
    omitted, behavior is unchanged from the generic engine.

    `style` is an elite style-preset slug (config/styles/<slug>.json). When
    given, its keyword block steers the Architect's art direction and is
    injected into the Generator, whose magic_media_prompt is then required
    (code-level) to contain the preset's keywords. Brand and style are
    orthogonal and may both be active.

    The Architect runs once to fix the brief; the Generator then revises
    against Reviewer feedback (or its own validation failures) until it
    passes or `max_attempts` is exhausted. Always returns the best-scoring
    attempt. Raises PipelineError if no attempt ever produced a valid card.
    """
    architect_kwargs = architect_kwargs or {}
    generator_kwargs = generator_kwargs or {}
    reviewer_kwargs = reviewer_kwargs or {}

    brand_profile = load_brand(brand) if brand else None

    # Style resolution: manual override takes precedence over auto-selection.
    style_preset = load_style(style) if style else None
    brief = build_brief(concept, brand=brand_profile, style=style_preset, **architect_kwargs)

    # If the user didn't pick a style, the Architect chose one automatically.
    if style_preset is None:
        auto_style_id = brief.get("selected_style_id")
        if auto_style_id:
            try:
                style_preset = load_style(auto_style_id)
            except Exception:
                style_preset = None  # invalid slug → continue without style

    history: list[dict[str, Any]] = []
    best_card: dict[str, Any] | None = None
    best_review: ReviewResult | None = None
    feedback: str | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            card = generate_prompt(
                brief,
                concept=concept,
                brand=brand_profile,
                style=style_preset,
                feedback=feedback,
                **generator_kwargs,
            )
        except PromptValidationError as exc:
            feedback = str(exc)
            history.append({"attempt": attempt, "card": None, "score": 0.0, "feedback": feedback})
            continue

        review = review_prompt(card, brand=brand_profile, **reviewer_kwargs)
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
