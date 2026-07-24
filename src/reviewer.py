"""Reviewer agent (Stage 3): scores a Generator card against the Canva
Automation Constitution.

Dual-provider architecture: defaults to DeepSeek (fast, cheap, single-engine
parity with Architect and Generator), with an optional Anthropic/Claude mode
enabled by setting REVIEWER_PROVIDER=anthropic in the environment. This lets
operators trade cost/latency for a different reviewing aesthetic — Claude
often produces more detailed, critical feedback, which can raise the quality
ceiling on multi-attempt pipelines.

When REVIEWER_PROVIDER is unset or set to "deepseek": the standard
single-engine path is used (OpenAI SDK -> DeepSeek, or the pure-httpx
DeepSeekClient fallback on Android/Termux).

When REVIEWER_PROVIDER is set to "anthropic": the Reviewer uses
src.http_client.AnthropicClient, which translates the existing
OpenAI-format call into Anthropic's native Messages API. Set
ANTHROPIC_API_KEY and optionally ANTHROPIC_MODEL (defaults to
claude-3-5-sonnet-20241022) / ANTHROPIC_BASE_URL.

This is also the "Critic" of the design-agency architecture — the rubric
criteria in design_rules.json evaluate cards against the Canva Native
Layout Engine paradigm: stock photo backgrounds, native gradients, Canva
built-in typography in vertical stacks, and native vector shapes (pill
buttons, badges, frames). AI image generation is penalized.

Factual compliance (exact font/color match for brands, contrast ratio,
text_zone consistency) is enforced deterministically in src/schema.py;
only genuinely subjective judgment (does it *feel* on-brand, is the
composition visually coherent) is left to the LLM.
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

DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"

DEFAULT_ANTHROPIC_MODEL = "claude-3-5-sonnet-20241022"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"


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
        "given the Canva Automation Constitution and a Canva card (JSON) "
        "designed for the Canva Native Layout Engine. "
        "Score the card against this rubric, on a 0-10 scale per criterion:\n"
        f"{criteria_desc}\n\n"
        f"{as_prompt_block(load_constitution())}"
        f"{brand_section}\n\n"
        "IMPORTANT: This card is built for Canva Native Layout Engine — "
        "backgrounds are Canva Stock Library search queries or native gradients "
        "(NOT AI-generated images), typography uses Canva built-in font boxes "
        "in vertical stacks, and graphic elements are native Canva vector "
        "shapes. Score AI image generation terms (Magic Media, DALL-E, "
        "Midjourney) as a defect under canva_fit and background_composition_"
        "quality. If target_tool is NOT 'Canva Native Layout Engine', score "
        "canva_fit at 0.\n\n"
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

    When the LLM returns malformed JSON that even the repair heuristics in
    ``src/llm_json`` cannot salvage, the call is retried once with a stern
    "JSON ONLY" correction appended to the conversation.  This prevents a
    single formatting glitch from crashing the entire pipeline.
    """
    constitution = load_constitution()
    rubric = constitution["review_rubric"]
    pass_threshold = float(rubric["pass_threshold"])

    if client is None:
        provider = os.environ.get("REVIEWER_PROVIDER", "deepseek").lower()
        if provider == "anthropic":
            from src.http_client import AnthropicClient

            client = AnthropicClient()  # type: ignore[assignment]
            if model == DEFAULT_MODEL:
                model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
        elif OpenAI is not None:
            client = OpenAI(
                api_key=os.environ.get("DEEPSEEK_API_KEY"),
                base_url=os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
            )
        else:
            from src.http_client import DeepSeekClient

            client = DeepSeekClient()  # type: ignore[assignment]

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _system_prompt(pass_threshold, rubric["criteria"], brand)},
        {"role": "user", "content": f"Canva card to review:\n{json.dumps(card, ensure_ascii=False, indent=2)}"},
    ]

    for attempt in (1, 2):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
        )
        raw_text = response.choices[0].message.content or ""

        try:
            data = extract_json(raw_text)
        except json.JSONDecodeError:
            if attempt == 1:
                # Append a stern correction and retry once.
                messages.append({"role": "assistant", "content": raw_text})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your response was NOT valid JSON — it could not be "
                            "parsed even after repair attempts.  You MUST respond "
                            "with ONLY a single JSON object and NOTHING else.  "
                            "No markdown fences, no prose, no commentary.  Just "
                            '{"score": <float>, "criteria_scores": {...}, '
                            '"feedback": "<string>"}.'
                        ),
                    }
                )
                continue
            raise ValueError(
                f"Reviewer did not return valid JSON after 2 attempts.\n"
                f"Last raw: {raw_text[:500]}"
            ) from None
        else:
            return ReviewResult.from_json(data, pass_threshold)

    # Unreachable — the loop always returns or raises.
    raise RuntimeError("unreachable")
