import json
from pathlib import Path

import pytest

from src.schema import DesignValidationError, validate_design

EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "examples" / "grand_opening_cafe.json"


def test_example_design_is_valid():
    draft = json.loads(EXAMPLE_PATH.read_text())
    validate_design(draft)  # should not raise


def test_missing_required_field_rejected():
    draft = json.loads(EXAMPLE_PATH.read_text())
    del draft["layout_instructions"]
    with pytest.raises(DesignValidationError):
        validate_design(draft)


def test_bad_hex_color_rejected():
    draft = json.loads(EXAMPLE_PATH.read_text())
    draft["color_palette"][0] = "not-a-color"
    with pytest.raises(DesignValidationError):
        validate_design(draft)


def test_too_few_colors_rejected():
    draft = json.loads(EXAMPLE_PATH.read_text())
    draft["color_palette"] = ["#FFFFFF", "#000000"]
    with pytest.raises(DesignValidationError):
        validate_design(draft)
