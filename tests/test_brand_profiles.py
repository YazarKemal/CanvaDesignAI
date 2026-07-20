import json
from pathlib import Path

import pytest

from src.brand_profiles import (
    BrandNotFoundError,
    approved_hex_colors,
    as_prompt_block,
    list_brands,
    load_brand,
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


def test_load_brand_with_custom_directory(tmp_path: Path):
    custom_dir = tmp_path / "brands"
    custom_dir.mkdir()
    (custom_dir / "acme.json").write_text(json.dumps({"slug": "acme", "name": "Acme"}))

    brand = load_brand("acme", brands_dir=custom_dir)
    assert brand["name"] == "Acme"
    assert list_brands(brands_dir=custom_dir) == ["acme"]


def test_list_brands_empty_dir_returns_empty_list(tmp_path: Path):
    assert list_brands(brands_dir=tmp_path / "does-not-exist") == []
