"""Omni-Channel Layout Adaptive Engine — on-demand adaptation of an already
approved Canva card to other channel formats (Story, Post, Banner, ...).

Deliberately does NOT re-run the full Architect -> Generator -> Reviewer
pipeline per format (that would be the slowest, most expensive option).
Instead, one small, focused DeepSeek call per target format holds the
concept/headline/subtext/color_palette/fonts fixed and only re-derives
what genuinely changes with aspect ratio: text_zone, the image prompt's
composition, the typography layer's background_layers, and the action
steps. The result is re-validated through the exact same
src.schema.validate_prompt used everywhere else, so contrast, typography
hierarchy, and text_zone consistency still hold for every variant.
"""

from __future__ import annotations

import json
import os
from typing import Any

try:
    from openai import OpenAI  # type: ignore[import-untyped]
except ImportError:
    OpenAI = None  # type: ignore[assignment]

from src.canva_rules import CANVA_KNOWLEDGE_BASE
from src.composition_rules import align_zone_language
from src.composition_rules import as_prompt_block as composition_prompt_block
from src.llm_json import extract_json
from src.schema import PromptValidationError, validate_prompt

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"
MAX_ADAPT_ATTEMPTS = 2

TARGET_FORMATS: dict[str, str] = {
    "instagram_post": CANVA_KNOWLEDGE_BASE["dimensions"]["instagram_post"],
    "instagram_story": CANVA_KNOWLEDGE_BASE["dimensions"]["instagram_story"],
    "banner": CANVA_KNOWLEDGE_BASE["dimensions"]["banner"],
}


class UnknownFormatError(ValueError):
    pass


def _system_prompt(target_format: str, aspect_ratio: str) -> str:
    return (
        "You are the Layout Adaptive Engine inside CaVDesign. You are given an "
        "ALREADY APPROVED Canva card and must adapt it to a new format: "
        f"'{target_format}' at aspect ratio {aspect_ratio}. Reply with a single "
        "JSON object and NOTHING else — no greeting, no prose, no markdown "
        "fences, no questions back to the user.\n\n"
        f"{composition_prompt_block(aspect_ratio)}\n\n"
        "HARD RULES:\n"
        "- concept, headline, subtext, color_palette, fonts, negative_prompt, "
        "and canva_keywords are FIXED — do not change them, do not repeat them "
        "in your reply.\n"
        "- Output EXACTLY these four keys, nothing else:\n"
        "  1. text_zone — one of 'top'/'bottom'/'left'/'right'/'center', "
        "chosen using the FORMAT-SPECIFIC COMPOSITION rules above for what best "
        "suits THIS aspect ratio (a 9:16 vertical story often wants a different "
        "zone than a 1:1 square).\n"
        "  2. magic_media_prompt — rewrite ONLY the composition/framing for "
        "the new aspect ratio per the composition rules above (leading lines, "
        "depth, lighting), keeping the same subject, medium, mood, and color "
        "palette. MUST reserve negative space per the chosen text_zone and "
        "mention that location in plain English, matching rule #1.\n"
        "  3. background_layers — how the image and typography layers stack "
        "for this format; MUST also mention the same text_zone location.\n"
        "  4. direct_action_tip — an ordered array of 2-5 concrete Canva steps "
        "for assembling THIS format specifically (mentioning the aspect ratio).\n\n"
        'Respond with raw JSON only, e.g.: {"text_zone": "top", '
        '"magic_media_prompt": "...", "background_layers": "...", '
        '"direct_action_tip": ["...", "..."]}'
    )


def _base_fields_message(base_card: dict[str, Any]) -> str:
    layer = base_card["layer_typography_architecture"]
    fixed = {
        "concept": base_card["concept"],
        "headline": layer["headline"],
        "subtext": layer["subtext"],
        "color_palette": layer["color_palette"],
        "fonts": layer["fonts"],
        "negative_prompt": base_card["negative_prompt"],
        "canva_keywords": base_card.get("canva_keywords", []),
    }
    return f"Approved card's fixed fields (do not change):\n{json.dumps(fixed, ensure_ascii=False, indent=2)}"


def _merge_variant(base_card: dict[str, Any], target_format: str, adapted: dict[str, Any]) -> dict[str, Any]:
    card = json.loads(json.dumps(base_card))  # deep copy
    zone = adapted["text_zone"]
    card["aspect_ratio"] = TARGET_FORMATS[target_format]
    card["text_zone"] = zone
    # The adaptation may have picked a NEW text_zone while leaving the old
    # zone's spatial wording in the reused prose. Reconcile the negative-space
    # direction in both the image prompt and the layer description so they
    # match the new zone before validation runs (fixes the class of
    # "text_zone is 'bottom' but magic_media_prompt never mentions 'bottom'"
    # failures deterministically, instead of relying on an LLM retry).
    card["magic_media_prompt"] = align_zone_language(
        adapted["magic_media_prompt"],
        zone,
        append_clause=(
            f"with deliberate negative space reserved at the {zone} of the frame "
            "for the typography overlay"
        ),
    )
    card["layer_typography_architecture"]["background_layers"] = align_zone_language(
        adapted["background_layers"],
        zone,
        append_clause=f"the headline and subtext occupy the reserved {zone} zone",
    )
    card["direct_action_tip"] = adapted["direct_action_tip"]
    return card


def _default_client() -> Any:
    if OpenAI is not None:
        return OpenAI(
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
        )
    from src.http_client import DeepSeekClient

    return DeepSeekClient()


def adapt_to_format(
    base_card: dict[str, Any],
    target_format: str,
    *,
    brand: dict[str, Any] | None = None,
    model: str = DEFAULT_MODEL,
    client: Any = None,
) -> dict[str, Any]:
    """Adapt `base_card` (an already-approved card) to `target_format`.

    Returns a new, fully validated card for that format. Raises
    UnknownFormatError for an unrecognized format name, or
    PromptValidationError if the adaptation never passes validation within
    MAX_ADAPT_ATTEMPTS lightweight local retries.
    """
    if target_format not in TARGET_FORMATS:
        raise UnknownFormatError(
            f"Unknown target format '{target_format}'. Available: {sorted(TARGET_FORMATS)}"
        )

    client = client or _default_client()
    aspect_ratio = TARGET_FORMATS[target_format]

    user_message = _base_fields_message(base_card)
    feedback: str | None = None
    last_error: PromptValidationError | None = None

    for _attempt in range(1, MAX_ADAPT_ATTEMPTS + 1):
        message = user_message
        if feedback:
            message += f"\n\nThe previous adaptation was rejected. Fix this:\n{feedback}"

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _system_prompt(target_format, aspect_ratio)},
                {"role": "user", "content": message},
            ],
            temperature=0.3,
        )
        raw_text = response.choices[0].message.content or ""

        try:
            adapted = extract_json(raw_text)
            variant = _merge_variant(base_card, target_format, adapted)
            validate_prompt(variant, brand=brand)
            return variant
        except (json.JSONDecodeError, KeyError, PromptValidationError) as exc:
            last_error = exc if isinstance(exc, PromptValidationError) else PromptValidationError(str(exc))
            feedback = str(last_error)

    raise last_error  # type: ignore[misc]


def generate_omni_channel_set(
    base_card: dict[str, Any],
    formats: list[str],
    *,
    brand: dict[str, Any] | None = None,
    model: str = DEFAULT_MODEL,
    client: Any = None,
) -> dict[str, dict[str, Any]]:
    """Adapt `base_card` to each format in `formats`. Returns {format: card}."""
    return {
        fmt: adapt_to_format(base_card, fmt, brand=brand, model=model, client=client) for fmt in formats
    }
