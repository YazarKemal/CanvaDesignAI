import json
from pathlib import Path

import pytest

from src.brand_profiles import load_brand
from src.schema import (
    PromptValidationError,
    find_forbidden_phrase,
    validate_brand_compliance,
    validate_prompt,
)

EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "examples" / "grand_opening_cafe.json"
EXAMPLE_BRAND = "example-cafe"


def _load_example() -> dict:
    return json.loads(EXAMPLE_PATH.read_text())


def test_example_card_is_valid():
    validate_prompt(_load_example())  # should not raise


def test_missing_required_field_rejected():
    card = _load_example()
    del card["direct_action_tip"]
    with pytest.raises(PromptValidationError):
        validate_prompt(card)


def test_missing_nested_layer_field_rejected():
    card = _load_example()
    del card["layer_typography_architecture"]["fonts"]
    with pytest.raises(PromptValidationError):
        validate_prompt(card)


def test_too_short_prompt_rejected():
    card = _load_example()
    card["magic_media_prompt"] = "a cafe"
    with pytest.raises(PromptValidationError):
        validate_prompt(card)


def test_bad_hex_color_rejected():
    card = _load_example()
    card["layer_typography_architecture"]["color_palette"][0] = "terracotta"
    with pytest.raises(PromptValidationError):
        validate_prompt(card)


def test_too_few_palette_colors_rejected():
    card = _load_example()
    card["layer_typography_architecture"]["color_palette"] = ["#4A2E1B", "#D4A373"]
    with pytest.raises(PromptValidationError):
        validate_prompt(card)


def test_direct_action_tip_must_be_array_of_at_least_two():
    card = _load_example()
    card["direct_action_tip"] = ["only one step"]
    with pytest.raises(PromptValidationError):
        validate_prompt(card)


def test_missing_text_zone_rejected():
    card = _load_example()
    del card["text_zone"]
    with pytest.raises(PromptValidationError):
        validate_prompt(card)


def test_invalid_text_zone_value_rejected():
    card = _load_example()
    card["text_zone"] = "middle-ish"
    with pytest.raises(PromptValidationError):
        validate_prompt(card)


# --- color contrast (Art Director Phase 1) ---

def test_low_contrast_palette_rejected():
    card = _load_example()
    # Three similar mid-tone colors: no pair reaches the 4.5:1 AA minimum.
    card["layer_typography_architecture"]["color_palette"] = ["#888888", "#8A8A8A", "#7E7E7E"]
    with pytest.raises(PromptValidationError, match="contrast"):
        validate_prompt(card)


def test_passing_contrast_palette_is_accepted():
    card = _load_example()
    card["layer_typography_architecture"]["color_palette"] = ["#000000", "#FFFFFF", "#D4A373"]
    validate_prompt(card)  # should not raise


# --- typography hierarchy (Art Director Phase 2) ---

def test_headline_too_many_words_rejected():
    card = _load_example()
    card["layer_typography_architecture"]["headline"] = "This Headline Has Way Too Many Words In It"
    with pytest.raises(PromptValidationError, match="headline"):
        validate_prompt(card)


def test_subtext_too_many_words_rejected():
    card = _load_example()
    card["layer_typography_architecture"]["subtext"] = (
        "This subtext rambles on for far too long with way more than the fourteen "
        "word limit that a short supporting line is supposed to respect here."
    )
    with pytest.raises(PromptValidationError, match="subtext"):
        validate_prompt(card)


# --- text_zone consistency (Art Director Phase 3) ---

def test_text_zone_not_mentioned_in_magic_media_prompt_rejected():
    card = _load_example()
    card["text_zone"] = "bottom"  # prompt still says "top" -> disagreement
    with pytest.raises(PromptValidationError, match="magic_media_prompt"):
        validate_prompt(card)


def test_text_zone_not_mentioned_in_background_layers_rejected():
    card = _load_example()
    # text_zone still agrees with magic_media_prompt ("top"), but
    # background_layers is rewritten to omit any zone keyword.
    card["layer_typography_architecture"]["background_layers"] = "generated image fills the whole canvas"
    with pytest.raises(PromptValidationError, match="background_layers"):
        validate_prompt(card)


# --- forbidden chat-phrase guard ---

def test_find_forbidden_phrase_none_on_clean_card():
    assert find_forbidden_phrase(_load_example()) is None


@pytest.mark.parametrize(
    "phrase",
    ["I can generate this for you!", "Would you like me to adjust it?", "Sure, here's your design."],
)
def test_forbidden_phrase_detected_in_top_level_field(phrase):
    card = _load_example()
    card["magic_media_prompt"] = card["magic_media_prompt"] + " " + phrase
    assert find_forbidden_phrase(card) is not None
    with pytest.raises(PromptValidationError):
        validate_prompt(card)


def test_forbidden_phrase_detected_in_nested_field():
    card = _load_example()
    card["layer_typography_architecture"]["background_layers"] += " Let me know if you want changes."
    with pytest.raises(PromptValidationError):
        validate_prompt(card)


def test_forbidden_phrase_detected_inside_list_field():
    card = _load_example()
    card["direct_action_tip"].append("Here is another tip for you.")
    with pytest.raises(PromptValidationError):
        validate_prompt(card)


# --- brand compliance (Design Agency) ---

def test_example_card_matches_example_brand_exactly():
    # The repo's example card happens to already use example-cafe's exact
    # signature fonts and only approved colors -- validate_prompt(brand=...)
    # should accept it with zero changes.
    brand = load_brand(EXAMPLE_BRAND)
    validate_prompt(_load_example(), brand=brand)  # should not raise


def test_wrong_headline_font_rejected():
    brand = load_brand(EXAMPLE_BRAND)
    card = _load_example()
    card["layer_typography_architecture"]["fonts"]["headline_font"] = "Poppins SemiBold"
    with pytest.raises(PromptValidationError, match="headline_font"):
        validate_brand_compliance(card, brand)
    with pytest.raises(PromptValidationError):
        validate_prompt(card, brand=brand)


def test_wrong_body_font_rejected():
    brand = load_brand(EXAMPLE_BRAND)
    card = _load_example()
    card["layer_typography_architecture"]["fonts"]["body_font"] = "Lato Regular"
    with pytest.raises(PromptValidationError, match="body_font"):
        validate_brand_compliance(card, brand)


def test_unapproved_color_rejected():
    brand = load_brand(EXAMPLE_BRAND)
    card = _load_example()
    card["layer_typography_architecture"]["color_palette"] = ["#4A2E1B", "#D4A373", "#123456"]
    with pytest.raises(PromptValidationError, match="approved colors"):
        validate_brand_compliance(card, brand)


def test_approved_color_case_insensitive():
    brand = load_brand(EXAMPLE_BRAND)
    card = _load_example()
    card["layer_typography_architecture"]["color_palette"] = ["#4a2e1b", "#d4a373", "#f5efe6"]
    validate_brand_compliance(card, brand)  # should not raise (case-insensitive)


def test_no_brand_means_no_brand_checks():
    # Without a brand, an off-brand font/color combo is perfectly valid --
    # brand compliance is opt-in.
    card = _load_example()
    card["layer_typography_architecture"]["fonts"]["headline_font"] = "Anton"
    validate_prompt(card)  # should not raise
