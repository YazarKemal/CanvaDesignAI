"""CLI entrypoint for CanvaDesignAI — the Art Director prompt engine.

Takes a plain concept and returns a graphic-designer-quality image-generation
prompt (for DALL-E 3 / Canva Magic Media), validated by the dual-agent loop.

Usage:
    python main.py "Grand Opening Cafe"
    python main.py "Grand Opening Cafe" --max-attempts 5
    python main.py "Grand Opening Cafe" --raw   # print just the prompt string
"""

from __future__ import annotations

import argparse
import json
import sys

from src.orchestrator import DEFAULT_MAX_ATTEMPTS, run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Engineer a graphic-designer-quality image prompt via the dual-agent pipeline."
    )
    parser.add_argument("concept", help='Plain concept, e.g. "Grand Opening Cafe"')
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print only the image_prompt string (ready to paste into DALL-E 3 / Magic Media).",
    )
    args = parser.parse_args(argv)

    result = run_pipeline(args.concept, max_attempts=args.max_attempts)

    if args.raw:
        print(result.prompt["image_prompt"])
    else:
        print(json.dumps(result.prompt, ensure_ascii=False, indent=2))

    status = "APPROVED" if result.approved else "BEST EFFORT (did not reach pass threshold)"
    print(f"\n--- {status} | score={result.review.score:.1f} | attempts={result.attempts} ---", file=sys.stderr)
    if not result.approved:
        print(f"Last feedback: {result.review.feedback}", file=sys.stderr)

    return 0 if result.approved else 1


if __name__ == "__main__":
    raise SystemExit(main())
