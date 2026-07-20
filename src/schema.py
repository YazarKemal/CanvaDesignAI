"""JSON schema and validator for the Canva automation card.

The pipeline's deliverable is a single "Canva card" with exactly three
mandatory components: a Magic Media prompt, a layer & typography
architecture, and a direct action tip, anchored to one canonical
`text_zone` so the image and the typography layer never disagree about
where the text goes. This project outputs cards ONLY — it never chats,
never asks the user a question, and never generates images itself.

Beyond schema shape, `validate_prompt` enforces several things at the code
level (independent of whether the LLM follows its system prompt):
- a hard ban on conversational filler ("I can generate...", etc.)
- WCAG color contrast (>= 4.5:1 within the palette)
- headline/subtext length limits (real "punchy" hierarchy, not just prose)
- text_zone being consistently referenced in both the image prompt and the
  background_layers description
"""

from __future__ import annotations

from typing import Any

import jsonschema

from src.color_science import InvalidHexColorError, best_contrast_pair

MIN_CONTRAST_RATIO = 4.5  # WCAG AA for normal-size text
MAX_HEADLINE_WORDS = 6
MAX_SUBTEXT_WORDS = 14
TEXT_ZONES: tuple[str, ...] = ("top", "bottom", "left", "right", "center")

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
        "text_zone",
        "layer_typography_architecture",
        "direct_action_tip",
    ],
    "properties": {
        "concept": {"type": "string", "minLength": 1},
        "magic_media_prompt": {"type": "string", "minLength": 30},
        "negative_prompt": {"type": "string", "minLength": 1},
        "aspect_ratio": {"type": "string", "minLength": 1},
        "target_tool": {"type": "string", "minLength": 1},
        "text_zone": {"type": "string", "enum": list(TEXT_ZONES)},
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
    """Raised when a card fails schema validation or any code-level Art
    Director rule (chat language, contrast, hierarchy, zone consistency)."""


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


def _word_count(text: str) -> int:
    return len(text.split())


def _validate_typography_hierarchy(layer: dict[str, Any]) -> None:
    headline_words = _word_count(layer["headline"])
    if headline_words > MAX_HEADLINE_WORDS:
        raise PromptValidationError(
            f"headline has {headline_words} words (max {MAX_HEADLINE_WORDS}) — "
            "must read as a short, punchy, placeholder-ready title."
        )
    subtext_words = _word_count(layer["subtext"])
    if subtext_words > MAX_SUBTEXT_WORDS:
        raise PromptValidationError(
            f"subtext has {subtext_words} words (max {MAX_SUBTEXT_WORDS}) — "
            "must read as one short supporting line, not a paragraph."
        )


def _validate_color_contrast(layer: dict[str, Any]) -> None:
    try:
        _a, _b, ratio = best_contrast_pair(layer["color_palette"])
    except InvalidHexColorError as exc:
        raise PromptValidationError(f"Invalid color in color_palette: {exc}") from exc

    if ratio < MIN_CONTRAST_RATIO:
        raise PromptValidationError(
            f"Best available contrast within color_palette is only {ratio:.1f}:1 "
            f"(need >= {MIN_CONTRAST_RATIO}:1, WCAG AA). Pick a palette with at "
            "least one near-black/near-white or otherwise high-contrast anchor "
            "color so headline text stays legible over the background."
        )


def _validate_text_zone_consistency(card: dict[str, Any]) -> None:
    zone = card["text_zone"].lower()
    prompt_text = card["magic_media_prompt"].lower()
    background_layers = card["layer_typography_architecture"]["background_layers"].lower()

    if zone not in prompt_text:
        raise PromptValidationError(
            f"text_zone is '{zone}' but magic_media_prompt never mentions '{zone}' — "
            "the image's reserved negative space must match text_zone exactly."
        )
    if zone not in background_layers:
        raise PromptValidationError(
            f"text_zone is '{zone}' but layer_typography_architecture.background_layers "
            f"never mentions '{zone}' — the typography layer's stated position must "
            "match text_zone exactly."
        )


def validate_prompt(card: dict[str, Any]) -> None:
    """Validate a Canva card: schema shape + every code-level Art Director
    rule (chat language, contrast, hierarchy, zone consistency).

    Raises PromptValidationError with a readable message on the first
    failing check.
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

    layer = card["layer_typography_architecture"]
    _validate_typography_hierarchy(layer)
    _validate_color_contrast(layer)
    _validate_text_zone_consistency(card)
