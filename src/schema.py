"""JSON schema and validator for the visual-prompt output.

Every prompt produced by the Generator agent must conform to this schema
before it is handed to the Reviewer agent. The deliverable is a
graphic-designer-quality image-generation PROMPT (for DALL-E 3 / Canva
Magic Media) — this project never generates images itself.
"""

from __future__ import annotations

from typing import Any

import jsonschema

PROMPT_OUTPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "CanvaDesignAI Visual Prompt Output",
    "type": "object",
    "required": [
        "concept",
        "image_prompt",
        "negative_prompt",
        "art_direction",
        "aspect_ratio",
        "target_tools",
    ],
    "properties": {
        "concept": {"type": "string", "minLength": 1},
        "image_prompt": {"type": "string", "minLength": 30},
        "negative_prompt": {"type": "string", "minLength": 1},
        "art_direction": {
            "type": "object",
            "required": ["medium", "composition", "lighting", "color_palette", "mood"],
            "properties": {
                "medium": {"type": "string", "minLength": 1},
                "composition": {"type": "string", "minLength": 1},
                "lighting": {"type": "string", "minLength": 1},
                "color_palette": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "minItems": 3,
                    "maxItems": 5,
                },
                "mood": {"type": "string", "minLength": 1},
                "camera": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "aspect_ratio": {"type": "string", "pattern": r"^\d{1,2}:\d{1,2}$"},
        "target_tools": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
        },
    },
    "additionalProperties": True,
}


class PromptValidationError(ValueError):
    """Raised when a prompt draft does not conform to PROMPT_OUTPUT_SCHEMA."""


def validate_prompt(draft: dict[str, Any]) -> None:
    """Validate a visual-prompt draft against the output schema.

    Raises PromptValidationError with a readable message if invalid.
    """
    try:
        jsonschema.validate(instance=draft, schema=PROMPT_OUTPUT_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise PromptValidationError(f"Prompt draft failed schema validation: {exc.message}") from exc
