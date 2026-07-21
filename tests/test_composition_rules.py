from src.composition_rules import (
    COMPOSITION_RULES,
    DEFAULT_RULE,
    as_prompt_block,
    aspect_family,
    composition_for,
    negative_space_for,
)


def test_aspect_family_normalizes_architect_format():
    # Architect emits "1:1 (1080x1080)".
    assert aspect_family("1:1 (1080x1080)") == "1:1"
    assert aspect_family("9:16 (1080x1920)") == "9:16"
    assert aspect_family("16:9 (1920x1080)") == "16:9"


def test_aspect_family_normalizes_omni_channel_format():
    # Omni-Channel's TARGET_FORMATS values put the ratio second: "1080x1920 (9:16)".
    assert aspect_family("1080x1920 (9:16)") == "9:16"
    assert aspect_family("1080x1080 (1:1)") == "1:1"
    assert aspect_family("1920x1080 (16:9)") == "16:9"


def test_aspect_family_maps_related_ratios_to_families():
    assert aspect_family("2480x3508 (3:4 aspect)") == "4:5"  # poster/flyer -> portrait
    assert aspect_family("1200x630 (1.91:1)") == "16:9"  # wide social -> horizontal
    assert aspect_family("1080x1350 (4:5)") == "4:5"


def test_aspect_family_unknown_returns_none():
    assert aspect_family("some weird 5:2 ratio") is None


def test_composition_for_known_and_unknown():
    assert composition_for("9:16 (1080x1920)") is COMPOSITION_RULES["9:16"]
    assert composition_for("totally unknown") is DEFAULT_RULE


def test_story_composition_is_vertical():
    rule = composition_for("1080x1920 (9:16)")
    assert "vertical leading lines" in rule["composition"]
    assert "floating atmospheric" in rule["lighting"]


def test_square_composition_is_centered_studio():
    rule = composition_for("1:1 (1080x1080)")
    assert "golden-ratio" in rule["composition"]
    assert "softbox" in rule["lighting"]


def test_banner_composition_is_horizontal_panoramic():
    rule = composition_for("1920x1080 (16:9)")
    assert "horizontal framing" in rule["composition"]
    assert "rule-of-thirds" in rule["composition"]
    assert "panoramic" in rule["depth"]


def test_negative_space_for_specific_zone():
    ns = negative_space_for("9:16 (1080x1920)", "top")
    assert "upper 40%" in ns

    ns_banner = negative_space_for("1920x1080 (16:9)", "left")
    assert "right third" in ns_banner  # subject offset right, text on the left two-thirds


def test_negative_space_for_unknown_zone_falls_back():
    ns = negative_space_for("1:1 (1080x1080)", "diagonal")
    assert "diagonal" in ns
    assert "negative space" in ns


def test_as_prompt_block_with_locked_zone_includes_only_that_zone():
    block = as_prompt_block("9:16 (1080x1920)", "top")
    assert "FORMAT-SPECIFIC COMPOSITION" in block
    assert "text_zone 'top'" in block
    assert "upper 40%" in block
    # The other zones' language should NOT be enumerated when a zone is locked.
    assert "left vertical third" not in block


def test_as_prompt_block_without_zone_lists_all_zones():
    block = as_prompt_block("1920x1080 (16:9)")
    for zone in ("top", "bottom", "center", "left", "right"):
        assert f"{zone}:" in block


def test_every_rule_has_all_five_zones():
    for rule in list(COMPOSITION_RULES.values()) + [DEFAULT_RULE]:
        assert set(rule["negative_space"]) == {"top", "bottom", "center", "left", "right"}
        for key in ("label", "composition", "lighting", "depth"):
            assert rule[key]
