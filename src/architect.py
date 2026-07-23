"""Architect agent (Stage 1): DeepSeek as the Canva design expert.

Takes the user's plain request, applies the Canva knowledge base, and emits
a compact "technical design brief" that the Generator (also DeepSeek) turns
into the final Canva card. This is the orchestrator's first step: detect
the design category/dimensions and lock the art direction + negative
constraints before any prompt text is written. Never chats, never asks a
question back — makes the most Canva-sensible assumption and proceeds.

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
    "detected_category": "instagram_post",
    "aspect_ratio": "1:1 (1080x1080)",
    "target_tool": "Canva Magic Media",
    "magic_media_style": "Minimalist",
    "text_zone": "top",
    "art_direction": {
        "color_palette": ["#8B5E34", "#F5EFE6", "#D4A373"],
        "lighting": "soft natural daylight",
        "mood": "minimalist, vintage, artisanal",
    },
    "canva_keywords": ["flat vector illustration", "isolated element on transparent background"],
    "negative_constraints": "reserve empty negative space at the top for the headline/subtext layer; no embedded text, no clutter",
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
            "matches the user's request spirit, use-case, and mood. The art_direction "
            "you choose must be consistent with this preset's palette_hint and "
            "recommended_magic_media_style."
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
            "art_direction.mood, lighting and magic_media_style to align with this "
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
            "10. Because a brand profile is active: art_direction.color_palette "
            "MUST be chosen only from this brand's approved_colors (do not "
            "invent new HEX values), and text_zone MUST avoid the brand's logo "
            f"placement_zone ('{zone}') so the headline/subtext never overlaps "
            "the logo."
        )

    return (
        "Sen Canva Tasarim Mimarisin (Canva Design Architect), bir otomasyon "
        "motorunun ilk asamasisin. Kullanicinin istegini analiz et ve Canva'nin "
        "Magic Media / Canva GPT araclarinda en yuksek kalitede gorseli "
        "verecek teknik parametreleri belirle.\n\n"
        "HARD RULES:\n"
        "- Reply with a single JSON object and NOTHING else — no greeting, no "
        "prose, no markdown fences, no explanation, no question back to the "
        "user.\n"
        "- If the request is ambiguous, make the most Canva-sensible "
        "assumption yourself and proceed. Never ask for clarification.\n\n"
        "CANVA KNOWLEDGE BASE (use these exact dimensions, styles and keywords):\n"
        f"{kb}"
        f"{auto_style_section}\n"
        "Your brief MUST include, at minimum:\n"
        "1. detected_category — one of the knowledge-base dimension keys.\n"
        "2. aspect_ratio — the matching canvas size (e.g. '1:1 (1080x1080)').\n"
        "3. target_tool — one of the knowledge-base target_tools.\n"
        "4. magic_media_style — one of the knowledge-base magic_media_styles.\n"
        "5. text_zone — exactly one of 'top', 'bottom', 'left', 'right', 'center': "
        "where the headline/subtext will live. Pick this ONCE here — it is the "
        "single source of truth the Generator must honor in both the image "
        "prompt and the typography layer, so they never disagree about placement.\n"
        "6. art_direction — {color_palette: 3-5 real HEX codes including at least "
        "one near-black or near-white anchor so text stays legible, lighting, mood}. "
        "Set lighting and mood with PRECISE professional design taxonomy, never "
        "generic adjectives: name a concrete light quality (e.g. 'soft natural "
        "morning window light', 'golden-hour rim light') and a specific "
        "material/texture-aware mood (e.g. 'minimalist Scandinavian, warm oak and "
        "matte porcelain') so the Generator can render it. When a brand profile is "
        "active, align lighting/mood with the brand's visual_identity.\n"
        "7. canva_keywords — 2-4 items drawn from canva_element_keywords.\n"
        "8. negative_constraints — MUST enforce deliberate negative space at "
        "text_zone's location and exclude embedded text."
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
