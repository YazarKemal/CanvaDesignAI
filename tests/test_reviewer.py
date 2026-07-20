import json
from types import SimpleNamespace

from src.brand_profiles import load_brand
from src.reviewer import review_prompt

CARD = {
    "concept": "Grand Opening Cafe",
    "magic_media_prompt": "A minimalist flat vector espresso cup, terracotta palette, negative space at top.",
    "negative_prompt": "embedded text, watermark",
    "aspect_ratio": "1:1 (1080x1080)",
    "target_tool": "Canva Magic Media",
    "layer_typography_architecture": {
        "headline": "Grand Opening",
        "subtext": "Freshly roasted, every morning.",
        "color_palette": ["#4A2E1B", "#D4A373", "#F5EFE6"],
        "fonts": {"headline_font": "Montserrat Bold", "body_font": "Playfair Display"},
        "background_layers": "image fills bottom 60%; cream panel behind top 40%",
    },
    "direct_action_tip": ["Open Magic Media and paste the prompt.", "Add a heading text box."],
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
    reply = json.dumps({"score": 8.5, "criteria_scores": {"format_discipline": 10}, "feedback": ""})
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


def test_review_prompt_embeds_card_and_rubric_in_request():
    reply = json.dumps({"score": 9.0, "criteria_scores": {}, "feedback": ""})
    client = _FakeOpenAIClient(reply)
    review_prompt(CARD, client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    assert "format_discipline" in system_msg
    assert "brand_fit" in system_msg  # rubric criterion always present
    user_msg = client.captured_kwargs["messages"][1]["content"]
    assert "Grand Opening Cafe" in user_msg


def test_review_prompt_embeds_brand_profile_when_active():
    brand = load_brand("example-cafe")
    reply = json.dumps({"score": 9.0, "criteria_scores": {"brand_fit": 9}, "feedback": ""})
    client = _FakeOpenAIClient(reply)
    review_prompt(CARD, brand=brand, client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    assert "BRAND PROFILE" in system_msg
    assert "example-cafe" in system_msg


def test_review_prompt_without_brand_omits_brand_section():
    reply = json.dumps({"score": 9.0, "criteria_scores": {}, "feedback": ""})
    client = _FakeOpenAIClient(reply)
    review_prompt(CARD, client=client)
    system_msg = client.captured_kwargs["messages"][0]["content"]
    assert "BRAND PROFILE" not in system_msg
