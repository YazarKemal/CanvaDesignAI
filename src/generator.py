"""Generator agent (Stage 2): DeepSeek as the Canva prompt engineer.

Single-engine architecture: every stage (Architect, Generator, Reviewer)
runs on DeepSeek. Takes the Architect's technical design brief and turns
it into a Canva automation card with exactly three mandatory components —
magic_media_prompt, layer_typography_architecture, direct_action_tip.
Never chats, never asks a question — only the card.
"""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from src.canva_rules import CANVA_KNOWLEDGE_BASE
from src.constitution import as_prompt_block, load_constitution
from src.llm_json import extract_json
from src.schema import PromptValidationError, validate_prompt

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"

OUTPUT_FORMAT_EXAMPLE = {
    "concept": "Grand Opening Cafe",
    "magic_media_prompt": (
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
    "layer_typography_architecture": {
        "headline": "Grand Opening",
        "subtext": "Freshly roasted, every morning.",
        "color_palette": ["#4A2E1B", "#D4A373", "#F5EFE6"],
        "fonts": {"headline_font": "Montserrat Bold", "body_font": "Playfair Display"},
        "background_layers": "generated image fills the bottom 60%; solid cream rectangle layer behind the top 40% carries the headline/subtext",
        "magic_media_style": "Flat Vector",
    },
    "direct_action_tip": [
        "Open Canva > Apps > Magic Media, paste magic_media_prompt, generate at 1:1 (1080x1080).",
        "Add a Heading text box in the empty top space and type the headline.",
        "Add a Subheading text box below it with the subtext.",
        "Set Text > Font to the headline_font/body_font pairing.",
        "Recolor the text and any shape accents using the color_palette HEX codes via the color picker.",
    ],
    "canva_keywords": ["flat vector illustration", "isolated element on transparent background"],
}


def _system_prompt() -> str:
    kb = json.dumps(CANVA_KNOWLEDGE_BASE, ensure_ascii=False, indent=2)
    return (
        "Sen Claude degil, DeepSeek tabanli bir Canva Prompt Muhendisisin "
        "(Canva Prompt Engineer) — bir otomasyon motorunun ikinci asamasisin. "
        "Your job: turn the Architect's design brief into ONE Canva automation "
        "card with exactly three mandatory components.\n\n"
        "HARD RULES:\n"
        "- Reply with a single JSON object and NOTHING else — no greeting, no "
        "prose, no markdown fences, no explanation, no question back to the "
        "user, no phrases like 'I can generate' / 'here is' / 'would you "
        "like'. Pure data only.\n"
        "- If anything in the brief is ambiguous, make the most Canva-sensible "
        "assumption yourself. Never ask for clarification.\n\n"
        f"{as_prompt_block(load_constitution())}\n\n"
        "CANVA KNOWLEDGE BASE:\n"
        f"{kb}\n\n"
        "The three mandatory components:\n"
        "1. magic_media_prompt — one flowing, copy-paste-ready English prompt "
        "built per the magic_media_prompt rules above (subject -> medium -> "
        "composition -> lighting -> color/mood -> camera -> quality). MUST "
        "reserve deliberate negative space for the typography layer and "
        "strategically place Canva library keywords from the brief. Do NOT "
        "put aspect-ratio flags (--ar) inside it; the ratio lives in the "
        "aspect_ratio field.\n"
        "2. layer_typography_architecture — {headline (<=6 words), subtext (one "
        "short line), color_palette (3-5 real HEX codes), fonts "
        "{headline_font, body_font} from the typography.approved_pairings, "
        "background_layers (how the generated image and text layers stack)}.\n"
        "3. direct_action_tip — an ordered array of 2-5 concrete, literally-"
        "clickable Canva steps per the direct_action_tip rules above.\n\n"
        "Honor the brief's aspect_ratio, target_tool, palette, style and "
        "negative_constraints exactly. Output MUST match this shape:\n"
        f"{json.dumps(OUTPUT_FORMAT_EXAMPLE, ensure_ascii=False, indent=2)}\n\n"
        "Respond with raw JSON only."
    )


def generate_prompt(
    brief: dict[str, Any],
    *,
    concept: str,
    feedback: str | None = None,
    model: str = DEFAULT_MODEL,
    client: OpenAI | None = None,
) -> dict[str, Any]:
    """Turn the Architect `brief` into a validated Canva card (Stage 2).

    `concept` is the original user request (carried into the card). If
    `feedback` is provided (from a prior Reviewer rejection or a schema/
    forbidden-phrase validation failure), it is appended so the Generator
    can course-correct on the next attempt.
    """
    client = client or OpenAI(
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
        base_url=os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
    )

    user_message = (
        f"Original concept: {concept}\n\n"
        f"Architect design brief (JSON):\n{json.dumps(brief, ensure_ascii=False, indent=2)}"
    )
    if feedback:
        user_message += (
            "\n\nThe previous card was rejected. Fix these issues before "
            f"responding:\n{feedback}"
        )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
    )
    raw_text = response.choices[0].message.content or ""

    try:
        card = extract_json(raw_text)
    except json.JSONDecodeError as exc:
        raise PromptValidationError(f"Generator did not return valid JSON: {exc}\nRaw: {raw_text}") from exc

    card.setdefault("concept", concept)
    validate_prompt(card)
    return card
