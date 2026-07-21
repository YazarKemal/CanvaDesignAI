import json
from pathlib import Path

import pytest

from src.brand_profiles import (
    BrandNotFoundError,
    approved_hex_colors,
    as_prompt_block,
    list_brands,
    load_brand,
    visual_identity_block,
)

EXAMPLE_SLUG = "example-cafe"


def test_load_brand_reads_repo_example():
    brand = load_brand(EXAMPLE_SLUG)
    assert brand["slug"] == EXAMPLE_SLUG
    assert brand["signature_fonts"]["headline_font"] == "Montserrat Bold"


def test_load_brand_missing_raises_with_available_list():
    with pytest.raises(BrandNotFoundError, match=EXAMPLE_SLUG):
        load_brand("does-not-exist")


def test_list_brands_includes_example():
    assert EXAMPLE_SLUG in list_brands()


def test_approved_hex_colors_flattens_all_groups():
    brand = load_brand(EXAMPLE_SLUG)
    colors = approved_hex_colors(brand)
    assert "#4A2E1B" in colors
    assert "#D4A373" in colors
    assert "#F5EFE6" in colors
    assert "#8B5E34" in colors


def test_approved_hex_colors_is_case_insensitive():
    brand = load_brand(EXAMPLE_SLUG)
    colors = approved_hex_colors(brand)
    assert "#4a2e1b" not in colors  # stored upper
    assert "#4A2E1B".upper() in colors


def test_as_prompt_block_embeds_brand_json():
    brand = load_brand(EXAMPLE_SLUG)
    block = as_prompt_block(brand)
    assert "BRAND PROFILE" in block
    assert brand["slug"] in block
    assert "Montserrat Bold" in block


def test_visual_identity_block_renders_image_steering():
    brand = load_brand(EXAMPLE_SLUG)
    block = visual_identity_block(brand)
    assert "BRAND VISUAL IDENTITY" in block
    assert "warm oak wood grain" in block  # texture cue
    assert "morning window light" in block  # lighting warmth
    assert "editorial photography" in block  # photographic register


def test_visual_identity_block_empty_when_absent():
    assert visual_identity_block({"slug": "bare", "name": "Bare"}) == ""


def test_as_prompt_block_includes_visual_identity_when_present():
    brand = load_brand(EXAMPLE_SLUG)
    block = as_prompt_block(brand)
    assert "BRAND VISUAL IDENTITY" in block
    assert "warm oak wood grain" in block


def test_as_prompt_block_omits_visual_identity_when_absent():
    block = as_prompt_block({"slug": "bare", "name": "Bare", "signature_fonts": {}})
    assert "BRAND PROFILE" in block
    assert "BRAND VISUAL IDENTITY" not in block


def test_as_prompt_block_excludes_visual_identity_when_requested():
    """When exclude_visual_identity=True, the block must NOT contain
    BRAND VISUAL IDENTITY or any texture/mood keywords, but must still
    carry the typography/color constraints."""
    brand = load_brand(EXAMPLE_SLUG)
    block = as_prompt_block(brand, exclude_visual_identity=True)
    assert "BRAND PROFILE" in block
    assert "BRAND VISUAL IDENTITY" not in block
    assert "warm oak wood grain" not in block
    assert "editorial photography" not in block
    # Brand JSON within the block must NOT contain the visual_identity key
    assert '"visual_identity"' not in block
    # But core brand data must still be there
    assert "Montserrat Bold" in block
    assert "#4A2E1B" in block


def test_as_prompt_block_includes_visual_identity_by_default():
    """Default behavior (exclude_visual_identity=False) must preserve the
    backward-compatible full brand block with visual identity."""
    brand = load_brand(EXAMPLE_SLUG)
    block = as_prompt_block(brand)  # default
    assert "BRAND VISUAL IDENTITY" in block
    assert "warm oak wood grain" in block
    assert "editorial photography" in block
    assert '"visual_identity"' in block


def test_load_brand_with_custom_directory(tmp_path: Path):
    custom_dir = tmp_path / "brands"
    custom_dir.mkdir()
    (custom_dir / "acme.json").write_text(json.dumps({"slug": "acme", "name": "Acme"}))

    brand = load_brand("acme", brands_dir=custom_dir)
    assert brand["name"] == "Acme"
    assert list_brands(brands_dir=custom_dir) == ["acme"]


def test_list_brands_empty_dir_returns_empty_list(tmp_path: Path):
    assert list_brands(brands_dir=tmp_path / "does-not-exist") == []
