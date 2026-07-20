"""Shared helper for pulling a JSON object out of an LLM text reply.

Strips markdown code fences first; if the remainder still doesn't parse
(e.g. the model added a stray sentence before/after the JSON despite
instructions), falls back to slicing between the first '{' and the last
'}' before giving up. Used by every stage (Architect, Generator, Reviewer)
so all three are equally resilient to a model that doesn't perfectly
follow the "raw JSON only" instruction.
"""

from __future__ import annotations

import json
from typing import Any


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[len("json"):]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise
