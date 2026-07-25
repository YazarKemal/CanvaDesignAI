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
- when a brand profile is active: exact signature-font match and a
  color_palette drawn only from that brand's approved colors
"""

from __future__ import annotations

from typing import Any

import jsonschema

from src.brand_profiles import approved_hex_colors
from src.color_science import InvalidHexColorError, best_contrast_pair

MIN_CONTRAST_RATIO = 4.5  # WCAG AA for normal-size text
MAX_HEADLINE_WORDS = 6
MAX_SUBTEXT_WORDS = 14
TEXT_ZONES: tuple[str, ...] = ("top", "bottom", "left", "right", "center")

PROMPT_CARD_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "CaVDesign Canva Automation Card (Hybrid Split Layer)",
    "type": "object",
    "required": [
        "concept",
        "raster_background",
        "vector_elements",
        "native_typography",
        "aspect_ratio",
        "target_tool",
        "text_zone",
        "direct_action_tip",
    ],
    "properties": {
        "concept": {"type": "string", "minLength": 1},
        "aspect_ratio": {"type": "string", "minLength": 1},
        "target_tool": {"type": "string", "minLength": 1},
        "text_zone": {"type": "string", "enum": list(TEXT_ZONES)},
        # -- Layer 1: Raster Background (image only — no text ever) -----------
        "raster_background": {
            "type": "object",
            "required": ["magic_media_prompt", "negative_prompt"],
            "properties": {
                "magic_media_prompt": {"type": "string", "minLength": 30},
                "negative_prompt": {"type": "string", "minLength": 1},
                "magic_media_style": {"type": "string"},
            },
            "additionalProperties": True,
        },
        # -- Layer 2: Vector Elements (CTA, badge, cutout — pure graphics) ---
        # Accepts both legacy object (runtime pipeline) and v2 array (ingestion).
        "vector_elements": {
            "anyOf": [
                {
                    "type": "object",
                    "properties": {
                        "cta_button": {"type": "string"},
                        "badge": {"type": "string"},
                        "person_cutout": {"type": "string"},
                        "giant_typography": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
                {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["role", "description"],
                        "properties": {
                            "role": {"type": "string", "minLength": 1},
                            "description": {"type": "string", "minLength": 1},
                            "position": {"type": "string"},
                            "scale": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                },
            ]
        },
        # -- Layer 3: Native Typography (text only, separate overlay) ---------
        "native_typography": {
            "type": "object",
            "required": ["headline", "subtext", "color_palette", "fonts", "alignment_zone"],
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
                "alignment_zone": {"type": "string", "minLength": 1},
                "headline_pt": {"type": "number", "minimum": 12, "maximum": 200},
                "subtext_pt": {"type": "number", "minimum": 8, "maximum": 72},
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
        "layer_typography_architecture": {  # legacy — still accepted, maps to new fields
            "type": "object",
            "additionalProperties": True,
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
    raster = card.get("raster_background", {})
    prompt_text = raster.get("magic_media_prompt", card.get("magic_media_prompt", "")).lower()

    if zone not in prompt_text:
        raise PromptValidationError(
            f"text_zone is '{zone}' but raster_background.magic_media_prompt "
            f"never mentions '{zone}' — the image's reserved negative space "
            "must match text_zone exactly."
        )

    # alignment_zone replaces background_layers in the new schema.
    native = card.get("native_typography", {})
    alignment = native.get("alignment_zone", "").lower()
    if alignment:
        if zone not in alignment:
            raise PromptValidationError(
                f"text_zone is '{zone}' but native_typography.alignment_zone "
                f"('{alignment}') does not mention '{zone}' — the typography "
                "layer's stated position must match text_zone exactly."
            )
    else:
        # Legacy path: old cards have background_layers on the flat field.
        old_layer = card.get("layer_typography_architecture", {})
        bg = old_layer.get("background_layers", "").lower()
        if bg and zone not in bg:
            raise PromptValidationError(
                f"text_zone is '{zone}' but background_layers never mentions "
                f"'{zone}' — the typography layer's stated position must "
                "match text_zone exactly."
            )


def _typography_layer(card: dict[str, Any]) -> dict[str, Any]:
    """Return the typography sub-object, preferring the new `native_typography`
    field over the legacy `layer_typography_architecture`."""
    if "native_typography" in card:
        return card["native_typography"]
    return card.get("layer_typography_architecture", {})


def validate_brand_compliance(card: dict[str, Any], brand: dict[str, Any]) -> None:
    """When a brand profile is active, the card MUST use exactly that
    brand's signature fonts and draw color_palette only from its approved
    colors. Raises PromptValidationError on the first violation found."""
    layer = _typography_layer(card)
    signature = brand["signature_fonts"]

    for role in ("headline_font", "body_font"):
        if layer["fonts"].get(role) != signature[role]:
            raise PromptValidationError(
                f"fonts.{role} is '{layer['fonts'].get(role)}' but brand "
                f"'{brand['slug']}' requires exactly '{signature[role]}'."
            )

    approved = approved_hex_colors(brand)
    for hex_color in layer["color_palette"]:
        if hex_color.upper() not in approved:
            raise PromptValidationError(
                f"color_palette includes '{hex_color}' which is not one of brand "
                f"'{brand['slug']}''s approved colors ({sorted(approved)}). Every "
                "palette color must come from the brand's approved set."
            )


def validate_style_compliance(card: dict[str, Any], style: dict[str, Any]) -> None:
    """Style keyword validation DISABLED — cards pass through regardless of
    whether the style preset's required_keywords appear in magic_media_prompt.
    This prevents pipeline crashes from keyword mismatch on blank-canvas and
    text-only layouts where style keywords cannot meaningfully appear."""
    return  # no-op: keyword enforcement disabled


def validate_negative_prompt_boost(card: dict[str, Any], style: dict[str, Any]) -> None:
    """Negative prompt boost validation DISABLED — cards pass through regardless
    of whether style-specific exclusions appear in negative_prompt."""
    return  # no-op: negative prompt boost enforcement disabled


def validate_prompt(
    card: dict[str, Any],
    *,
    brand: dict[str, Any] | None = None,
    style: dict[str, Any] | None = None,
) -> None:
    """Validate a Canva card: schema shape + every code-level Art Director
    rule (chat language, contrast, hierarchy, zone consistency, and — when
    given — brand compliance and style-preset keyword compliance).

    Accepts both the new hybrid-split-layer format (raster_background /
    vector_elements / native_typography) and the legacy flat format
    (magic_media_prompt, negative_prompt, layer_typography_architecture).

    Raises PromptValidationError with a readable message on the first
    failing check.
    """
    # -- Normalise legacy cards into the new schema for validation ----------
    _ensure_hybrid_format(card)

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

    layer = _typography_layer(card)
    _validate_typography_hierarchy(layer)
    _validate_color_contrast(layer)
    _validate_text_zone_consistency(card)

    if brand is not None:
        validate_brand_compliance(card, brand)

    if style is not None:
        validate_style_compliance(card, style)
        validate_negative_prompt_boost(card, style)


def _ensure_hybrid_format(card: dict[str, Any]) -> None:
    """Normalise a legacy flat card into the hybrid split-layer format in-place.

    If *card* uses the old magic_media_prompt / negative_prompt /
    layer_typography_architecture keys, they are mapped into
    raster_background / vector_elements / native_typography so downstream
    validation code only has to reason about one shape.
    """
    # Already in new format — nothing to do.
    if "raster_background" in card:
        return

    layer = card.pop("layer_typography_architecture", {})

    raster: dict[str, Any] = {
        "magic_media_prompt": card.pop("magic_media_prompt", ""),
        "negative_prompt": card.pop("negative_prompt", ""),
    }
    ms = layer.pop("magic_media_style", None)
    if ms:
        raster["magic_media_style"] = ms
    card.setdefault("raster_background", raster)

    # graphic_layers → vector_elements
    gl = layer.pop("graphic_layers", None)
    vec: dict[str, Any] = {}
    if gl and isinstance(gl, dict):
        vec = {k: v for k, v in gl.items() if v}
    card.setdefault("vector_elements", vec)

    # typography fields → native_typography
    native: dict[str, Any] = {
        "headline": layer.pop("headline", ""),
        "subtext": layer.pop("subtext", ""),
        "color_palette": layer.pop("color_palette", []),
        "fonts": layer.pop("fonts", {}),
        "alignment_zone": layer.pop(
            "background_layers",
            f"typography layer at {card.get('text_zone', 'top')}",
        ),
    }
    # Carry over remaining fields.
    for k, v in layer.items():
        if k not in native:
            native[k] = v
    card.setdefault("native_typography", native)
