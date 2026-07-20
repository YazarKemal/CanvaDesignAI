"""Canva knowledge base — the terms, dimensions and library keywords that
Canva's Magic Media / Canva GPT algorithms understand best.

This is the fixed "Canva expertise" the Architect agent (DeepSeek) reasons
over when it turns a plain user request into a technical design brief. Kept
as plain data so both agents and the tests share one source of truth.
"""

from __future__ import annotations

from typing import Any

CANVA_KNOWLEDGE_BASE: dict[str, Any] = {
    "dimensions": {
        "instagram_post": "1080x1080 (1:1)",
        "instagram_portrait": "1080x1350 (4:5)",
        "instagram_story": "1080x1920 (9:16)",
        "facebook_post": "1200x630 (1.91:1)",
        "flyer_a4": "2480x3508 (3:4 aspect)",
        "poster": "2480x3508 (3:4 aspect)",
        "presentation": "1920x1080 (16:9)",
        "youtube_thumbnail": "1280x720 (16:9)",
        "logo": "500x500 (1:1)",
        "business_card": "1050x600 (7:4 aspect)",
    },
    "magic_media_styles": [
        "Vibrant",
        "Minimalist",
        "3D Model",
        "Retro Anime",
        "Watercolor",
        "Cyberpunk",
        "Paper Cut",
        "Flat Vector",
        "Photographic",
        "Concept Art",
        "Neon",
    ],
    "canva_element_keywords": [
        "organic fluid shapes",
        "glassmorphism card overlay",
        "duotone accent",
        "isolated element on transparent background",
        "boho line art",
        "bauhaus geometric layout",
        "flat vector illustration",
        "grainy gradient texture",
        "editorial collage",
        "minimal line icons",
        "risograph print texture",
    ],
    "target_tools": ["Canva Magic Media", "DALL-E 3", "Canva GPT", "Midjourney"],
    "negative_space_rule": (
        "Always reserve deliberate empty negative space (top, bottom, or one "
        "side) so the user can overlay real, crisp typography in Canva without "
        "the generated image's own detail clashing with the text."
    ),
}

# Lightweight keyword -> canonical design category, used as a cheap hint the
# Architect can lean on (it may still override based on the full request).
CATEGORY_HINTS: dict[str, str] = {
    "instagram post": "instagram_post",
    "instagram gonderisi": "instagram_post",
    "instagram gönderisi": "instagram_post",
    "story": "instagram_story",
    "hikaye": "instagram_story",
    "reel": "instagram_story",
    "flyer": "flyer_a4",
    "brosur": "flyer_a4",
    "broşür": "flyer_a4",
    "poster": "poster",
    "afiş": "poster",
    "afis": "poster",
    "presentation": "presentation",
    "sunum": "presentation",
    "thumbnail": "youtube_thumbnail",
    "logo": "logo",
    "business card": "business_card",
    "kartvizit": "business_card",
}


def dimensions_for(category: str) -> str | None:
    """Return the Canva dimension string for a known category, or None."""
    return CANVA_KNOWLEDGE_BASE["dimensions"].get(category)


def detect_category(text: str) -> str | None:
    """Best-effort category detection from a free-text request (hint only)."""
    lowered = text.lower()
    for keyword, category in CATEGORY_HINTS.items():
        if keyword in lowered:
            return category
    return None
