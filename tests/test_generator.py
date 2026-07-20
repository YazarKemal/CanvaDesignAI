import json
from types import SimpleNamespace

from src.generator import generate_prompt

VALID_DRAFT = {
    "concept": "Grand Opening Cafe",
    "image_prompt": (
        "A flat-white with rosetta latte art in a matte-black cup on reclaimed oak, "
        "photography on 85mm f/1.4, rule of thirds, soft golden-hour window light, "
        "warm amber and espresso tones on cream, cozy artisanal mood, high detail."
    ),
    "negative_prompt": "text, watermark, deformed hands, cluttered background",
    "art_direction": {
        "medium": "photography",
        "composition": "rule of thirds, empty upper third",
        "lighting": "soft golden-hour window light",
        "color_palette": ["#4A2E1B", "#D4A373", "#F5EFE6"],
        "mood": "cozy, artisanal",
        "camera": "85mm f/1.4",
    },
    "aspect_ratio": "4:5",
    "target_tools": ["DALL-E 3", "Canva Magic Media"],
}


class _FakeAnthropicClient:
    def __init__(self, reply_text: str):
        self._reply_text = reply_text
        self.messages = SimpleNamespace(create=self._create)
        self.captured_kwargs = None

    def _create(self, **kwargs):
        self.captured_kwargs = kwargs
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self._reply_text)])


def test_generate_prompt_parses_valid_json_reply():
    client = _FakeAnthropicClient(json.dumps(VALID_DRAFT))
    draft = generate_prompt("Grand Opening Cafe", client=client)
    assert draft["concept"] == "Grand Opening Cafe"
    assert client.captured_kwargs["messages"][0]["content"].startswith("Concept: Grand Opening Cafe")


def test_generate_prompt_strips_markdown_fences():
    fenced = f"```json\n{json.dumps(VALID_DRAFT)}\n```"
    client = _FakeAnthropicClient(fenced)
    draft = generate_prompt("Grand Opening Cafe", client=client)
    assert draft["aspect_ratio"] == "4:5"


def test_generate_prompt_includes_feedback_on_retry():
    client = _FakeAnthropicClient(json.dumps(VALID_DRAFT))
    generate_prompt("Grand Opening Cafe", feedback="Specify the lighting direction.", client=client)
    sent = client.captured_kwargs["messages"][0]["content"]
    assert "Specify the lighting direction." in sent
