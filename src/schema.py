"""JSON schema and validator for the Canva prompt card.

The pipeline's deliverable is a single "prompt card" — a copy-paste-ready
image prompt plus the parameters the CaVDesign chat UI renders. The field
names below map 1:1 onto the ChatPromptCard component (prompt_text,
aspect_ratio, target_tool, canva_tip). This project outputs prompts only;
it never generates images.
"""

from __future__ import annotations

from typing import Any

import jsonschema

PROMPT_CARD_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "CaVDesign Prompt Card",
    "type": "object",
    "required": [
        "concept",
        "prompt_text",
        "negative_prompt",
        "aspect_ratio",
        "target_tool",
        "canva_tip",
        "art_direction",
    ],
    "properties": {
        "concept": {"type": "string", "minLength": 1},
        "prompt_text": {"type": "string", "minLength": 30},
        "negative_prompt": {"type": "string", "minLength": 1},
        "aspect_ratio": {"type": "string", "minLength": 1},
        "target_tool": {"type": "string", "minLength": 1},
        "canva_tip": {"type": "string", "minLength": 1},
        "art_direction": {
            "type": "object",
            "required": ["color_palette", "lighting", "mood"],
            "properties": {
                "color_palette": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "minItems": 3,
                    "maxItems": 5,
                },
                "lighting": {"type": "string", "minLength": 1},
                "mood": {"type": "string", "minLength": 1},
                "magic_media_style": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "canva_keywords": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
    },
    "additionalProperties": True,
}


class PromptValidationError(ValueError):
    """Raised when a prompt card does not conform to PROMPT_CARD_SCHEMA."""


def validate_prompt(card: dict[str, Any]) -> None:
    """Validate a prompt card against the output schema.

    Raises PromptValidationError with a readable message if invalid.
    """
    try:
        jsonschema.validate(instance=card, schema=PROMPT_CARD_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise PromptValidationError(f"Prompt card failed schema validation: {exc.message}") from exc
