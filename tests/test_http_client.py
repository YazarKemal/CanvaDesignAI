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
