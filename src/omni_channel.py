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
import re
from typing import Any

try:
    from openai import OpenAI  # type: ignore[import-untyped]
except ImportError:
    OpenAI = None  # type: ignore[assignment]

from src.canva_rules import CANVA_KNOWLEDGE_BASE
from src.composition_rules import align_zone_language
from src.composition_rules import as_prompt_block as composition_prompt_block
from src.llm_json import extract_json
from src.schema import PromptValidationError, _ensure_hybrid_format, validate_prompt

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"
MAX_ADAPT_ATTEMPTS = 2

TARGET_FORMATS: dict[str, str] = {
    "instagram_post": CANVA_KNOWLEDGE_BASE["dimensions"]["instagram_post"],
    "instagram_story": CANVA_KNOWLEDGE_BASE["dimensions"]["instagram_story"],
    "banner": CANVA_KNOWLEDGE_BASE["dimensions"]["banner"],
    # Brand Launch Kit assets
    "logo_emblem": CANVA_KNOWLEDGE_BASE["dimensions"]["logo"],
    "opening_poster": CANVA_KNOWLEDGE_BASE["dimensions"]["poster"],
    "menu_list": CANVA_KNOWLEDGE_BASE["dimensions"]["flyer_a4"],
    "packaging_merch": CANVA_KNOWLEDGE_BASE["dimensions"]["instagram_post"],
}

# Brand Launch Kit — 4 assets that share brand tokens (fonts, colors, visual
# identity) but differ in aspect ratio and concept.  Generated automatically
# when a brand profile is active in /api/chat.
BRAND_KIT_ASSETS: dict[str, dict[str, str]] = {
    "logo_emblem": {
        "aspect_ratio": CANVA_KNOWLEDGE_BASE["dimensions"]["logo"],
        "label": "🪧 Logo & Emblem",
        "concept_override": "logo and emblem mark design",
        "layout_directive": (
            "LOGO & EMBLEM LAYOUT RULES (strict):\n"
            "- NO CTA buttons, NO promotional badges, NO discount labels.\n"
            "- Layer 2 (vector_elements): a single centered vector emblem/icon "
            "drawn from the brand's visual identity (coffee cup, leaf, geometric "
            "monogram). No pill_button, no badge.\n"
            "- Layer 3 (native_typography): brand name as headline (Poppins Bold "
            "or the brand's signature headline font), centered below the emblem. "
            "Subtext: 'Est. 2026' in the brand's body font, small and centered.\n"
            "- alignment_zone: center of canvas, vertical stack.\n"
            "- Palette: use ONLY the brand's approved_colors.\n"
            "- Keep it minimal — this is an identity mark, not a promotional graphic."
        ),
    },
    "opening_poster": {
        "aspect_ratio": CANVA_KNOWLEDGE_BASE["dimensions"]["poster"],
        "label": "📣 Grand Opening Poster",
        "concept_override": "grand opening event poster",
        "layout_directive": (
            "GRAND OPENING POSTER LAYOUT RULES (strict):\n"
            "- NO 'Order Now' CTA, NO discount badge. This is an editorial event poster.\n"
            "- Layer 2 (vector_elements): three info blocks arranged in a clean grid:\n"
            "  1. 'GRAND OPENING' — large, bold, the hero element.\n"
            "  2. 'Date' block — show a date placeholder like 'SAT / 15.08.26' in "
            "a clean editorial layout (thin rule lines above/below).\n"
            "  3. 'Location' block — '123 Brew Lane, Portland' in the brand's body "
            "font, small and refined.\n"
            "- Layer 3 (native_typography): headline is the event title; subtext is "
            "a one-line tagline. alignment_zone: top or center-left.\n"
            "- Visual style: editorial magazine poster — generous whitespace, "
            "strong typographic hierarchy, one accent color from the brand palette "
            "for the date/location blocks."
        ),
    },
    "menu_list": {
        "aspect_ratio": CANVA_KNOWLEDGE_BASE["dimensions"]["flyer_a4"],
        "label": "📜 Menu & Product List",
        "concept_override": "menu and product listing",
        "layout_directive": (
            "MENU & PRODUCT LIST LAYOUT RULES (strict):\n"
            "- NO CTA button, NO discount badge. This is a product catalogue.\n"
            "- Layer 2 (vector_elements): subtle divider lines between categories. "
            "No pill_button, no badge.\n"
            "- Layer 3 (native_typography): headline is the menu title. "
            "Subtext is a brief description (e.g. 'Handcrafted daily').\n"
            "- direct_action_tip steps MUST describe a PRICED MENU LAYOUT:\n"
            "  1. Category headers: 'ESPRESSO', 'BREWS', 'PASTRIES' in the brand's "
            "headline font, separated by thin horizontal rule lines.\n"
            "  2. Under each category, list 3-4 items with prices right-aligned "
            "(e.g. 'Flat White .................... 4.50' in the brand's body font).\n"
            "  3. Use dot-leader tabs for price alignment — consistent tab stops.\n"
            "  4. Palette: use the brand's approved_colors. Prices in the accent color.\n"
            "- alignment_zone: top for the menu title, then full-width for the list."
        ),
    },
    "packaging_merch": {
        "aspect_ratio": CANVA_KNOWLEDGE_BASE["dimensions"]["instagram_post"],
        "label": "☕ Packaging & Merch",
        "concept_override": "packaging and merchandise design",
        "layout_directive": (
            "PACKAGING & MERCH LAYOUT RULES (strict):\n"
            "- This is a CUP SLEEVE / LABEL / STICKER print template — minimal, "
            "repeatable, brand-forward.\n"
            "- Layer 2 (vector_elements): a REPEATING PATTERN of the brand's emblem "
            "or a simple geometric motif (circles, lines, dots) in one of the "
            "brand's approved_colors at low opacity. No CTA, no badge, no button.\n"
            "- Layer 3 (native_typography): headline is the brand name (centered, "
            "prominent). Subtext is a short tagline or 'small-batch · handcrafted' "
            "style descriptor. alignment_zone: center.\n"
            "- direct_action_tip steps MUST describe a PRINT-READY layout:\n"
            "  1. Set up a square canvas at 1080x1080 px.\n"
            "  2. Add the brand emblem/logo centered at the top 30% of the canvas.\n"
            "  3. Add the brand name in the headline font, centered below the emblem.\n"
            "  4. Add a repeating background pattern using the brand's secondary "
            "color at 8-12% opacity — circles, dots, or the brand motif.\n"
            "  5. Add footer text: brand website or 'est. 2026' in small body font.\n"
            "- The result should look like a coffee cup sleeve or product label — "
            "clean, tactile, ready for print."
        ),
    },
}

# Reverse mapping: ratio short-form → format key.
_RATIO_TO_FORMAT: dict[str, str] = {
    "1:1": "instagram_post",
    "9:16": "instagram_story",
    "16:9": "banner",
}


def detect_format_from_aspect_ratio(aspect_ratio: str) -> str | None:
    """Map a card's aspect_ratio string to the matching TARGET_FORMATS key.

    Handles both ``"1:1 (1080x1080)"`` and ``"1080x1080 (1:1)"`` by
    extracting just the ratio portion.
    """
    match = re.search(r"(\d+:\d+)", aspect_ratio)
    if not match:
        return None
    return _RATIO_TO_FORMAT.get(match.group(1))


class UnknownFormatError(ValueError):
    pass


def _system_prompt(
    target_format: str,
    aspect_ratio: str,
    style: dict[str, Any] | None = None,
    layout_directive: str | None = None,
) -> str:
    style_section = ""
    if style is not None:
        required = ", ".join(f"'{k}'" for k in style.get("required_keywords", []))
        style_section = (
            f"\n\nThe base design uses the '{style['name']}' elite style preset. Its "
            f"signature keywords MUST be preserved verbatim in your rewritten "
            f"magic_media_prompt (do not drop them): {required}.\n"
        )
    layout_section = ""
    if layout_directive:
        layout_section = f"\n\n{layout_directive}\n"
    return (
        "You are the Layout Adaptive Engine inside CaVDesign. You are given an "
        "ALREADY APPROVED Canva card and must adapt it to a new format: "
        f"'{target_format}' at aspect ratio {aspect_ratio}. Reply with a single "
        "JSON object and NOTHING else — no greeting, no prose, no markdown "
        "fences, no questions back to the user.\n\n"
        f"{composition_prompt_block(aspect_ratio)}"
        f"{layout_section}"
        f"{style_section}\n\n"
        "HARD RULES:\n"
        "- concept, headline, subtext, color_palette, fonts, negative_prompt, "
        "and canva_keywords are FIXED — do not change them, do not repeat them "
        "in your reply.\n"
        "- vector_elements MAY be rewritten if a layout_directive is given above "
        "(the directive may add/remove specific vector shapes).\n"
        "- Output these keys (omit vector_elements if unchanged):\n"
        "  1. text_zone — one of 'top'/'bottom'/'left'/'right'/'center', "
        "chosen using the FORMAT-SPECIFIC COMPOSITION rules above for what best "
        "suits THIS aspect ratio.\n"
        "  2. magic_media_prompt — rewrite ONLY the composition/framing for "
        "the new aspect ratio per the composition rules above, keeping the same "
        "subject, medium, mood, color palette, and any elite style keywords. "
        "MUST reserve negative space per the chosen text_zone.\n"
        "  3. background_layers — how the image and typography layers stack "
        "for this format; MUST mention the same text_zone location.\n"
        "  4. vector_elements (OPTIONAL) — only include if the layout directive "
        "requires different vector shapes (e.g. remove CTA/badge, add info "
        "blocks, add repeating pattern). Each key maps to a single concrete "
        "Canva shape instruction string.\n"
        "  5. direct_action_tip — an ordered array of 2-5 concrete Canva steps "
        "for assembling THIS format specifically (mentioning the aspect ratio).\n\n"
        'Respond with raw JSON only, e.g.: {"text_zone": "top", '
        '"magic_media_prompt": "...", "background_layers": "...", '
        '"direct_action_tip": ["...", "..."]}'
    )


def _base_fields_message(base_card: dict[str, Any]) -> str:
    # Normalise to hybrid format without mutating the original.
    card = json.loads(json.dumps(base_card))
    _ensure_hybrid_format(card)

    native = card.get("native_typography", {})
    raster = card.get("raster_background", {})

    fixed = {
        "concept": card["concept"],
        "headline": native.get("headline", ""),
        "subtext": native.get("subtext", ""),
        "color_palette": native.get("color_palette", []),
        "fonts": native.get("fonts", {}),
        "negative_prompt": raster.get("negative_prompt", ""),
        "canva_keywords": card.get("canva_keywords", []),
    }
    return f"Approved card's fixed fields (do not change):\n{json.dumps(fixed, ensure_ascii=False, indent=2)}"


def _merge_variant(base_card: dict[str, Any], target_format: str, adapted: dict[str, Any]) -> dict[str, Any]:
    card = json.loads(json.dumps(base_card))  # deep copy
    _ensure_hybrid_format(card)  # normalise to hybrid format

    zone = adapted["text_zone"]
    card["aspect_ratio"] = TARGET_FORMATS[target_format]
    card["text_zone"] = zone

    mp = adapted.get("magic_media_prompt", "")
    if isinstance(mp, list):
        mp = " ".join(str(s) for s in mp)
    card.setdefault("raster_background", {})
    card["raster_background"]["magic_media_prompt"] = align_zone_language(
        mp,
        zone,
        append_clause=(
            f"with deliberate negative space reserved at the {zone} of the frame "
            "for the typography overlay"
        ),
    )
    bg_layers = adapted.get("background_layers", "")
    if isinstance(bg_layers, list):
        bg_layers = " ".join(str(s) for s in bg_layers)
    card.setdefault("native_typography", {})
    card["native_typography"]["alignment_zone"] = align_zone_language(
        bg_layers,
        zone,
        append_clause=f"the headline and subtext occupy the reserved {zone} zone",
    )
    card["direct_action_tip"] = adapted["direct_action_tip"]
    # Override vector_elements if the adaptation provides new ones.
    if "vector_elements" in adapted and isinstance(adapted["vector_elements"], dict):
        card["vector_elements"] = adapted["vector_elements"]
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
    style: dict[str, Any] | None = None,
    model: str = DEFAULT_MODEL,
    client: Any = None,
) -> dict[str, Any]:
    """Adapt `base_card` (an already-approved card) to `target_format`.

    Returns a new, fully validated card for that format. If `style` is given,
    the adapter is reminded to preserve the preset's signature keywords and
    the variant is validated against them. Raises UnknownFormatError for an
    unrecognized format name, or PromptValidationError if the adaptation never
    passes validation within MAX_ADAPT_ATTEMPTS lightweight local retries.
    """
    if target_format not in TARGET_FORMATS:
        raise UnknownFormatError(
            f"Unknown target format '{target_format}'. Available: {sorted(TARGET_FORMATS)}"
        )

    client = client or _default_client()
    aspect_ratio = TARGET_FORMATS[target_format]

    # Inject brand-kit layout directive if this is a brand kit asset.
    kit_directive = BRAND_KIT_ASSETS.get(target_format, {}).get("layout_directive")

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
                {"role": "system", "content": _system_prompt(
                    target_format, aspect_ratio, style, layout_directive=kit_directive,
                )},
                {"role": "user", "content": message},
            ],
            temperature=0.3,
        )
        raw_text = response.choices[0].message.content or ""

        try:
            adapted = extract_json(raw_text)
            variant = _merge_variant(base_card, target_format, adapted)
            validate_prompt(variant, brand=brand, style=style)
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
    style: dict[str, Any] | None = None,
    model: str = DEFAULT_MODEL,
    client: Any = None,
) -> dict[str, dict[str, Any]]:
    """Adapt `base_card` to each format in `formats`. Returns {format: card}."""
    return {
        fmt: adapt_to_format(base_card, fmt, brand=brand, style=style, model=model, client=client)
        for fmt in formats
    }
