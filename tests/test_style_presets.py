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
