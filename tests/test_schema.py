import json
from pathlib import Path

import pytest

from src.schema import PromptValidationError, validate_prompt

EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "examples" / "grand_opening_cafe.json"


def test_example_prompt_is_valid():
    draft = json.loads(EXAMPLE_PATH.read_text())
    validate_prompt(draft)  # should not raise


def test_missing_required_field_rejected():
    draft = json.loads(EXAMPLE_PATH.read_text())
    del draft["negative_prompt"]
    with pytest.raises(PromptValidationError):
        validate_prompt(draft)


def test_missing_nested_art_direction_field_rejected():
    draft = json.loads(EXAMPLE_PATH.read_text())
    del draft["art_direction"]["lighting"]
    with pytest.raises(PromptValidationError):
        validate_prompt(draft)


def test_bad_aspect_ratio_rejected():
    draft = json.loads(EXAMPLE_PATH.read_text())
    draft["aspect_ratio"] = "widescreen"
    with pytest.raises(PromptValidationError):
        validate_prompt(draft)


def test_too_short_image_prompt_rejected():
    draft = json.loads(EXAMPLE_PATH.read_text())
    draft["image_prompt"] = "a cafe"
    with pytest.raises(PromptValidationError):
        validate_prompt(draft)


def test_too_few_palette_colors_rejected():
    draft = json.loads(EXAMPLE_PATH.read_text())
    draft["art_direction"]["color_palette"] = ["amber", "cream"]
    with pytest.raises(PromptValidationError):
        validate_prompt(draft)
