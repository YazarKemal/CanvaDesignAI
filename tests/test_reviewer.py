import json
from types import SimpleNamespace

from src.reviewer import review_design

DRAFT = {
    "theme": "Modern Cafe",
    "color_palette": ["#4A2E1B", "#F5EFE6", "#D4A373"],
    "typography": {"headline": "Montserrat Bold", "body_text": "Join us!"},
    "image_prompts": {"main_visual": "A latte with micro-foam art."},
    "layout_instructions": "Top 40% text, bottom 60% visual.",
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


def test_review_design_pass():
    reply = json.dumps({"score": 9.1, "criteria_scores": {"contrast_compliance": 9}, "feedback": ""})
    client = _FakeOpenAIClient(reply)
    result = review_design(DRAFT, client=client)
    assert result.passed is True
    assert result.score == 9.1


def test_review_design_fail_below_threshold():
    reply = json.dumps({"score": 5.5, "criteria_scores": {}, "feedback": "Increase text contrast."})
    client = _FakeOpenAIClient(reply)
    result = review_design(DRAFT, client=client)
    assert result.passed is False
    assert "contrast" in result.feedback.lower()


def test_review_design_strips_markdown_fences():
    fenced = "```json\n" + json.dumps({"score": 8.5, "criteria_scores": {}, "feedback": ""}) + "\n```"
    client = _FakeOpenAIClient(fenced)
    result = review_design(DRAFT, client=client)
    assert result.passed is True
