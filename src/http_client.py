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
    def base_url(self) -> str:
        """Drop-in for openai.OpenAI().base_url."""
        return self._chat_completion.base_url

    @property
    def chat(self) -> DeepSeekChatNamespace:
        return DeepSeekChatNamespace(self._chat_completion)


# -- Anthropic Messages API client (OpenAI-compatible shim) -------------------

ANTHROPIC_DEFAULT_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_API_VERSION = "2023-06-01"


class AnthropicChatCompletion:
    """Translates an OpenAI-format `.create()` call into Anthropic's native
    Messages API, so callers that speak `client.chat.completions.create(...)`
    can target Claude without changing their call site."""

    def __init__(
        self,
        api_key: str,
        base_url: str = ANTHROPIC_DEFAULT_BASE_URL,
        timeout: float = 120.0,
    ):
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
        **__: Any,
    ) -> DeepSeekResponse:
        # Extract system messages (Anthropic requires them in a top-level
        # ``system`` param, not inside the ``messages`` array).
        system_parts: list[str] = []
        anthropic_messages: list[dict[str, str]] = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                system_parts.append(str(msg.get("content", "")))
            elif role in ("user", "assistant"):
                anthropic_messages.append({"role": role, "content": str(msg.get("content", ""))})

        body: dict[str, Any] = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_parts:
            body["system"] = "\n\n".join(system_parts)

        url = f"{self.base_url}/v1/messages"
        resp = httpx.post(
            url,
            json=body,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": ANTHROPIC_API_VERSION,
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        # Anthropic returns content as an array of blocks; extract the first
        # text block as the OpenAI-compatible `message.content` string.
        content_blocks = data.get("content", [])
        text = ""
        for block in content_blocks:
            if block.get("type") == "text":
                text += block.get("text", "")
        if not text and content_blocks:
            text = str(content_blocks[0])

        return DeepSeekResponse(
            choices=[DeepSeekChoice(message=DeepSeekMessage(content=text))]
        )


class AnthropicCompletions:
    """Drop-in for `openai.OpenAI().chat.completions`."""

    def __init__(self, chat_completion: AnthropicChatCompletion):
        self._chat_completion = chat_completion

    def create(self, **kwargs: Any) -> DeepSeekResponse:
        return self._chat_completion.create(**kwargs)


class AnthropicChatNamespace:
    """Drop-in for `openai.OpenAI().chat` — holds `.completions`."""

    def __init__(self, chat_completion: AnthropicChatCompletion):
        self.completions = AnthropicCompletions(chat_completion)


class AnthropicClient:
    """Drop-in for `openai.OpenAI(...)` that routes to Anthropic's Messages API.

    Translates OpenAI-compatible ``chat.completions.create(...)`` calls into
    Anthropic-native requests so existing single-engine code can target Claude
    models without changing its call-site pattern."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self._chat_completion = AnthropicChatCompletion(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
            base_url=base_url or os.environ.get(
                "ANTHROPIC_BASE_URL", ANTHROPIC_DEFAULT_BASE_URL
            ),
        )

    @property
    def base_url(self) -> str:
        return self._chat_completion.base_url

    @property
    def chat(self) -> AnthropicChatNamespace:
        return AnthropicChatNamespace(self._chat_completion)
