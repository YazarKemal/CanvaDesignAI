"""Architect agent (Stage 1): DeepSeek as the Canva design expert.

Takes the user's plain request, applies the Canva knowledge base, and emits
a compact "technical design brief" that the Claude Generator turns into a
copy-paste-ready prompt. This is the orchestrator step of the workbench:
detect the design category/dimensions and lock the art direction + negative
constraints before any prompt text is written.
"""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from src.canva_rules import CANVA_KNOWLEDGE_BASE, detect_category, dimensions_for

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"

BRIEF_SCHEMA_HINT = {
    "detected_category": "instagram_post",
    "aspect_ratio": "1:1 (1080x1080)",
    "target_tool": "Canva Magic Media",
    "magic_media_style": "Minimalist",
    "art_direction": {
        "color_palette": ["warm terracotta", "cream", "espresso brown"],
        "lighting": "soft natural daylight",
        "mood": "minimalist, vintage, artisanal",
    },
    "canva_keywords": ["flat vector illustration", "isolated element on transparent background"],
    "negative_constraints": "reserve empty negative space at the top for overlaid text; no embedded text, no clutter",
}


def _system_prompt() -> str:
    kb = json.dumps(CANVA_KNOWLEDGE_BASE, ensure_ascii=False, indent=2)
    return (
        "Sen Canva Tasarim Mimarisin (Canva Design Architect). Kullanicinin "
        "istegini analiz et ve Canva'nin Magic Media / Canva GPT araclarinda en "
        "yuksek kalitede gorseli verecek teknik parametreleri belirle. You reply "
        "with a single JSON object and nothing else — no prose, no markdown "
        "fences.\n\n"
        "CANVA KNOWLEDGE BASE (use these exact dimensions, styles and keywords):\n"
        f"{kb}\n\n"
        "Your brief MUST include, at minimum:\n"
        "1. detected_category — one of the knowledge-base dimension keys.\n"
        "2. aspect_ratio — the matching canvas size (e.g. '1:1 (1080x1080)').\n"
        "3. target_tool — one of the knowledge-base target_tools.\n"
        "4. magic_media_style — one of the knowledge-base magic_media_styles.\n"
        "5. art_direction — {color_palette (3-5), lighting, mood}.\n"
        "6. canva_keywords — 2-4 items drawn from canva_element_keywords.\n"
        "7. negative_constraints — MUST enforce deliberate negative space for "
        "overlaid text and exclude embedded text.\n\n"
        "Example shape (values illustrative only):\n"
        f"{json.dumps(BRIEF_SCHEMA_HINT, ensure_ascii=False, indent=2)}\n\n"
        "Respond with raw JSON only."
    )


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[len("json"):]
    return json.loads(text.strip())


def build_brief(
    user_message: str,
    *,
    model: str = DEFAULT_MODEL,
    client: OpenAI | None = None,
) -> dict[str, Any]:
    """Produce a technical design brief for `user_message` (Stage 1)."""
    client = client or OpenAI(
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
        base_url=os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
    )

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
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": f"User request: {user_message}{hint_text}"},
        ],
        temperature=0.2,
    )
    raw_text = response.choices[0].message.content or ""

    try:
        return _extract_json(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Architect did not return valid JSON: {exc}\nRaw: {raw_text}") from exc
