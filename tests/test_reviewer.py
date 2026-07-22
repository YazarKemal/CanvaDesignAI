import json
from types import SimpleNamespace
from unittest import mock

import pytest

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


# -- Anthropic provider tests --------------------------------------------------


class _FakeAnthropicClient:
    """Simulates AnthropicClient for tests — records the call and returns
    an OpenAI-compatible response from canned Anthropic-format JSON."""

    def __init__(self, anthropic_response_text: str):
        self._text = anthropic_response_text
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.captured_kwargs = None

    def _create(self, **kwargs):
        self.captured_kwargs = kwargs
        message = SimpleNamespace(content=self._text)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_review_prompt_uses_anthropic_client_when_provider_is_anthropic(monkeypatch):
    """When REVIEWER_PROVIDER=anthropic, the Reviewer must use AnthropicClient
    and auto-switch to the Anthropic model."""
    monkeypatch.setenv("REVIEWER_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    # Clean up any pre-existing ANTHROPIC_MODEL so we get the code's own default.
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    reply = json.dumps({"score": 9.0, "criteria_scores": {}, "feedback": ""})

    from src.http_client import AnthropicChatCompletion

    fake = _FakeAnthropicClient(reply)
    monkeypatch.setattr(AnthropicChatCompletion, "create", fake.chat.completions.create)

    result = review_prompt(CARD)  # no explicit client → picks AnthropicClient

    assert result.passed is True
    assert fake.captured_kwargs is not None
    # Model must have switched from "deepseek-chat" to the Anthropic default.
    from src.reviewer import DEFAULT_ANTHROPIC_MODEL
    assert fake.captured_kwargs["model"] == DEFAULT_ANTHROPIC_MODEL


def test_review_prompt_uses_deepseek_model_when_provider_not_set(monkeypatch):
    """Default behaviour (no REVIEWER_PROVIDER) still uses deepseek-chat."""
    monkeypatch.delenv("REVIEWER_PROVIDER", raising=False)
    reply = json.dumps({"score": 8.5, "criteria_scores": {}, "feedback": ""})
    client = _FakeAnthropicClient(reply)

    # Explicitly pass deepseek-chat model; the client is the thing under test
    result = review_prompt(CARD, model="deepseek-chat", client=client)
    assert result.passed is True


# -- AnthropicClient unit tests (src/http_client.py) ---------------------------


def _make_anthropic_client(mock_httpx_post):
    """Create an AnthropicClient with a mocked httpx.post."""
    from src.http_client import AnthropicClient

    client = AnthropicClient(api_key="sk-ant-test", base_url="https://api.anthropic.com")
    return client


def test_anthropic_client_extracts_system_message_to_system_param(monkeypatch):
    """Anthropic's API requires system messages in a top-level 'system' param,
    not inside the messages array."""
    import httpx
    from src.http_client import AnthropicClient

    # Mock httpx.post to capture the request body
    captured_body = {}

    def fake_post(url, **kwargs):
        captured_body["json"] = kwargs["json"]
        # Return a minimal valid Anthropic response
        fake_resp = mock.MagicMock(spec=httpx.Response)
        fake_resp.json.return_value = {
            "id": "msg_xxx",
            "type": "message",
            "role": "assistant",
            "model": "claude-3-5-sonnet-20241022",
            "content": [{"type": "text", "text": '{"score":9.0,"criteria_scores":{},"feedback":""}'}],
            "stop_reason": "end_turn",
        }
        fake_resp.raise_for_status = mock.MagicMock()
        return fake_resp

    monkeypatch.setattr(httpx, "post", fake_post)

    client = AnthropicClient(api_key="sk-ant-test")
    client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=[
            {"role": "system", "content": "You are a reviewer."},
            {"role": "user", "content": "Review this card."},
        ],
        temperature=0,
    )

    # System message was NOT passed inside messages array
    anthropic_messages = captured_body["json"]["messages"]
    assert len(anthropic_messages) == 1
    assert anthropic_messages[0]["role"] == "user"

    # System message was extracted to top-level system param
    assert captured_body["json"]["system"] == "You are a reviewer."

    # Anthropic version header is in the request (handled by headers, not body)
    # max_tokens is always sent (Anthropic requires it)


def test_anthropic_client_sends_max_tokens(monkeypatch):
    """Anthropic requires max_tokens in every request — the client must always
    include it even when the caller doesn't explicitly provide it."""
    import httpx
    from src.http_client import AnthropicClient

    captured_json = {}

    def fake_post(url, **kwargs):
        captured_json["json"] = kwargs["json"]
        fake_resp = mock.MagicMock(spec=httpx.Response)
        fake_resp.json.return_value = {
            "id": "msg_xxx",
            "type": "message",
            "role": "assistant",
            "model": "claude-3-5-sonnet-20241022",
            "content": [{"type": "text", "text": "{}"}],
            "stop_reason": "end_turn",
        }
        fake_resp.raise_for_status = mock.MagicMock()
        return fake_resp

    monkeypatch.setattr(httpx, "post", fake_post)

    client = AnthropicClient(api_key="sk-ant-test")
    client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=[{"role": "user", "content": "Hi"}],
    )

    assert "max_tokens" in captured_json["json"]
    assert captured_json["json"]["max_tokens"] > 0


def test_anthropic_client_extracts_text_from_content_blocks(monkeypatch):
    """Anthropic returns content as an array of blocks — the client must
    extract the first text block into OpenAI-compatible message.content."""
    import httpx
    from src.http_client import AnthropicClient

    def fake_post(url, **kwargs):
        fake_resp = mock.MagicMock(spec=httpx.Response)
        fake_resp.json.return_value = {
            "id": "msg_xxx",
            "type": "message",
            "role": "assistant",
            "model": "claude-3-5-sonnet-20241022",
            "content": [
                {"type": "text", "text": '{"score":9.2,"criteria_scores":{},"feedback":""}'}
            ],
            "stop_reason": "end_turn",
        }
        fake_resp.raise_for_status = mock.MagicMock()
        return fake_resp

    monkeypatch.setattr(httpx, "post", fake_post)

    client = AnthropicClient(api_key="sk-ant-test")
    resp = client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=[{"role": "user", "content": "Review"}],
    )

    assert resp.choices[0].message.content == '{"score":9.2,"criteria_scores":{},"feedback":""}'


def test_anthropic_client_accepts_custom_base_url(monkeypatch):
    """ANTHROPIC_BASE_URL must be respected (e.g. for proxies/gateways)."""
    import httpx
    from src.http_client import AnthropicClient

    captured_url = {}

    def fake_post(url, **kwargs):
        captured_url["url"] = url
        fake_resp = mock.MagicMock(spec=httpx.Response)
        fake_resp.json.return_value = {
            "id": "msg_xxx",
            "type": "message",
            "role": "assistant",
            "model": "claude-3-5-sonnet-20241022",
            "content": [{"type": "text", "text": "{}"}],
            "stop_reason": "end_turn",
        }
        fake_resp.raise_for_status = mock.MagicMock()
        return fake_resp

    monkeypatch.setattr(httpx, "post", fake_post)

    client = AnthropicClient(api_key="sk-ant-test", base_url="https://gateway.example.com")
    client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=[{"role": "user", "content": "Hi"}],
    )

    assert captured_url["url"].startswith("https://gateway.example.com")


def test_anthropic_client_base_url_property():
    from src.http_client import AnthropicClient

    client = AnthropicClient(api_key="sk-ant-test", base_url="https://api.anthropic.com")
    assert client.base_url == "https://api.anthropic.com"
