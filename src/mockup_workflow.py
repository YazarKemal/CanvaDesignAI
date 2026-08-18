"""Interactive mockup art-direction workflow for CaVDesign.

This layer sits on top of :mod:`src.mockup_engine` and turns the engine's
one-shot six-scene output into a guided, art-director-style conversation.

The workflow distinguishes two different ideas:

- **Creative directions** — 2-4 artwork-specific art-direction concepts (e.g.
  "Moody Collector Apartment", "Minimal Black Gallery") inferred from the
  analysis. Exactly one is recommended.
- **Listing roles** — the six mockup/listing types (hero, lifestyle, close_up,
  scale, alternative_scene, clean_product) that say *where* the artwork goes in
  an Etsy listing.

Flow:

1. ``analyze_artwork`` — analyse the artwork, infer creative directions, ask
   3-5 category- and mood-aware clarifying questions.
2. ``refine_strategy`` — apply the user's selected creative direction + answers
   (+ optional listing role) into a refined art-direction strategy.
3. ``build_final_prompt`` — combine the artwork analysis, refined creative
   direction, requested listing role, deterministic category archetype and
   preservation constraints into the final image-generation prompt.

No image is rendered here. The workflow is a prompt strategist / art director;
every step is deterministic apart from the single multimodal vision call
performed inside ``analyze_artwork`` (reused from the engine).
"""

from __future__ import annotations

from typing import Any

from src.mockup_engine import (
    MOCKUP_TYPES,
    NEGATIVE_SUFFIX,
    SCENE_ARCHETYPES,
    MockupEngineError,
    _archetype_for,
    _inject_preservation,
    generate_mockup_set,
)

# Each listing role maps to a recommended usage on Etsy.
USAGE_MAP = {
    "hero": "Etsy hero image / first listing image",
    "lifestyle": "Lifestyle listing image (second image)",
    "close_up": "Close-up detail image (material / finish)",
    "scale": "Scale / size-context image",
    "alternative_scene": "Alternative secondary listing image",
    "clean_product": "Clean product-only listing image",
}

PRESERVATION_NOTES = (
    "Do not redesign or repaint the artwork.",
    "Do not alter, rewrite or misspell any text/typography.",
    "Do not change the artwork's colours.",
    "Do not reinterpret faces or objects in the artwork.",
    "Only place the unchanged original design into the mockup scene; apply only the "
    "physically necessary perspective for realistic placement.",
)


def _question(key: str, question: str, options: list[str]) -> dict[str, Any]:
    return {"id": key, "question": question, "options": options, "key": key}


# --------------------------------------------------------------------------- #
# Creative direction concepts, seeded per product category.
# --------------------------------------------------------------------------- #

# Each seed carries a short mood descriptor and keywords used to pick which
# concept best matches the artwork's inferred mood/style.
CREATIVE_SEEDS: dict[str, list[dict[str, Any]]] = {
    "wall_art": [
        {"id": "moody_collector", "title": "Moody Collector Apartment", "mood": "cinematic, dramatic", "environment": "dark styled apartment with a curated gallery wall", "presentation_style": "premium framed, low-key lighting", "mood_keywords": ["moody", "dark", "cinematic", "dramatic", "collector", "noir", "premium"]},
        {"id": "minimal_gallery", "title": "Minimal Black Gallery", "mood": "minimal, clean", "environment": "clean black gallery wall", "presentation_style": "minimal, high-contrast, unframed", "mood_keywords": ["minimal", "clean", "gallery", "bright", "light", "modern", "simple"]},
        {"id": "boutique_interior", "title": "Boutique Home Interior", "mood": "warm, editorial", "environment": "bright boutique home interior", "presentation_style": "editorial, soft daylight, framed", "mood_keywords": ["bright", "warm", "editorial", "cozy", "colorful", "home", "lived"]},
    ],
    "poster": [
        {"id": "boutique_cinema_lobby", "title": "Boutique Cinema Lobby", "mood": "cinematic, dramatic", "environment": "dim cinema lobby with marquee light", "presentation_style": "cinematic, dramatic, framed poster", "mood_keywords": ["dark", "cinematic", "dramatic", "noir", "moody", "film", "poster"]},
        {"id": "clean_gallery", "title": "Clean Gallery Frame", "mood": "minimal, clean", "environment": "clean bright gallery wall", "presentation_style": "minimal framed, bright light", "mood_keywords": ["minimal", "clean", "gallery", "bright", "modern", "simple"]},
        {"id": "editorial_home", "title": "Editorial Home Studio", "mood": "warm, editorial", "environment": "styled home studio wall", "presentation_style": "editorial, soft daylight", "mood_keywords": ["bright", "warm", "editorial", "cozy", "home"]},
    ],
    "printable": [
        {"id": "cozy_print_studio", "title": "Cozy Print Studio", "mood": "warm, cozy", "environment": "warm desk with a framed print", "presentation_style": "editorial, warm light, framed", "mood_keywords": ["warm", "cozy", "editorial", "home", "bright"]},
        {"id": "minimal_flatlay", "title": "Minimal Flat-Lay", "mood": "minimal, clean", "environment": "clean bright flat-lay surface", "presentation_style": "minimal flat-lay, even light", "mood_keywords": ["minimal", "clean", "bright", "modern", "simple"]},
        {"id": "boho_home", "title": "Boho Home Decor", "mood": "colorful, bohemian", "environment": "bright bohemian interior", "presentation_style": "colorful, styled, warm", "mood_keywords": ["colorful", "bohemian", "warm", "home", "bright", "playful"]},
    ],
    "invitation": [
        {"id": "elegant_ceremony", "title": "Elegant Ceremony Suite", "mood": "elegant, romantic", "environment": "soft floral tabletop", "presentation_style": "elegant flat-lay, soft light", "mood_keywords": ["elegant", "warm", "romantic", "classic", "refined"]},
        {"id": "modern_minimal", "title": "Modern Minimal Stationery", "mood": "minimal, modern", "environment": "crisp clean flat-lay", "presentation_style": "minimal, crisp, bright", "mood_keywords": ["minimal", "modern", "clean", "crisp", "simple"]},
        {"id": "rustic_garden", "title": "Rustic Garden Party", "mood": "rustic, natural", "environment": "garden outdoor table", "presentation_style": "natural, warm, garden", "mood_keywords": ["rustic", "natural", "garden", "warm", "colorful"]},
    ],
    "book_cover": [
        {"id": "literary_nook", "title": "Literary Reading Nook", "mood": "cozy, literary", "environment": "cozy bookshelf setting", "presentation_style": "editorial, warm light", "mood_keywords": ["cozy", "literary", "warm", "editorial", "classic"]},
        {"id": "minimal_shelf", "title": "Minimal Bookshelf", "mood": "minimal, clean", "environment": "clean minimalist shelf", "presentation_style": "minimal, modern, bright", "mood_keywords": ["minimal", "clean", "modern", "bright", "simple"]},
        {"id": "editorial_studio", "title": "Editorial Cover Studio", "mood": "editorial, dramatic", "environment": "studio cover presentation", "presentation_style": "premium, dramatic, studio", "mood_keywords": ["editorial", "premium", "dramatic", "dark", "cinematic"]},
    ],
    "journal_planner": [
        {"id": "productive_desk", "title": "Productive Morning Desk", "mood": "bright, productive", "environment": "bright desk with coffee", "presentation_style": "clean, bright, organized", "mood_keywords": ["productive", "bright", "clean", "organized", "minimal"]},
        {"id": "cozy_study", "title": "Cozy Study Corner", "mood": "cozy, warm", "environment": "warm study nook", "presentation_style": "warm, editorial", "mood_keywords": ["cozy", "warm", "study", "home"]},
        {"id": "minimal_flatlay", "title": "Minimal Flat-Lay", "mood": "minimal, clean", "environment": "clean flat-lay", "presentation_style": "minimal, bright", "mood_keywords": ["minimal", "clean", "bright", "modern"]},
    ],
    "sticker": [
        {"id": "playful_desk", "title": "Playful Desk Flat-Lay", "mood": "playful, bright", "environment": "bright playful desk", "presentation_style": "colorful flat-lay, bright light", "mood_keywords": ["playful", "bright", "fun", "colorful", "cute"]},
        {"id": "lifestyle_applied", "title": "Lifestyle Applied", "mood": "casual, lifestyle", "environment": "stickers on laptop, bottle and journal", "presentation_style": "lifestyle, casual, real use", "mood_keywords": ["lifestyle", "casual", "fun", "colorful", "bright"]},
        {"id": "minimal_sheet", "title": "Minimal Sticker Sheet", "mood": "minimal, clean", "environment": "clean minimal sheet", "presentation_style": "minimal, bright", "mood_keywords": ["minimal", "clean", "modern", "simple"]},
    ],
    "apparel_graphic": [
        {"id": "street_style", "title": "Street Style Edit", "mood": "bold, urban", "environment": "urban street-style backdrop", "presentation_style": "bold, trendy, styled", "mood_keywords": ["street", "urban", "bold", "trendy", "edgy", "casual"]},
        {"id": "clean_studio", "title": "Clean Studio Garment", "mood": "clean, minimal", "environment": "studio garment flat-lay", "presentation_style": "clean studio, even light", "mood_keywords": ["clean", "studio", "minimal", "modern", "bright"]},
        {"id": "lifestyle_wear", "title": "Lifestyle Worn", "mood": "lifestyle, casual", "environment": "model in a styled setting", "presentation_style": "lifestyle, worn, natural", "mood_keywords": ["lifestyle", "casual", "worn", "bold", "bright"]},
    ],
    "phone_wallpaper": [
        {"id": "minimal_device", "title": "Minimal Device Hero", "mood": "minimal, clean", "environment": "clean minimal background", "presentation_style": "clean device, bright light", "mood_keywords": ["minimal", "clean", "bright", "modern", "simple"]},
        {"id": "lifestyle_desk", "title": "Lifestyle Desk Scene", "mood": "warm, lifestyle", "environment": "styled desk with the phone", "presentation_style": "lifestyle, warm, casual", "mood_keywords": ["lifestyle", "desk", "warm", "casual", "bright"]},
        {"id": "dark_moody_screen", "title": "Dark Moody Screen", "mood": "dark, cinematic", "environment": "dim ambient scene with subtle screen glow", "presentation_style": "dark, cinematic, moody", "mood_keywords": ["dark", "moody", "dramatic", "cinematic", "noir"]},
    ],
    "album_art": [
        {"id": "vinyl_listening", "title": "Vinyl Listening Room", "mood": "atmospheric, moody", "environment": "record player moody setup", "presentation_style": "atmospheric, dramatic, editorial", "mood_keywords": ["moody", "cinematic", "atmospheric", "dark", "dramatic", "retro"]},
        {"id": "clean_cover", "title": "Clean Cover Studio", "mood": "clean, minimal", "environment": "studio cover presentation", "presentation_style": "clean studio, even light", "mood_keywords": ["clean", "studio", "minimal", "modern", "bright"]},
        {"id": "streaming_screen", "title": "Streaming Screen", "mood": "digital, modern", "environment": "device streaming screen", "presentation_style": "digital, modern, bright", "mood_keywords": ["digital", "clean", "modern", "bright", "minimal"]},
    ],
    "generic": [
        {"id": "editorial_feature", "title": "Editorial Feature", "mood": "editorial, premium", "environment": "styled editorial presentation", "presentation_style": "editorial, premium, polished", "mood_keywords": ["editorial", "premium", "dramatic", "dark", "refined"]},
        {"id": "minimal_clean", "title": "Minimal Clean", "mood": "minimal, clean", "environment": "clean neutral scene", "presentation_style": "minimal, bright", "mood_keywords": ["minimal", "clean", "bright", "modern", "simple"]},
        {"id": "warm_lifestyle", "title": "Warm Lifestyle", "mood": "warm, lifestyle", "environment": "warm lived-in scene", "presentation_style": "warm, lifestyle, approachable", "mood_keywords": ["warm", "lifestyle", "cozy", "bright", "home"]},
    ],
}

# Category-aware clarifying questions. React to the product category; a
# mood/style-aware question is appended when the analysis supports it.
QUESTION_BANK: dict[str, list[dict[str, Any]]] = {
    "wall_art": [
        _question("framing", "Framed or unframed?", ["Framed", "Unframed"]),
        _question("tone", "Premium editorial or minimal clean?", ["Premium editorial", "Minimal clean"]),
        _question("setting", "Realistic home interior or studio scene?", ["Home interior", "Studio scene"]),
        _question("audience", "Collector-style display or casual decor?", ["Collector-style", "Casual decor"]),
    ],
    "poster": [
        _question("framing", "Framed or unframed?", ["Framed", "Unframed"]),
        _question("tone", "Premium editorial or minimal clean?", ["Premium editorial", "Minimal clean"]),
        _question("setting", "Realistic home interior or studio scene?", ["Home interior", "Studio scene"]),
        _question("audience", "Collector-style display or casual decor?", ["Collector-style", "Casual decor"]),
    ],
    "printable": [
        _question("framing", "Presented as a framed print or unframed sheet?", ["Framed", "Unframed"]),
        _question("tone", "Premium editorial or minimal clean?", ["Premium editorial", "Minimal clean"]),
        _question("setting", "Flat-lay tabletop or wall scene?", ["Flat-lay tabletop", "Wall scene"]),
    ],
    "invitation": [
        _question("style", "Elegant classic or modern minimal?", ["Elegant classic", "Modern minimal"]),
        _question("setting", "Flat-lay or hand-held invitation?", ["Flat-lay", "Hand-held"]),
        _question("tone", "Warm romantic or crisp neutral?", ["Warm romantic", "Crisp neutral"]),
    ],
    "book_cover": [
        _question("format", "Hardcover or paperback presentation?", ["Hardcover", "Paperback"]),
        _question("setting", "Cozy reading scene or clean studio?", ["Cozy reading scene", "Clean studio"]),
        _question("lighting", "Warm ambient or bright daylight?", ["Warm ambient", "Bright daylight"]),
    ],
    "journal_planner": [
        _question("format", "Open in use or closed cover?", ["Open in use", "Closed cover"]),
        _question("setting", "Styled desk or minimal flat-lay?", ["Styled desk", "Minimal flat-lay"]),
    ],
    "sticker": [
        _question("surface", "Which surfaces should stickers appear on?", ["Laptop", "Water bottle", "Journal", "Mixed"]),
        _question("finish", "Glossy or matte vinyl?", ["Glossy", "Matte"]),
    ],
    "apparel_graphic": [
        _question("presentation", "On model or flat-lay garment?", ["On model", "Flat-lay garment"]),
        _question("setting", "Studio or street-style context?", ["Studio", "Street-style"]),
    ],
    "phone_wallpaper": [
        _question("device", "Portrait phone or tablet / landscape?", ["Portrait phone", "Tablet / landscape"]),
        _question("background", "Clean minimal background or styled lifestyle scene?", ["Clean minimal", "Lifestyle scene"]),
        _question("screen", "Home screen or lock screen focus?", ["Home screen", "Lock screen"]),
    ],
    "album_art": [
        _question("format", "Vinyl sleeve or streaming screen?", ["Vinyl sleeve", "Streaming screen"]),
        _question("setting", "Listening setup or clean studio?", ["Listening setup", "Clean studio"]),
    ],
    "generic": [
        _question("framing", "Framed or unframed?", ["Framed", "Unframed"]),
        _question("tone", "Premium editorial or minimal clean?", ["Premium editorial", "Minimal clean"]),
        _question("setting", "Realistic scene or studio scene?", ["Realistic scene", "Studio scene"]),
        _question("audience", "Collector-style display or casual decor?", ["Collector-style", "Casual decor"]),
    ],
}

# Deterministic refinement: (question key) -> ordered (option-substring, field overrides).
REFINEMENT_RULES: dict[str, list[tuple[str, dict[str, str]]]] = {
    "framing": [
        ("framed", {"surface_or_frame": "exact artwork in a slim frame", "composition": "centered with the frame visible"}),
        ("unframed", {"surface_or_frame": "exact artwork mounted unframed edge-to-edge", "composition": "centered, artwork fills the surface"}),
    ],
    "tone": [
        ("premium", {"styling_notes": "premium editorial styling", "realism_notes": "polished, high-end finish"}),
        ("minimal", {"styling_notes": "minimal clean styling", "realism_notes": "clean and uncluttered"}),
        ("sophisticated", {"styling_notes": "editorial sophisticated styling"}),
        ("approachable", {"styling_notes": "approachable and inviting styling"}),
        ("warm", {"styling_notes": "warm romantic styling", "lighting": "soft warm romantic light"}),
        ("crisp", {"styling_notes": "crisp neutral styling"}),
        ("cozy", {"styling_notes": "cozy inviting styling"}),
        ("productive", {"styling_notes": "bright productive styling", "lighting": "bright clear daylight"}),
        ("bold", {"styling_notes": "bold vibrant styling"}),
        ("muted", {"styling_notes": "muted minimal styling"}),
    ],
    "setting": [
        ("home interior", {"environment": "realistic styled home interior"}),
        ("studio", {"environment": "clean studio scene"}),
        ("flat-lay tabletop", {"environment": "styled tabletop flat-lay"}),
        ("wall scene", {"environment": "wall display scene"}),
        ("flat-lay", {"environment": "elegant flat-lay"}),
        ("hand-held", {"environment": "hand-held setting"}),
        ("reading scene", {"environment": "cozy reading scene"}),
        ("styled desk", {"environment": "styled desk setting"}),
        ("minimal flat-lay", {"environment": "minimal flat-lay"}),
        ("playful bright", {"environment": "playful bright flat-lay"}),
        ("street-style", {"environment": "street-style outdoor setting"}),
        ("lifestyle scene", {"environment": "styled lifestyle scene"}),
        ("listening setup", {"environment": "record listening setup"}),
        ("realistic scene", {"environment": "realistic styled scene"}),
    ],
    "lighting": [
        ("dramatic", {"lighting": "dramatic moody lighting"}),
        ("bright natural", {"lighting": "bright natural light"}),
        ("bright airy", {"lighting": "bright airy light"}),
        ("soft warm", {"lighting": "soft warm light"}),
        ("bright clean", {"lighting": "bright clean light"}),
        ("warm ambient", {"lighting": "warm ambient light"}),
        ("bright daylight", {"lighting": "bright daylight"}),
        ("bright clear", {"lighting": "bright clear daylight"}),
        ("bright", {"lighting": "bright clean light"}),
        ("moody dramatic", {"lighting": "moody dramatic light"}),
        ("dark moody", {"lighting": "dark moody ambient light"}),
    ],
    "audience": [
        ("collector", {"styling_notes": "collector-style premium display"}),
        ("casual", {"styling_notes": "casual approachable decor"}),
    ],
    "style": [
        ("elegant classic", {"styling_notes": "elegant classic styling", "realism_notes": "refined and timeless"}),
        ("modern minimal", {"styling_notes": "modern minimal styling", "environment": "clean minimal setting"}),
    ],
    "format": [
        ("hardcover", {"surface_or_frame": "hardcover binding with matte cover", "environment": "cozy reading setting"}),
        ("paperback", {"surface_or_frame": "paperback cover with soft-touch finish", "environment": "cozy reading setting"}),
        ("open in use", {"composition": "open to show the layout in use", "environment": "styled desk setting"}),
        ("closed", {"composition": "closed cover centered", "environment": "styled desk setting"}),
        ("vinyl sleeve", {"surface_or_frame": "vinyl sleeve cover", "environment": "record listening setup"}),
        ("streaming", {"surface_or_frame": "streaming screen", "environment": "clean device presentation"}),
    ],
    "surface": [
        ("laptop", {"environment": "flat-lay on a laptop lid", "artwork_placement": "stickers placed on the laptop"}),
        ("water bottle", {"environment": "flat-lay beside a water bottle", "artwork_placement": "stickers applied to the bottle"}),
        ("journal", {"environment": "flat-lay on an open journal", "artwork_placement": "stickers on the journal"}),
        ("mixed", {"environment": "flat-lay with mixed surfaces", "artwork_placement": "stickers on multiple surfaces"}),
    ],
    "finish": [
        ("glossy", {"surface_or_frame": "glossy vinyl finish"}),
        ("matte", {"surface_or_frame": "matte vinyl finish"}),
    ],
    "presentation": [
        ("on model", {"environment": "styled setting with a model wearing the garment", "composition": "garment on model, graphic clearly visible"}),
        ("flat-lay", {"environment": "flat-lay garment presentation", "composition": "garment flat, graphic centered"}),
    ],
    "device": [
        ("portrait", {"surface_or_frame": "portrait smartphone OLED screen", "composition": "portrait phone centered"}),
        ("tablet", {"surface_or_frame": "tablet screen in landscape", "composition": "tablet centered"}),
    ],
    "background": [
        ("clean minimal", {"environment": "clean minimal background"}),
        ("lifestyle", {"environment": "styled lifestyle scene"}),
    ],
    "screen": [
        ("home screen", {"composition": "home screen layout with app icons visible"}),
        ("lock screen", {"composition": "lock screen showing the full wallpaper, clock visible"}),
    ],
    "mood_tone": [
        ("darker cinematic", {"lighting": "darker cinematic lighting", "styling_notes": "dark cinematic styling"}),
        ("cleaner gallery", {"environment": "clean gallery", "styling_notes": "clean gallery styling", "lighting": "bright even light"}),
        ("clean gallery", {"environment": "clean gallery", "styling_notes": "clean gallery styling", "lighting": "bright even light"}),
        ("warm home", {"environment": "warm home setting", "lighting": "warm natural light", "styling_notes": "warm inviting styling"}),
    ],
}


# --------------------------------------------------------------------------- #
# Creative direction inference.
# --------------------------------------------------------------------------- #


def _analysis_text(analysis: dict[str, Any]) -> str:
    parts = [
        " ".join(analysis.get("mood", [])),
        analysis.get("visual_style", ""),
        analysis.get("content_summary", ""),
        analysis.get("product_category", ""),
    ]
    return " ".join(parts).lower()


def _rationale(seed: dict[str, Any], category_label: str, analysis: dict[str, Any]) -> str:
    palette = analysis.get("dominant_colors") or []
    palette_phrase = ", ".join(palette) if palette else "distinctive"
    visual_style = analysis.get("visual_style") or "distinctive"
    mood_phrase = " and ".join(analysis.get("mood", [])) or seed["mood"]
    return (
        f"Strong fit for this {category_label}: the artwork's {visual_style} style "
        f"and {mood_phrase} mood support a {seed['presentation_style']} presentation, "
        f"using a palette of {palette_phrase}."
    )


def creative_directions_from(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Infer 2-4 artwork-specific creative directions; mark exactly one recommended."""
    category = analysis.get("product_category", "generic")
    seeds = CREATIVE_SEEDS.get(category, CREATIVE_SEEDS["generic"])
    category_label = SCENE_ARCHETYPES.get(category, SCENE_ARCHETYPES["generic"])["label"]
    text = _analysis_text(analysis)

    def score(seed: dict[str, Any]) -> int:
        return sum(1 for keyword in seed["mood_keywords"] if keyword in text)

    best_index = max(range(len(seeds)), key=lambda i: (score(seeds[i]), -i))

    directions: list[dict[str, Any]] = []
    for i, seed in enumerate(seeds):
        directions.append(
            {
                "id": seed["id"],
                "title": seed["title"],
                "rationale": _rationale(seed, category_label, analysis),
                "environment": seed["environment"],
                "mood": seed["mood"],
                "presentation_style": seed["presentation_style"],
                "recommended": i == best_index,
            }
        )
    return directions


def _mood_question(analysis: dict[str, Any]) -> dict[str, Any] | None:
    text = _analysis_text(analysis)
    if any(keyword in text for keyword in ("dark", "moody", "noir", "cinematic", "dramatic")):
        return _question(
            "mood_tone",
            "For this design I'd suggest a dark, dramatic interior. "
            "Would you prefer darker cinematic or a cleaner gallery-style look?",
            ["Darker cinematic", "Cleaner gallery-style"],
        )
    if any(keyword in text for keyword in ("bright", "minimal", "clean", "modern")):
        return _question(
            "mood_tone",
            "For this design a clean, bright look suits. "
            "Would you prefer a clean gallery or a warm home setting?",
            ["Clean gallery", "Warm home"],
        )
    return None


def clarifying_questions_for(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Return 3-5 category- and mood-aware clarifying questions."""
    category = analysis.get("product_category", "generic")
    questions = QUESTION_BANK.get(category, QUESTION_BANK["generic"])[:5]
    mood_question = _mood_question(analysis)
    if mood_question is not None and len(questions) < 5:
        questions = questions[:4] + [mood_question]
    return questions


def _find_direction(analysis: dict[str, Any], selected_direction: str) -> dict[str, Any]:
    for direction in analysis.get("recommended_directions", []) or []:
        if direction.get("id") == selected_direction:
            return direction
    raise MockupEngineError(f"Unknown creative direction: {selected_direction}")


# --------------------------------------------------------------------------- #
# Step 1: analyze.
# --------------------------------------------------------------------------- #


def analyze_artwork(
    image_bytes: bytes,
    mime_type: str,
    *,
    marketplace: str = "Etsy",
    product_type_hint: str = "",
    audience_hint: str = "",
    creative_direction: str = "",
    vision_client: Any = None,
) -> dict[str, Any]:
    """Analyse artwork, infer creative directions and ask clarifying questions."""
    engine_result = generate_mockup_set(
        image_bytes,
        mime_type,
        marketplace=marketplace,
        product_type_hint=product_type_hint,
        audience_hint=audience_hint,
        creative_direction=creative_direction,
        vision_client=vision_client,
    )

    asset_analysis = engine_result["asset_analysis"]
    directions = creative_directions_from(asset_analysis)
    best = next((d for d in directions if d["recommended"]), directions[0] if directions else None)

    result: dict[str, Any] = dict(engine_result)
    result["recommended_directions"] = directions
    result["best_recommendation"] = (
        {
            "id": best["id"],
            "title": best["title"],
            "message": (
                f"I think the {best['title']} direction is the strongest fit for this "
                f"artwork because its {best['mood']} character supports a "
                f"{best['presentation_style']} presentation. Do you agree?"
            ),
        }
        if best
        else None
    )
    result["clarification_needed"] = True
    result["clarifying_questions"] = clarifying_questions_for(asset_analysis)
    return result


# --------------------------------------------------------------------------- #
# Step 2: refine.
# --------------------------------------------------------------------------- #


def _apply_refinements(
    fields: dict[str, str], answers: dict[str, Any]
) -> tuple[dict[str, str], dict[str, str]]:
    applied: dict[str, str] = {}
    for key, answer in answers.items():
        if answer is None:
            continue
        lowered = str(answer).lower()
        for substring, overrides in REFINEMENT_RULES.get(key, []):
            if substring in lowered:
                fields.update(overrides)
                applied[key] = str(answer)
                break
    return fields, applied


def _remaining_questions(
    analysis: dict[str, Any], answers: dict[str, Any]
) -> list[dict[str, Any]]:
    answered = {str(k) for k in answers if answers.get(k) not in (None, "", False)}
    asset_analysis = analysis.get("asset_analysis") or analysis
    return [q for q in clarifying_questions_for(asset_analysis) if q["key"] not in answered]


def refine_strategy(
    analysis: dict[str, Any],
    selected_direction: str,
    answers: dict[str, Any] | None = None,
    listing_role: str = "hero",
) -> dict[str, Any]:
    """Refine a strategy from the selected creative direction + answers + role."""
    answers = answers or {}
    if listing_role not in MOCKUP_TYPES:
        raise MockupEngineError(f"Unknown listing role: {listing_role}")

    direction = _find_direction(analysis, selected_direction)
    category = analysis.get("asset_analysis", {}).get("product_category", "generic")
    archetype = _archetype_for(category, listing_role)

    fields: dict[str, str] = {
        "environment": direction["environment"],
        "surface_or_frame": archetype["surface_or_frame"],
        "lighting": archetype["lighting"],
        "camera": archetype["camera"],
        "composition": archetype["composition"],
        "artwork_placement": archetype["artwork_placement"],
        "realism_notes": archetype["realism_notes"],
    }
    fields["styling_notes"] = f"{direction['title']}: {direction['presentation_style']}"
    fields, applied = _apply_refinements(fields, answers)

    return {
        "direction": {"id": direction["id"], "title": direction["title"]},
        "listing_role": listing_role,
        "category": category,
        "presentation_mode": (
            analysis.get("asset_analysis", {}).get("presentation_mode", "hybrid")
        ),
        "creative_mood": direction["mood"],
        "scene_direction": archetype["direction"],
        "environment": fields["environment"],
        "surface_or_frame": fields["surface_or_frame"],
        "lighting": fields["lighting"],
        "camera": fields["camera"],
        "composition": fields["composition"],
        "artwork_placement": fields["artwork_placement"],
        "realism_notes": fields["realism_notes"],
        "styling_notes": fields["styling_notes"],
        "applied_answers": applied,
        "remaining_questions": _remaining_questions(analysis, answers),
    }


# --------------------------------------------------------------------------- #
# Step 3: generate.
# --------------------------------------------------------------------------- #


def _answers_to_clause(answers: dict[str, Any]) -> str:
    parts = [f"{key}={value}" for key, value in answers.items() if value not in (None, "")]
    return "; ".join(parts)


def build_final_prompt(
    analysis: dict[str, Any],
    selected_direction: str,
    listing_role: str = "hero",
    answers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Emit the final prompt for a creative direction + listing role.

    Combines the uploaded-artwork analysis, the refined creative direction, the
    requested listing role, the deterministic category archetype and the
    preservation constraints.
    """
    answers = answers or {}
    if listing_role not in MOCKUP_TYPES:
        raise MockupEngineError(f"Unknown listing role: {listing_role}")

    direction = _find_direction(analysis, selected_direction)
    category = analysis.get("asset_analysis", {}).get("product_category", "generic")

    chosen = next(
        (m for m in analysis.get("mockups", []) if m.get("type") == listing_role),
        None,
    )
    if chosen is not None:
        prompt = _inject_preservation(chosen.get("prompt", ""))
        negative_prompt = chosen.get("negative_prompt", "")
    else:
        archetype = _archetype_for(category, listing_role)
        base = (
            f"Photorealistic {listing_role.replace('_', ' ')} mockup: "
            f"{archetype['direction']}. Match the artwork's style and lighting."
        )
        prompt = _inject_preservation(base)
        negative_prompt = NEGATIVE_SUFFIX

    creative_clause = (
        f"Creative direction: {direction['title']} ({direction['mood']}; "
        f"{direction['presentation_style']}; {direction['environment']})."
    )
    prompt = f"{prompt} {creative_clause}".strip()

    if answers:
        clause = _answers_to_clause(answers)
        if clause:
            prompt = f"{prompt} Client preferences: {clause}."

    return {
        "direction": {"id": direction["id"], "title": direction["title"]},
        "listing_role": listing_role,
        "category": category,
        "final_prompt": prompt,
        "negative_prompt": negative_prompt,
        "preservation_notes": list(PRESERVATION_NOTES),
        "recommended_usage": USAGE_MAP.get(listing_role, "Listing image"),
    }
