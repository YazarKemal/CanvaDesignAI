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
    "text_zone": "center",
    "canva_keywords": ["blank canvas", "text-only layout", "pure typography"],
    # -- Layer 1: Background — BLANK CANVAS ONLY, no visuals ----------------
    "raster_background": {
        "magic_media_prompt": (
            "BLANK CANVAS — solid #FFFFFF (pure white) background with the "
            "typography block centered in the middle of the frame. "
            "NO stock photos, NO templates, NO images, NO illustrations, "
            "NO gradients, NO textures, NO patterns, NO placeholders. "
            "A completely empty white canvas ready for pure text typography. "
            "The reserved negative space at the center holds the headline and subtext."
        ),
        "negative_prompt": (
            "no images, no photos, no stock visuals, no illustrations, "
            "no templates, no placeholders, no gradients, no textures, "
            "no patterns, no watermarks, no logos, no AI-generated imagery"
        ),
        "layout_style": "Minimalist",
    },
    # -- Layer 2: Vector Elements — structural rules only --------------------
    "vector_elements": {
        "top_rule": (
            "thin horizontal rule at 1 px weight in #000000 at 30% opacity, "
            "spanning 60% of canvas width, centered, positioned 120 px from "
            "the top edge. Use Canva's built-in line shape."
        ),
        "bottom_rule": (
            "thin horizontal rule at 1 px weight in #000000 at 30% opacity, "
            "spanning 60% of canvas width, centered, positioned 120 px from "
            "the bottom edge. Use Canva's built-in line shape."
        ),
    },
    # -- Layer 3: Native Typography — TEXT ONLY ------------------------------
    "native_typography": {
        "headline": "Grand Opening",
        "subtext": "Freshly roasted, every morning.",
        "headline_pt": 48,
        "subtext_pt": 16,
        "color_palette": ["#000000", "#333333", "#999999", "#F5F5F5"],
        "fonts": {"headline_font": "Montserrat Bold", "body_font": "Montserrat Regular"},
        "alignment_zone": "centered horizontally, vertical stack starting at 35% from top",
        "giant_footer_text": {
            "text": "PORTFOLIO",
            "pt": 96,
            "color": "#000000",
            "font": "Montserrat ExtraBold",
            "position": "bottom 10% of canvas, centered horizontally",
            "tracking": "0.15em",
        },
    },
    "direct_action_tip": [
        "PRIMARY (Canva Native Layout Engine — BLANK CANVAS, TEXT ONLY): (1) Open Canva → Create Design → 1080x1080. Start from a BLANK canvas — do NOT search templates, do NOT use Stock Library. (2) Set background to solid #FFFFFF (pure white). (3) Add a Heading text box centered at 35% from top: type 'Grand Opening', set Montserrat Bold 48 pt, #000000. (4) Add Subheading below: 'Freshly roasted, every morning.', Montserrat Regular 16 pt, #333333. (5) Insert a thin horizontal line at 120 px from top (1 px, #000000 30% opacity). (6) Insert a thin horizontal line at 120 px from bottom (1 px, #000000 30% opacity). (7) Add a GIANT text box at bottom 10%: type 'PORTFOLIO', set Montserrat ExtraBold 96 pt, #000000, tracking 0.15em, centered. (8) NO photos, NO stock images, NO templates — pure text typography only.",
        "ALTERNATIVE (Manual): Open Canva → Blank 1080x1080 canvas. Set background #FFFFFF. Add text boxes only — no images, no templates, no stock library.",
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

    # -- Layer 1 rule: Background — BLANK CANVAS, NO VISUALS ----------------
    l1_rule = (
        "1. raster_background — Layer 1 (Background: BLANK WHITE CANVAS ONLY). "
        "magic_media_prompt MUST describe a solid #FFFFFF (pure white) blank "
        "canvas with NO images, NO stock photos, NO templates, NO illustrations, "
        "NO gradients, NO textures, NO patterns, NO placeholders of any kind. "
        "MUST mention the text_zone location (e.g. 'the reserved negative space "
        "at the center holds the headline and subtext') so the schema validator "
        "sees text_zone consistency. "
        "This is a TEXT-ONLY layout — the canvas must be completely empty "
        "except for the typography and thin structural rules added in Layers 2-3. "
        "negative_prompt MUST start with 'no images, no photos, no stock visuals, "
        "no illustrations, no templates, no placeholders' as the first terms. "
        "layout_style: 'Minimalist'. "
        "NEVER describe a stock photo search query — there are NO visuals."
    )

    return (
        "Sen Claude degil, DeepSeek tabanli bir Canva Prompt Muhendisisin "
        "(Canva Prompt Engineer) — bir otomasyon motorunun ikinci asamasisin. "
        "Your job: turn the Architect's design brief into ONE Canva automation "
        "card — a PURE TYPOGRAPHY layout on a BLANK WHITE CANVAS.\n\n"
        "HARD RULES:\n"
        "- BLANK CANVAS ONLY: Start from a completely empty #FFFFFF (pure white) "
        "canvas. NEVER search templates, NEVER use Canva Stock Library, NEVER "
        "describe stock photos, NEVER include images/illustrations/photos of any "
        "kind. This is TEXT-ONLY typography.\n"
        "- target_tool MUST be 'Canva Native Layout Engine'.\n"
        "- NO TEMPLATES: DO NOT reference any Canva template name, template "
        "category, or pre-built layout. 'Portfolio' is NOT a template — it is "
        "a giant footer text element you add yourself.\n"
        "- NO AI IMAGE GENERATION: magic_media_prompt describes a BLANK WHITE "
        "CANVAS, not a stock photo search. negative_prompt excludes all imagery.\n"
        "- TEXT-ONLY RULES:\n"
        "  a. BLANK BACKGROUND: Layer 1 is solid #FFFFFF. Nothing else.\n"
        "  b. STRUCTURAL RULES ONLY: Layer 2 (vector_elements) contains thin "
        "horizontal/vertical rules (1 px, #000000 at 20-30% opacity) for "
        "structure. NO decorative shapes, NO frames, NO badges, NO buttons.\n"
        "  c. PURE TYPOGRAPHY: Layer 3 (native_typography) is the ONLY content. "
        "headline (48-72 pt, Montserrat Bold or Helvetica, #000000), subtext "
        "(14-18 pt, Montserrat Regular or Helvetica Light, #333333).\n"
        "  d. GIANT FOOTER: native_typography MUST include a giant_footer_text "
        "object: text='PORTFOLIO', pt=80-120, color='#000000', "
        "font='Montserrat ExtraBold' or 'Helvetica Bold', positioned at the "
        "bottom 10% of the canvas, centered, with 0.10-0.20em letter-spacing.\n"
        "  e. COLOR PALETTE: monochrome — #000000, #333333, #666666, "
        "#999999, #F5F5F5. Include at least one near-white anchor (#F5F5F5) "
        "paired with #000000 to guarantee WCAG AA contrast >= 4.5:1. "
        "All text is black/dark grey on the white canvas.\n"
        "- Reply with a single JSON object and NOTHING else — no greeting, no "
        "prose, no markdown fences, no explanation. Pure data only.\n"
        "- If anything in the brief is ambiguous, make the most Canva-sensible "
        "assumption yourself. Never ask for clarification.\n\n"
        f"{as_prompt_block(load_constitution())}\n\n"
        "CANVA KNOWLEDGE BASE:\n"
        f"{kb}"
        f"{composition_section}\n\n"
        "THE THREE HYBRID LAYERS (independent, composed in order 1→2→3):\n\n"
        f"{l1_rule}\n\n"
        "2. vector_elements — Layer 2 (Structural Rules Only). MAXIMUM 2-3 "
        "elements: thin horizontal rules at 1 px weight, #000000 at 20-30% "
        "opacity, spanning 40-60% of canvas width. Positioned as top/bottom "
        "separators (e.g. 120 px from top edge, 120 px from bottom edge). "
        "NO decorative shapes, NO frames, NO badges, NO buttons, NO icons. "
        "Use ONLY Canva's built-in line shape.\n\n"
        "3. native_typography — Layer 3 (Pure Typography — TEXT ONLY). "
        "headline (<=6 words, 48-72 pt, Montserrat Bold or Helvetica Bold, "
        "#000000), subtext (<=14 words, 14-18 pt, Montserrat Regular or "
        "Helvetica Light, #333333). giant_footer_text object REQUIRED: "
        "text='PORTFOLIO', pt=80-120, color='#000000', font='Montserrat "
        "ExtraBold' or 'Helvetica Bold', position='bottom 10% of canvas, "
        "centered', tracking='0.15em'. color_palette is monochrome: "
        "#000000, #333333, #666666. fonts from Canva's built-in library: "
        "Montserrat or Helvetica families. alignment_zone specifies where "
        "the headline/subtext stack sits (centered horizontally, starting "
        "at 30-40% from top).\n\n"
        "4. direct_action_tip — an ordered array of 2-5 steps. Step 1 "
        "(PRIMARY) describes the blank-canvas text-only build in order: "
        "set background #FFFFFF, add headline, add subtext, add structural "
        "rules, add giant PORTFOLIO footer. NO stock library steps, NO "
        "template steps, NO photo steps. Remaining steps are manual Canva "
        "text-only UI actions."
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
