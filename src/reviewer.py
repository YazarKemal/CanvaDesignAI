"""Reviewer agent (Stage 3): DeepSeek scores a Generator card against the
Canva Automation Constitution.

Single-engine architecture: DeepSeek runs Architect, Generator and Reviewer.
It is fast and cheap enough to run on every Generator attempt without
materially affecting cost/latency.

This is also the "Critic" of the design-agency architecture — rather than
adding a separate fourth LLM stage, the existing rubric gained a
`brand_fit` criterion (design_rules.json) that this same call scores when
a brand profile is active. Factual brand compliance (exact font/color
match) is enforced deterministically in src/schema.py; only the
genuinely subjective judgment (does it *feel* on-brand) is left to the
LLM, in the call that already runs on every attempt.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

try:
    from openai import OpenAI  # type: ignore[import-untyped]
except ImportError:
    OpenAI = None  # type: ignore[assignment]

from src.brand_profiles import as_prompt_block as brand_prompt_block
from src.constitution import as_prompt_block, load_constitution
from src.llm_json import extract_json

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


def _system_prompt(
    pass_threshold: float, criteria: list[dict[str, Any]], brand: dict[str, Any] | None = None
) -> str:
    criteria_desc = "\n".join(
        f"- {c['id']} (weight {c['weight']}): {c['question']}" for c in criteria
    )
    brand_section = f"\n\n{brand_prompt_block(brand)}" if brand is not None else ""
    return (
        "You are the Reviewer agent inside CaVDesign — a strict but fair Canva "
        "automation QA reviewer (the Critic of this design agency). You are "
        "given the Canva Automation Constitution and a Canva card (JSON). "
        "Score the card against this rubric, on a 0-10 scale per criterion:\n"
        f"{criteria_desc}\n\n"
        f"{as_prompt_block(load_constitution())}"
        f"{brand_section}\n\n"
        "Compute the weighted average as the overall `score` (0-10). A card "
        f"passes if score >= {pass_threshold}. If the card contains ANY "
        "conversational/chat language (greetings, questions back to the user, "
        "'here is', 'would you like', etc.), score format_discipline as 0 no "
        "matter how good the rest of the card is.\n\n"
        "Respond with raw JSON only, no markdown fences, matching exactly:\n"
        "{\n"
        '  "score": <weighted average, float>,\n'
        '  "criteria_scores": {"<criterion_id>": <0-10>, ...},\n'
        '  "feedback": "<if score < threshold, concrete actionable fixes; '
        'empty string if it passes>"\n'
        "}\n\n"
        "Your own reply must ALSO be pure JSON — no greeting, no commentary."
    )


def review_prompt(
    card: dict[str, Any],
    *,
    brand: dict[str, Any] | None = None,
    model: str = DEFAULT_MODEL,
    client: OpenAI | None = None,
) -> ReviewResult:
    """Score a Canva card. Returns a ReviewResult with pass/fail + feedback.

    If `brand` is given, its profile is embedded so the rubric's brand_fit
    criterion is judged against real constraints rather than guesswork.
    """
    constitution = load_constitution()
    rubric = constitution["review_rubric"]
    pass_threshold = float(rubric["pass_threshold"])

    if client is None:
        if OpenAI is not None:
            client = OpenAI(
                api_key=os.environ.get("DEEPSEEK_API_KEY"),
                base_url=os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
            )
        else:
            from src.http_client import DeepSeekClient
            client = DeepSeekClient()  # type: ignore[assignment]

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _system_prompt(pass_threshold, rubric["criteria"], brand)},
            {"role": "user", "content": f"Canva card to review:\n{json.dumps(card, ensure_ascii=False, indent=2)}"},
        ],
        temperature=0,
    )
    raw_text = response.choices[0].message.content or ""

    try:
        data = extract_json(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Reviewer did not return valid JSON: {exc}\nRaw: {raw_text}") from exc

    return ReviewResult.from_json(data, pass_threshold)
