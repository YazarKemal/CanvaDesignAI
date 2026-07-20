import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.omni_channel import (
    TARGET_FORMATS,
    UnknownFormatError,
    adapt_to_format,
    generate_omni_channel_set,
)
from src.schema import PromptValidationError

EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "examples" / "grand_opening_cafe.json"


def _load_base_card() -> dict:
    return json.loads(EXAMPLE_PATH.read_text())


VALID_STORY_ADAPTATION = {
    "text_zone": "center",
    "magic_media_prompt": (
        "A minimalist 3d flat vector illustration for a specialty coffee shop grand "
        "opening, earthy terracotta and warm cream color palette, tall vertical "
        "framing with the espresso cup centered, ample negative space at the center "
        "for overlaying text in Canva, vintage aesthetic, isolated on a plain background."
    ),
    "background_layers": "generated image fills the frame; a centered cream panel behind the middle band carries the headline/subtext",
    "direct_action_tip": [
        "Open Canva > Apps > Magic Media, paste magic_media_prompt, generate at 9:16 (1080x1920).",
        "Add a Heading text box centered in the frame and type the headline.",
    ],
}


class _FakeClient:
    def __init__(self, replies: list[str]):
        self._replies = list(replies)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        content = self._replies.pop(0)
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_target_formats_includes_expected_keys():
    assert set(TARGET_FORMATS) == {"instagram_post", "instagram_story", "banner"}


def test_adapt_to_format_merges_fixed_fields_with_adaptation():
    base = _load_base_card()
    client = _FakeClient([json.dumps(VALID_STORY_ADAPTATION)])

    variant = adapt_to_format(base, "instagram_story", client=client)

    # Fixed fields carried over unchanged.
    assert variant["concept"] == base["concept"]
    assert variant["layer_typography_architecture"]["headline"] == base["layer_typography_architecture"]["headline"]
    assert variant["layer_typography_architecture"]["color_palette"] == base["layer_typography_architecture"]["color_palette"]
    assert variant["layer_typography_architecture"]["fonts"] == base["layer_typography_architecture"]["fonts"]
    assert variant["negative_prompt"] == base["negative_prompt"]

    # Adapted fields.
    assert variant["aspect_ratio"] == TARGET_FORMATS["instagram_story"]
    assert variant["text_zone"] == "center"
    assert variant["magic_media_prompt"] == VALID_STORY_ADAPTATION["magic_media_prompt"]
    assert variant["layer_typography_architecture"]["background_layers"] == VALID_STORY_ADAPTATION["background_layers"]

    # The original base card object must not be mutated.
    assert base["text_zone"] == "top"
    assert base["aspect_ratio"] != variant["aspect_ratio"]


def test_adapt_to_format_does_not_change_base_card_headline_reference():
    base = _load_base_card()
    client = _FakeClient([json.dumps(VALID_STORY_ADAPTATION)])
    variant = adapt_to_format(base, "instagram_story", client=client)
    variant["layer_typography_architecture"]["headline"] = "Mutated"
    assert base["layer_typography_architecture"]["headline"] == "Grand Opening"


def test_adapt_to_format_unknown_format_raises():
    base = _load_base_card()
    with pytest.raises(UnknownFormatError):
        adapt_to_format(base, "tiktok-does-not-exist", client=_FakeClient([]))


def test_adapt_to_format_retries_once_on_zone_inconsistency_then_succeeds():
    base = _load_base_card()
    broken = dict(VALID_STORY_ADAPTATION)
    broken["magic_media_prompt"] = "A prompt that forgot to mention the zone at all."
    client = _FakeClient([json.dumps(broken), json.dumps(VALID_STORY_ADAPTATION)])

    variant = adapt_to_format(base, "instagram_story", client=client)

    assert variant["text_zone"] == "center"
    assert len(client.calls) == 2
    # Second call's user message should include feedback about the failure.
    assert "rejected" in client.calls[1]["messages"][1]["content"].lower()


def test_adapt_to_format_raises_after_exhausting_attempts():
    base = _load_base_card()
    broken = dict(VALID_STORY_ADAPTATION)
    broken["magic_media_prompt"] = "Never mentions any zone keyword."
    client = _FakeClient([json.dumps(broken), json.dumps(broken)])

    with pytest.raises(PromptValidationError):
        adapt_to_format(base, "instagram_story", client=client)


def test_generate_omni_channel_set_calls_adapt_for_each_format():
    base = _load_base_card()
    client = _FakeClient([json.dumps(VALID_STORY_ADAPTATION), json.dumps(VALID_STORY_ADAPTATION)])

    variants = generate_omni_channel_set(base, ["instagram_story", "banner"], client=client)

    assert set(variants) == {"instagram_story", "banner"}
    assert variants["banner"]["aspect_ratio"] == TARGET_FORMATS["banner"]
