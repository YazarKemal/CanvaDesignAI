"""Loader for the CaVDesign Canva Automation Constitution (design_rules.json).

All three stages (Architect, Generator, Reviewer) read from the same file
so the rules they operate under never drift out of sync.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent / "design_rules.json"


@lru_cache(maxsize=1)
def load_constitution(path: str | Path = DEFAULT_RULES_PATH) -> dict[str, Any]:
    """Load and cache the design constitution JSON."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def as_prompt_block(constitution: dict[str, Any] | None = None) -> str:
    """Render the constitution as a compact instruction block for LLM prompts."""
    rules = constitution or load_constitution()
    return (
        "CANVA AUTOMATION CONSTITUTION (must be followed exactly, no exceptions. "
        "Output the card JSON only -- never chat, never ask a question):\n"
        + json.dumps(rules, ensure_ascii=False, indent=2)
    )
