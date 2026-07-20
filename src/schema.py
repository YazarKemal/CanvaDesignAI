"""JSON schema and validator for the Canva automation card.

The pipeline's deliverable is a single "Canva card" with exactly three
mandatory components: a Magic Media prompt, a layer & typography
architecture, and a direct action tip. This project outputs cards ONLY —
it never chats, never asks the user a question, and never generates images
itself.

In addition to schema shape, `validate_prompt` enforces a hard,
code-level ban on conversational filler ("I can generate...", "Would you
like...", etc.) so the "never chat" rule does not depend on the LLM
remembering to follow its system prompt.
"""

from __future__ import annotations

from typing import Any

import jsonschema

PROMPT_CARD_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "CaVDesign Canva Automation Card",
    "type": "object",
    "required": [
        "concept",
        "magic_media_prompt",
        "negative_prompt",
        "aspect_ratio",
        "target_tool",
        "layer_typography_architecture",
        "direct_action_tip",
    ],
    "properties": {
        "concept": {"type": "string", "minLength": 1},
        "magic_media_prompt": {"type": "string", "minLength": 30},
        "negative_prompt": {"type": "string", "minLength": 1},
        "aspect_ratio": {"type": "string", "minLength": 1},
        "target_tool": {"type": "string", "minLength": 1},
        "layer_typography_architecture": {
            "type": "object",
            "required": ["headline", "subtext", "color_palette", "fonts", "background_layers"],
            "properties": {
                "headline": {"type": "string", "minLength": 1},
                "subtext": {"type": "string", "minLength": 1},
                "color_palette": {
                    "type": "array",
                    "items": {"type": "string", "pattern": r"^#[0-9A-Fa-f]{6}$"},
                    "minItems": 3,
                    "maxItems": 5,
                },
                "fonts": {
                    "type": "object",
                    "required": ["headline_font", "body_font"],
                    "properties": {
                        "headline_font": {"type": "string", "minLength": 1},
                        "body_font": {"type": "string", "minLength": 1},
                    },
                    "additionalProperties": True,
                },
                "background_layers": {"type": "string", "minLength": 1},
                "magic_media_style": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "direct_action_tip": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 2,
        },
        "canva_keywords": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
    },
    "additionalProperties": True,
}

# Deterministic, code-level ban — independent of whether the LLM honors its
# system prompt. Matched case-insensitively as substrings against every
# string leaf in the card.
FORBIDDEN_PHRASES: tuple[str, ...] = (
    "i can generate",
    "i can create",
    "i could generate",
    "i'd be happy",
    "i would be happy",
    "i'm happy to",
    "i am happy to",
    "would you like",
    "do you want",
    "do you'd like",
    "let me know",
    "feel free",
    "sure!",
    "sure,",
    "certainly!",
    "of course!",
    "here is",
    "here's",
    "i hope this helps",
    "as an ai",
    "as a language model",
    "great question",
    "hi!",
    "hello!",
    "no problem",
)


class PromptValidationError(ValueError):
    """Raised when a card fails schema validation or contains banned chat language."""


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _iter_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _iter_strings(v)


def find_forbidden_phrase(card: dict[str, Any]) -> str | None:
    """Return the first banned conversational phrase found anywhere in the
    card's string values, or None if the card is clean."""
    for text in _iter_strings(card):
        lowered = text.lower()
        for phrase in FORBIDDEN_PHRASES:
            if phrase in lowered:
                return phrase
    return None


def validate_prompt(card: dict[str, Any]) -> None:
    """Validate a Canva card: schema shape + zero conversational language.

    Raises PromptValidationError with a readable message if either check fails.
    """
    try:
        jsonschema.validate(instance=card, schema=PROMPT_CARD_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise PromptValidationError(f"Card failed schema validation: {exc.message}") from exc

    banned = find_forbidden_phrase(card)
    if banned:
        raise PromptValidationError(
            f"Card contains banned conversational language ('{banned}'). "
            "Output must be pure Canva automation data — no chat, no questions."
        )
