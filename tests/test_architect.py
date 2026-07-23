import json
from types import SimpleNamespace

import pytest

from src.architect import build_brief
from src.brand_profiles import load_brand

BRIEF = {
    "detected_category": "instagram_post",
    "aspect_ratio": "1:1 (1080x1080)",
    "target_tool": "Canva Magic Media",
    "magic_media_style": "Minimalist",
    "art_direction": {
        "color_palette": ["terracotta", "cream", "espresso brown"],
        "lighting": "soft natural daylight",
        "mood": "minimalist, vintage",
    },
    "canva_keywords": ["flat vector illustration", "isolated element on transparent background"],
    "negative_constraints": "reserve empty negative space at the top; no embedded text",
}


class _FakeOpenAIClient:
    def __init__(self, reply_content: str):
        self._reply_content = reply_content
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.captured_kwargs = None

    def _create(self, **kwargs):
        self.captured_kwargs = kwargs
        message = SimpleNamespace(content=self._reply_content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_build_brief_parses_json_and_injects_category_hint():
    client = _FakeOpenAIClient(json.dumps(BRIEF))
    brief = build_brief("Kadikoy icin instagram gonderisi, minimalist vintage", client=client)

    assert brief["aspect_ratio"] == "1:1 (1080x1080)"
    user_msg = client.captured_kwargs["messages"][1]["content"]
    # The keyword match should surface a category hint for the model.
    assert "instagram_post" in user_msg


def test_build_brief_strips_markdown_fences():
    fenced = f"```json\n{json.dumps(BRIEF)}\n```"
    client = _FakeOpenAIClient(fenced)
    brief = build_brief("a poster", client=client)
    assert brief["target_tool"] == "Canva Magic Media"


def test_build_brief_raises_on_bad_json():
    client = _FakeOpenAIClient("not json at all")
    with pytest.raises(ValueError):
        build_brief("a flyer", client=client)


def test_build_brief_embeds_brand_and_logo_zone_when_brand_given():
    brand = load_brand("example-cafe")
    client = _FakeOpenAIClient(json.dumps(BRIEF))
    build_brief("Grand Opening Cafe", brand=brand, client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    assert "BRAND PROFILE" in system_msg
    assert "bottom-right" in system_msg  # brand's logo.placement_zone


def test_build_brief_without_brand_omits_brand_section():
    client = _FakeOpenAIClient(json.dumps(BRIEF))
    build_brief("Grand Opening Cafe", client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    assert "BRAND PROFILE" not in system_msg


def test_build_brief_steers_art_direction_with_aesthetic_taxonomy():
    client = _FakeOpenAIClient(json.dumps(BRIEF))
    build_brief("a cafe post", client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    assert "professional design taxonomy" in system_msg
    assert "never" in system_msg.lower() and "generic adjectives" in system_msg


def test_build_brief_without_manual_style_includes_auto_style_menu():
    """When no style is manually selected, the Architect's system prompt
    must include the AVAILABLE STYLE PRESETS menu so it can auto-pick a
    style — BUT only when the Auto Style Injector does NOT already match
    a keyword.  An ambiguous request like 'a coffee shop instagram post'
    triggers the auto-injector (cafe/coffee keywords), so the menu is
    omitted because a style IS now active.  Requests with no keyword
    hits still get the full menu."""
    client = _FakeOpenAIClient(json.dumps(BRIEF))
    build_brief("a generic design with no specific keywords", client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    assert "AVAILABLE STYLE PRESETS" in system_msg
    assert "selected_style_id" in system_msg
    # The menu should list multiple presets
    assert "warm-editorial-minimalist" in system_msg
    assert "bauhaus-modernist-poster" in system_msg


def test_build_brief_with_manual_style_omits_auto_style_menu():
    """When a manual style IS selected, the auto-selection menu must NOT
    appear — user override takes precedence."""
    from src.style_presets import load_style

    style = load_style("kodachrome-americana")
    client = _FakeOpenAIClient(json.dumps(BRIEF))
    build_brief("a travel post", style=style, client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    assert "AVAILABLE STYLE PRESETS" not in system_msg
    assert "ELITE STYLE PRESET" in system_msg  # manual style block is shown
    # The requirement #9 must not reference the auto-selection menu
    assert "from the AVAILABLE STYLE PRESETS list above" not in system_msg


def test_build_brief_output_includes_selected_style_id():
    """The Architect's brief output MUST include a selected_style_id field
    when auto-style is active, matching one of the available preset slugs."""
    from src.style_presets import list_styles

    # Make a brief that includes a valid selected_style_id
    brief_with_style = dict(BRIEF, selected_style_id="warm-editorial-minimalist")
    client = _FakeOpenAIClient(json.dumps(brief_with_style))
    brief = build_brief("a calm lifestyle carousel", client=client)
    assert "selected_style_id" in brief
    assert brief["selected_style_id"] in list_styles()
