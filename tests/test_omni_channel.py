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


def test_adapt_to_format_auto_corrects_zone_mismatch_without_retry():
    # The adaptation changed text_zone to 'center' but its prompt never mentions
    # 'center'. This used to hard-fail validation and burn a retry; it is now
    # reconciled deterministically on the first attempt.
    base = _load_base_card()
    mismatched = dict(VALID_STORY_ADAPTATION)
    mismatched["text_zone"] = "center"
    mismatched["magic_media_prompt"] = (
        "A minimalist 3d flat vector illustration for a specialty coffee shop grand "
        "opening, earthy terracotta and warm cream palette, isolated on a plain background."
    )
    mismatched["background_layers"] = "generated image fills the frame behind the copy"
    client = _FakeClient([json.dumps(mismatched)])

    variant = adapt_to_format(base, "instagram_story", client=client)

    assert variant["text_zone"] == "center"
    assert len(client.calls) == 1  # no retry needed — healed in place
    assert "center" in variant["magic_media_prompt"].lower()
    assert "center" in variant["layer_typography_architecture"]["background_layers"].lower()


def test_adapt_to_format_rewrites_stale_zone_direction_in_prompt():
    # Prompt reused the OLD 'top' negative-space wording while the new zone is
    # 'bottom' — the direction must be rewritten, not just appended to.
    base = _load_base_card()
    stale = dict(VALID_STORY_ADAPTATION)
    stale["text_zone"] = "bottom"
    stale["magic_media_prompt"] = (
        "A minimalist 3d flat vector illustration for a specialty coffee shop grand "
        "opening, top-down espresso cup, ample negative space at the top for overlaying "
        "text in Canva, isolated on a plain background."
    )
    stale["background_layers"] = "cream panel reserved in the top band carries the headline"
    client = _FakeClient([json.dumps(stale)])

    variant = adapt_to_format(base, "instagram_story", client=client)

    prompt = variant["magic_media_prompt"]
    assert "negative space at the bottom" in prompt
    assert "negative space at the top" not in prompt
    # The unrelated camera-angle phrase must be preserved.
    assert "top-down espresso cup" in prompt


def test_adapt_to_format_retries_then_raises_on_unhealable_failure():
    # A forbidden chat phrase is NOT something zone-reconciliation can fix, so
    # the retry-then-raise path still works for genuine validation failures.
    base = _load_base_card()
    chatty = dict(VALID_STORY_ADAPTATION)
    chatty["direct_action_tip"] = ["Sure, here is your story layout.", "Add a heading."]
    client = _FakeClient([json.dumps(chatty), json.dumps(chatty)])

    with pytest.raises(PromptValidationError):
        adapt_to_format(base, "instagram_story", client=client)
    assert len(client.calls) == 2  # exhausted both attempts


def test_generate_omni_channel_set_calls_adapt_for_each_format():
    base = _load_base_card()
    client = _FakeClient([json.dumps(VALID_STORY_ADAPTATION), json.dumps(VALID_STORY_ADAPTATION)])

    variants = generate_omni_channel_set(base, ["instagram_story", "banner"], client=client)

    assert set(variants) == {"instagram_story", "banner"}
    assert variants["banner"]["aspect_ratio"] == TARGET_FORMATS["banner"]


def test_adapt_injects_format_specific_composition_for_story():
    base = _load_base_card()
    client = _FakeClient([json.dumps(VALID_STORY_ADAPTATION)])
    adapt_to_format(base, "instagram_story", client=client)
    system_msg = client.calls[0]["messages"][0]["content"]
    assert "FORMAT-SPECIFIC COMPOSITION" in system_msg
    assert "vertical leading lines" in system_msg  # 9:16 recipe
    assert "golden-ratio" not in system_msg


STYLE_STORY_ADAPTATION = {
    "text_zone": "center",
    "magic_media_prompt": (
        "High contrast monochromatic black and white base, deep shadows, distressed grunge "
        "texture, a single vibrant neon accent, tall vertical framing, vast dark negative "
        "space at the center for bold typography."
    ),
    "background_layers": "image fills the frame; a dark panel behind the center carries the headline/subtext",
    "direct_action_tip": [
        "Open Canva > Apps > Magic Media, paste magic_media_prompt, generate at 9:16 (1080x1920).",
        "Add a Heading text box centered in the frame.",
    ],
}


def test_adapt_injects_style_preset_and_preserves_keywords():
    from src.style_presets import load_style

    style = load_style("neo-grunge-streetwear")
    base = _load_base_card()
    client = _FakeClient([json.dumps(STYLE_STORY_ADAPTATION)])

    variant = adapt_to_format(base, "instagram_story", style=style, client=client)

    system_msg = client.calls[0]["messages"][0]["content"]
    assert "Neo-Grunge Streetwear" in system_msg
    assert "distressed grunge texture" in system_msg  # required keyword reminder
    # style compliance held on the adapted variant
    assert "distressed grunge texture" in variant["magic_media_prompt"]


def test_adapt_rejects_variant_that_drops_style_keywords():
    from src.style_presets import load_style

    style = load_style("neo-grunge-streetwear")
    base = _load_base_card()
    # An adaptation that forgot the grunge keywords entirely (twice -> exhausts retries).
    dropped = dict(STYLE_STORY_ADAPTATION)
    dropped["magic_media_prompt"] = (
        "A soft pastel watercolor scene, gentle light, ample negative space at the center for text."
    )
    client = _FakeClient([json.dumps(dropped), json.dumps(dropped)])

    with pytest.raises(PromptValidationError, match="style keyword"):
        adapt_to_format(base, "instagram_story", style=style, client=client)


def test_adapt_injects_horizontal_composition_for_banner():
    base = _load_base_card()
    banner_adaptation = dict(VALID_STORY_ADAPTATION)
    banner_adaptation["text_zone"] = "left"
    banner_adaptation["magic_media_prompt"] = (
        "A minimalist 3d flat vector illustration for a specialty coffee shop grand "
        "opening, earthy terracotta and warm cream color palette, wide horizontal "
        "framing with the espresso cup offset to the right, ample negative space on "
        "the left for overlaying text in Canva, isolated on a plain background."
    )
    banner_adaptation["background_layers"] = (
        "generated image fills the frame; a clean panel on the left carries the headline/subtext"
    )
    client = _FakeClient([json.dumps(banner_adaptation)])
    adapt_to_format(base, "banner", client=client)
    system_msg = client.calls[0]["messages"][0]["content"]
    assert "dynamic horizontal framing" in system_msg  # 16:9 recipe
    assert "panoramic" in system_msg
