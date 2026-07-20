"""Turns a text image prompt into real image bytes.

Canva's public Connect API does not expose "Magic Media" (its AI
text-to-image feature) to third-party developers — only asset upload and
design creation. So before anything can be pushed into Canva, the
Generator's `image_prompts.main_visual` string has to be turned into an
actual image via a real text-to-image model. This module does that via the
OpenAI Images API.
"""

from __future__ import annotations

import base64
import os

from openai import OpenAI

DEFAULT_MODEL = "gpt-image-1"
DEFAULT_SIZE = "1024x1024"


class OpenAIImageProvider:
    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        client: OpenAI | None = None,
    ):
        self.model = model
        self.client = client or OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def generate_image(self, prompt: str, *, size: str = DEFAULT_SIZE) -> bytes:
        """Generate an image for `prompt` and return raw image bytes (PNG)."""
        response = self.client.images.generate(model=self.model, prompt=prompt, size=size)
        b64_data = response.data[0].b64_json
        return base64.b64decode(b64_data)
