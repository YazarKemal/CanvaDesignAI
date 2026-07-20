import json
from types import SimpleNamespace

from src.generator import generate_design

VALID_DRAFT = {
    "theme": "Modern Cafe",
    "color_palette": ["#4A2E1B", "#F5EFE6", "#D4A373"],
    "typography": {
        "headline": "Montserrat Bold: [Cafe Name]",
        "body_text": "Join us for warm vibes!",
    },
    "image_prompts": {
        "main_visual": "Cinematic shot of a latte with micro-foam art on a wooden table.",
    },
    "layout_instructions": "Place text at the top 40% of the canvas.",
}


class _FakeAnthropicClient:
    def __init__(self, reply_text: str):
        self._reply_text = reply_text
        self.messages = SimpleNamespace(create=self._create)
        self.captured_kwargs = None

    def _create(self, **kwargs):
        self.captured_kwargs = kwargs
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self._reply_text)])


def test_generate_design_parses_valid_json_reply():
    client = _FakeAnthropicClient(json.dumps(VALID_DRAFT))
    draft = generate_design("Grand Opening Cafe", client=client)
    assert draft["theme"] == "Modern Cafe"
    assert client.captured_kwargs["messages"][0]["content"].startswith("Design concept: Grand Opening Cafe")


def test_generate_design_strips_markdown_fences():
    fenced = f"```json\n{json.dumps(VALID_DRAFT)}\n```"
    client = _FakeAnthropicClient(fenced)
    draft = generate_design("Grand Opening Cafe", client=client)
    assert draft["color_palette"] == VALID_DRAFT["color_palette"]


def test_generate_design_includes_feedback_in_prompt_on_retry():
    client = _FakeAnthropicClient(json.dumps(VALID_DRAFT))
    generate_design("Grand Opening Cafe", feedback="Fix contrast on headline.", client=client)
    sent = client.captured_kwargs["messages"][0]["content"]
    assert "Fix contrast on headline." in sent
