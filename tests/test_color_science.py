import pytest

from src.color_science import (
    InvalidHexColorError,
    best_contrast_pair,
    contrast_ratio,
    hue_distance,
    is_clashing_pair,
    relative_luminance,
)


def test_relative_luminance_black_and_white():
    assert relative_luminance("#000000") == pytest.approx(0.0, abs=1e-9)
    assert relative_luminance("#FFFFFF") == pytest.approx(1.0, abs=1e-9)


def test_contrast_ratio_black_white_is_21_to_1():
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.01)


def test_contrast_ratio_is_symmetric():
    assert contrast_ratio("#4A2E1B", "#F5EFE6") == pytest.approx(contrast_ratio("#F5EFE6", "#4A2E1B"))


def test_contrast_ratio_same_color_is_1_to_1():
    assert contrast_ratio("#808080", "#808080") == pytest.approx(1.0, abs=0.01)


def test_contrast_ratio_two_similar_midtones_is_low():
    # Two close mid-grays should be well under the 4.5 WCAG AA threshold.
    assert contrast_ratio("#888888", "#8A8A8A") < 1.2


def test_invalid_hex_raises():
    with pytest.raises(InvalidHexColorError):
        relative_luminance("terracotta")
    with pytest.raises(InvalidHexColorError):
        contrast_ratio("#FFF", "#000000")  # 3-digit shorthand not supported


def test_hue_distance_red_and_cyan_are_opposite():
    # Red (0deg) and cyan (180deg) are on opposite sides of the wheel.
    assert hue_distance("#FF0000", "#00FFFF") == pytest.approx(180.0, abs=1.0)


def test_hue_distance_same_hue_is_zero():
    assert hue_distance("#FF0000", "#CC0000") == pytest.approx(0.0, abs=1.0)


def test_is_clashing_pair_true_for_adjacent_saturated_hues():
    # Saturated red vs. a saturated orange-red sit close on the wheel.
    assert is_clashing_pair("#FF0000", "#FF3300") is True


def test_is_clashing_pair_false_for_true_complementary_scheme():
    # Saturated red vs. saturated cyan are ~180 degrees apart -- a
    # deliberate complementary scheme, not an accidental clash.
    assert is_clashing_pair("#FF0000", "#00FFFF") is False


def test_is_clashing_pair_false_when_one_color_is_desaturated():
    assert is_clashing_pair("#FF0000", "#F5EFE6") is False


def test_best_contrast_pair_picks_highest_ratio():
    a, b, ratio = best_contrast_pair(["#4A2E1B", "#D4A373", "#F5EFE6"])
    assert {a, b} == {"#4A2E1B", "#F5EFE6"}
    assert ratio == pytest.approx(contrast_ratio("#4A2E1B", "#F5EFE6"))


def test_best_contrast_pair_requires_at_least_two_colors():
    with pytest.raises(ValueError):
        best_contrast_pair(["#4A2E1B"])
