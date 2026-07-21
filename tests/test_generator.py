import json
from types import SimpleNamespace

import pytest

from src.brand_profiles import load_brand
from src.generator import generate_prompt
from src.schema import PromptValidationError
from src.style_presets import load_style

BRIEF = {
    "aspect_ratio": "1:1 (1080x1080)",
    "target_tool": "Canva Magic Media",
    "text_zone": "top",
    "art_direction": {"color_palette": ["#4A2E1B", "#D4A373", "#F5EFE6"], "lighting": "daylight", "mood": "minimalist"},
    "canva_keywords": ["flat vector illustration"],
    "negative_constraints": "empty top for text; no embedded text",
}

VALID_CARD = {
    "concept": "Grand Opening Cafe",
    "magic_media_prompt": (
        "A minimalist flat vector illustration for a specialty coffee shop opening, "
        "terracotta and cream palette, top-down espresso cup, ample negative space at "
        "the top for overlaid text, isolated on a plain background."
    ),
    "negative_prompt": "embedded text, watermark, clutter",
    "aspect_ratio": "1:1 (1080x1080)",
    "target_tool": "Canva Magic Media",
    "text_zone": "top",
    "layer_typography_architecture": {
        "headline": "Grand Opening",
        "subtext": "Freshly roasted, every morning.",
        "color_palette": ["#4A2E1B", "#D4A373", "#F5EFE6"],
        "fonts": {"headline_font": "Montserrat Bold", "body_font": "Playfair Display"},
        "background_layers": "image fills bottom 60%; cream panel behind top 40%",
    },
    "direct_action_tip": [
        "Open Magic Media and paste the prompt.",
        "Add a heading text box with the headline.",
    ],
    "canva_keywords": ["flat vector illustration"],
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


def test_generate_prompt_parses_card_and_embeds_brief():
    client = _FakeOpenAIClient(json.dumps(VALID_CARD))
    card = generate_prompt(BRIEF, concept="Grand Opening Cafe", client=client)
    assert card["magic_media_prompt"].startswith("A minimalist flat vector")
    sent = client.captured_kwargs["messages"][1]["content"]
    assert "Original concept: Grand Opening Cafe" in sent
    assert "Canva Magic Media" in sent  # brief was embedded


def test_generate_prompt_strips_markdown_fences():
    fenced = f"```json\n{json.dumps(VALID_CARD)}\n```"
    client = _FakeOpenAIClient(fenced)
    card = generate_prompt(BRIEF, concept="Grand Opening Cafe", client=client)
    assert card["aspect_ratio"] == "1:1 (1080x1080)"


def test_generate_prompt_recovers_json_wrapped_in_stray_prose():
    # Defense-in-depth: model ignored "raw JSON only" and added a wrapper sentence.
    wrapped = "Sure thing, here is the data:\n" + json.dumps(VALID_CARD) + "\nLet me know!"
    client = _FakeOpenAIClient(wrapped)
    # The chat wrapper text is outside the JSON, so the extracted card itself is clean.
    card = generate_prompt(BRIEF, concept="Grand Opening Cafe", client=client)
    assert card["concept"] == "Grand Opening Cafe"


def test_generate_prompt_defaults_concept_when_missing():
    card_without_concept = {k: v for k, v in VALID_CARD.items() if k != "concept"}
    client = _FakeOpenAIClient(json.dumps(card_without_concept))
    card = generate_prompt(BRIEF, concept="Fallback Concept", client=client)
    assert card["concept"] == "Fallback Concept"


def test_generate_prompt_includes_feedback_on_retry():
    client = _FakeOpenAIClient(json.dumps(VALID_CARD))
    generate_prompt(BRIEF, concept="Cafe", feedback="Add more negative space.", client=client)
    sent = client.captured_kwargs["messages"][1]["content"]
    assert "Add more negative space." in sent


def test_generate_prompt_raises_on_forbidden_chat_phrase():
    chatty_card = dict(VALID_CARD)
    chatty_card["magic_media_prompt"] = VALID_CARD["magic_media_prompt"] + " Would you like any changes?"
    client = _FakeOpenAIClient(json.dumps(chatty_card))
    with pytest.raises(PromptValidationError):
        generate_prompt(BRIEF, concept="Cafe", client=client)


def test_default_client_uses_deepseek_via_openai_sdk_even_with_anthropic_key_set(monkeypatch):
    # Single-engine architecture: an ANTHROPIC_API_KEY in the environment
    # must never route the Generator to Claude -- DeepSeek is the only engine.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-be-ignored")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test")
    import src.generator as generator_module

    client = generator_module._default_client()
    assert "deepseek" in str(client.base_url).lower()


def test_default_client_falls_back_to_http_client_when_openai_sdk_missing(monkeypatch):
    import src.generator as generator_module
    from src.http_client import DeepSeekClient

    monkeypatch.setattr(generator_module, "OpenAI", None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test")

    client = generator_module._default_client()
    assert isinstance(client, DeepSeekClient)


def test_generator_module_has_no_anthropic_import():
    import src.generator as generator_module

    assert not hasattr(generator_module, "anthropic")


def test_generate_prompt_embeds_brand_profile_in_system_prompt():
    brand = load_brand("example-cafe")
    client = _FakeOpenAIClient(json.dumps(VALID_CARD))  # VALID_CARD already matches this brand
    generate_prompt(BRIEF, concept="Grand Opening Cafe", brand=brand, client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    assert "BRAND PROFILE" in system_msg
    assert "example-cafe" in system_msg


def test_generate_prompt_rejects_off_brand_font_when_brand_active():
    brand = load_brand("example-cafe")
    off_brand_card = json.loads(json.dumps(VALID_CARD))
    off_brand_card["layer_typography_architecture"]["fonts"]["headline_font"] = "Anton"
    client = _FakeOpenAIClient(json.dumps(off_brand_card))

    with pytest.raises(PromptValidationError, match="headline_font"):
        generate_prompt(BRIEF, concept="Grand Opening Cafe", brand=brand, client=client)


def test_generate_prompt_without_brand_ignores_font_choice():
    off_brand_card = json.loads(json.dumps(VALID_CARD))
    off_brand_card["layer_typography_architecture"]["fonts"]["headline_font"] = "Anton"
    client = _FakeOpenAIClient(json.dumps(off_brand_card))

    card = generate_prompt(BRIEF, concept="Grand Opening Cafe", client=client)  # no brand
    assert card["layer_typography_architecture"]["fonts"]["headline_font"] == "Anton"


def test_generate_prompt_injects_format_specific_composition_from_brief():
    # The 1:1 brief must steer the system prompt toward square/studio composition
    # and the locked text_zone's precise negative-space language.
    client = _FakeOpenAIClient(json.dumps(VALID_CARD))
    generate_prompt(BRIEF, concept="Grand Opening Cafe", client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    assert "FORMAT-SPECIFIC COMPOSITION" in system_msg
    assert "golden-ratio" in system_msg  # 1:1 recipe
    assert "text_zone 'top'" in system_msg
    assert "top 40%" in system_msg  # 1:1 top negative-space line


def test_generate_prompt_composition_varies_by_aspect_ratio():
    story_brief = dict(BRIEF, aspect_ratio="9:16 (1080x1920)", text_zone="center")
    client = _FakeOpenAIClient(json.dumps(VALID_CARD))
    generate_prompt(story_brief, concept="Cafe", client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    assert "vertical leading lines" in system_msg  # 9:16 recipe, not the 1:1 one
    assert "golden-ratio" not in system_msg


def test_generate_prompt_embeds_brand_visual_identity_in_image_steering():
    brand = load_brand("example-cafe")
    client = _FakeOpenAIClient(json.dumps(VALID_CARD))
    generate_prompt(BRIEF, concept="Grand Opening Cafe", brand=brand, client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    assert "BRAND VISUAL IDENTITY" in system_msg
    assert "warm oak wood grain" in system_msg  # texture cue must reach the image prompt


def test_style_overrides_brand_visual_identity_when_both_active():
    """When both brand and style are active, brand visual_identity keywords
    (mood, textures, photographic style) must NOT appear — the style
    preset's visual architecture wins."""
    brand = load_brand("example-cafe")
    style = load_style("corporate-dynamic-vector")
    # Build a card whose magic_media_prompt carries the corporate style's
    # required_keywords and whose fonts/colors match the example-cafe brand.
    corporate_card = json.loads(json.dumps(VALID_CARD))
    corporate_card["magic_media_prompt"] = (
        "Ultra-clean modern corporate aesthetic hero shot, smooth gradient background, "
        "sharp 3D vector wave elements at the borders, brilliant softbox lighting, a "
        "highly isolated subject, empty negative space at the top for bold typography."
    )
    corporate_card["layer_typography_architecture"]["fonts"] = {
        "headline_font": "Montserrat Bold", "body_font": "Playfair Display"
    }
    corporate_card["layer_typography_architecture"]["color_palette"] = ["#4A2E1B", "#D4A373", "#F5EFE6"]
    client = _FakeOpenAIClient(json.dumps(corporate_card))
    generate_prompt(BRIEF, concept="Corporate cafe graphic", brand=brand, style=style, client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    # Style override rule must be present
    assert "STYLE OVERRIDE RULE" in system_msg
    # Brand visual identity's explicit block header must NOT appear (it's suppressed)
    assert "BRAND VISUAL IDENTITY" not in system_msg
    # The brand's visual_identity key must be stripped from the embedded JSON
    assert '"visual_identity"' not in system_msg
    # But brand typography/color constraints must still be present
    assert "BRAND PROFILE" in system_msg
    assert "Montserrat Bold" in system_msg
    # Style keywords must be present
    assert "ELITE STYLE PRESET" in system_msg
    assert "modern corporate aesthetic" in system_msg


def test_style_overrides_magic_media_prompt_opening_instruction():
    """When a style is active (with or without brand), the magic_media_prompt
    rule must instruct the LLM to open with the style's keywords first."""
    style = load_style("holographic-glassmorphism")
    # Card with holographic required keywords
    holo_card = json.loads(json.dumps(VALID_CARD))
    holo_card["magic_media_prompt"] = (
        "Iridescent dark purple and neon chrome gradients wash across a smooth "
        "glassmorphism surface with layered depth, soft glowing glass refraction, "
        "shimmering holographic fluid background, a clean flat vector iconic icon "
        "in the center, empty top area for text overlay."
    )
    client = _FakeOpenAIClient(json.dumps(holo_card))
    generate_prompt(BRIEF, concept="Holo poster", style=style, client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    assert "MUST OPEN with the Style Preset" in system_msg


def test_brand_visual_identity_still_active_when_no_style():
    """Without a style preset, the brand's visual_identity must still steer
    the image prompt (backward-compatible behavior)."""
    brand = load_brand("example-cafe")
    client = _FakeOpenAIClient(json.dumps(VALID_CARD))
    generate_prompt(BRIEF, concept="Grand Opening Cafe", brand=brand, client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    assert "BRAND VISUAL IDENTITY" in system_msg
    assert "warm oak wood grain" in system_msg
    assert "STYLE OVERRIDE RULE" not in system_msg


def test_brand_without_visual_identity_works_with_style():
    """A brand that has no visual_identity block should still work cleanly
    when combined with a style preset — no crash, no orphaned override text."""
    bare_brand = {
        "slug": "bare-brand",
        "name": "Bare Brand",
        "signature_fonts": {"headline_font": "Inter", "body_font": "Inter"},
        "approved_colors": {"primary": ["#111111"], "secondary": ["#EEEEEE"], "accent": ["#39FF14"]},
    }
    style = load_style("corporate-dynamic-vector")
    bare_card = json.loads(json.dumps(VALID_CARD))
    bare_card["magic_media_prompt"] = (
        "Ultra-clean modern corporate aesthetic hero shot, smooth gradient background, "
        "sharp 3D vector wave elements at the borders, brilliant softbox lighting, a "
        "highly isolated subject, empty negative space at the top for bold typography."
    )
    bare_card["layer_typography_architecture"]["fonts"] = {"headline_font": "Inter", "body_font": "Inter"}
    bare_card["layer_typography_architecture"]["color_palette"] = ["#111111", "#EEEEEE", "#39FF14"]
    client = _FakeOpenAIClient(json.dumps(bare_card))
    card = generate_prompt(BRIEF, concept="Bare brand + style", brand=bare_brand, style=style, client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    assert "ELITE STYLE PRESET" in system_msg
    assert "STYLE OVERRIDE RULE" in system_msg
    assert "BRAND PROFILE" in system_msg
    assert card["layer_typography_architecture"]["fonts"]["headline_font"] == "Inter"


# A card whose magic_media_prompt actually contains the neo-grunge required
# keywords AND references text_zone 'top', with a high-contrast monochrome+neon
# palette so it also passes the contrast check.
STYLE_CARD = json.loads(json.dumps(VALID_CARD))
STYLE_CARD["magic_media_prompt"] = (
    "High contrast monochromatic black and white base of a lone figure, deep shadows, "
    "distressed grunge texture, a single vibrant neon green spray paint accent, edgy "
    "underground aesthetic, vast dark negative space at the top for bold typography."
)
STYLE_CARD["layer_typography_architecture"]["color_palette"] = ["#0A0A0A", "#F5F5F5", "#39FF14"]
STYLE_CARD["layer_typography_architecture"]["background_layers"] = (
    "image fills the frame; dark panel behind the top carries the headline/subtext"
)


def test_generate_prompt_injects_style_preset_block():
    style = load_style("neo-grunge-streetwear")
    client = _FakeOpenAIClient(json.dumps(STYLE_CARD))
    generate_prompt(BRIEF, concept="Underground gig poster", style=style, client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    assert "ELITE STYLE PRESET" in system_msg
    assert "distressed grunge texture" in system_msg  # verbatim keyword block


def test_generate_prompt_accepts_card_that_carries_required_style_keywords():
    style = load_style("neo-grunge-streetwear")
    client = _FakeOpenAIClient(json.dumps(STYLE_CARD))
    card = generate_prompt(BRIEF, concept="Underground gig poster", style=style, client=client)
    assert "distressed grunge texture" in card["magic_media_prompt"]


def test_generate_prompt_rejects_card_missing_required_style_keyword():
    style = load_style("neo-grunge-streetwear")
    off_style = json.loads(json.dumps(VALID_CARD))  # generic prompt, no grunge keywords
    client = _FakeOpenAIClient(json.dumps(off_style))
    with pytest.raises(PromptValidationError, match="style keyword"):
        generate_prompt(BRIEF, concept="Underground gig poster", style=style, client=client)


# -- Few-shot golden card injection tests ---------------------------------


def test_generator_injects_golden_card_when_style_has_match():
    """When the active style has a golden reference card, the system prompt
    must include the GOLDEN REFERENCE CARD block with the matching style_id."""
    style = load_style("warm-editorial-minimalist")
    # Build a card that carries warm-editorial-minimalist required keywords
    warm_card = json.loads(json.dumps(VALID_CARD))
    warm_card["magic_media_prompt"] = (
        "Warm editorial minimalist lifestyle composition with a thin-line "
        "ornamental border, soft natural morning window light, cream paper "
        "texture background, aged terracotta accents, high-end editorial "
        "photography register, generous airy negative space at the top, a "
        "single ceramic cup on linen."
    )
    client = _FakeOpenAIClient(json.dumps(warm_card))
    generate_prompt(BRIEF, concept="Calm lifestyle post", style=style, client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    assert "GOLDEN REFERENCE CARD" in system_msg
    assert "warm-editorial-minimalist" in system_msg
    assert "9." in system_msg  # score


def test_generator_skips_golden_card_for_unknown_style_silently():
    """A style_id with no golden card must NOT crash — the injection is
    silently skipped and the prompt is built normally."""
    unknown_style = {
        "slug": "future-unreleased-style",
        "name": "Future Unreleased",
        "magic_media_keywords": "some keywords for testing purposes",
        "required_keywords": ["some keywords", "testing"],
        "recommended_magic_media_style": "Flat Vector",
        "palette_hint": "#111 #EEE",
        "best_for": "testing edge cases",
    }
    test_card = json.loads(json.dumps(VALID_CARD))
    test_card["magic_media_prompt"] = (
        "A test image with some keywords for testing purposes, flat vector "
        "illustration style, empty negative space at the top."
    )
    test_card["concept"] = "Test"  # override VALID_CARD's default concept
    client = _FakeOpenAIClient(json.dumps(test_card))
    card = generate_prompt(BRIEF, concept="Test", style=unknown_style, client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    assert "GOLDEN REFERENCE CARD" not in system_msg
    assert "ELITE STYLE PRESET" in system_msg  # normal style block still present
    assert card["concept"] == "Test"


def test_golden_card_injection_does_not_change_llm_call_count():
    """Few-shot injection is a prompt-content addition, NOT an extra API
    call. The Generator must still make exactly ONE .create() call."""
    style = load_style("kodachrome-americana")
    # Card with kodachrome required keywords
    koda_card = json.loads(json.dumps(VALID_CARD))
    koda_card["magic_media_prompt"] = (
        "1970s Kodachrome color documentary photography of a vintage roadside "
        "diner, saturated warm reds, deep teal shadows, fine analog film grain, "
        "golden-hour rim light with long shadows, quiet roadside Americana "
        "stillness, empty sky at the top for text."
    )
    client = _FakeOpenAIClient(json.dumps(koda_card))
    generate_prompt(BRIEF, concept="Roadside diner post", style=style, client=client)

    # The fake client captures exactly one call per generate_prompt invocation
    assert client.captured_kwargs is not None
    assert client.captured_kwargs["model"] == "deepseek-chat"
    assert len(client.captured_kwargs["messages"]) == 2
