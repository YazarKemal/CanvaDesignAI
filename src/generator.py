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
    "canva_keywords": ["editorial grid layout", "low-detail negative space 40%", "matte uncoated texture"],
    # -- Layer 1: Background (stock photo or gradient — NO AI generation) ----
    "raster_background": {
        "magic_media_prompt": (
            "A Canva stock photo search query for: modern specialty coffee shop interior, "
            "warm terracotta and uncoated cream matte palette, top-down flat lay of espresso cup "
            "beside an open notebook on a warm linen-textured oak table, 40% deliberate "
            "low-detail negative space at the top for typography overlay, soft natural "
            "window light, Behance editorial composition. "
            "Use Canva Stock Library — do NOT generate with AI."
        ),
        "negative_prompt": (
            "no AI-generated imagery, no text, no numbers, no letters, "
            "no watermark, no logo, cluttered composition, harsh oversaturation, "
            "busy background, high-detail fill, pattern overload"
        ),
        "layout_style": "Editorial",
    },
    # -- Layer 2: Vector Elements (native Canva shapes) ----------------------
    "vector_elements": {
        "thin_divider": (
            "horizontal hairline rule at 0.5 px weight in #D4A373 at 60% opacity, "
            "spanning 40% of canvas width, centered, positioned between subtext and "
            "micro-labels. Use Canva's built-in line shape."
        ),
        "accent_frame": (
            "thin rectangular border frame in muted brass #B8936E at 1 px weight, "
            "inset 48 px from all canvas edges. Use Canva's built-in rectangle shape "
            "with no fill, stroke only."
        ),
    },
    # -- Layer 3: Native Typography (Behance 2026 editorial hierarchy) --------
    "native_typography": {
        "headline": "Grand Opening",
        "subtext": "Freshly roasted, every morning.",
        "headline_pt": 72,
        "subtext_pt": 18,
        "color_palette": ["#3B2A1E", "#B8936E", "#E8DDD0", "#8B9D6B", "#D4C5B9"],
        "fonts": {"headline_font": "Montserrat Bold", "body_font": "Cormorant Garamond Regular"},
        "alignment_zone": "top 30% of canvas, left-aligned with 48 px left margin, vertical stack",
        "micro_tags": {
            "volume_line": "VOL.01 / 2026",
            "category_line": "EDITORIAL BRANDING",
            "origin_line": "CRAFTED IN TURKEY",
            "micro_pt": 9,
            "micro_color": "#B8936E",
            "micro_font": "Inter Regular",
            "micro_spacing": "24 px below subtext, separated by thin divider rule",
        },
    },
    "direct_action_tip": [
        "PRIMARY (Canva Native Layout Engine): Build this Behance-editorial design with Canva's native tools — (1) Search Canva Stock Library for 'modern coffee shop interior warm terracotta matte' and set the photo as full-bleed background at 1:1 (1080x1080), ensuring 40% low-detail negative space at the top. (2) Add a Heading text box at top 30%, left-aligned: type 'Grand Opening', set Montserrat Bold 72 pt, #3B2A1E. (3) Add Subheading below: 'Freshly roasted, every morning.', Cormorant Garamond Regular 18 pt, #B8936E. (4) Insert a thin horizontal line (0.5 px, #B8936E at 60% opacity) as divider. (5) Add three micro-label text boxes below the divider in Inter Regular 9 pt, #B8936E: 'VOL.01 / 2026', 'EDITORIAL BRANDING', 'CRAFTED IN TURKEY' — each on its own line with 4 px spacing. (6) Insert a thin rectangular border frame inset 48 px from all edges in muted brass #B8936E at 1 px stroke, no fill.",
        "ALTERNATIVE (Step-by-step manual): Open Canva → Create Design → 1080x1080. Go to Photos tab and search 'coffee shop interior matte editorial', drag a stock photo to fill the canvas. Add a Heading text box at top 30% left-aligned, type 'Grand Opening', set Montserrat Bold 72 pt. Add subtext below at 18 pt. Insert a thin line shape as divider. Add three small text boxes for micro-labels at 9 pt. Insert a rectangle shape with no fill, 1 px stroke for the border frame.",
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
            "absolute precedence. MUST reserve at least 40% deliberate low-detail "
            "negative space at the text_zone location — describe the background as "
            "having a large uncluttered zone (solid colour, soft texture, or "
            "gentle gradient, NOT busy pattern or high-detail fill). "
            "negative_prompt: MUST always contain 'no AI-generated imagery, "
            "no text, no numbers, no letters, busy background, high-detail fill' "
            "as the first terms. layout_style: one of the knowledge-base "
            "layout_styles. NEVER describe AI generation parameters."
        )
    else:
        l1_rule = (
            "1. raster_background — Layer 1 (Background: stock photo or native "
            "gradient). magic_media_prompt: a Canva Stock Library search query "
            "OR a gradient definition (subject -> setting -> composition -> "
            "lighting -> color/mood -> quality descriptors). MUST reserve at "
            "least 40% deliberate low-detail negative space at the text_zone "
            "location — describe the background as having a large uncluttered "
            "zone. negative_prompt: MUST always contain 'no AI-generated imagery, "
            "no text, no numbers, no letters, busy background, high-detail fill' "
            "as the first terms. layout_style: one of the knowledge-base "
            "layout_styles. NEVER describe AI generation parameters."
        )

    return (
        "Sen Claude degil, DeepSeek tabanli bir Canva Prompt Muhendisisin "
        "(Canva Prompt Engineer) — bir otomasyon motorunun ikinci asamasisin. "
        "Your job: turn the Architect's design brief into ONE Canva automation "
        "card using the HYBRID SPLIT LAYER architecture at BEHANCE PORTFOLIO "
        "2026 editorial standard — background (stock photo / native gradient), "
        "vector elements (editorial frames, thin rules, negative-space accents), "
        "and typography (Canva text boxes with radical point-size contrast).\n\n"
        "HARD RULES:\n"
        "- DO NOT use Magic Media or AI image generation. All backgrounds "
        "must be Canva Stock Library search queries or native CSS gradients. "
        "All visual elements must be native Canva shapes. All typography must "
        "use Canva's built-in font boxes.\n"
        "- target_tool MUST be 'Canva Native Layout Engine'.\n"
        "- BEHANCE 2026 EDITORIAL STANDARD — every card must meet these:\n"
        "  a. 40% LOW-DETAIL NEGATIVE SPACE: Layer 1 background MUST describe "
        "at least 40% of the canvas as deliberate low-detail negative space "
        "(uncluttered, solid or softly textured, no busy elements) at the "
        "text_zone location. The negative_prompt MUST exclude 'busy background', "
        "'high-detail fill', 'pattern overload'.\n"
        "  b. RADICAL POINT-SIZE CONTRAST: headline_pt MUST be 64-72 pt; "
        "subtext_pt MUST be 16-20 pt; micro_tags.micro_pt MUST be 8-10 pt. "
        "The ratio between headline and micro-label must be at least 6:1.\n"
        "  c. MICRO-METADATA IN LAYER 3: native_typography MUST include a "
        "micro_tags object with three editorial labels:\n"
        "    - volume_line: 'VOL.01 / 2026' (or current year)\n"
        "    - category_line: a 2-3 word editorial category (e.g. 'EDITORIAL "
        "BRANDING', 'VISUAL IDENTITY', 'CAFE CULTURE')\n"
        "    - origin_line: 'CRAFTED IN TURKEY' (or the brand's origin)\n"
        "    - micro_pt: 9, micro_color: one of the palette's muted tones, "
        "micro_font: 'Inter Regular' or brand body font at small size\n"
        "    - micro_spacing: positioned 24 px below subtext, separated by a "
        "thin divider rule\n"
        "  d. BEHANCE-LEVEL PALETTE: prefer matte/raw editorial tones — "
        "uncoated paper (#E8DDD0), warm linen (#D4C5B9), rich pistachio "
        "(#8B9D6B), muted brass (#B8936E), deep espresso (#3B2A1E). Palette "
        "must include at least ONE muted/warm neutral and ONE deep anchor.\n"
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
        "2. vector_elements — Layer 2 (Editorial Vector Accents: thin divider "
        "rules, hairline frames, subtle geometric accents). Avoid loud CTA "
        "buttons unless the brief explicitly requests them. Prefer: thin "
        "horizontal/vertical rules (0.5-1 px), rectangular border frames "
        "(1 px stroke, no fill, muted brass or warm neutral color), subtle "
        "corner brackets, or tiny geometric markers. These are Canva's "
        "BUILT-IN line/rectangle shapes — NOT AI-generated.\n\n"
        "3. native_typography — Layer 3 (Behance Editorial Typography Stack). "
        "headline (<=6 words, 64-72 pt, bold weight), subtext (<=14 words, "
        "16-20 pt, regular/light weight), micro_tags (3 editorial labels at "
        "8-10 pt in a muted tone, separated by a thin rule). color_palette "
        "(4-5 HEX codes including at least one matte neutral and one deep "
        "anchor from the Behance palette). fonts {{headline_font, body_font}} "
        "from native_typography lists. alignment_zone MUST specify exact "
        "coordinates (e.g. 'top 30%, left-aligned with 48 px margin') and "
        "reference the same text_zone location. The micro_tags object MUST "
        "be present with volume_line, category_line, origin_line, micro_pt, "
        "micro_color, micro_font, and micro_spacing.\n\n"
        "4. direct_action_tip — an ordered array of 2-5 steps. Step 1 "
        "(PRIMARY) is a unified Canva Native Layout Engine instruction block "
        "listing all values INLINE. Must include the micro-label text boxes "
        "and the editorial divider rule. Remaining steps are manual Canva UI "
        "steps."
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
