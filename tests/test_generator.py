import json
from types import SimpleNamespace

import pytest

from src.generator import generate_prompt
from src.schema import PromptValidationError

BRIEF = {
    "aspect_ratio": "1:1 (1080x1080)",
    "target_tool": "Canva Magic Media",
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
