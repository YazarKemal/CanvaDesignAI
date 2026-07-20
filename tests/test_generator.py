import json
from types import SimpleNamespace

from src.generator import generate_prompt

BRIEF = {
    "aspect_ratio": "1:1 (1080x1080)",
    "target_tool": "Canva Magic Media",
    "art_direction": {"color_palette": ["terracotta", "cream", "espresso"], "lighting": "daylight", "mood": "minimalist"},
    "canva_keywords": ["flat vector illustration"],
    "negative_constraints": "empty top for text; no embedded text",
}

VALID_CARD = {
    "concept": "Grand Opening Cafe",
    "prompt_text": (
        "A minimalist flat vector illustration for a specialty coffee shop opening, "
        "terracotta and cream palette, top-down espresso cup, ample negative space at "
        "the top for overlaid text, isolated on a plain background."
    ),
    "negative_prompt": "embedded text, watermark, clutter",
    "aspect_ratio": "1:1 (1080x1080)",
    "target_tool": "Canva Magic Media",
    "canva_tip": "Drop your headline into the empty top third.",
    "art_direction": {
        "color_palette": ["terracotta", "warm cream", "espresso brown"],
        "lighting": "soft natural daylight",
        "mood": "minimalist, vintage",
        "magic_media_style": "Flat Vector",
    },
    "canva_keywords": ["flat vector illustration"],
}


class _FakeAnthropicClient:
    def __init__(self, reply_text: str):
        self._reply_text = reply_text
        self.messages = SimpleNamespace(create=self._create)
        self.captured_kwargs = None

    def _create(self, **kwargs):
        self.captured_kwargs = kwargs
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self._reply_text)])


def test_generate_prompt_parses_card_and_passes_brief():
    client = _FakeAnthropicClient(json.dumps(VALID_CARD))
    card = generate_prompt(BRIEF, concept="Grand Opening Cafe", client=client)
    assert card["prompt_text"].startswith("A minimalist flat vector")
    sent = client.captured_kwargs["messages"][0]["content"]
    assert "Original concept: Grand Opening Cafe" in sent
    assert "Canva Magic Media" in sent  # brief was embedded


def test_generate_prompt_defaults_concept_when_missing():
    card_without_concept = {k: v for k, v in VALID_CARD.items() if k != "concept"}
    client = _FakeAnthropicClient(json.dumps(card_without_concept))
    card = generate_prompt(BRIEF, concept="Fallback Concept", client=client)
    assert card["concept"] == "Fallback Concept"


def test_generate_prompt_includes_feedback_on_retry():
    client = _FakeAnthropicClient(json.dumps(VALID_CARD))
    generate_prompt(BRIEF, concept="Cafe", feedback="Add more negative space.", client=client)
    sent = client.captured_kwargs["messages"][0]["content"]
    assert "Add more negative space." in sent
