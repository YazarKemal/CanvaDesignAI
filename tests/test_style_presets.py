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
}


def test_list_styles_includes_all_three_presets():
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


def test_load_style_with_custom_directory(tmp_path: Path):
    custom = tmp_path / "styles"
    custom.mkdir()
    (custom / "x.json").write_text(json.dumps({"slug": "x", "name": "X", "required_keywords": []}))
    assert load_style("x", styles_dir=custom)["name"] == "X"
    assert list_styles(styles_dir=custom) == ["x"]
