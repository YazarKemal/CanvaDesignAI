"""Architect agent (Stage 1): DeepSeek as the Canva design expert.

Takes the user's plain request, applies the Canva knowledge base, and emits
a compact "technical design brief" that the Generator (also DeepSeek) turns
into the final Canva card. This is the orchestrator's first step: detect
the design category/dimensions and lock the art direction + negative
constraints before any prompt text is written. Never chats, never asks a
question back — makes the most Canva-sensible assumption and proceeds.
"""

from __future__ import annotations

import json
import os
from typing import Any

try:
    from openai import OpenAI  # type: ignore[import-untyped]
except ImportError:
    OpenAI = None  # type: ignore[assignment]

from src.brand_profiles import as_prompt_block as brand_prompt_block
from src.canva_rules import CANVA_KNOWLEDGE_BASE, detect_category, dimensions_for
from src.llm_json import extract_json

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"

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
}


def _system_prompt(brand: dict[str, Any] | None = None) -> str:
    kb = json.dumps(CANVA_KNOWLEDGE_BASE, ensure_ascii=False, indent=2)
    brand_section = ""
    if brand is not None:
        zone = brand.get("logo", {}).get("placement_zone", "")
        brand_section = (
            f"\n\n{brand_prompt_block(brand)}\n\n"
            "9. Because a brand profile is active: art_direction.color_palette "
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
        f"{kb}\n\n"
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
        "one near-black or near-white anchor so text stays legible, lighting, mood}.\n"
        "7. canva_keywords — 2-4 items drawn from canva_element_keywords.\n"
        "8. negative_constraints — MUST enforce deliberate negative space at "
        "text_zone's location and exclude embedded text."
        f"{brand_section}\n\n"
        "Example shape (values illustrative only):\n"
        f"{json.dumps(BRIEF_SCHEMA_HINT, ensure_ascii=False, indent=2)}\n\n"
        "Respond with raw JSON only."
    )


def build_brief(
    user_message: str,
    *,
    brand: dict[str, Any] | None = None,
    model: str = DEFAULT_MODEL,
    client: OpenAI | None = None,
) -> dict[str, Any]:
    """Produce a technical design brief for `user_message` (Stage 1).

    If `brand` is given, the brief's color_palette and text_zone are
    constrained by that brand profile.
    """
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
            {"role": "system", "content": _system_prompt(brand)},
            {"role": "user", "content": f"User request: {user_message}{hint_text}"},
        ],
        temperature=0.2,
    )
    raw_text = response.choices[0].message.content or ""

    try:
        return extract_json(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Architect did not return valid JSON: {exc}\nRaw: {raw_text}") from exc
