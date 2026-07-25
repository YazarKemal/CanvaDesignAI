"""Tests for src/vision_client.py — the pure-httpx OpenAI Vision client."""

import json

import httpx
import pytest

from src.vision_client import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    OpenAIVisionClient,
    VisionClientError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status_code = status
        self.text = json.dumps(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}",
                request=object(),  # type: ignore[arg-type]
                response=self,  # type: ignore[arg-type]
            )

    def json(self):
        return self._payload


def _minimal_card_json() -> str:
    return json.dumps(
        {
            "concept": "Test Template",
            "aspect_ratio": "1:1 (1080x1080)",
            "target_tool": "Canva Native Layout Engine",
            "text_zone": "top",
            "canva_keywords": ["editorial", "minimal"],
            "raster_background": {
                "magic_media_prompt": "A Canva stock photo search query for a warm coffee shop interior...",
                "negative_prompt": "no AI-generated imagery, no text, no watermark",
                "layout_style": "Minimalist",
            },
            "vector_elements": {
                "thin_divider": "horizontal 0.5px rule in muted gold at 60% opacity",
            },
            "native_typography": {
                "headline": "Hello World",
                "subtext": "A short subtext.",
                "headline_pt": 72,
                "subtext_pt": 18,
                "color_palette": ["#3B2A1E", "#B8936E", "#E8DDD0", "#8B9D6B", "#D4C5B9"],
                "fonts": {"headline_font": "Montserrat Bold", "body_font": "Cormorant Garamond Regular"},
                "alignment_zone": "top 30% of canvas, left-aligned with 48px margin",
                "micro_tags": {
                    "volume_line": "VOL.01 / 2026",
                    "category_line": "EDITORIAL BRANDING",
                    "origin_line": "CRAFTED IN TURKEY",
                    "micro_pt": 9,
                    "micro_color": "#B8936E",
                    "micro_font": "Inter Regular",
                    "micro_spacing": "24 px below subtext",
                },
            },
            "direct_action_tip": ["Step 1: Do X", "Step 2: Do Y"],
        }
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_raises_when_api_key_missing(monkeypatch):
    """A missing API key should raise VisionClientError immediately, not
    silently proceed with an empty key."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(VisionClientError, match="OPENAI_API_KEY"):
        OpenAIVisionClient(api_key="")


def test_sends_correct_payload_shape(monkeypatch):
    """The HTTP request body must match OpenAI's chat/completions vision format:
    base64 data URL inside image_url, model set, and Authorization header."""
    captured = {}

    def fake_post(url, *, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["body"] = json
        captured["headers"] = headers
        return _FakeResponse({"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    client = OpenAIVisionClient(api_key="sk-test-vision")
    result = client.deconstruct_image(b"\x89PNGfake", "image/png", prompt="Describe this.")

    # Verify the request went to the right endpoint
    assert "/v1/chat/completions" in captured["url"]

    body = captured["body"]
    assert body["model"] == DEFAULT_MODEL
    assert body["max_tokens"] == 4096
    assert body["temperature"] == 0.0

    # Messages structure
    messages = body["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"

    content_parts = messages[0]["content"]
    assert len(content_parts) == 2

    # First part: text prompt
    assert content_parts[0]["type"] == "text"
    assert content_parts[0]["text"] == "Describe this."

    # Second part: image_url with base64 data URL
    assert content_parts[1]["type"] == "image_url"
    img = content_parts[1]["image_url"]
    assert img["detail"] == "high"
    assert img["url"].startswith("data:image/png;base64,")

    # Auth header
    assert captured["headers"]["Authorization"] == "Bearer sk-test-vision"

    # Result
    assert result == "{}"


def test_extracts_content_from_valid_response(monkeypatch):
    """A well-formed response should return the message content string."""
    expected = _minimal_card_json()

    def fake_post(url, *, json=None, headers=None, timeout=None):
        return _FakeResponse({"choices": [{"message": {"content": expected}}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    client = OpenAIVisionClient(api_key="sk-test-vision")
    result = client.deconstruct_image(b"fake", "image/jpeg", prompt="x")
    assert result == expected


def test_raises_on_empty_content(monkeypatch):
    """An empty content string should raise VisionClientError."""
    def fake_post(url, *, json=None, headers=None, timeout=None):
        return _FakeResponse({"choices": [{"message": {"content": ""}}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    client = OpenAIVisionClient(api_key="sk-test-vision")
    with pytest.raises(VisionClientError, match="empty"):
        client.deconstruct_image(b"fake", "image/png", prompt="x")


def test_raises_on_non_string_content(monkeypatch):
    """A null or missing content field should raise VisionClientError."""
    def fake_post(url, *, json=None, headers=None, timeout=None):
        return _FakeResponse({"choices": [{"message": {"content": None}}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    client = OpenAIVisionClient(api_key="sk-test-vision")
    with pytest.raises(VisionClientError, match="empty"):
        client.deconstruct_image(b"fake", "image/png", prompt="x")


def test_raises_on_http_error(monkeypatch):
    """HTTP errors (4xx, 5xx) should raise VisionClientError with status info."""
    def fake_post(url, *, json=None, headers=None, timeout=None):
        return _FakeResponse({"error": {"message": "Invalid API key"}}, status=401)

    monkeypatch.setattr(httpx, "post", fake_post)

    client = OpenAIVisionClient(api_key="sk-test-vision")
    with pytest.raises(VisionClientError, match="401"):
        client.deconstruct_image(b"fake", "image/png", prompt="x")


def test_default_base_url_is_openai(monkeypatch):
    """When no base_url is given, it should default to api.openai.com."""
    captured = {}

    def fake_post(url, *, json=None, headers=None, timeout=None):
        captured["url"] = url
        return _FakeResponse({"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    client = OpenAIVisionClient(api_key="sk-test-vision")
    client.deconstruct_image(b"fake", "image/png", prompt="x")
    assert captured["url"].startswith(DEFAULT_BASE_URL)


def test_custom_base_url_respected(monkeypatch):
    """Custom base_url should be used verbatim (e.g. for proxies / Azure)."""
    captured = {}

    def fake_post(url, *, json=None, headers=None, timeout=None):
        captured["url"] = url
        return _FakeResponse({"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    client = OpenAIVisionClient(api_key="sk-x", base_url="https://custom-proxy.example.com")
    client.deconstruct_image(b"fake", "image/png", prompt="x")
    assert captured["url"].startswith("https://custom-proxy.example.com")


def test_custom_model_respected(monkeypatch):
    """Custom model name should be sent in the request body."""
    captured = {}

    def fake_post(url, *, json=None, headers=None, timeout=None):
        captured["body"] = json
        return _FakeResponse({"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    client = OpenAIVisionClient(api_key="sk-x", model="gpt-4o-mini")
    client.deconstruct_image(b"fake", "image/png", prompt="x")
    assert captured["body"]["model"] == "gpt-4o-mini"
