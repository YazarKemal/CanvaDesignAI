import json
import re
from xml.etree import ElementTree as ET

import pytest

from src.preview_generator import (
    _desaturate_hex,
    _parse_pixel_dims,
    _text_zone_rect,
    _xml_escape,
    generate_wireframe,
)

CARD = {
    "concept": "Grand Opening Cafe",
    "magic_media_prompt": "A minimalist flat vector espresso cup, terracotta palette, top negative space.",
    "negative_prompt": "embedded text, watermark",
    "aspect_ratio": "1:1 (1080x1080)",
    "target_tool": "Canva Magic Media",
    "text_zone": "top",
    "layer_typography_architecture": {
        "headline": "Grand Opening",
        "subtext": "Freshly roasted, every morning.",
        "color_palette": ["#4A2E1B", "#D4A373", "#F5EFE6"],
        "fonts": {"headline_font": "Montserrat Bold", "body_font": "Playfair Display"},
        "background_layers": "image fills bottom 60%; cream panel behind top 40%",
        "magic_media_style": "Flat Vector",
    },
    "direct_action_tip": [
        "Open Magic Media and paste the prompt.",
        "Add a heading text box.",
    ],
}


# -- XML / character escaping -------------------------------------------------


def test_xml_escape_handles_special_chars():
    assert _xml_escape("<script>") == "&lt;script&gt;"
    assert _xml_escape('a "quote" & more') == "a &quot;quote&quot; &amp; more"
    assert _xml_escape("plain text") == "plain text"


# -- Aspect-ratio parsing -----------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected_w, expected_h",
    [
        ("1:1 (1080x1080)", 1080, 1080),
        ("1080x1350 (4:5)", 1080, 1350),
        ("1080x1920 (9:16)", 1080, 1920),
        ("2480x3508 (3:4 aspect)", 2480, 3508),
        ("1200x630 (1.91:1)", 1200, 630),
        ("1920x1080 (16:9)", 1920, 1080),
        ("1280x720 (16:9)", 1280, 720),
        ("500x500 (1:1)", 500, 500),
        ("1050x600 (7:4 aspect)", 1050, 600),
        # Unicode multiplication sign
        ("1080×1080", 1080, 1080),
    ],
)
def test_parse_pixel_dims(raw, expected_w, expected_h):
    w, h = _parse_pixel_dims(raw)
    assert w == expected_w
    assert h == expected_h


def test_parse_pixel_dims_fallback_on_unrecognised():
    w, h = _parse_pixel_dims("some random string")
    assert w == 1080
    assert h == 1080


# -- Text-zone geometry -------------------------------------------------------


def test_text_zone_rect_top():
    x, y, w, h = _text_zone_rect(1080, 1080, "top")
    assert x == 0
    assert y == 0
    assert w == 1080
    assert h == pytest.approx(1080 * 0.32, abs=2)


def test_text_zone_rect_bottom():
    x, y, w, h = _text_zone_rect(1080, 1080, "bottom")
    assert x == 0
    assert y > 700  # near the bottom
    assert w == 1080


def test_text_zone_rect_left():
    x, y, w, h = _text_zone_rect(1080, 1080, "left")
    assert x == 0
    assert y == 0
    assert w == pytest.approx(1080 * 0.32, abs=2)
    assert h == 1080


def test_text_zone_rect_right():
    x, y, w, h = _text_zone_rect(1080, 1080, "right")
    assert x > 700  # near the right edge
    assert y == 0
    assert h == 1080


def test_text_zone_rect_center():
    x, y, w, h = _text_zone_rect(1080, 1080, "center")
    # Center should be floating inset — not touching all edges
    assert x > 100
    assert y > 100
    assert w < 900
    assert h < 700


# -- Desaturate helper --------------------------------------------------------


def test_desaturate_hex_zero_amount_returns_original():
    assert _desaturate_hex("#FF0000", 0.0) == "#ff0000"


def test_desaturate_hex_full_amount_returns_grey():
    result = _desaturate_hex("#FF0000", 1.0)
    # Pure red → grey at luminance ~76
    r, g, b = (int(result.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    assert r == g == b


def test_desaturate_hex_partial():
    result = _desaturate_hex("#0000FF", 0.5)
    r, g, b = (int(result.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    # Blue desaturated halfway — red/green channels should have risen
    assert r > 0
    assert g > 0
    assert b < 255


# -- Wireframe HTML output ----------------------------------------------------


def test_generate_wireframe_returns_complete_html_document():
    html = generate_wireframe(CARD)
    assert html.strip().startswith("<!DOCTYPE html>")
    assert "<html" in html
    assert "</html>" in html
    assert "<head>" in html
    assert "<body>" in html
    assert "<style>" in html


def test_generate_wireframe_contains_svg_canvas():
    html = generate_wireframe(CARD)
    assert html.count("<svg") == 1
    assert html.count("</svg>") == 1
    assert 'viewBox="0 0 1080 1080"' in html


def test_generate_wireframe_renders_concept_in_title_and_heading():
    html = generate_wireframe(CARD)
    assert "<title>CaVDesign Wireframe — Grand Opening Cafe</title>" in html
    assert "<h1>Grand Opening Cafe</h1>" in html


def test_generate_wireframe_renders_text_zone_label():
    html = generate_wireframe(CARD)
    assert "text_zone: top" in html


def test_generate_wireframe_renders_headline_and_subtext_in_svg():
    html = generate_wireframe(CARD)
    assert "Grand Opening" in html
    assert "Freshly roasted, every morning." in html


def test_generate_wireframe_renders_color_palette_swatches():
    html = generate_wireframe(CARD)
    for hex_code in ("#4A2E1B", "#D4A373", "#F5EFE6"):
        assert hex_code in html
    assert "swatch" in html.lower()


def test_generate_wireframe_renders_typography_info():
    html = generate_wireframe(CARD)
    assert "Montserrat Bold" in html
    assert "Playfair Display" in html


def test_generate_wireframe_renders_aspect_ratio_and_tool():
    html = generate_wireframe(CARD)
    assert "1:1 (1080x1080)" in html
    assert "Canva Magic Media" in html


def test_generate_wireframe_includes_contrast_badge():
    html = generate_wireframe(CARD)
    # Palette #4A2E1B vs #F5EFE6 has excellent contrast
    assert "contrast-ok" in html
    assert "AA" in html


def test_generate_wireframe_with_low_contrast_palette_shows_fail_badge():
    card = json.loads(json.dumps(CARD))
    card["layer_typography_architecture"]["color_palette"] = [
        "#888888",
        "#8A8A8A",
        "#7E7E7E",
    ]
    html = generate_wireframe(card)
    assert "contrast-bad" in html
    assert "FAIL" in html


def test_generate_wireframe_escapes_special_chars_in_concept():
    card = json.loads(json.dumps(CARD))
    card["concept"] = 'Cafe <special> & "More"'
    html = generate_wireframe(card)
    assert "Cafe " in html
    assert "&lt;special&gt;" in html
    assert "&amp;" in html
    assert "&quot;More&quot;" in html
    # No raw injection
    assert "<special>" not in html


def test_generate_wireframe_escapes_special_chars_in_headline():
    card = json.loads(json.dumps(CARD))
    card["layer_typography_architecture"]["headline"] = "Sale <b>50%</b> & More"
    html = generate_wireframe(card)
    assert "&lt;b&gt;50%&lt;/b&gt;" in html


def test_every_text_zone_produces_valid_output():
    for zone in ("top", "bottom", "left", "right", "center"):
        card = json.loads(json.dumps(CARD))
        card["text_zone"] = zone
        html = generate_wireframe(card)
        assert f"text_zone: {zone}" in html
        assert html.count("<svg") == 1
        assert "</html>" in html


def test_generate_wireframe_dimension_badge_present():
    html = generate_wireframe(CARD)
    assert "1080×1080" in html or "1080x1080" in html


def test_generate_wireframe_magic_media_style_in_meta():
    html = generate_wireframe(CARD)
    assert "Flat Vector" in html


def test_generate_wireframe_without_magic_media_style_still_works():
    card = json.loads(json.dumps(CARD))
    del card["layer_typography_architecture"]["magic_media_style"]
    html = generate_wireframe(card)
    assert "<svg" in html
    assert "</html>" in html


def test_generate_wireframe_no_raw_json_field_names_leak():
    """The wireframe must be a visual preview, not a JSON dump — no
    snake_case field names should appear as visible labels."""
    html = generate_wireframe(CARD)
    assert "color_palette" not in html
    assert "layer_typography_architecture" not in html
    assert "magic_media_prompt" not in html
    assert "direct_action_tip" not in html


def test_generate_wireframe_svg_contains_image_area_label():
    html = generate_wireframe(CARD)
    assert "IMAGE AREA" in html


def test_aspect_ratio_handles_different_orientations():
    portrait_card = json.loads(json.dumps(CARD))
    portrait_card["aspect_ratio"] = "1080x1920 (9:16)"
    portrait_card["text_zone"] = "center"
    html = generate_wireframe(portrait_card)
    assert "viewBox" in html
    # viewBox should reflect the portrait dimensions
    assert "1080 1920" in html

    landscape_card = json.loads(json.dumps(CARD))
    landscape_card["aspect_ratio"] = "1920x1080 (16:9)"
    html = generate_wireframe(landscape_card)
    assert "1920 1080" in html


def test_svg_contains_both_rect_and_text_elements():
    html = generate_wireframe(CARD)
    assert "<rect" in html
    assert "<text" in html
    assert "text-anchor" in html
