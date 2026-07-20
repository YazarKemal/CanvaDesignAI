import json
from types import SimpleNamespace

from src.reviewer import review_prompt

DRAFT = {
    "concept": "Grand Opening Cafe",
    "image_prompt": "A flat-white with rosetta latte art, photography, golden-hour light, warm tones.",
    "negative_prompt": "text, watermark",
    "art_direction": {
        "medium": "photography",
        "composition": "rule of thirds",
        "lighting": "golden hour",
        "color_palette": ["#4A2E1B", "#D4A373", "#F5EFE6"],
        "mood": "cozy",
    },
    "aspect_ratio": "4:5",
    "target_tools": ["DALL-E 3"],
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


def test_review_prompt_pass():
    reply = json.dumps({"score": 9.1, "criteria_scores": {"concept_fidelity": 9}, "feedback": ""})
    client = _FakeOpenAIClient(reply)
    result = review_prompt(DRAFT, client=client)
    assert result.passed is True
    assert result.score == 9.1


def test_review_prompt_fail_below_threshold():
    reply = json.dumps({"score": 5.5, "criteria_scores": {}, "feedback": "Specify a camera and lens."})
    client = _FakeOpenAIClient(reply)
    result = review_prompt(DRAFT, client=client)
    assert result.passed is False
    assert "camera" in result.feedback.lower()


def test_review_prompt_strips_markdown_fences():
    fenced = "```json\n" + json.dumps({"score": 8.5, "criteria_scores": {}, "feedback": ""}) + "\n```"
    client = _FakeOpenAIClient(fenced)
    result = review_prompt(DRAFT, client=client)
    assert result.passed is True
