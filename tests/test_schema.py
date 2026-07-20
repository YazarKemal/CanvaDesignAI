import json
from pathlib import Path

import pytest

from src.schema import PromptValidationError, find_forbidden_phrase, validate_prompt

EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "examples" / "grand_opening_cafe.json"


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
