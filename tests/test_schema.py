import json
from pathlib import Path

import pytest

from src.schema import PromptValidationError, validate_prompt

EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "examples" / "grand_opening_cafe.json"


def test_example_card_is_valid():
    card = json.loads(EXAMPLE_PATH.read_text())
    validate_prompt(card)  # should not raise


def test_missing_required_field_rejected():
    card = json.loads(EXAMPLE_PATH.read_text())
    del card["canva_tip"]
    with pytest.raises(PromptValidationError):
        validate_prompt(card)


def test_missing_nested_art_direction_field_rejected():
    card = json.loads(EXAMPLE_PATH.read_text())
    del card["art_direction"]["lighting"]
    with pytest.raises(PromptValidationError):
        validate_prompt(card)


def test_too_short_prompt_text_rejected():
    card = json.loads(EXAMPLE_PATH.read_text())
    card["prompt_text"] = "a cafe"
    with pytest.raises(PromptValidationError):
        validate_prompt(card)


def test_too_few_palette_colors_rejected():
    card = json.loads(EXAMPLE_PATH.read_text())
    card["art_direction"]["color_palette"] = ["terracotta", "cream"]
    with pytest.raises(PromptValidationError):
        validate_prompt(card)
