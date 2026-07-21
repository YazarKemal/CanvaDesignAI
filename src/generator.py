"""Generator agent (Stage 2): DeepSeek as the Canva prompt engineer.

Single-engine architecture: every stage (Architect, Generator, Reviewer)
runs on DeepSeek. Takes the Architect's technical design brief and turns
it into a Canva automation card with exactly three mandatory components —
magic_media_prompt, layer_typography_architecture, direct_action_tip.
Never chats, never asks a question — only the card.

Uses the `openai` SDK when available; falls back to `src.http_client`'s
pure-httpx `DeepSeekClient` when it isn't (e.g. on Android/Termux, where
the SDK's `jiter` C-extension dependency won't compile).
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
from src.canva_rules import CANVA_KNOWLEDGE_BASE
from src.composition_rules import as_prompt_block as composition_prompt_block
from src.constitution import as_prompt_block, load_constitution
from src.golden_cards import as_few_shot_block
from src.llm_json import extract_json
from src.schema import PromptValidationError, validate_prompt
from src.style_presets import as_prompt_block as style_prompt_block

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
    "text_zone": "top",
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


def _system_prompt(
    brand: dict[str, Any] | None = None,
    *,
    aspect_ratio: str | None = None,
    text_zone: str | None = None,
    style: dict[str, Any] | None = None,
) -> str:
    kb = json.dumps(CANVA_KNOWLEDGE_BASE, ensure_ascii=False, indent=2)
    composition_section = ""
    if aspect_ratio:
        composition_section = f"\n\n{composition_prompt_block(aspect_ratio, text_zone)}"

    # -- Style preset section (with override when brand is also active) -----
    style_section = ""
    if style is not None:
        override = brand is not None
        style_section = f"\n\n{style_prompt_block(style, override_brand=override)}"
        # Few-shot injection: include the golden reference card for this exact
        # style so the Generator has a concrete 9.0+ example to calibrate against.
        golden_block = as_few_shot_block(style["slug"])
        if golden_block:
            style_section += golden_block

    # -- Brand profile section (suppress visual_identity when style overrides) -
    brand_section = ""
    if brand is not None:
        exclude_vi = style is not None
        brand_section = f"\n\n{brand_prompt_block(brand, exclude_visual_identity=exclude_vi)}"
        brand_section += (
            "\n\nBRAND CONSTRAINT SUMMARY: Because a brand profile is active: "
            "fonts.headline_font and fonts.body_font MUST be EXACTLY this brand's "
            "signature_fonts (ignore typography.approved_pairings entirely), and every "
            "color_palette entry MUST be one of this brand's approved_colors "
            "verbatim — do not invent, blend, or approximate a new HEX value."
        )
        if style is not None:
            brand_section += (
                " The Style Preset's visual architecture OVERRIDES the Brand's "
                "visual_identity — the Brand ONLY contributes typography, colors, "
                "and logo placement to the typography layer, NOT visual mood or "
                "photographic direction to the image prompt."
            )
        else:
            # When no style is active, brand visual_identity IS active for the image
            brand_section += (
                " The Brand's visual_identity (mood, lighting, textures, "
                "photographic style) must ALSO be embedded in magic_media_prompt "
                "so the generated image reads on-brand."
            )

    # -- magic_media_prompt construction rule (style-first when style active) -
    if style is not None:
        magic_media_rule = (
            "1. magic_media_prompt — MUST OPEN with the Style Preset's visual "
            "architecture keywords verbatim at the very beginning of the prompt "
            "(for maximum AI image-model adherence to the style), then continue "
            "with the standard structure (subject -> medium -> composition -> "
            "lighting -> color/mood -> camera -> quality). The Style Preset's "
            "aesthetic takes absolute precedence over any brand visual_identity "
            "in the image description. MUST reserve deliberate negative space "
            "for the typography layer AT THE LOCATION GIVEN BY text_zone below, "
            "and strategically place Canva library keywords from the brief. Do "
            "NOT put aspect-ratio flags (--ar) inside it; the ratio lives in "
            "the aspect_ratio field."
        )
    else:
        magic_media_rule = (
            "1. magic_media_prompt — one flowing, copy-paste-ready English prompt "
            "built per the magic_media_prompt rules above (subject -> medium -> "
            "composition -> lighting -> color/mood -> camera -> quality). MUST "
            "reserve deliberate negative space for the typography layer AT THE "
            "LOCATION GIVEN BY text_zone below, and strategically place Canva "
            "library keywords from the brief. Do NOT put aspect-ratio flags "
            "(--ar) inside it; the ratio lives in the aspect_ratio field."
        )

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
        f"{kb}"
        f"{composition_section}\n\n"
        "The three mandatory components:\n"
        f"{magic_media_rule}\n"
        "2. layer_typography_architecture — {headline (<=6 words), subtext (one "
        "short line, <=14 words), color_palette (3-5 real HEX codes), fonts "
        "{headline_font, body_font} from the typography.approved_pairings, "
        "background_layers (how the generated image and text layers stack — "
        "MUST reference the same text_zone location).\n"
        "3. direct_action_tip — an ordered array of 2-5 concrete, literally-"
        "clickable Canva steps per the direct_action_tip rules above."
        f"{style_section}"
        f"{brand_section}\n\n"
        "text_zone — copy the brief's text_zone value verbatim (top/bottom/"
        "left/right/center). Both magic_media_prompt and background_layers "
        "MUST mention this same location in plain English (e.g. text_zone "
        "'top' -> mention 'top' in both) so the image's negative space and "
        "the typography layer never disagree about where the text goes.\n\n"
        "Honor the brief's aspect_ratio, target_tool, palette, style and "
        "negative_constraints exactly. Output MUST match this shape:\n"
        f"{json.dumps(OUTPUT_FORMAT_EXAMPLE, ensure_ascii=False, indent=2)}\n\n"
        "Respond with raw JSON only."
    )


def _default_client() -> Any:
    if OpenAI is not None:
        return OpenAI(
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
        )
    from src.http_client import DeepSeekClient

    return DeepSeekClient()


def generate_prompt(
    brief: dict[str, Any],
    *,
    concept: str,
    brand: dict[str, Any] | None = None,
    style: dict[str, Any] | None = None,
    feedback: str | None = None,
    model: str = DEFAULT_MODEL,
    client: Any = None,
) -> dict[str, Any]:
    """Turn the Architect `brief` into a validated Canva card (Stage 2).

    `concept` is the original user request (carried into the card). If
    `brand` is given, the card's fonts/colors are constrained to that
    brand and validated against it. If `style` is given, its elite keyword
    block is injected and its required_keywords are enforced against
    magic_media_prompt. If `feedback` is provided (from a prior Reviewer
    rejection or a schema/forbidden-phrase/brand/style validation failure),
    it is appended so the Generator can course-correct on the next attempt.
    """
    client = client or _default_client()

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
            {
                "role": "system",
                "content": _system_prompt(
                    brand,
                    aspect_ratio=brief.get("aspect_ratio"),
                    text_zone=brief.get("text_zone"),
                    style=style,
                ),
            },
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
    validate_prompt(card, brand=brand, style=style)
    return card
