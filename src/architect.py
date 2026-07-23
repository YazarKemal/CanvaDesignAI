"""Architect agent (Stage 1): DeepSeek as the Canva design expert.

Takes the user's plain request, applies the Canva knowledge base, and emits
a compact "technical design brief" that the Generator (also DeepSeek) turns
into the final Canva card. This is the orchestrator's first step: detect
the design category/dimensions and lock the layout composition (background,
typography, graphic elements) + negative constraints before any card is
produced. Never chats, never asks a question back — makes the most
Canva-sensible assumption and proceeds.

All references to Magic Media / AI image generation have been retired.
The Architect now reasons in terms of the **Canva Native Layout Engine**:
Canva stock photos / gradient backgrounds, built-in typography font boxes
(Poppins, Montserrat, etc. in vertical stacks), and native vector shapes
(pill buttons, badges, frames).

When `style` is None or "none", the **Auto Style Injector** scans the
user's prompt for keywords (planner, nightclub, cafe, retro, …) and
resolves the best-matching style preset automatically, so that even
unstyled requests get a coherent visual identity without the user having
to browse the preset menu.
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

from src.brand_profiles import as_prompt_block as brand_prompt_block
from src.canva_rules import CANVA_KNOWLEDGE_BASE, detect_category, dimensions_for
from src.llm_json import extract_json
from src.style_presets import (
    StyleNotFoundError,
    as_prompt_block as style_prompt_block,
    best_for_summaries,
    load_style,
)

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"

# -- Auto Style Injector -------------------------------------------------------
# Maps free-text keywords (lowercased) to style-preset slugs.  The keyword
# is matched case-insensitively against the user's prompt; first hit wins.
# Only consulted when no manual style override is provided.

AUTO_STYLE_HINTS: dict[str, str] = {
    "planner": "utility-planner-ornamental",
    "ajanda": "utility-planner-ornamental",
    "planlayıcı": "utility-planner-ornamental",
    "nightclub": "vaporwave-arcade-dusk",
    "gece kulübü": "vaporwave-arcade-dusk",
    "arcade": "vaporwave-arcade-dusk",
    "cafe": "warm-editorial-minimalist",
    "coffee": "warm-editorial-minimalist",
    "kahve": "warm-editorial-minimalist",
    "pastane": "warm-editorial-minimalist",
    "editorial": "warm-editorial-minimalist",
    "retro": "y2k-chrome-gloss",
    "y2k": "y2k-chrome-gloss",
    "hyperpop": "y2k-chrome-gloss",
    "concert": "psychedelic-fillmore",
    "konser": "psychedelic-fillmore",
    "müzik": "psychedelic-fillmore",
    "indie": "psychedelic-fillmore",
    "rock": "psychedelic-fillmore",
    "streetwear": "neo-grunge-streetwear",
    "sokak modası": "neo-grunge-streetwear",
    "hip hop": "neo-grunge-streetwear",
    "grunge": "neo-grunge-streetwear",
    "corporate": "corporate-dynamic-vector",
    "kurumsal": "corporate-dynamic-vector",
    "saas": "corporate-dynamic-vector",
    "tech": "corporate-dynamic-vector",
    "startup": "corporate-dynamic-vector",
    "wedding": "art-nouveau-botanical",
    "düğün": "art-nouveau-botanical",
    "nikah": "formal-ceremonial-turkish",
    "davet": "art-nouveau-botanical",
    "invitation": "art-nouveau-botanical",
    "davetiye": "art-nouveau-botanical",
    "luxury": "art-deco-metropolis",
    "lüks": "art-deco-metropolis",
    "fashion": "swiss-international-grid",
    "moda": "swiss-international-grid",
    "minimal": "swiss-international-grid",
    "minimalist": "swiss-international-grid",
    "poster": "bauhaus-modernist-poster",
    "afiş": "bauhaus-modernist-poster",
    "flyer": "riso-print-editorial",
    "broşür": "riso-print-editorial",
    "brosur": "riso-print-editorial",
    "menu": "memphis-design-pop",
    "menü": "memphis-design-pop",
    "restaurant": "memphis-design-pop",
    "travel": "kodachrome-americana",
    "seyahat": "kodachrome-americana",
    "vintage": "kodachrome-americana",
    "gaming": "streamer-energetic-glitch",
    "oyun": "streamer-energetic-glitch",
    "streamer": "streamer-energetic-glitch",
    "yayın": "streamer-energetic-glitch",
    "architecture": "brutalist-concrete",
    "mimari": "brutalist-concrete",
    "mobilya": "mid-century-modern-print",
    "furniture": "mid-century-modern-print",
    "japon": "ukiyo-e-woodblock",
    "matcha": "ukiyo-e-woodblock",
    "çay": "ukiyo-e-woodblock",
    "tören": "formal-ceremonial-turkish",
    "resmi": "formal-ceremonial-turkish",
    "ceremonial": "formal-ceremonial-turkish",
}


def auto_detect_style(text: str) -> dict[str, Any] | None:
    """Scan *text* for keywords that suggest a specific style preset.

    Returns the loaded style dict on the first keyword hit, or ``None``
    when nothing matches.  The lookup is fast (no LLM call) and runs
    before the Architect LLM is invoked, so the detected style can be
    threaded into the brief-generation prompt alongside the category hint.
    """
    lowered = text.lower()
    for keyword, slug in AUTO_STYLE_HINTS.items():
        if keyword in lowered:
            try:
                return load_style(slug)
            except StyleNotFoundError:
                continue
    return None


BRIEF_SCHEMA_HINT = {
    "detected_category": "instagram_story",
    "aspect_ratio": "9:16 (1080x1920)",
    "target_tool": "Canva Native Layout Engine",
    "layout_style": "Minimalist",
    "text_zone": "top",
    "background": {
        "type": "stock_photo",
        "search_keywords": "modern coffee shop interior, warm morning light",
        "fallback_gradient": {"angle": 135, "stops": ["#3A1C71", "#D76D77", "#FFAF7B"]},
    },
    "typography": {
        "headline_font": "Poppins Bold",
        "body_font": "Montserrat Regular",
        "arrangement": "vertical stack, left-aligned",
        "color_palette": ["#FFFFFF", "#F5EFE6", "#D4A373"],
    },
    "graphic_elements": [
        {"type": "pill_button", "label": "Sipariş Ver", "color": "#D4A373", "position": "bottom-center"},
        {"type": "badge", "label": "%20 İndirim", "color": "#8B5E34", "position": "top-right"},
    ],
    "canva_keywords": ["vertical text stack", "full-bleed stock photo", "pill button CTA"],
    "negative_constraints": "reserve negative space at top for headline/subtext; no AI-generated imagery; all visuals must be Canva stock library or native gradients",
    "selected_style_id": "warm-editorial-minimalist",
}


def _style_selection_rule(style: dict[str, Any] | None) -> str:
    """Return the style-selection requirement line for the brief template.

    When no manual style was chosen (*style* is None) the Architect must
    auto-select a preset from the menu shown above.  When a manual style IS
    active the Architect simply confirms that slug — no menu, no extra choice.
    """
    if style is None:
        return (
            "\n9. selected_style_id — the slug of the ONE style preset (from the "
            "AVAILABLE STYLE PRESETS list above) whose best_for description best "
            "matches the user's request spirit, use-case, and mood. The background, "
            "typography and graphic_elements you choose must be consistent with this "
            "preset's palette_hint and recommended_layout_style."
        )
    return (
        "\n9. selected_style_id — set this to the slug of the active style "
        "preset you were given above. Do NOT auto-select a different style; "
        "the user has already chosen one explicitly."
    )


def _system_prompt(
    brand: dict[str, Any] | None = None, style: dict[str, Any] | None = None
) -> str:
    kb = json.dumps(CANVA_KNOWLEDGE_BASE, ensure_ascii=False, indent=2)

    # -- Manual style override (user picked one in the UI) ------------------
    style_section = ""
    if style is not None:
        style_section = (
            f"\n\n{style_prompt_block(style)}\n\nBecause a style preset is active: set "
            "background, typography and graphic_elements to align with this "
            "preset, and pick a color_palette consistent with its palette guidance."
        )

    # -- Auto style selection (no manual override → Architect picks best fit)
    auto_style_section = ""
    if style is None:
        summaries = best_for_summaries()
        auto_style_section = (
            "\n\nAVAILABLE STYLE PRESETS (pick exactly ONE whose best_for "
            "description best matches the spirit and use-case of the user's "
            "request — set selected_style_id to its slug):\n"
            f"{summaries}\n"
        )

    # -- Brand section ------------------------------------------------------
    brand_section = ""
    if brand is not None:
        zone = brand.get("logo", {}).get("placement_zone", "")
        brand_section = (
            f"\n\n{brand_prompt_block(brand)}\n\n"
            "10. Because a brand profile is active: typography.color_palette "
            "MUST be chosen only from this brand's approved_colors (do not "
            "invent new HEX values), and text_zone MUST avoid the brand's logo "
            f"placement_zone ('{zone}') so the headline/subtext never overlaps "
            "the logo."
        )

    return (
        "Sen Canva Tasarim Mimarisin (Canva Design Architect), bir otomasyon "
        "motorunun ilk asamasisin. Kullanicinin istegini analiz et ve Canva "
        "Native Layout Engine kullanarak native tipografi kutulari, stok "
        "gorseller ve yerlesik vektor sekillerle en yuksek kalitede tasarimi "
        "olusturacak teknik parametreleri belirle.\n\n"
        "HARD RULES:\n"
        "- DO NOT use Magic Media or AI image generation. Generate layouts "
        "using native Canva typography boxes, stock visuals, and native "
        "elements (gradients, pill buttons, badges, frames, vector shapes).\n"
        "- Reply with a single JSON object and NOTHING else — no greeting, no "
        "prose, no markdown fences, no explanation, no question back to the "
        "user.\n"
        "- If the request is ambiguous, make the most Canva-sensible "
        "assumption yourself and proceed. Never ask for clarification.\n\n"
        "CANVA KNOWLEDGE BASE (use these exact dimensions, layout_styles, "
        "stock_photo_keywords, native_typography, and native_graphic_shapes):\n"
        f"{kb}"
        f"{auto_style_section}\n"
        "Your brief MUST include, at minimum:\n"
        "1. detected_category — one of the knowledge-base dimension keys.\n"
        "2. aspect_ratio — the matching canvas size (e.g. '9:16 (1080x1920)').\n"
        "3. target_tool — MUST be 'Canva Native Layout Engine' (never Magic Media "
        "or any AI image generator).\n"
        "4. layout_style — one of the knowledge-base layout_styles.\n"
        "5. text_zone — exactly one of 'top', 'bottom', 'left', 'right', 'center': "
        "where the headline/subtext will live, dictating both background "
        "composition and typography placement so they never disagree.\n"
        "6. background — {type: 'stock_photo'|'gradient'|'solid', "
        "search_keywords (if stock_photo): concrete Canva stock-library search "
        "terms (e.g. 'corporate office space', 'minimalist tech environment'); "
        "fallback_gradient (if gradient/solid): {angle, stops: [3-5 HEX codes]} }. "
        "Always prefer stock_photo with search_keywords drawn from "
        "stock_photo_keywords in the knowledge base. When gradient, use stops "
        "that complement the typography color_palette.\n"
        "7. typography — {headline_font (from native_typography.headline_fonts), "
        "body_font (from native_typography.body_fonts), arrangement (from "
        "native_typography.arrangements), color_palette: 3-5 HEX codes including "
        "at least one near-white anchor so text stays legible}. All fonts MUST "
        "be drawn from native_typography lists — these are Canva's built-in font "
        "boxes that render crisply at any size. Arrangement specifies vertical "
        "stack direction and alignment.\n"
        "8. graphic_elements — a list of native Canva shapes to overlay: "
        "each with {type (from native_graphic_shapes), label (short text), "
        "color (HEX), position (e.g. 'bottom-center', 'top-right')}. "
        "Include at least one pill_button (CTA) and one badge where appropriate. "
        "These are Canva's built-in vector shapes — no AI generation needed.\n"
        "9. canva_keywords — 2-4 items from canva_element_keywords or stock_photo_keywords.\n"
        "10. negative_constraints — MUST enforce deliberate negative space at "
        "text_zone's location, exclude AI-generated imagery, and specify that "
        "all visuals are Canva stock library or native elements."
        f"{_style_selection_rule(style)}"
        f"{style_section}"
        f"{brand_section}\n\n"
        "Example shape (values illustrative only):\n"
        f"{json.dumps(BRIEF_SCHEMA_HINT, ensure_ascii=False, indent=2)}\n\n"
        "Respond with raw JSON only."
    )


def build_brief(
    user_message: str,
    *,
    brand: dict[str, Any] | None = None,
    style: dict[str, Any] | None = None,
    model: str = DEFAULT_MODEL,
    client: OpenAI | None = None,
) -> dict[str, Any]:
    """Produce a technical design brief for `user_message` (Stage 1).

    If `brand` is given, the brief's color_palette and text_zone are
    constrained by that brand profile. If `style` is given, its elite style
    preset steers the brief's art_direction (mood/lighting/palette/style).

    When *style* is ``None``, the **Auto Style Injector** scans the user
    message for keywords and picks the best-matching preset before the
    Architect LLM runs — so even unstyled requests get a coherent visual
    identity.
    """
    # -- Auto Style Injector: keyword-based style detection -----------------
    auto_style: dict[str, Any] | None = style
    if auto_style is None:
        detected = auto_detect_style(user_message)
        if detected is not None:
            auto_style = detected

    if client is None:
        if OpenAI is not None:
            client = OpenAI(
                api_key=os.environ.get("DEEPSEEK_API_KEY"),
                base_url=os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
            )
        else:
            from src.http_client import DeepSeekClient
            client = DeepSeekClient()  # type: ignore[assignment]

    hint = detect_category(user_message)
    hint_text = ""
    if hint:
        hint_text = (
            f"\n\n(Category hint from keyword match: '{hint}' -> "
            f"{dimensions_for(hint)}. Confirm or override based on the full request.)"
        )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _system_prompt(brand, auto_style)},
            {"role": "user", "content": f"User request: {user_message}{hint_text}"},
        ],
        temperature=0.2,
    )
    raw_text = response.choices[0].message.content or ""

    try:
        brief = extract_json(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Architect did not return valid JSON: {exc}\nRaw: {raw_text}") from exc

    # Stamp the auto-detected style slug so downstream stages know which
    # preset was resolved (even when the user didn't explicitly pick one).
    if style is None and auto_style is not None:
        brief.setdefault("selected_style_id", auto_style["slug"])

    return brief
