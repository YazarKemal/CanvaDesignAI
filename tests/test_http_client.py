"""Regression coverage for src/http_client.py's DeepSeekClient.

Caught via a real (mocked-server) end-to-end run: the `openai` SDK, given
base_url="https://api.deepseek.com", posts to "/chat/completions" (no /v1
prefix — confirmed against DeepSeek's official API docs). DeepSeekClient
must hit the exact same path so behavior doesn't silently differ between
environments where the `openai` package installs and ones (e.g. Termux)
where it doesn't and this httpx-based fallback is used instead.
"""

import json

import httpx
import pytest

from src.http_client import DeepSeekClient


class _FakeHttpxResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_deepseek_client_posts_to_chat_completions_without_v1_prefix(monkeypatch):
    captured = {}

    def fake_post(url, *, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeHttpxResponse({"choices": [{"message": {"content": "hi"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    client = DeepSeekClient(api_key="sk-test", base_url="https://api.deepseek.com")
    client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": "x"}])

    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert "/v1/" not in captured["url"]


def test_deepseek_client_strips_trailing_slash_from_base_url(monkeypatch):
    captured = {}

    def fake_post(url, *, json=None, headers=None, timeout=None):
        captured["url"] = url
        return _FakeHttpxResponse({"choices": [{"message": {"content": "hi"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    client = DeepSeekClient(api_key="sk-test", base_url="https://api.deepseek.com/")
    client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": "x"}])

    assert captured["url"] == "https://api.deepseek.com/chat/completions"


def test_deepseek_client_sends_bearer_auth_header(monkeypatch):
    captured = {}

    def fake_post(url, *, json=None, headers=None, timeout=None):
        captured["headers"] = headers
        return _FakeHttpxResponse({"choices": [{"message": {"content": "hi"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    client = DeepSeekClient(api_key="sk-test", base_url="https://api.deepseek.com")
    client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": "x"}])

    assert captured["headers"]["Authorization"] == "Bearer sk-test"


def test_deepseek_client_returns_content_matching_openai_sdk_shape(monkeypatch):
    def fake_post(url, *, json=None, headers=None, timeout=None):
        return _FakeHttpxResponse({"choices": [{"message": {"content": json_content}}]})

    json_content = json.dumps({"score": 9.0})
    monkeypatch.setattr(httpx, "post", fake_post)

    client = DeepSeekClient(api_key="sk-test", base_url="https://api.deepseek.com")
    response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": "x"}])

    assert response.choices[0].message.content == json_content


def test_deepseek_client_falls_back_to_reasoning_content_when_content_empty(monkeypatch):
    """Adapter: when ``content`` is empty/null, extract from ``reasoning_content``.

    DeepSeek reasoning models (deepseek-v4-flash, deepseek-reasoner) put
    their final answer in ``reasoning_content`` while leaving ``content``
    blank or containing only a brief summary.  This test ensures the
    httpx-based fallback client handles that payload shape correctly.
    """
    reasoning_payload = json.dumps({"score": 8.5, "feedback": "good"})

    def fake_post(url, *, json=None, headers=None, timeout=None):
        return _FakeHttpxResponse({
            "choices": [{
                "message": {
                    "content": "",
                    "reasoning_content": reasoning_payload,
                }
            }]
        })

    monkeypatch.setattr(httpx, "post", fake_post)

    client = DeepSeekClient(api_key="sk-test", base_url="https://api.deepseek.com")
    response = client.chat.completions.create(
        model="deepseek-v4-flash", messages=[{"role": "user", "content": "review this card"}]
    )

    assert response.choices[0].message.content == reasoning_payload


def test_deepseek_client_falls_back_to_reasoning_alias_field(monkeypatch):
    """Also check the deprecated ``reasoning`` alias used by older API versions."""
    reasoning_payload = json.dumps({"score": 7.0, "feedback": "fix typography"})

    def fake_post(url, *, json=None, headers=None, timeout=None):
        return _FakeHttpxResponse({
            "choices": [{
                "message": {
                    "content": None,
                    "reasoning": reasoning_payload,
                }
            }]
        })

    monkeypatch.setattr(httpx, "post", fake_post)

    client = DeepSeekClient(api_key="sk-test", base_url="https://api.deepseek.com")
    response = client.chat.completions.create(
        model="deepseek-v4-flash", messages=[{"role": "user", "content": "review this card"}]
    )

    assert response.choices[0].message.content == reasoning_payload


def test_deepseek_client_uses_content_when_both_fields_present(monkeypatch):
    """When both ``content`` and ``reasoning_content`` are present, prefer ``content``."""
    def fake_post(url, *, json=None, headers=None, timeout=None):
        return _FakeHttpxResponse({
            "choices": [{
                "message": {
                    "content": "primary content",
                    "reasoning_content": "chain-of-thought reasoning",
                }
            }]
        })

    monkeypatch.setattr(httpx, "post", fake_post)

    client = DeepSeekClient(api_key="sk-test", base_url="https://api.deepseek.com")
    response = client.chat.completions.create(
        model="deepseek-v4-pro", messages=[{"role": "user", "content": "x"}]
    )

    assert response.choices[0].message.content == "primary content"


def test_deepseek_client_handles_completely_empty_response(monkeypatch):
    """When all fields are empty/null/missing, return an empty string gracefully."""
    def fake_post(url, *, json=None, headers=None, timeout=None):
        return _FakeHttpxResponse({
            "choices": [{
                "message": {}
            }]
        })

    monkeypatch.setattr(httpx, "post", fake_post)

    client = DeepSeekClient(api_key="sk-test", base_url="https://api.deepseek.com")
    response = client.chat.completions.create(
        model="deepseek-v4-flash", messages=[{"role": "user", "content": "x"}]
    )

    assert response.choices[0].message.content == ""
