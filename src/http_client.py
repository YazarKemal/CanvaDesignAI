"""Lightweight HTTP client that replaces the `openai` SDK for DeepSeek.

The `openai` SDK depends on `jiter` (a C extension that won't compile on
Android ARM64 / Termux). This module provides a drop-in-compatible wrapper
around httpx so the single-engine DeepSeek pipeline works on any platform
without native dependencies.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx


class DeepSeekChatCompletion:
    """Minimal drop-in for `openai.OpenAI().chat.completions.create(...)`."""

    def __init__(self, api_key: str, base_url: str, timeout: float = 120.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> DeepSeekResponse:
        # DeepSeek's real endpoint has no /v1 prefix (unlike OpenAI's own
        # API) -- this must match exactly what the `openai` SDK path hits
        # when given the same base_url, so both code paths behave
        # identically regardless of whether the SDK is installed.
        url = f"{self.base_url}/chat/completions"
        resp = httpx.post(
            url,
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        return DeepSeekResponse(
            choices=[DeepSeekChoice(message=DeepSeekMessage(content=choice["message"]["content"]))]
        )


@dataclass
class DeepSeekMessage:
    content: str


@dataclass
class DeepSeekChoice:
    message: DeepSeekMessage


@dataclass
class DeepSeekResponse:
    choices: list[DeepSeekChoice] = field(default_factory=list)


class DeepSeekCompletions:
    """Drop-in for `openai.OpenAI().chat.completions` — the leaf with `.create()`."""

    def __init__(self, chat_completion: DeepSeekChatCompletion):
        self._chat_completion = chat_completion

    def create(self, **kwargs: Any) -> DeepSeekResponse:
        return self._chat_completion.create(**kwargs)


class DeepSeekChatNamespace:
    """Drop-in for `openai.OpenAI().chat` — holds `.completions`."""

    def __init__(self, chat_completion: DeepSeekChatCompletion):
        self.completions = DeepSeekCompletions(chat_completion)


class DeepSeekClient:
    """Drop-in for `openai.OpenAI(...)` scoped to DeepSeek."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self._chat_completion = DeepSeekChatCompletion(
            api_key=api_key or os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url=base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )

    @property
    def chat(self) -> DeepSeekChatNamespace:
        return DeepSeekChatNamespace(self._chat_completion)
