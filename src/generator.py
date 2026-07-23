"""Generator agent (Stage 2): DeepSeek as the Canva prompt engineer.

Single-engine architecture: every stage (Architect, Generator, Reviewer)
runs on DeepSeek. Takes the Architect's technical design brief and turns
it into a Canva automation card using the HYBRID SPLIT LAYER architecture
with native Canva elements — stock photos / gradient backgrounds, built-in
typography font boxes, and native vector shapes (pill buttons, badges).

All AI image generation (Magic Media, DALL-E, Midjourney) references have
been retired. The Generator now produces cards designed for the **Canva
Native Layout Engine**: searchable stock-library backgrounds, crisp Canva
typography, and native vector graphic elements.

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
    "target_tool": "Canva Native Layout Engine",
    "text_zone": "top",
    "canva_keywords": ["vertical text stack", "full-bleed stock photo", "pill button CTA"],
    # -- Layer 1: Background (stock photo or gradient — NO AI generation) ----
    "raster_background": {
        "magic_media_prompt": (
            "A Canva stock photo search query for: modern specialty coffee shop interior, "
            "warm terracotta and cream color palette, top-down flat lay of espresso cup "
            "beside an open notebook on a clean oak table, ample negative space at the "
            "top for overlaying text, soft natural window light, editorial composition. "
            "Use Canva Stock Library — do NOT generate with AI."
        ),
        "negative_prompt": (
            "no AI-generated imagery, no text, no numbers, no letters, "
            "no watermark, no logo, cluttered composition, harsh oversaturation"
        ),
        "layout_style": "Flat Vector",
    },
    # -- Layer 2: Vector Elements (native Canva shapes) ----------------------
    "vector_elements": {
        "cta_button": (
            "rounded pill button 'Order Now' in white Montserrat Bold at 16 pt, "
            "filled with #4A2E1B, 40 px border-radius, positioned bottom-right "
            "corner with 48 px margin from the right and bottom edges. Use Canva's "
            "built-in rounded rectangle shape — native element, not AI-generated."
        ),
        "badge": (
            "small rounded pill badge reading 'NEW' in white on #D4A373 fill, "
            "32 px height, 12 px horizontal padding, positioned top-right corner "
            "with 24 px margin from the top and right edges. Use Canva's built-in "
            "pill shape — native element."
        ),
        "accent_shape": (
            "large semi-transparent circle in #D4A373 at 8% opacity behind the "
            "headline zone, 400 px diameter, centred horizontally at 30% from top. "
            "Use Canva's built-in circle shape."
        ),
    },
    # -- Layer 3: Native Typography (Canva text boxes — vertical stack) ------
    "native_typography": {
        "headline": "Grand Opening",
        "subtext": "Freshly roasted, every morning.",
        "headline_pt": 48,
        "subtext_pt": 18,
        "color_palette": ["#4A2E1B", "#D4A373", "#F5EFE6"],
        "fonts": {"headline_font": "Montserrat Bold", "body_font": "Playfair Display"},
        "alignment_zone": "top 40% of canvas, centred horizontally, vertical stack",
    },
    "direct_action_tip": [
        "PRIMARY (Canva Native Layout Engine): Build this design entirely with Canva's native tools — (1) Search Canva Stock Library for 'modern coffee shop interior warm terracotta' and set the photo as full-bleed background at 1:1 (1080x1080). (2) Add a Heading text box at top 40%: type 'Grand Opening', set Montserrat Bold 48 pt, #4A2E1B. (3) Add a Subheading below: 'Freshly roasted, every morning.', Playfair Display 18 pt, #D4A373. (4) Insert a Rounded Rectangle shape for the CTA: fill #4A2E1B, border-radius 40 px, add text 'Order Now' in white Montserrat Bold 16 pt, position bottom-right. (5) Insert a Pill shape for the badge: fill #D4A373, add text 'NEW' in white 12 pt, position top-right.",
        "ALTERNATIVE (Step-by-step manual): Open Canva → Create Design → 1080x1080. Go to Photos tab and search 'coffee shop interior warm', drag a stock photo to fill the canvas. Add a Heading text box, type 'Grand Opening', set font to Montserrat Bold 48 pt with color #4A2E1B. Add subtext below. Insert Shapes → Rounded Rectangle for the CTA button. Insert Shapes → Pill for the badge.",
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
            # When no style is active, brand visual_identity IS active for the background
            brand_section += (
                " The Brand's visual_identity (mood, lighting, textures, "
                "photographic style) must ALSO be embedded in magic_media_prompt "
                "(the Canva Stock Library search query) so the background reads "
                "on-brand."
            )

    # -- Background composition rule (style-first when style active) ---------
    if style is not None:
        background_composition_rule = (
            "1. magic_media_prompt — a Canva Stock Library search query OR a "
            "precise native-gradient description. MUST OPEN with the Style "
            "Preset's visual architecture keywords verbatim, then continue "
            "with the standard structure (subject -> setting -> composition -> "
            "lighting -> color/mood -> quality descriptors). The Style Preset's "
            "aesthetic takes absolute precedence over any brand visual_identity. "
            "MUST reserve deliberate negative space for the typography layer AT "
            "THE LOCATION GIVEN BY text_zone below. This is a stock photo search "
            "query, NOT an AI image-generation prompt. Do NOT put aspect-ratio "
            "flags (--ar) inside it."
        )
    else:
        background_composition_rule = (
            "1. magic_media_prompt — a Canva Stock Library search query OR a "
            "precise native-gradient description (subject -> setting -> "
            "composition -> lighting -> color/mood -> quality descriptors). "
            "MUST reserve deliberate negative space for the typography layer "
            "AT THE LOCATION GIVEN BY text_zone below. This is a stock photo "
            "search query, NOT an AI image-generation prompt. Do NOT put "
            "aspect-ratio flags (--ar) inside it."
        )

    # -- Layer 1 rule: Background (stock photo or gradient — NO AI) ---------
    if style is not None:
        l1_rule = (
            "1. raster_background — Layer 1 (Background: stock photo or native "
            "gradient). magic_media_prompt: a Canva Stock Library search query "
            "OR a gradient definition. MUST OPEN with the Style Preset's visual "
            "architecture keywords verbatim. The Style Preset's aesthetic takes "
            "absolute precedence. MUST reserve deliberate negative space at the "
            "text_zone location. negative_prompt: MUST always contain 'no "
            "AI-generated imagery, no text, no numbers, no letters' as the "
            "first terms. layout_style: one of the knowledge-base layout_styles. "
            "NEVER describe AI generation parameters — this layer searches "
            "Canva's built-in stock library or uses native gradients."
        )
    else:
        l1_rule = (
            "1. raster_background — Layer 1 (Background: stock photo or native "
            "gradient). magic_media_prompt: a Canva Stock Library search query "
            "OR a gradient definition (subject -> setting -> composition -> "
            "lighting -> color/mood -> quality descriptors). MUST reserve "
            "deliberate negative space at the text_zone location. "
            "negative_prompt: MUST always contain 'no AI-generated imagery, "
            "no text, no numbers, no letters' as the first terms. "
            "layout_style: one of the knowledge-base layout_styles. NEVER "
            "describe AI generation parameters — this layer searches Canva's "
            "built-in stock library or uses native gradients."
        )

    return (
        "Sen Claude degil, DeepSeek tabanli bir Canva Prompt Muhendisisin "
        "(Canva Prompt Engineer) — bir otomasyon motorunun ikinci asamasisin. "
        "Your job: turn the Architect's design brief into ONE Canva automation "
        "card using the HYBRID SPLIT LAYER architecture — background (stock "
        "photo / native gradient), vector elements (native Canva shapes), and "
        "typography (Canva text boxes in vertical stacks).\n\n"
        "HARD RULES:\n"
        "- DO NOT use Magic Media or AI image generation. All backgrounds "
        "must be Canva Stock Library search queries or native CSS gradients. "
        "All visual elements must be native Canva shapes (pill buttons, "
        "badges, frames, rectangles, circles). All typography must use "
        "Canva's built-in font boxes.\n"
        "- target_tool MUST be 'Canva Native Layout Engine' — never 'Canva "
        "Magic Media', 'DALL-E 3', or any AI image generator.\n"
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
        "2. vector_elements — Layer 2 (Native Canva Shapes: pill buttons, "
        "badges, frames, accent shapes on top of the background). Each key "
        "(cta_button, badge, accent_shape, decorative_frame) is a single "
        "concrete instruction string describing one Canva native shape with "
        "its colour, size, border-radius, and position specified in pixels. "
        "These are Canva's BUILT-IN vector shapes (Elements tab) — they are "
        "NOT AI-generated. Always specify which Canva shape type to use. "
        "Shapes must NOT contain the headline or subtext copy (that goes in "
        "Layer 3).\n\n"
        "3. native_typography — Layer 3 (Canva Text Boxes: the ONLY layer "
        "with readable text, in a vertical stack). headline (<=6 words), "
        "subtext (<=14 words), headline_pt (point size, 24-96), subtext_pt "
        "(point size, 12-32), color_palette (3-5 HEX codes including the "
        "text fill colours), fonts {{headline_font, body_font}} from "
        "native_typography lists — use Canva's built-in fonts like Poppins "
        "Bold, Montserrat Bold, Inter Regular, Lato Regular. alignment_zone "
        "(where on the canvas this text block sits — MUST reference the same "
        "text_zone location, and specify 'vertical stack' + alignment). The "
        "receiving assistant will render this layer as real Canva text "
        "objects, so pt sizes and HEX colours must be exact.\n\n"
        "4. direct_action_tip — an ordered array of 2-5 steps per the "
        "direct_action_tip rules above. Step 1 (PRIMARY) is a unified "
        "Canva Native Layout Engine instruction block that lists the actual "
        "stock photo query, native shapes, and typography values INLINE for "
        "holistic one-pass execution. Remaining steps (ALTERNATIVE) are "
        "concrete, literally-clickable Canva UI steps using native tools: "
        "Stock Library search, Elements tab shapes, Text tab fonts."
        f"{style_section}"
        f"{brand_section}\n\n"
        "text_zone — copy the brief's text_zone value verbatim. Both "
        "raster_background.magic_media_prompt and native_typography."
        "alignment_zone MUST mention this same location so the background "
        "and the typography overlay never disagree.\n\n"
        "Honor the brief's aspect_ratio, target_tool, background, typography, "
        "graphic_elements, and negative_constraints exactly. Output MUST "
        "match this shape:\n"
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
