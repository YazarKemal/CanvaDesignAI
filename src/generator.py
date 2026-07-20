"""Generator agent (Stage 2): Claude as the Canva prompt engineer.

Takes the Architect's technical design brief and turns it into a single
copy-paste-ready image prompt (for Canva Magic Media / DALL-E 3 / Canva
GPT), formatted as the prompt card the UI renders. It never generates
images — only the prompt.
"""

from __future__ import annotations

import json
import os
from typing import Any

import anthropic

from src.canva_rules import CANVA_KNOWLEDGE_BASE
from src.constitution import as_prompt_block, load_constitution
from src.schema import PromptValidationError, validate_prompt

DEFAULT_MODEL = "claude-sonnet-5"

OUTPUT_FORMAT_EXAMPLE = {
    "concept": "Grand Opening Cafe",
    "prompt_text": (
        "A minimalist 3d flat vector illustration for a specialty coffee shop grand "
        "opening, earthy terracotta and warm cream color palette, top-down view of an "
        "espresso cup next to an open notebook, ample negative space at the top for "
        "overlaying text in Canva, vintage aesthetic, clean lines, isolated on a plain "
        "background."
    ),
    "negative_prompt": (
        "embedded text, watermark, logo, cluttered composition, extra fingers, "
        "low resolution, jpeg artifacts, harsh oversaturation"
    ),
    "aspect_ratio": "1:1 (1080x1080)",
    "target_tool": "Canva Magic Media",
    "canva_tip": "Paste into Magic Media, then drop your headline into the empty top third.",
    "art_direction": {
        "color_palette": ["terracotta", "warm cream", "espresso brown"],
        "lighting": "soft natural daylight",
        "mood": "minimalist, vintage, artisanal",
        "magic_media_style": "Flat Vector",
    },
    "canva_keywords": ["flat vector illustration", "isolated element on transparent background"],
}


def _system_prompt() -> str:
    kb = json.dumps(CANVA_KNOWLEDGE_BASE, ensure_ascii=False, indent=2)
    return (
        "Sen Claude & ChatGPT icin Canva Prompt Muhendisisin (Canva Prompt "
        "Engineer). Your job: turn the Architect's design brief into ONE prompt "
        "text that works at 100% quality in Canva Magic Media, Canva GPT or "
        "DALL-E 3. Reply with a single JSON object and nothing else — no prose, "
        "no markdown fences.\n\n"
        f"{as_prompt_block(load_constitution())}\n\n"
        "CANVA KNOWLEDGE BASE:\n"
        f"{kb}\n\n"
        "Rules:\n"
        "- prompt_text: one flowing, copy-paste-ready prompt. MUST include "
        "deliberate empty negative space for overlaid text, and strategically "
        "place Canva library keywords (e.g. 'flat vector', 'isolated object') "
        "from the brief. Do NOT put aspect-ratio flags (--ar) inside prompt_text; "
        "the ratio lives in the aspect_ratio field.\n"
        "- Honor the brief's aspect_ratio, target_tool, palette, style and "
        "negative_constraints exactly.\n"
        "- canva_tip: one short, practical Canva usage tip for this design.\n"
        "- Output MUST match this shape:\n"
        f"{json.dumps(OUTPUT_FORMAT_EXAMPLE, ensure_ascii=False, indent=2)}\n\n"
        "Respond with raw JSON only."
    )


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[len("json"):]
    return json.loads(text.strip())


def generate_prompt(
    brief: dict[str, Any],
    *,
    concept: str,
    feedback: str | None = None,
    model: str = DEFAULT_MODEL,
    client: anthropic.Anthropic | None = None,
) -> dict[str, Any]:
    """Turn the Architect `brief` into a validated prompt card (Stage 2).

    `concept` is the original user request (carried into the card). If
    `feedback` is provided (from a prior Reviewer rejection), it is appended
    so the Generator can course-correct on the next attempt.
    """
    client = client or anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    user_message = (
        f"Original concept: {concept}\n\n"
        f"Architect design brief (JSON):\n{json.dumps(brief, ensure_ascii=False, indent=2)}"
    )
    if feedback:
        user_message += (
            "\n\nThe previous prompt was rejected by the Reviewer agent. "
            f"Fix these issues before responding:\n{feedback}"
        )

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=_system_prompt(),
        messages=[{"role": "user", "content": user_message}],
    )
    raw_text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )

    try:
        card = _extract_json(raw_text)
    except json.JSONDecodeError as exc:
        raise PromptValidationError(f"Generator did not return valid JSON: {exc}\nRaw: {raw_text}") from exc

    card.setdefault("concept", concept)
    validate_prompt(card)
    return card
