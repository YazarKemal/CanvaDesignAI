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
            "- Layer 1 (raster_background): solid matte background colour from the "
            "brand palette OR a subtle uncoated-paper texture. Use 'minimalist "
            "line-art emblem' or 'fine engraving' style — NEVER 'flat vector "
            "illustration'. negative_prompt MUST include 'no gibberish text, "
            "no embedded letters, no fake words, no stock vector clip-art'.\n"
            "- Layer 2 (vector_elements): a single centered vector emblem/icon "
            "drawn from the brand's visual identity (coffee cup, leaf, geometric "
            "monogram). Rendered as a clean line-art glyph or fine engraving mark. "
            "No pill_button, no badge.\n"
            "- Layer 3 (native_typography): brand name as headline, centered below "
            "the emblem. SUBTEXT IS STRICTLY LIMITED to 'EST. 2026' or a 2-3 word "
            "tagline (e.g. 'Artisanal Coffee'). NO paragraphs, NO sentences, "
            "NO descriptions in the subtext field — it is an identity mark, not a "
            "brochure. micro_tags: 'VOL.01 / 2026', 'BRAND IDENTITY', the origin.\n"
            "- alignment_zone: center of canvas, vertical stack.\n"
            "- Palette: use ONLY the brand's approved_colors."
        ),
    },
    "opening_poster": {
        "aspect_ratio": CANVA_KNOWLEDGE_BASE["dimensions"]["poster"],
        "label": "📣 Grand Opening Poster",
        "concept_override": "grand opening event poster",
        "layout_directive": (
            "GRAND OPENING POSTER LAYOUT RULES (strict):\n"
            "- NO 'Order Now' CTA, NO discount badge. This is an editorial event poster.\n"
            "- Layer 1 (raster_background): 'high-end editorial studio photography' "
            "style — rich depth, shallow DOF, dramatic lighting. Search Canva Stock "
            "Library for editorial interior/food/flatlay photos. NEVER 'flat vector "
            "illustration'. negative_prompt MUST include 'no gibberish text, no "
            "embedded letters, no fake words, no stock vector clip-art'.\n"
            "- Layer 2 (vector_elements): three info blocks arranged in a clean grid:\n"
            "  1. 'GRAND OPENING' — large, bold, the hero element.\n"
            "  2. 'Date' block — show a date placeholder like 'SAT / 15.08.26' in "
            "a clean editorial layout (thin rule lines above/below).\n"
            "  3. 'Location' block — '123 Brew Lane, Portland' in the brand's body "
            "font, small and refined.\n"
            "- Layer 3 (native_typography): headline is the event title; subtext is "
            "a one-line tagline (max 6 words). alignment_zone: top or center-left.\n"
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
            "- Layer 1 (raster_background): a SOFT TEXTURED BACKGROUND only — matte "
            "uncoated paper, warm linen, or subtle grain texture in a brand-approved "
            "neutral colour. Do NOT describe any foreground objects, food items, "
            "products, illustrations, or photography in the background — the image "
            "must be a CLEAN, EMPTY canvas with ZERO visual clutter. The top 20% and "
            "bottom 15% must be completely empty negative space (no texture variation, "
            "no vignette, no gradient fade — pure solid/lightly-textured zone). "
            "NEVER 'flat vector illustration'. negative_prompt MUST include 'no "
            "gibberish text, no embedded letters, no fake words, no stock vector "
            "clip-art, no food photography, no product images, no illustrated items'.\n"
            "- Layer 2 (vector_elements): subtle divider lines between categories "
            "(thin horizontal rules at 0.5 px in a muted brand color). No pill_button, "
            "no badge.\n"
            "- Layer 3 (native_typography): headline is the menu title. Subtext is "
            "a brief descriptor (max 4 words, e.g. 'Handcrafted Daily').\n"
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
            "- This is a BOX DIE-CUT PACKAGING SLEEVE / REPEATING BRAND PATTERN "
            "GRID template — NOT a poster, NOT a social media graphic, NOT an "
            "advertisement.\n"
            "- Layer 1 (raster_background): a REPEATING SEAMLESS PATTERN of the "
            "brand's emblem or geometric motif in one brand-approved color at 8-12% "
            "opacity on a matte uncoated paper or kraft-paper-toned background. "
            "Describe it as 'seamless repeating brand pattern grid' or 'die-cut "
            "packaging sleeve template'. NEVER 'flat vector illustration', NEVER "
            "'editorial photography', NEVER scene descriptions. negative_prompt "
            "MUST include 'no gibberish text, no embedded letters, no fake words, "
            "no stock vector clip-art, no poster layout, no social media template'.\n"
            "- Layer 2 (vector_elements): a repeating geometric pattern OR a single "
            "centered die-cut outline frame. No CTA, no badge, no button. Use Canva's "
            "built-in grid/repeat or frame shapes.\n"
            "- Layer 3 (native_typography): headline is the brand name (centered, "
            "prominent). Subtext is STRICTLY limited to a 2-3 word descriptor "
            "('small-batch · handcrafted') or 'EST. 2026'. alignment_zone: center.\n"
            "- direct_action_tip steps MUST describe a PRINT-READY template:\n"
            "  1. Set up a square canvas at 1080x1080 px.\n"
            "  2. Create a repeating pattern grid using the brand's emblem/motif.\n"
            "  3. Add a centered die-cut frame or sleeve outline.\n"
            "  4. Place brand name centered in the frame.\n"
            "  5. Add footer: brand website or 'est. 2026' in small body font.\n"
            "- The result must look like a physical coffee cup sleeve or product "
            "label — tactile, minimal, ready for print production."
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
        "- subtext_override MAY be provided if the layout directive specifies a "
        "different subtext (e.g. 'EST. 2026' for logos, or a shorter tagline).\n"
        "- negative_prompt_boost — additional exclusion terms to APPEND to the "
        "base negative_prompt (e.g. 'no gibberish text, no fake words').\n"
        "- Output these keys (omit optional ones if unchanged):\n"
        "  1. text_zone\n"
        "  2. magic_media_prompt\n"
        "  3. background_layers\n"
        "  4. vector_elements (OPTIONAL)\n"
        "  5. subtext_override (OPTIONAL) — new subtext string if the layout "
        "directive requires a shorter/different one\n"
        "  6. negative_prompt_boost (OPTIONAL) — extra exclusion terms to append\n"
        "  7. direct_action_tip\n\n"
        'Respond with raw JSON only, e.g.: {"text_zone": "top", '
        '"magic_media_prompt": "...", "background_layers": "...", '
        '"subtext_override": "EST. 2026", '
        '"negative_prompt_boost": "no gibberish text, no fake words", '
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
    # Override subtext if the adaptation provides one (e.g. logo → 'EST. 2026').
    if adapted.get("subtext_override") and isinstance(adapted["subtext_override"], str):
        card.setdefault("native_typography", {})
        card["native_typography"]["subtext"] = adapted["subtext_override"]
    # Append extra negative_prompt terms if the adaptation provides them.
    if adapted.get("negative_prompt_boost") and isinstance(adapted["negative_prompt_boost"], str):
        card.setdefault("raster_background", {})
        existing = card["raster_background"].get("negative_prompt", "")
        card["raster_background"]["negative_prompt"] = (
            f"{existing}, {adapted['negative_prompt_boost']}"
            if existing else adapted["negative_prompt_boost"]
        )
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
