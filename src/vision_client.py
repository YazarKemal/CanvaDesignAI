"""Lightweight OpenAI Vision client — pure httpx, zero SDK dependencies.

Follows the same pattern as :mod:`src.http_client` (DeepSeekClient) so the
ingestion layer works on Android / Termux without the ``openai`` SDK (whose
``jiter`` C-extension won't compile on ARM64).

Used ONLY by :mod:`src.template_ingest` for deconstructing template images
into card JSON — never by the runtime Architect → Generator → Reviewer pipeline.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o"
DEFAULT_BASE_URL = "https://api.openai.com"
DEFAULT_TIMEOUT = 120.0


class VisionClientError(RuntimeError):
    """Raised when the vision client cannot proceed — missing API key,
    non-JSON response, HTTP error, etc."""


@dataclass
class _VisionMessage:
    content: str


@dataclass
class _VisionChoice:
    message: _VisionMessage


@dataclass
class _VisionResponse:
    choices: list[_VisionChoice] = field(default_factory=list)


class OpenAIVisionClient:
    """Stateless OpenAI Vision client that sends an image + prompt and returns
    the raw text response.

    Does NOT depend on the ``openai`` SDK — uses :mod:`httpx` directly so it
    works on Android / Termux without native C extensions.

    Usage::

        client = OpenAIVisionClient()
        raw_json_text = client.deconstruct_image(
            image_bytes, "image/png",
            prompt="Describe this design template as JSON...",
        )
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.model = model or os.environ.get("OPENAI_VISION_MODEL", DEFAULT_MODEL)
        self.timeout = timeout

        if not self.api_key:
            raise VisionClientError(
                "OPENAI_API_KEY is not set.  Export it in your shell or add it to "
                "the project .env file so the vision client can authenticate."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def deconstruct_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        *,
        prompt: str,
    ) -> str:
        """Send an image to the OpenAI Vision API and return the raw text.

        Parameters
        ----------
        image_bytes:
            Raw image file content (PNG, JPEG, WebP, GIF — anything the
            Vision API accepts).
        mime_type:
            IANA media type string, e.g. ``"image/png"`` or ``"image/jpeg"``.
        prompt:
            The text instruction that accompanies the image.

        Returns
        -------
        str
            The model's raw text response (expected to be JSON, but the
            caller is responsible for parsing).

        Raises
        ------
        VisionClientError
            On HTTP errors, empty responses, or unexpected payload shapes.
        """
        data_url = self._as_data_url(image_bytes, mime_type)

        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                    ],
                }
            ],
            "max_tokens": 4096,
            "temperature": 0.0,
        }

        url = f"{self.base_url}/v1/chat/completions"
        logger.debug("Vision request: model=%s mime=%s prompt_len=%d", self.model, mime_type, len(prompt))

        try:
            resp = httpx.post(
                url,
                json=body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VisionClientError(
                f"OpenAI Vision API returned {exc.response.status_code}: "
                f"{_safe_body(exc.response)}"
            ) from exc
        except httpx.RequestError as exc:
            raise VisionClientError(f"HTTP request to OpenAI Vision API failed: {exc}") from exc

        data = resp.json()
        logger.debug("Vision response keys: %s", list(data.keys()))

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise VisionClientError(
                f"Unexpected vision response shape — expected "
                f"choices[0].message.content.  Keys: {list(data.keys())}"
            ) from exc

        if not content or not isinstance(content, str):
            raise VisionClientError(
                f"Vision API returned empty or non-string content: {content!r}"
            )

        return content

    def repair_json(
        self,
        card_json: str,
        error_message: str,
        *,
        prompt: str = "",
    ) -> str:
        """Send a failing card + validation error to the LLM and return
        the corrected JSON as a raw string.

        This is a **text-only** call — no image is sent.  It reuses the same
        model and HTTP machinery as :meth:`deconstruct_image`.

        Parameters
        ----------
        card_json:
            The current (broken) card serialised as a JSON string.
        error_message:
            The validation error message describing what is wrong.
        prompt:
            Optional system-level instruction prepended to the request.

        Returns
        -------
        str
            The model's raw text response (expected to be corrected JSON).
        """
        full_prompt = (
            f"{prompt}\n\n"
            f"--- CURRENT (BROKEN) CARD ---\n{card_json}\n\n"
            f"--- VALIDATION ERROR ---\n{error_message}\n\n"
            f"Return ONLY the corrected JSON object, no markdown, no commentary."
        )

        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": full_prompt,
                }
            ],
            "max_tokens": 4096,
            "temperature": 0.0,
        }

        url = f"{self.base_url}/v1/chat/completions"
        logger.debug("Repair request: model=%s error_len=%d", self.model, len(error_message))

        try:
            resp = httpx.post(
                url,
                json=body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VisionClientError(
                f"OpenAI Vision API returned {exc.response.status_code}: "
                f"{_safe_body(exc.response)}"
            ) from exc
        except httpx.RequestError as exc:
            raise VisionClientError(f"HTTP request to OpenAI Vision API failed: {exc}") from exc

        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise VisionClientError(
                f"Unexpected vision response shape — expected "
                f"choices[0].message.content.  Keys: {list(data.keys())}"
            ) from exc

        if not content or not isinstance(content, str):
            raise VisionClientError(
                f"Vision API returned empty or non-string content: {content!r}"
            )

        return content

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _as_data_url(image_bytes: bytes, mime_type: str) -> str:
        """Encode *image_bytes* as an RFC 2397 data URL."""
        b64 = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{mime_type};base64,{b64}"


def _safe_body(response: httpx.Response) -> str:
    """Return a truncated version of the response body for error messages."""
    try:
        text = response.text
    except Exception:
        return "[unreadable body]"
    if len(text) > 500:
        return text[:500] + "..."
    return text
