import json
from pathlib import Path

import pytest

from src.schema import PromptValidationError, validate_style_compliance
from src.style_presets import (
    StyleNotFoundError,
    as_prompt_block,
    list_styles,
    load_style,
    required_keywords,
)

EXPECTED_SLUGS = {
    "neo-grunge-streetwear",
    "holographic-glassmorphism",
    "corporate-dynamic-vector",
    "riso-print-editorial",
    "bauhaus-modernist-poster",
    "kodachrome-americana",
    "swiss-international-grid",
    "memphis-design-pop",
    "art-deco-metropolis",
    "brutalist-concrete",
    "ukiyo-e-woodblock",
    "psychedelic-fillmore",
    "vaporwave-arcade-dusk",
    "mid-century-modern-print",
    "art-nouveau-botanical",
    "constructivist-agitprop",
    "dutch-golden-age-still-life",
    "y2k-chrome-gloss",
    "warm-editorial-minimalist",
    "streamer-energetic-glitch",
    "formal-ceremonial-turkish",
    "utility-planner-ornamental",
}

# The 4 wave-3 presets: defined to close observed market gaps in the library
# (travel/lifestyle editorial, streamer/personal-brand glitch, culture-neutral
# ceremonial formal, and a utility-first ornamental planner).
WAVE3_SLUGS = {
    "warm-editorial-minimalist",
    "streamer-energetic-glitch",
    "formal-ceremonial-turkish",
    "utility-planner-ornamental",
}

# The 12 wave-2 presets: each anchored to a concrete art/design tradition and
# required to draw terms from the aesthetic_taxonomy lexicons.
WAVE2_SLUGS = {
    "swiss-international-grid",
    "memphis-design-pop",
    "art-deco-metropolis",
    "brutalist-concrete",
    "ukiyo-e-woodblock",
    "psychedelic-fillmore",
    "vaporwave-arcade-dusk",
    "mid-century-modern-print",
    "art-nouveau-botanical",
    "constructivist-agitprop",
    "dutch-golden-age-still-life",
    "y2k-chrome-gloss",
}


def test_list_styles_includes_all_expected_presets():
    assert EXPECTED_SLUGS.issubset(set(list_styles()))


def test_load_style_reads_preset():
    style = load_style("neo-grunge-streetwear")
    assert style["name"] == "Neo-Grunge Streetwear"
    assert "distressed grunge texture" in style["magic_media_keywords"]


def test_load_style_missing_raises_with_available_list():
    with pytest.raises(StyleNotFoundError, match="neo-grunge-streetwear"):
        load_style("does-not-exist")


def test_required_keywords_present_for_each_preset():
    for slug in EXPECTED_SLUGS:
        style = load_style(slug)
        kws = required_keywords(style)
        assert len(kws) >= 2
        # every required keyword must literally appear in the full keyword block
        block = style["magic_media_keywords"].lower()
        for kw in kws:
            assert kw.lower() in block


def test_as_prompt_block_embeds_exact_keywords_and_defers_negative_space():
    block = as_prompt_block(load_style("holographic-glassmorphism"))
    assert "ELITE STYLE PRESET" in block
    assert "iridescent dark purple and neon chrome gradients" in block  # verbatim keywords
    assert "text_zone" in block  # negative-space deferral instruction


def test_validate_style_compliance_passes_when_keywords_present():
    style = load_style("corporate-dynamic-vector")
    card = {
        "magic_media_prompt": (
            "An ultra-clean modern corporate aesthetic hero shot, smooth gradient background, "
            "sharp 3D vector wave elements at the borders, brilliant softbox lighting, a highly "
            "isolated subject, top negative space for text."
        )
    }
    validate_style_compliance(card, style)  # should not raise


def test_validate_style_compliance_raises_when_keyword_missing():
    style = load_style("corporate-dynamic-vector")
    card = {"magic_media_prompt": "A plain corporate image with a gradient and some waves."}
    with pytest.raises(PromptValidationError, match="style keyword"):
        validate_style_compliance(card, style)


def test_new_presets_reference_concrete_art_traditions():
    # Each new preset is anchored to a specific tradition, not a generic vibe.
    riso = load_style("riso-print-editorial")
    assert "risograph print texture" in riso["magic_media_keywords"].lower()

    bauhaus = load_style("bauhaus-modernist-poster")
    assert "bauhaus geometric layout" in bauhaus["magic_media_keywords"].lower()
    assert "1920s" in bauhaus["magic_media_keywords"]

    kodak = load_style("kodachrome-americana")
    assert "kodachrome color documentary" in kodak["magic_media_keywords"].lower()
    # draws its light quality verbatim from the aesthetic_taxonomy lexicon
    assert "golden-hour rim light" in kodak["magic_media_keywords"]


def test_wave2_presets_are_anchored_to_concrete_traditions():
    # Each of the 12 wave-2 presets is pinned to one specific, nameable
    # art/design tradition via a distinctive anchor keyword that
    # validate_style_compliance will hard-enforce in every image prompt.
    anchors = {
        "swiss-international-grid": "swiss international typographic style",
        "memphis-design-pop": "memphis design",
        "art-deco-metropolis": "art deco",
        "brutalist-concrete": "brutalist architecture",
        "ukiyo-e-woodblock": "ukiyo-e woodblock",
        "psychedelic-fillmore": "psychedelic concert poster",
        "vaporwave-arcade-dusk": "vaporwave",
        "mid-century-modern-print": "mid-century modern",
        "art-nouveau-botanical": "art nouveau lithograph",
        "constructivist-agitprop": "constructivist agitprop",
        "dutch-golden-age-still-life": "dutch golden age still life",
        "y2k-chrome-gloss": "y2k",
    }
    for slug, anchor in anchors.items():
        style = load_style(slug)
        assert anchor in style["magic_media_keywords"].lower()
        assert any(anchor in kw.lower() for kw in style["required_keywords"]), (
            f"{slug}: tradition anchor '{anchor}' must be code-enforced via required_keywords"
        )


def test_wave2_presets_use_aesthetic_taxonomy_lexicon_term():
    # Every wave-2 preset must draw at least one term verbatim from the
    # aesthetic_taxonomy lexicons (materials / light / register). Earlier
    # presets predate this convention and are exempt.
    from src.constitution import load_constitution

    tax = load_constitution()["aesthetic_taxonomy"]
    lexicon = {
        t.lower()
        for key in ("material_texture_lexicon", "light_quality_lexicon", "register_lexicon")
        for t in tax[key]
    }
    for slug in WAVE2_SLUGS | WAVE3_SLUGS:
        block = load_style(slug)["magic_media_keywords"].lower()
        assert any(term in block for term in lexicon), (
            f"{slug}: magic_media_keywords uses no aesthetic_taxonomy lexicon term"
        )


def test_wave3_presets_are_anchored_and_code_enforced():
    # Each wave-3 preset's defining register/signature is itself a
    # required_keyword, so the gap it was designed to close is code-enforced
    # in every generated image prompt.
    anchors = {
        "warm-editorial-minimalist": "warm editorial minimalist",
        "streamer-energetic-glitch": "streamer glitch",
        "formal-ceremonial-turkish": "formal ceremonial",
        "utility-planner-ornamental": "utility planner layout",
    }
    for slug, anchor in anchors.items():
        style = load_style(slug)
        assert anchor in style["magic_media_keywords"].lower()
        assert any(anchor in kw.lower() for kw in style["required_keywords"])


def test_ceremonial_preset_is_culture_neutral():
    # Deliberately defined without any specific flag or national emblem —
    # tone and composition only, usable across cultures.
    style = load_style("formal-ceremonial-turkish")
    block = style["magic_media_keywords"].lower()
    assert "emblem-free" in block
    for symbol in ("crescent", "star and crescent", "eagle", "cross"):
        assert symbol not in block


def test_utility_planner_reconciles_with_hero_subject_composition():
    # The planner preset reframes the grid as the composition recipes'
    # "isolated hero subject" so the two system-prompt sections agree, and a
    # full planner card passes validate_prompt end-to-end.
    from src.schema import validate_prompt

    planner = load_style("utility-planner-ornamental")
    assert "planner grid itself is the isolated hero subject" in planner["magic_media_keywords"]

    card = {
        "concept": "Weekly Planner",
        "magic_media_prompt": planner["magic_media_keywords"][:-1]
        + ", the header band at the top left empty for overlaying text in Canva.",
        "negative_prompt": "embedded text, numbers, letters, watermark, clutter",
        "aspect_ratio": "2480x3508 (3:4 aspect)",
        "target_tool": "Canva Magic Media",
        "text_zone": "top",
        "layer_typography_architecture": {
            "headline": "Weekly Planner",
            "subtext": "Plan the week, one clean grid.",
            "color_palette": ["#152A52", "#B5893A", "#F6F0E2"],
            "fonts": {
                "headline_font": "Cormorant Garamond SemiBold",
                "body_font": "Josefin Sans Regular",
            },
            "background_layers": "the ornamental planner grid fills the page; the top header band carries the headline/subtext",
            "magic_media_style": "Flat Vector",
        },
        "direct_action_tip": [
            "Open Magic Media, paste the prompt, generate at 3:4.",
            "Add a Heading in the top header band.",
        ],
    }
    validate_prompt(card, style=planner)  # must not raise


def test_every_preset_uses_valid_canva_style_and_contrastable_palette_hint():
    import re

    from src.canva_rules import CANVA_KNOWLEDGE_BASE
    from src.color_science import best_contrast_pair

    for slug in EXPECTED_SLUGS:
        style = load_style(slug)
        assert style["recommended_magic_media_style"] in CANVA_KNOWLEDGE_BASE["magic_media_styles"]
        hexes = re.findall(r"#[0-9A-Fa-f]{6}", style.get("palette_hint", ""))
        assert len(hexes) >= 2, f"{slug}: palette_hint should carry concrete HEX guidance"
        _a, _b, ratio = best_contrast_pair(hexes)
        assert ratio >= 4.5, (
            f"{slug}: palette_hint's colors max out at {ratio:.1f}:1 — a palette drawn "
            "from the hint could never pass the WCAG gate"
        )


def test_load_style_with_custom_directory(tmp_path: Path):
    custom = tmp_path / "styles"
    custom.mkdir()
    (custom / "x.json").write_text(json.dumps({"slug": "x", "name": "X", "required_keywords": []}))
    assert load_style("x", styles_dir=custom)["name"] == "X"
    assert list_styles(styles_dir=custom) == ["x"]


def test_as_prompt_block_with_override_brand_includes_hierarchy_directive():
    """When override_brand=True, the block must contain the STYLE OVERRIDE RULE
    instructing the LLM that the style replaces the brand's visual identity."""
    style = load_style("corporate-dynamic-vector")
    block = as_prompt_block(style, override_brand=True)
    assert "ELITE STYLE PRESET" in block
    assert "STYLE OVERRIDE RULE" in block
    assert "REPLACES and OVERRIDES" in block
    assert "Color Palette, Typography" in block  # brand's remaining contribution


def test_as_prompt_block_without_override_brand_omits_hierarchy_directive():
    """Default behavior (override_brand=False) must NOT include the override
    directive — style-only mode without a brand."""
    style = load_style("neo-grunge-streetwear")
    block = as_prompt_block(style)  # default
    assert "ELITE STYLE PRESET" in block
    assert "STYLE OVERRIDE RULE" not in block
    assert "REPLACES and OVERRIDES" not in block


def test_every_preset_has_best_for():
    """Every style preset must carry a non-empty best_for one-liner so the
    Architect can auto-select the best-fit style for any user concept."""
    from src.style_presets import best_for_summaries

    for slug in EXPECTED_SLUGS:
        style = load_style(slug)
        best = style.get("best_for", "")
        assert isinstance(best, str), f"{slug}: best_for must be a string"
        assert len(best.strip()) >= 10, (
            f"{slug}: best_for is too short ('{best}') — must be a meaningful "
            "one-sentence use-case description"
        )

    # best_for_summaries() must include every slug
    summaries = best_for_summaries()
    for slug in EXPECTED_SLUGS:
        assert slug in summaries, f"{slug} missing from best_for_summaries() output"


def test_best_for_summaries_includes_all_presets():
    """best_for_summaries() output must contain every preset slug and its
    best_for text so the Architect has the full menu."""
    from src.style_presets import best_for_summaries

    summaries = best_for_summaries()
    assert len(summaries) > 0
    # Should have one line per preset
    lines = [l for l in summaries.split("\n") if l.startswith("- ")]
    assert len(lines) == len(EXPECTED_SLUGS), (
        f"Expected {len(EXPECTED_SLUGS)} lines, got {len(lines)}"
    )
