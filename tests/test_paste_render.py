import json
from pathlib import Path

from src.paste_render import render_for_assistant_paste

EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "examples" / "grand_opening_cafe.json"


def _load_example() -> dict:
    return json.loads(EXAMPLE_PATH.read_text())


def test_render_starts_with_plain_first_person_directive_not_fake_system_tag():
    text = render_for_assistant_paste(_load_example())
    first_line = text.splitlines()[0]

    assert first_line.startswith("Using your connected Canva tool")
    # Must never impersonate a system/override channel.
    for banned in ("SYSTEM:", "OVERRIDE", "ignore previous instructions", "you are now"):
        assert banned.lower() not in text.lower()


def test_render_tells_assistant_not_to_ask_questions_and_use_canva_tool():
    text = render_for_assistant_paste(_load_example())
    assert "do not ask me any clarifying questions" in text.lower()
    assert "canva tool" in text.lower()


def test_render_includes_all_three_mandatory_components():
    card = _load_example()
    text = render_for_assistant_paste(card)

    assert card["magic_media_prompt"] in text
    assert card["layer_typography_architecture"]["headline"] in text
    assert card["layer_typography_architecture"]["subtext"] in text
    for hex_color in card["layer_typography_architecture"]["color_palette"]:
        assert hex_color in text
    for step in card["direct_action_tip"]:
        assert step in text


def test_render_numbers_the_action_steps_in_order():
    card = _load_example()
    text = render_for_assistant_paste(card)
    for i, step in enumerate(card["direct_action_tip"], start=1):
        assert f"{i}. {step}" in text


def test_render_includes_aspect_ratio_and_target_tool():
    card = _load_example()
    text = render_for_assistant_paste(card)
    assert card["aspect_ratio"] in text
    assert card["target_tool"] in text


def test_unified_brief_warns_fonts_and_palette_are_styling_not_visible_text():
    """Font names and HEX codes are typography-layer instructions, not
    visible text to render. Without explicit disclaimers, some AI design
    tools misinterpret them and render the raw values on the card."""
    text = render_for_assistant_paste(_load_example())
    assert "do NOT render the font names as visible text" in text
    assert "do NOT render the codes as visible text" in text
    assert "this is the visible title text" in text.lower()
    assert "this is the visible supporting text" in text.lower()
