"""CLI entrypoint for CaVDesign — the Canva Prompt Workbench.

Single-engine architecture: takes a plain concept and runs the three-stage
DeepSeek pipeline (Architect -> Generator -> Reviewer) to produce a Canva
automation card (magic_media_prompt, layer_typography_architecture,
direct_action_tip). Never chats, never asks a question — card only.

Usage:
    python main.py "Kafe acilisi icin Instagram gonderisi"
    python main.py "Grand Opening Cafe" --max-attempts 5
    python main.py "Grand Opening Cafe" --raw   # print just the Magic Media prompt string
"""

from __future__ import annotations

import argparse
import json
import sys

from src.orchestrator import DEFAULT_MAX_ATTEMPTS, PipelineError, run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a Canva automation card via the single-engine DeepSeek workbench."
    )
    parser.add_argument("concept", help='Plain concept, e.g. "Grand Opening Cafe"')
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print only the magic_media_prompt string (ready to paste into Canva Magic Media / DALL-E 3).",
    )
    args = parser.parse_args(argv)

    try:
        result = run_pipeline(args.concept, max_attempts=args.max_attempts)
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.raw:
        print(result.card["magic_media_prompt"])
    else:
        print(json.dumps(result.card, ensure_ascii=False, indent=2))

    status = "APPROVED" if result.approved else "BEST EFFORT (did not reach pass threshold)"
    print(f"\n--- {status} | score={result.review.score:.1f} | attempts={result.attempts} ---", file=sys.stderr)
    if not result.approved:
        print(f"Last feedback: {result.review.feedback}", file=sys.stderr)

    return 0 if result.approved else 1


if __name__ == "__main__":
    raise SystemExit(main())
