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
from src.schema import PromptValidationError, _ensure_hybrid_format, validate_prompt
from src.style_presets import as_prompt_block as style_prompt_block

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"

OUTPUT_FORMAT_EXAMPLE = {
    "concept": "Grand Opening Cafe",
    "aspect_ratio": "1:1 (1080x1080)",
    "target_tool": "Canva Magic Media",
    "text_zone": "top",
    "canva_keywords": ["flat vector illustration", "isolated element on transparent background"],
    # -- Layer 1: Raster Background (image only — strict no-text rule) -----
    "raster_background": {
        "magic_media_prompt": (
            "A minimalist 3d flat vector illustration for a specialty coffee shop grand "
            "opening, earthy terracotta and warm cream color palette, top-down view of an "
            "espresso cup next to an open notebook, ample negative space at the top for "
            "overlaying text in Canva, vintage aesthetic, clean lines, isolated on a plain "
            "background."
        ),
        "negative_prompt": (
            "no text, no numbers, no letters, completely blank space, "
            "embedded text, watermark, logo, cluttered composition, extra fingers, "
            "low resolution, jpeg artifacts, harsh oversaturation"
        ),
        "magic_media_style": "Flat Vector",
    },
    # -- Layer 2: Vector Elements (CTA, badge — pure graphic shapes) -------
    "vector_elements": {
        "cta_button": (
            "rounded pill button 'Order Now' in white Montserrat Bold at 16 px, "
            "filled with #4A2E1B, 40 px border-radius, positioned bottom-right "
            "corner with 48 px margin from the right and bottom edges"
        ),
        "badge": (
            "small rounded pill badge reading 'NEW' in white on #D4A373 fill, "
            "32 px height, 12 px horizontal padding, positioned top-right corner "
            "with 24 px margin from the top and right edges"
        ),
        "person_cutout": (
            "clean-edged espresso cup and notebook illustration centred below "
            "the headline zone, flat vector isolated on transparent background"
        ),
        "giant_typography": (
            "the word 'COFFEE' at 5× headline scale in Montserrat Bold at 10% "
            "opacity behind the main headline, overlapping the top text zone"
        ),
    },
    # -- Layer 3: Native Typography (text only — separate overlay) ---------
    "native_typography": {
        "headline": "Grand Opening",
        "subtext": "Freshly roasted, every morning.",
        "headline_pt": 48,
        "subtext_pt": 18,
        "color_palette": ["#4A2E1B", "#D4A373", "#F5EFE6"],
        "fonts": {"headline_font": "Montserrat Bold", "body_font": "Playfair Display"},
        "alignment_zone": "top 40% of canvas, centred horizontally, cream background panel behind text",
    },
    "direct_action_tip": [
        "PRIMARY (AI-Assistant Holistic Generation): Feed this entire design to your Canva-connected AI assistant (Claude or ChatGPT) as a single unified request — magic_media_prompt: 'A minimalist 3d flat vector illustration for a specialty coffee shop grand opening.' | Headline: 'Grand Opening' (48 pt Montserrat Bold, #4A2E1B) | Subtext: 'Freshly roasted, every morning.' (18 pt Playfair Display, #D4A373) | Color palette: #4A2E1B, #D4A373, #F5EFE6 | Format: 1:1 (1080x1080) | Alignment zone: top 40% centred | CTA: 'Order Now' pill bottom-right | Badge: 'NEW' pill top-right. Generate the complete visual+vector+typography composition holistically in ONE pass.",
        "ALTERNATIVE (Manual Magic Media): Open Canva > Apps > Magic Media, paste the magic_media_prompt, and generate at 1:1 (1080x1080).",
        "Add a Heading text box in the top 40% zone, type 'Grand Opening', set to Montserrat Bold 48 pt in #4A2E1B.",
        "Add the 'Order Now' CTA: draw a rounded rectangle bottom-right, fill #4A2E1B, add white text at 16 pt.",
        "Add the 'NEW' badge: draw a rounded pill top-right, fill #D4A373, add white text at 12 pt.",
    ],
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

    # -- magic_media_prompt rule for Layer 1 (strict no-text) ---------------
    if style is not None:
        l1_rule = (
            "1. raster_background — Layer 1 (Raster Background: image ONLY). "
            "magic_media_prompt: MUST OPEN with the Style Preset's visual "
            "architecture keywords verbatim, then continue with the standard "
            "structure (subject -> medium -> composition -> lighting -> "
            "color/mood -> camera -> quality). The Style Preset's aesthetic "
            "takes absolute precedence. MUST reserve deliberate negative space "
            "at the text_zone location. negative_prompt: MUST always contain "
            "'no text, no numbers, no letters, completely blank space' as the "
            "first four terms — the raster layer must NEVER contain any "
            "renderable letters, numerals, or glyphs. Do NOT put aspect-ratio "
            "flags (--ar) inside magic_media_prompt."
        )
    else:
        l1_rule = (
            "1. raster_background — Layer 1 (Raster Background: image ONLY). "
            "magic_media_prompt: one flowing, copy-paste-ready English prompt "
            "(subject -> medium -> composition -> lighting -> color/mood -> "
            "camera -> quality). MUST reserve deliberate negative space at the "
            "text_zone location. negative_prompt: MUST always contain 'no text, "
            "no numbers, no letters, completely blank space' as the first four "
            "terms — the raster layer must NEVER contain any renderable "
            "letters, numerals, or glyphs. Do NOT put aspect-ratio flags "
            "inside magic_media_prompt."
        )

    return (
        "Sen Claude degil, DeepSeek tabanli bir Canva Prompt Muhendisisin "
        "(Canva Prompt Engineer) — bir otomasyon motorunun ikinci asamasisin. "
        "Your job: turn the Architect's design brief into ONE Canva automation "
        "card using the HYBRID SPLIT LAYER architecture — three independent "
        "layers that the receiving assistant composes in precise layer order.\n\n"
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
        "THE THREE HYBRID LAYERS (independent, composed in order 1→2→3):\n\n"
        f"{l1_rule}\n\n"
        "2. vector_elements — Layer 2 (Vector Graphics: decorative shapes on "
        "top of the raster). Optional but recommended when the style preset "
        "carries graphic_composition rules. Each key (cta_button, badge, "
        "person_cutout, giant_typography) is a single concrete instruction "
        "string describing one Canva shape/text element with its colour, size, "
        "border-radius, and position specified in pixels where applicable. "
        "These are PURE graphic shapes — they must NOT contain the headline "
        "or subtext copy (that goes in Layer 3).\n\n"
        "3. native_typography — Layer 3 (Native Text: the ONLY layer with "
        "readable text). headline (<=6 words), subtext (<=14 words), "
        "headline_pt (point size, 24-96), subtext_pt (point size, 12-32), "
        "color_palette (3-5 HEX codes including the text fill colours), "
        "fonts {{headline_font, body_font}} from typography.approved_pairings, "
        "alignment_zone (where on the canvas this text block sits — MUST "
        "reference the same text_zone location). The receiving assistant "
        "will render this layer as real Canva text objects, so pt sizes and "
        "HEX colours must be exact, not approximate.\n\n"
        "4. direct_action_tip — an ordered array of 3-5 steps per the "
        "direct_action_tip rules above. Step 1 is the PRIMARY path: a unified "
        "holistic-design instruction block that lists the actual raster, vector "
        "and typography values INLINE. Steps 2-5 are the ALTERNATIVE manual "
        "Magic Media path: concrete, literally-clickable Canva UI steps."
        f"{style_section}"
        f"{brand_section}\n\n"
        "text_zone — copy the brief's text_zone value verbatim. Both "
        "raster_background.magic_media_prompt and native_typography."
        "alignment_zone MUST mention this same location so the background "
        "image's negative space and the typography overlay never disagree.\n\n"
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
    # Ensure the returned card uses the hybrid split-layer format so every
    # downstream consumer (API, paste_render, omni_channel, tests) sees the
    # new structure regardless of what the LLM emitted.
    _ensure_hybrid_format(card)
    return card
