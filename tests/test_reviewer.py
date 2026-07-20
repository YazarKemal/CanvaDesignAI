import json
from types import SimpleNamespace

from src.reviewer import review_prompt

CARD = {
    "concept": "Grand Opening Cafe",
    "prompt_text": "A minimalist flat vector espresso cup, terracotta palette, negative space at top.",
    "negative_prompt": "embedded text, watermark",
    "aspect_ratio": "1:1 (1080x1080)",
    "target_tool": "Canva Magic Media",
    "canva_tip": "Add your headline up top.",
    "art_direction": {"color_palette": ["terracotta", "cream", "espresso"], "lighting": "daylight", "mood": "minimalist"},
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


def test_review_prompt_pass_at_threshold():
    # pass_threshold is 8.5 in the constitution.
    reply = json.dumps({"score": 8.5, "criteria_scores": {"canva_fit": 9}, "feedback": ""})
    client = _FakeOpenAIClient(reply)
    result = review_prompt(CARD, client=client)
    assert result.passed is True
    assert result.score == 8.5


def test_review_prompt_fail_just_below_threshold():
    reply = json.dumps({"score": 8.4, "criteria_scores": {}, "feedback": "Reserve more negative space."})
    client = _FakeOpenAIClient(reply)
    result = review_prompt(CARD, client=client)
    assert result.passed is False
    assert "negative space" in result.feedback.lower()


def test_review_prompt_strips_markdown_fences():
    fenced = "```json\n" + json.dumps({"score": 9.0, "criteria_scores": {}, "feedback": ""}) + "\n```"
    client = _FakeOpenAIClient(fenced)
    result = review_prompt(CARD, client=client)
    assert result.passed is True
