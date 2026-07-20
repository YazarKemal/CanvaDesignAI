"""Generator agent: turns a plain concept into a world-class visual prompt.

Uses Claude (Anthropic API) with the Art Director Constitution embedded as
a system prompt, and forces the reply into the PROMPT_OUTPUT_SCHEMA shape.
The output is a PROMPT for DALL-E 3 / Canva Magic Media — this agent never
generates images.
"""

from __future__ import annotations

import json
import os
from typing import Any

import anthropic

from src.constitution import as_prompt_block, load_constitution
from src.schema import PromptValidationError, validate_prompt

DEFAULT_MODEL = "claude-sonnet-5"

OUTPUT_FORMAT_EXAMPLE = {
    "concept": "Grand Opening Cafe",
    "image_prompt": (
        "A flat-white with delicate rosetta latte art in a matte-black ceramic cup, "
        "resting on a reclaimed-oak counter, photography shot on 85mm f/1.4 with "
        "shallow depth of field, rule-of-thirds with the cup on the lower-left third "
        "and clean empty upper space for a headline, soft golden-hour window light "
        "raking from the right, warm amber and deep espresso tones against a cream "
        "background, cozy and artisanal mood, high detail."
    ),
    "negative_prompt": (
        "text, watermark, signature, logo, extra fingers, deformed hands, cluttered "
        "background, low resolution, jpeg artifacts, harsh oversaturation"
    ),
    "art_direction": {
        "medium": "photography",
        "composition": "rule of thirds, subject lower-left, empty upper third for headline, eye-level",
        "lighting": "soft golden-hour window light from the right",
        "color_palette": ["#4A2E1B", "#D4A373", "#F5EFE6"],
        "mood": "cozy, artisanal, inviting",
        "camera": "85mm f/1.4, shallow depth of field",
    },
    "aspect_ratio": "4:5",
    "target_tools": ["DALL-E 3", "Canva Magic Media"],
}


def _system_prompt() -> str:
    return (
        "You are the Generator agent inside CanvaDesignAI — a world-class art "
        "director and prompt engineer. Given a plain concept, you engineer ONE "
        "graphic-designer-quality image-generation prompt (for DALL-E 3 / Canva "
        "Magic Media) as a single JSON object and nothing else — no prose, no "
        "markdown fences, no commentary. You never generate images; you only "
        "produce the prompt.\n\n"
        f"{as_prompt_block(load_constitution())}\n\n"
        "OUTPUT FORMAT — your reply MUST be valid JSON matching exactly this "
        "shape (keys and nesting), e.g.:\n"
        f"{json.dumps(OUTPUT_FORMAT_EXAMPLE, ensure_ascii=False, indent=2)}\n\n"
        "Rules for the reply:\n"
        "- image_prompt: the star deliverable. One or two flowing sentences built "
        "per the prompt_structure rules (subject -> medium -> composition -> "
        "lighting -> color/mood -> camera -> quality). Concrete and renderable.\n"
        "- negative_prompt: what to exclude, seeded from the constitution baseline.\n"
        "- art_direction: the explicit choices behind the prompt (medium, "
        "composition, lighting, 3-5 color palette, mood; camera optional).\n"
        "- aspect_ratio: 'W:H' chosen for the intended use (do NOT put ratio flags "
        "in image_prompt).\n"
        "- Respond with raw JSON only."
    )


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[len("json"):]
    return json.loads(text.strip())


def generate_prompt(
    concept: str,
    *,
    feedback: str | None = None,
    model: str = DEFAULT_MODEL,
    client: anthropic.Anthropic | None = None,
) -> dict[str, Any]:
    """Generate a structured visual prompt for `concept`.

    If `feedback` is provided (from a prior Reviewer rejection), it is
    appended so the Generator can course-correct on the next attempt.
    """
    client = client or anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    user_message = f"Concept: {concept}"
    if feedback:
        user_message += (
            "\n\nThe previous prompt was rejected by the Reviewer agent. "
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
        raise PromptValidationError(f"Generator did not return valid JSON: {exc}\nRaw: {raw_text}") from exc

    validate_prompt(draft)
    return draft
