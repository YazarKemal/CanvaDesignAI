"""JSON schema and validator for the structured design output.

Every design produced by the Generator agent must conform to this schema
before it is handed to the Reviewer agent (and, ultimately, wired up to the
Canva API).
"""

from __future__ import annotations

from typing import Any

import jsonschema

DESIGN_OUTPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "CanvaDesignAI Structured Design Output",
    "type": "object",
    "required": [
        "theme",
        "color_palette",
        "typography",
        "image_prompts",
        "layout_instructions",
    ],
    "properties": {
        "theme": {"type": "string", "minLength": 1},
        "color_palette": {
            "type": "array",
            "items": {"type": "string", "pattern": "^#[0-9A-Fa-f]{6}$"},
            "minItems": 3,
            "maxItems": 5,
        },
        "typography": {
            "type": "object",
            "required": ["headline", "body_text"],
            "properties": {
                "headline": {"type": "string", "minLength": 1},
                "body_text": {"type": "string", "minLength": 1},
            },
            "additionalProperties": True,
        },
        "image_prompts": {
            "type": "object",
            "required": ["main_visual"],
            "properties": {
                "main_visual": {"type": "string", "minLength": 10},
            },
            "additionalProperties": True,
        },
        "layout_instructions": {"type": "string", "minLength": 1},
    },
    "additionalProperties": True,
}


class DesignValidationError(ValueError):
    """Raised when a design draft does not conform to DESIGN_OUTPUT_SCHEMA."""


def validate_design(draft: dict[str, Any]) -> None:
    """Validate a design draft against the structured output schema.

    Raises DesignValidationError with a readable message if invalid.
    """
    try:
        jsonschema.validate(instance=draft, schema=DESIGN_OUTPUT_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise DesignValidationError(f"Design draft failed schema validation: {exc.message}") from exc
