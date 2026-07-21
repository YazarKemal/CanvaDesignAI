from src.composition_rules import (
    COMPOSITION_RULES,
    DEFAULT_RULE,
    align_zone_language,
    as_prompt_block,
    aspect_family,
    composition_for,
    negative_space_for,
)

_CLAUSE = "with deliberate negative space reserved at the {zone} for the overlay"


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


def test_align_zone_language_rewrites_stale_direction():
    text = "ample negative space at the top for overlaying text in Canva"
    out = align_zone_language(text, "bottom", append_clause=_CLAUSE.format(zone="bottom"))
    assert "negative space at the bottom" in out
    assert "at the top" not in out


def test_align_zone_language_leaves_camera_angle_untouched():
    text = "top-down espresso cup, ample negative space at the top for text"
    out = align_zone_language(text, "bottom", append_clause=_CLAUSE.format(zone="bottom"))
    assert "top-down espresso cup" in out  # camera angle preserved
    assert "negative space at the bottom" in out


def test_align_zone_language_leaves_subject_placement_untouched():
    # Only the negative-space direction is rewritten; the subject's own
    # placement ("on the right") must stay put.
    text = "the espresso cup on the right, negative space at the top for the headline"
    out = align_zone_language(text, "left", append_clause=_CLAUSE.format(zone="left"))
    assert "on the right" in out
    assert "negative space at the left" in out
    assert "at the top" not in out


def test_align_zone_language_appends_when_no_zone_reference():
    text = "A minimalist scene with warm oak textures and soft morning light."
    out = align_zone_language(text, "bottom", append_clause=_CLAUSE.format(zone="bottom"))
    assert "bottom" in out.lower()
    assert out.count(".") == 1  # tidy single sentence terminator, no double period


def test_align_zone_language_noop_when_already_correct():
    text = "wide framing, empty negative space along the left for overlaying text"
    out = align_zone_language(text, "left", append_clause=_CLAUSE.format(zone="left"))
    assert out == text  # already consistent — untouched


def test_align_zone_language_normalizes_centre_to_center():
    text = "reserved area toward the centre for the headline"
    out = align_zone_language(text, "center", append_clause=_CLAUSE.format(zone="center"))
    assert "center" in out
    assert "centre" not in out


def test_align_zone_language_guarantees_zone_for_all_targets():
    text = "A clean vector illustration of a coffee cup, isolated on a plain background."
    for zone in ("top", "bottom", "center", "left", "right"):
        out = align_zone_language(text, zone, append_clause=_CLAUSE.format(zone=zone))
        assert zone in out.lower()
