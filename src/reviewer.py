"""Reviewer agent: scores a Generator prompt against the Art Director Constitution.

Uses DeepSeek (an OpenAI-compatible API) because it is fast and cheap enough
to run on every Generator attempt without materially affecting cost/latency.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from src.constitution import as_prompt_block, load_constitution

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"


@dataclass
class ReviewResult:
    score: float
    passed: bool
    criteria_scores: dict[str, float] = field(default_factory=dict)
    feedback: str = ""

    @classmethod
    def from_json(cls, data: dict[str, Any], pass_threshold: float) -> "ReviewResult":
        score = float(data["score"])
        return cls(
            score=score,
            passed=score >= pass_threshold,
            criteria_scores={k: float(v) for k, v in data.get("criteria_scores", {}).items()},
            feedback=data.get("feedback", ""),
        )


def _system_prompt(pass_threshold: float, criteria: list[dict[str, Any]]) -> str:
    criteria_desc = "\n".join(
        f"- {c['id']} (weight {c['weight']}): {c['question']}" for c in criteria
    )
    return (
        "You are the Reviewer agent inside CanvaDesignAI — a strict but fair "
        "art director reviewing image-generation prompts. You are given the "
        "Art Director Constitution and a visual-prompt draft (JSON). Score the "
        "prompt against this rubric, on a 0-10 scale per criterion:\n"
        f"{criteria_desc}\n\n"
        f"{as_prompt_block(load_constitution())}\n\n"
        "Compute the weighted average as the overall `score` (0-10). A prompt "
        f"passes if score >= {pass_threshold}.\n\n"
        "Respond with raw JSON only, no markdown fences, matching exactly:\n"
        "{\n"
        '  "score": <weighted average, float>,\n'
        '  "criteria_scores": {"<criterion_id>": <0-10>, ...},\n'
        '  "feedback": "<if score < threshold, concrete actionable fixes; '
        'empty string if it passes>"\n'
        "}"
    )


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[len("json"):]
    return json.loads(text.strip())


def review_prompt(
    draft: dict[str, Any],
    *,
    model: str = DEFAULT_MODEL,
    client: OpenAI | None = None,
) -> ReviewResult:
    """Score a visual-prompt draft. Returns a ReviewResult with pass/fail + feedback."""
    constitution = load_constitution()
    rubric = constitution["review_rubric"]
    pass_threshold = float(rubric["pass_threshold"])

    client = client or OpenAI(
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
        base_url=os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _system_prompt(pass_threshold, rubric["criteria"])},
            {"role": "user", "content": f"Visual prompt to review:\n{json.dumps(draft, ensure_ascii=False, indent=2)}"},
        ],
        temperature=0,
    )
    raw_text = response.choices[0].message.content or ""

    try:
        data = _extract_json(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Reviewer did not return valid JSON: {exc}\nRaw: {raw_text}") from exc

    return ReviewResult.from_json(data, pass_threshold)
