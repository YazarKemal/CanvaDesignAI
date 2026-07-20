"""Generator agent: turns a concept into a structured design draft.

Uses Claude (Anthropic API) with the Design Constitution embedded as a
system prompt, and forces the reply into the DESIGN_OUTPUT_SCHEMA shape.
"""

from __future__ import annotations

import json
import os
from typing import Any

import anthropic

from src.constitution import as_prompt_block, load_constitution
from src.schema import DesignValidationError, validate_design

DEFAULT_MODEL = "claude-sonnet-5"

OUTPUT_FORMAT_EXAMPLE = {
    "theme": "Modern Cafe",
    "color_palette": ["#4A2E1B", "#F5EFE6", "#D4A373"],
    "typography": {
        "headline": "Placeholder: [Cafe Name]",
        "body_text": "Join us for warm vibes!",
    },
    "image_prompts": {
        "main_visual": (
            "Cinematic shot of a latte with perfect micro-foam art, resting on a "
            "wooden table, soft window light, subtle drop shadow."
        )
    },
    "layout_instructions": (
        "Place text at the top 40% of the canvas. Keep the bottom 60% for the "
        "main visual inside a draggable frame."
    ),
}


def _system_prompt() -> str:
    return (
        "You are the Generator agent inside CanvaDesignAI. Given a short design "
        "concept, you produce ONE design draft as a single JSON object and "
        "nothing else — no prose, no markdown fences, no commentary.\n\n"
        f"{as_prompt_block(load_constitution())}\n\n"
        "OUTPUT FORMAT — your reply MUST be valid JSON matching exactly this "
        "shape (keys and nesting), e.g.:\n"
        f"{json.dumps(OUTPUT_FORMAT_EXAMPLE, ensure_ascii=False, indent=2)}\n\n"
        "Rules for the reply:\n"
        "- color_palette: 3-5 hex colors (e.g. \"#4A2E1B\"), chosen per the "
        "color_theory rules in the constitution.\n"
        "- typography.headline / typography.body_text: pick ONE approved_pairing "
        "from the constitution and describe it plus give placeholder copy.\n"
        "- image_prompts.main_visual: a single vivid, camera-ready prompt string.\n"
        "- layout_instructions: concrete placement instructions honoring the "
        "white_space and layout rules.\n"
        "- Respond with raw JSON only."
    )


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[len("json"):]
    return json.loads(text.strip())


def generate_design(
    concept: str,
    *,
    feedback: str | None = None,
    model: str = DEFAULT_MODEL,
    client: anthropic.Anthropic | None = None,
) -> dict[str, Any]:
    """Generate a structured design draft for `concept`.

    If `feedback` is provided (from a prior Reviewer rejection), it is
    appended so the Generator can course-correct on the next attempt.
    """
    client = client or anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    user_message = f"Design concept: {concept}"
    if feedback:
        user_message += (
            "\n\nThe previous draft was rejected by the Reviewer agent. "
            f"Fix these issues before responding:\n{feedback}"
        )

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=_system_prompt(),
        messages=[{"role": "user", "content": user_message}],
    )
    raw_text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )

    try:
        draft = _extract_json(raw_text)
    except json.JSONDecodeError as exc:
        raise DesignValidationError(f"Generator did not return valid JSON: {exc}\nRaw: {raw_text}") from exc

    validate_design(draft)
    return draft
